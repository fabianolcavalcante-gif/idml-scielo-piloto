from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import Field, model_validator

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.release.validation_engine import ValidatorCommand

_GIT_REVISION_PATTERN = r"^[0-9a-f]{40}$"
_IMAGE_ID_PATTERN = r"^sha256:[0-9a-f]{64}$"


class ValidatorChannel(StrEnum):
    ACTIVE = "active"
    ROLLBACK = "rollback"


class ValidatorArtifact(StrictModel):
    name: Literal["packtools", "spsvalidator"]
    channel: ValidatorChannel
    version: str = Field(min_length=1, max_length=100)
    profile_id: Literal["sps-1.10/jats-1.3"]
    adapter_contract: Literal["1.1.0"]
    source_url: str = Field(pattern=r"^https://github\.com/scieloorg/")
    source_revision: str = Field(pattern=_GIT_REVISION_PATTERN)
    dockerfile: str
    command: tuple[str, ...] = Field(min_length=1, max_length=10)
    input_suffix: Literal[".xml", ".zip"]
    environment: Literal["linux-container/read-only/no-network/non-root"]
    timeout_seconds: int = Field(ge=1, le=1800)
    max_output_bytes: int = Field(ge=1024, le=64 * 1024 * 1024)
    image_id: str | None = Field(default=None, pattern=_IMAGE_ID_PATTERN)

    @model_validator(mode="after")
    def safe_paths_and_command(self) -> Self:
        dockerfile = PurePosixPath(self.dockerfile)
        if dockerfile.is_absolute() or ".." in dockerfile.parts:
            raise ValueError("validator dockerfile must be a safe repository path")
        if sum(item.count("{candidate}") for item in self.command) != 1:
            raise ValueError("validator command requires exactly one candidate placeholder")
        return self

    def command_specification(self) -> ValidatorCommand:
        if self.image_id is None:
            raise ValueError("validator image has not been qualified")
        return ValidatorCommand(
            name=self.name,
            version=self.version,
            profile_id=self.profile_id,
            adapter_contract=self.adapter_contract,
            command=self.command,
            input_suffix=self.input_suffix,
            environment=self.environment,
            timeout_seconds=self.timeout_seconds,
            max_output_bytes=self.max_output_bytes,
            tool_sha256=self.image_id.removeprefix("sha256:"),
        )


class XpmArtifact(StrictModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    archive_name: str = Field(min_length=1, max_length=200)
    archive_sha256: str = Field(pattern=SHA256_PATTERN)
    profile_compatibility: Literal["sps-1.9-only"]
    environment: Literal["dedicated-windows-worker"]
    integration_status: Literal["worker-pending"]


class ValidatorRegistry(StrictModel):
    registry_version: Literal["1.0.0"]
    profile_id: Literal["sps-1.10/jats-1.3"]
    validators: tuple[ValidatorArtifact, ...]
    xpm: XpmArtifact

    @model_validator(mode="after")
    def active_and_rollback_are_complete(self) -> Self:
        expected = {
            (name, channel)
            for name in ("packtools", "spsvalidator")
            for channel in ValidatorChannel
        }
        actual = {(item.name, item.channel) for item in self.validators}
        if actual != expected or len(actual) != len(self.validators):
            raise ValueError("registry requires one active and one rollback artifact per validator")
        for name in ("packtools", "spsvalidator"):
            revisions = {item.source_revision for item in self.validators if item.name == name}
            if len(revisions) != 2:
                raise ValueError("active and rollback revisions must differ")
        return self

    def select(self, name: str, channel: ValidatorChannel) -> ValidatorArtifact:
        matches = [
            item for item in self.validators if item.name == name and item.channel == channel
        ]
        if len(matches) != 1:
            raise ValueError("validator selection is not unique")
        return matches[0]


def load_validator_registry(path: Path) -> ValidatorRegistry:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ValidatorRegistry.model_validate(raw)
