from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path

from idml_foundation.ai.registry import repository_root


class CostUnavailable(RuntimeError):
    """Raised when a monetary cost cannot be established without guessing."""


@dataclass(frozen=True)
class ModelPrice:
    model_key: str
    input_usd_per_million_tokens: Decimal
    cached_input_usd_per_million_tokens: Decimal
    output_usd_per_million_tokens: Decimal
    source: str
    effective_date: str

    def estimate_microusd(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> int:
        if min(input_tokens, output_tokens, cached_input_tokens) < 0:
            raise ValueError("token usage cannot be negative")
        if cached_input_tokens > input_tokens:
            raise ValueError("cached input cannot exceed total input")
        # USD / 1M tokens is numerically equal to micro-USD / token.
        uncached_input_tokens = input_tokens - cached_input_tokens
        estimate = (
            Decimal(uncached_input_tokens) * self.input_usd_per_million_tokens
            + Decimal(cached_input_tokens) * self.cached_input_usd_per_million_tokens
            + Decimal(output_tokens) * self.output_usd_per_million_tokens
        )
        return int(estimate.to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class ResolvedCost:
    microusd: int
    source: str
    pricing_version: str | None
    model_key: str


@dataclass(frozen=True)
class PricingCatalog:
    version: str
    prices: dict[str, ModelPrice]
    source_policy: str = "provider_or_exact_catalog_fail_closed"

    @property
    def priced_models(self) -> tuple[str, ...]:
        return tuple(sorted(self.prices))

    def resolve(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int,
        provider_cost_microusd: int | None,
    ) -> ResolvedCost:
        if min(input_tokens, output_tokens, cached_input_tokens) < 0:
            raise ValueError("token usage cannot be negative")
        if cached_input_tokens > input_tokens:
            raise ValueError("cached input cannot exceed total input")
        model_key = normalize_model_key(provider, model)
        if provider_cost_microusd is not None:
            if provider_cost_microusd < 0:
                raise ValueError("provider cost cannot be negative")
            return ResolvedCost(
                microusd=provider_cost_microusd,
                source="provider",
                pricing_version=None,
                model_key=model_key,
            )
        price = self.prices.get(model_key)
        if price is None:
            raise CostUnavailable(f"no exact monetary price configured for {model_key}")
        return ResolvedCost(
            microusd=price.estimate_microusd(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
            ),
            source="estimated",
            pricing_version=self.version,
            model_key=model_key,
        )


def normalize_model_key(provider: str, model: str) -> str:
    normalized_provider = provider.strip().casefold()
    normalized_model = model.strip().casefold()
    if not normalized_provider or not normalized_model:
        raise ValueError("provider and model are required for cost accounting")
    if "/" in normalized_model:
        return normalized_model
    return f"{normalized_provider}/{normalized_model}"


def _decimal_rate(value: object, *, field: str) -> Decimal:
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid pricing field {field}") from exc
    if not rate.is_finite() or rate < 0:
        raise ValueError(f"invalid pricing field {field}")
    return rate


def load_pricing_catalog(path: Path | None = None) -> PricingCatalog:
    catalog_path = path or repository_root() / "config" / "agent-pricing-v1.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    version = str(payload.get("version", ""))
    if not version.startswith("agent-pricing-1."):
        raise ValueError("unsupported agent pricing version")
    if payload.get("currency") != "USD" or payload.get("unit") != "usd_per_million_tokens":
        raise ValueError("unsupported agent pricing currency or unit")
    source_policy = str(payload.get("source_policy", ""))
    if source_policy != "provider_or_exact_catalog_fail_closed":
        raise ValueError("unsupported agent pricing source policy")
    raw_models = payload.get("models")
    if not isinstance(raw_models, dict):
        raise ValueError("agent pricing models must be an object")
    prices: dict[str, ModelPrice] = {}
    for raw_key, raw_value in raw_models.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, dict):
            raise ValueError("invalid agent pricing model entry")
        model_key = raw_key.strip().casefold()
        if model_key != raw_key or "/" not in model_key:
            raise ValueError("agent pricing model keys must be normalized provider/model values")
        input_rate = _decimal_rate(
            raw_value.get("input_usd_per_million_tokens"),
            field="input_usd_per_million_tokens",
        )
        output_rate = _decimal_rate(
            raw_value.get("output_usd_per_million_tokens"),
            field="output_usd_per_million_tokens",
        )
        cached_input_rate = _decimal_rate(
            raw_value.get("cached_input_usd_per_million_tokens"),
            field="cached_input_usd_per_million_tokens",
        )
        if input_rate == 0 and cached_input_rate == 0 and output_rate == 0:
            raise ValueError("an agent pricing entry cannot have all zero rates")
        source = str(raw_value.get("source", "")).strip()
        effective_date = str(raw_value.get("effective_date", "")).strip()
        if not source or not effective_date:
            raise ValueError("agent pricing source and effective date are required")
        prices[model_key] = ModelPrice(
            model_key=model_key,
            input_usd_per_million_tokens=input_rate,
            cached_input_usd_per_million_tokens=cached_input_rate,
            output_usd_per_million_tokens=output_rate,
            source=source,
            effective_date=effective_date,
        )
    return PricingCatalog(version=version, prices=prices, source_policy=source_policy)
