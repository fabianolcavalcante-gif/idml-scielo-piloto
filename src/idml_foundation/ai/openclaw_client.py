from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from idml_foundation.ai.orchestration import ProviderResponse, ProviderUnavailable
from idml_foundation.domain.common import canonical_bytes

MAX_GATEWAY_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_GATEWAY_ERROR_BYTES = 64 * 1024
MAX_INPUT_IMAGE_BYTES = 512 * 1024
MAX_INPUT_IMAGES_TOTAL_BYTES = 640 * 1024
MAX_INPUT_IMAGES = 4
_SAFE_ERROR_FRAGMENT = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_JSON_FENCE = re.compile(
    r"\A```(?:json)?[ \t]*\r?\n(?P<body>[\s\S]*?)\r?\n```[ \t]*\Z",
    re.IGNORECASE,
)
_STRUCTURED_OUTPUT_FUNCTION = "submit_idml_structured_output"


class JsonPostTransport(Protocol):
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]: ...


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


class UrllibJsonPostTransport:
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        if urlsplit(url).scheme not in {"http", "https"}:
            raise ValueError("gateway transport only permits HTTP(S)")
        request = Request(  # noqa: S310 - scheme is restricted immediately above
            url,
            data=canonical_bytes(payload),
            headers=headers,
            method="POST",
        )
        try:
            with build_opener(_NoRedirects).open(request, timeout=timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                if content_type != "application/json":
                    raise RuntimeError("OpenClaw gateway returned an unsupported content type")
                raw = response.read(MAX_GATEWAY_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            error_code = _gateway_http_error_code(exc)
            if exc.code >= 500 or exc.code == 429:
                raise ProviderUnavailable(error_code) from exc
            raise RuntimeError(error_code) from exc
        except (TimeoutError, URLError) as exc:
            raise ProviderUnavailable("OpenClaw gateway is unavailable") from exc
        if len(raw) > MAX_GATEWAY_RESPONSE_BYTES:
            raise RuntimeError("OpenClaw gateway response exceeds the size limit")
        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("OpenClaw gateway returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("OpenClaw gateway response must be an object")
        return decoded


def _gateway_http_error_code(exc: HTTPError) -> str:
    fragments = ["OPENCLAW", "HTTP", str(exc.code)]
    try:
        raw = exc.read(MAX_GATEWAY_ERROR_BYTES + 1)
        if len(raw) <= MAX_GATEWAY_ERROR_BYTES:
            decoded = json.loads(raw)
            error = decoded.get("error") if isinstance(decoded, dict) else None
            if isinstance(error, dict):
                for field in ("type", "code"):
                    value = error.get(field)
                    if isinstance(value, str) and _SAFE_ERROR_FRAGMENT.fullmatch(value):
                        fragment = re.sub(r"[^A-Za-z0-9]", "_", value).upper()
                        if fragment not in fragments:
                            fragments.append(fragment)
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        pass
    return "_".join(fragments)[:100]


@dataclass(frozen=True)
class ParsedUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int


@dataclass(frozen=True)
class AgentInputImage:
    """Authenticated in-memory image; raw bytes are deliberately omitted from repr/logs."""

    media_type: Literal["image/png", "image/jpeg"]
    data: bytes = field(repr=False)
    sha256: str

    def __post_init__(self) -> None:
        if not self.data or len(self.data) > MAX_INPUT_IMAGE_BYTES:
            raise ValueError("agent input image size is outside the allowed bound")
        signatures = {
            "image/png": b"\x89PNG\r\n\x1a\n",
            "image/jpeg": b"\xff\xd8\xff",
        }
        if not self.data.startswith(signatures[self.media_type]):
            raise ValueError("agent input image bytes do not match media type")
        digest = hashlib.sha256(self.data).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256) or digest != self.sha256:
            raise ValueError("agent input image hash is invalid")

    @classmethod
    def authenticated(
        cls,
        *,
        media_type: Literal["image/png", "image/jpeg"],
        data: bytes,
    ) -> AgentInputImage:
        return cls(media_type=media_type, data=data, sha256=hashlib.sha256(data).hexdigest())


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(f"OpenClaw gateway returned invalid {field}")
    return value


def _parse_usage(payload: dict[str, Any]) -> ParsedUsage:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("OpenClaw gateway response has no usage metadata")
    input_tokens = _integer(usage.get("input_tokens"), field="input token usage")
    output_tokens = _integer(usage.get("output_tokens"), field="output token usage")
    cached_input_tokens = 0
    details = usage.get("input_tokens_details")
    if details is not None:
        if not isinstance(details, dict):
            raise RuntimeError("OpenClaw gateway returned invalid input token details")
        cached_input_tokens = _integer(
            details.get("cached_tokens", 0),
            field="cached input token usage",
        )
    else:
        for alias in ("cache_read_tokens", "cacheRead"):
            if alias in usage:
                cached_input_tokens = _integer(
                    usage[alias],
                    field="cached input token usage",
                )
                break
    if cached_input_tokens > input_tokens:
        raise RuntimeError("OpenClaw cached input exceeds total input")
    return ParsedUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
    )


def _parse_json_object(candidate: str, *, error_prefix: str) -> dict[str, Any]:
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{error_prefix} is not JSON") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError(f"{error_prefix} must be a JSON object")
    return decoded


def _parse_output(payload: dict[str, Any]) -> dict[str, Any]:
    output = payload.get("output")
    if not isinstance(output, list):
        raise RuntimeError("OpenClaw gateway response has no output items")
    function_calls = [
        item for item in output if isinstance(item, dict) and item.get("type") == "function_call"
    ]
    if function_calls:
        if len(output) != 1 or len(function_calls) != 1:
            raise RuntimeError("OpenClaw gateway must return exactly one structured output")
        call = function_calls[0]
        if call.get("name") != _STRUCTURED_OUTPUT_FUNCTION:
            raise RuntimeError("OpenClaw gateway returned an unexpected output function")
        arguments = call.get("arguments")
        if not isinstance(arguments, str):
            raise RuntimeError("OpenClaw gateway function arguments are invalid")
        if payload.get("status") not in {None, "completed", "incomplete"}:
            raise RuntimeError("OpenClaw gateway response did not complete")
        return _parse_json_object(arguments, error_prefix="OpenClaw gateway function arguments")

    if payload.get("status") not in {None, "completed"}:
        raise RuntimeError("OpenClaw gateway response did not complete")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            raise RuntimeError("OpenClaw gateway returned a non-message output")
        content = item.get("content")
        if not isinstance(content, list):
            raise RuntimeError("OpenClaw gateway returned invalid message content")
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                raise RuntimeError("OpenClaw gateway returned unsupported output content")
            text = part.get("text")
            if not isinstance(text, str):
                raise RuntimeError("OpenClaw gateway output text is invalid")
            texts.append(text)
    if len(texts) != 1:
        raise RuntimeError("OpenClaw gateway must return exactly one JSON output")
    candidate = texts[0].strip()
    fenced = _JSON_FENCE.fullmatch(candidate)
    if fenced is not None:
        candidate = fenced.group("body").strip()
    return _parse_json_object(candidate, error_prefix="OpenClaw gateway output")


def _coarse_tool_property(schema: dict[str, Any]) -> dict[str, Any]:
    """Reduce a validation schema to the provider's conservative function-schema subset."""
    schema_type = schema.get("type")
    if schema_type in {"string", "number", "integer", "boolean", "null"}:
        reduced: dict[str, Any] = {"type": schema_type}
        if isinstance(schema.get("enum"), list) and schema["enum"]:
            reduced["enum"] = schema["enum"]
        elif "const" in schema:
            reduced["enum"] = [schema["const"]]
        return reduced
    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict) and items.get("type") in {
            "string",
            "number",
            "integer",
            "boolean",
        }:
            return {"type": "array", "items": _coarse_tool_property(items)}
        return {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        }
    if schema_type == "object":
        return {"type": "object", "additionalProperties": True}
    return {}


