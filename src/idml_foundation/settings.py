from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IDML_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = "sqlite+pysqlite:///./idml-development.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    artifact_root: Path = Path("./artifacts")
    automation_authorization_root: Path | None = None
    enrichment_root: Path | None = None
    enrichment_location: Literal["local", "vps"] | None = None
    validator_socket: Path | None = None
    validator_scoped_authorities: bool = False
    validator_registry_path: Path | None = None
    xpm_socket: Path | None = None
    journal_profile_path: Path | None = None
    session_pepper: SecretStr = SecretStr("development-only-change-this-pepper")
    mfa_encryption_key: SecretStr = SecretStr("development-only-mfa-encryption-key")
    log_level: str = "INFO"
    upload_max_bytes: int = Field(default=100 * 1024 * 1024, ge=1)
    upload_max_concurrency: int = Field(default=1, ge=1, le=4)
    upload_temp_reserve_bytes: int = Field(default=256 * 1024 * 1024, ge=1)
    upload_idle_timeout_seconds: float = Field(default=30, ge=0.05, le=300)
    upload_total_timeout_seconds: float = Field(default=300, ge=0.05, le=1800)
    artifact_tenant_quota_bytes: int = Field(default=2 * 1024**3, ge=1)
    artifact_tenant_max_files: int = Field(default=10_000, ge=1, le=100_000)
    artifact_disk_reserve_bytes: int = Field(default=5 * 1024**3, ge=1)
    zip_max_entries: int = Field(default=5_000, ge=1)
    zip_max_uncompressed_bytes: int = Field(default=500 * 1024 * 1024, ge=1)
    zip_max_ratio: int = Field(default=100, ge=1)
    zip_max_depth: int = Field(default=16, ge=2, le=64)
    zip_max_path_bytes: int = Field(default=512, ge=32, le=4096)
    session_ttl_seconds: int = Field(default=8 * 60 * 60, ge=300, le=7 * 24 * 60 * 60)
    auth_login_max_failures: int = Field(default=5, ge=2, le=100)
    auth_login_window_seconds: int = Field(default=15 * 60, ge=60, le=24 * 60 * 60)
    auth_recovery_max_requests: int = Field(default=3, ge=1, le=100)
    auth_recovery_window_seconds: int = Field(default=60 * 60, ge=60, le=24 * 60 * 60)
    feature_web_edit_provider: bool = False
    feature_openclaw: bool = False
    feature_ai_swarm: bool = False
    openclaw_gateway_url: str = "http://openclaw:47716"
    openclaw_gateway_token: SecretStr = SecretStr("")
    ai_timeout_seconds: int = Field(default=45, ge=1, le=300)
    ai_max_attempts: int = Field(default=2, ge=1, le=2)
    ai_max_input_tokens: int = Field(default=12_000, ge=1)
    ai_max_output_tokens: int = Field(default=2_000, ge=1)
    ai_max_cost_microusd: int = Field(default=50_000, ge=1)
    ai_max_concurrency: int = Field(default=1, ge=1, le=1)
    ai_confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    ai_max_repair_cycles: int = Field(default=2, ge=0, le=2)
    feature_clamav: bool = False
    clamav_socket: Path | None = None
    clamav_host: str = "clamav"
    clamav_port: int = 3310

    @model_validator(mode="after")
    def reject_unsafe_production_defaults(self) -> "Settings":
        if self.environment in {"staging", "production"}:
            pepper = self.session_pepper.get_secret_value()
            if "change" in pepper.lower() or len(pepper) < 32:
                raise ValueError("IDML_SESSION_PEPPER must be a strong environment secret")
            mfa_key = self.mfa_encryption_key.get_secret_value()
            if "development" in mfa_key.lower() or len(mfa_key) < 32:
                raise ValueError("IDML_MFA_ENCRYPTION_KEY must be a strong environment secret")
            if self.database_url.startswith("sqlite"):
                raise ValueError("SQLite is not allowed outside development/test")
        if self.feature_openclaw and len(self.openclaw_gateway_token.get_secret_value()) < 32:
            raise ValueError("IDML_OPENCLAW_GATEWAY_TOKEN is required when OpenClaw is enabled")
        if self.validator_scoped_authorities and not (
            self.validator_socket and self.validator_registry_path and self.journal_profile_path
        ):
            raise ValueError(
                "scoped validators require explicit socket, registry and journal profile"
            )
        if self.xpm_socket and not (
            self.validator_scoped_authorities
            and self.validator_socket
            and self.validator_registry_path
            and self.journal_profile_path
        ):
            raise ValueError("XPM requires scoped modern validators and explicit profile/registry")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
