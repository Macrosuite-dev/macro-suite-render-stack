from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_app_name: str = "Macro Suite License API"
    api_environment: Literal["development", "production"] = "development"
    database_url: str = "sqlite:///./macro_suite_license.sqlite3"
    public_base_url: str | None = None
    dashboard_base_url: str | None = None
    render_external_url: str | None = None

    admin_api_token: str = "change-me-admin-api-token"
    license_key_secret: str = "change-me-license-key-secret"
    activation_token_secret: str = "change-me-activation-token-secret"
    client_shared_secret: str = ""

    activation_token_issuer: str = "macro-suite-license"
    activation_token_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    heartbeat_interval_seconds: int = Field(default=15, ge=10, le=120)
    require_client_signatures: bool = False
    client_signature_ttl_seconds: int = Field(default=120, ge=30, le=600)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @computed_field
    @property
    def resolved_public_base_url(self) -> str:
        value = (self.public_base_url or self.render_external_url or "").strip().rstrip("/")
        return value

    @model_validator(mode="after")
    def validate_production_requirements(self) -> "Settings":
        if self.api_environment == "production":
            lowered = str(self.database_url or "").lower()
            if not lowered or lowered.startswith("sqlite"):
                raise ValueError("Production requires a PostgreSQL DATABASE_URL.")
            if not self.resolved_public_base_url or not self.resolved_public_base_url.startswith("https://"):
                raise ValueError("Production requires PUBLIC_BASE_URL or RENDER_EXTERNAL_URL to use https://")
            if self.dashboard_base_url and not str(self.dashboard_base_url).strip().startswith("https://"):
                raise ValueError("Production requires DASHBOARD_BASE_URL to use https://")

        required = {
            "ADMIN_API_TOKEN": self.admin_api_token,
            "LICENSE_KEY_SECRET": self.license_key_secret,
            "ACTIVATION_TOKEN_SECRET": self.activation_token_secret,
        }
        for key, value in required.items():
            text = str(value or "").strip()
            if not text or text.startswith("change-me"):
                raise ValueError(f"{key} must be configured with a real secret.")
        if self.require_client_signatures:
            client_secret = str(self.client_shared_secret or "").strip()
            if not client_secret or client_secret.startswith("change-me"):
                raise ValueError("CLIENT_SHARED_SECRET must be configured when REQUIRE_CLIENT_SIGNATURES=true.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