def _tool_parameters(output_schema: dict[str, Any]) -> dict[str, Any]:
    properties = output_schema.get("properties", {})
    required = output_schema.get("required", [])
    if (
        output_schema.get("type") != "object"
        or not isinstance(properties, dict)
        or not isinstance(required, list)
        or any(not isinstance(name, str) or name not in properties for name in required)
    ):
        raise ValueError("structured output schema must be a closed root object")
    return {
        "type": "object",
        "properties": {
            str(name): _coarse_tool_property(schema)
            for name, schema in properties.items()
            if isinstance(schema, dict)
        },
        "required": required,
        "additionalProperties": False,
    }


class OpenClawResponsesClient:
    """Restricted OpenResponses client. It never follows redirects or exposes secrets in errors."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        expected_model_key: str,
        transport: JsonPostTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid OpenClaw gateway URL")
        if len(token) < 32:
            raise ValueError("OpenClaw gateway token is missing or too short")
        provider, separator, model = expected_model_key.partition("/")
        if (
            not separator
            or not provider
            or not model
            or expected_model_key != expected_model_key.casefold()
        ):
            raise ValueError("OpenClaw expected model must be exact provider/model")
        self.endpoint = f"{base_url.rstrip('/')}/v1/responses"
        self.token = token
        self.expected_provider = provider
        self.expected_model = model
        self.expected_model_key = expected_model_key
        self.transport = transport or UrllibJsonPostTransport()

    async def run_agent(
        self,
        *,
        agent_id: str,
        session_key: str,
        system_prompt: str,
        input_envelope: dict[str, Any],
        output_schema: dict[str, Any],
        tool_allowlist: frozenset[str],
        timeout_seconds: int,
        max_output_tokens: int,
        input_images: tuple[AgentInputImage, ...] = (),
    ) -> ProviderResponse:
        if not agent_id or not session_key:
            raise ValueError("OpenClaw agent and session are required")
        del tool_allowlist
        schema_text = canonical_bytes(output_schema).decode("utf-8")
        envelope_text = canonical_bytes(input_envelope).decode("utf-8")
        if len(input_images) > MAX_INPUT_IMAGES:
            raise ValueError("agent input image count exceeds the allowed bound")
        if sum(len(image.data) for image in input_images) > MAX_INPUT_IMAGES_TOTAL_BYTES:
            raise ValueError("agent input images exceed the aggregate size bound")
        request_input: Any = envelope_text
        if input_images:
            content: list[dict[str, Any]] = [{"type": "input_text", "text": envelope_text}]
            content.extend(
                {
                    "type": "input_image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": base64.b64encode(image.data).decode("ascii"),
                    },
                }
                for image in input_images
            )
            request_input = [{"type": "message", "role": "user", "content": content}]
        request_payload: dict[str, Any] = {
            "model": f"openclaw/{agent_id}",
            "instructions": (
                f"{system_prompt}\n\n"
                f"Call `{_STRUCTURED_OUTPUT_FUNCTION}` exactly once with the complete answer. "
                "Do not emit assistant text before or after the call. This terminal function is "
                "only a structured output channel: it is never executed and has no side effects. "
                "No executable gateway tools are available or permitted. The function arguments "
                "must also match this authoritative schema, which the backend revalidates: "
                f"{schema_text}"
            ),
            "input": request_input,
            "tools": [
                {
                    "type": "function",
                    "name": _STRUCTURED_OUTPUT_FUNCTION,
                    "description": (
                        "Submit the complete evidence-bound IDML evaluation output. "
                        "This function is not executed."
                    ),
                    "parameters": _tool_parameters(output_schema),
                    "strict": False,
                }
            ],
            "tool_choice": {
                "type": "function",
                "name": _STRUCTURED_OUTPUT_FUNCTION,
            },
            "max_tool_calls": 1,
            "max_output_tokens": max_output_tokens,
            "user": session_key,
        }
        response_payload = await asyncio.to_thread(
            self.transport.post_json,
            url=self.endpoint,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-openclaw-agent-id": agent_id,
                "x-openclaw-model": self.expected_model_key,
                "x-openclaw-session-key": session_key,
            },
            payload=request_payload,
            timeout_seconds=timeout_seconds,
        )
        usage = _parse_usage(response_payload)
        return ProviderResponse(
            payload=_parse_output(response_payload),
            provider=self.expected_provider,
            model=self.expected_model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
        )
