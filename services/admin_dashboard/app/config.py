from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    dashboard_app_name: str = "Macro Suite Admin Dashboard"
    dashboard_environment: Literal["development", "production"] = "development"
    dashboard_public_base_url: str | None = None
    render_external_url: str | None = None
    dashboard_session_secret: str = "change-me-dashboard-session-secret"
    dashboard_admin_username: str = "admin"
    dashboard_admin_password: str = "change-me"
    license_api_base_url: str = "http://127.0.0.1:8000"
    license_api_admin_token: str = Field(
        default="change-me-admin-api-token",
        validation_alias=AliasChoices("ADMIN_API_TOKEN", "LICENSE_API_ADMIN_TOKEN"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @computed_field
    @property
    def resolved_public_base_url(self) -> str:
        value = (self.dashboard_public_base_url or self.render_external_url or "").strip().rstrip("/")
        return value

    @model_validator(mode="after")
    def validate_production_requirements(self) -> "Settings":
        if self.dashboard_environment == "production":
            if not self.resolved_public_base_url or not self.resolved_public_base_url.startswith("https://"):
                raise ValueError("Production requires DASHBOARD_PUBLIC_BASE_URL or RENDER_EXTERNAL_URL to use https://")
            if not str(self.license_api_base_url or "").strip().startswith("https://"):
                raise ValueError("Production requires LICENSE_API_BASE_URL to use https://")
        required = {
            "DASHBOARD_SESSION_SECRET": self.dashboard_session_secret,
            "DASHBOARD_ADMIN_PASSWORD": self.dashboard_admin_password,
            "ADMIN_API_TOKEN": self.license_api_admin_token,
        }
        for key, value in required.items():
            text = str(value or "").strip()
            if not text or text.startswith("change-me"):
                raise ValueError(f"{key} must be configured with a real secret.")
        if not str(self.dashboard_admin_username or "").strip():
            raise ValueError("DASHBOARD_ADMIN_USERNAME must be configured.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
