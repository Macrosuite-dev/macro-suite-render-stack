from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .security import normalize_license_key


class GenerateLicenseRequest(BaseModel):
    duration_days: int = Field(ge=1, le=3650)
    max_devices: int = Field(default=1, ge=1, le=25)
    product: str = Field(default="Macro Suite", min_length=1, max_length=100)
    customer_name: str | None = Field(default=None, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)


class GenerateLicenseResponse(BaseModel):
    id: int
    license_key: str
    status: str
    expires_at: datetime | None
    max_devices: int
    customer_name: str | None


class ActivateRequest(BaseModel):
    license_key: str = Field(min_length=19, max_length=19)
    device_id: str = Field(min_length=6, max_length=128)
    device_name: str = Field(min_length=1, max_length=255)
    device_fingerprint: str = Field(min_length=32, max_length=128)

    @field_validator("license_key", mode="before")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return normalize_license_key(value)

    @field_validator("device_fingerprint", mode="before")
    @classmethod
    def normalize_fingerprint(cls, value: str) -> str:
        return str(value or "").strip().lower()


class ValidateRequest(BaseModel):
    activation_token: str = Field(min_length=20)
    device_id: str = Field(min_length=6, max_length=128)
    device_fingerprint: str = Field(min_length=32, max_length=128)

    @field_validator("device_fingerprint", mode="before")
    @classmethod
    def normalize_fingerprint(cls, value: str) -> str:
        return str(value or "").strip().lower()


class HeartbeatRequest(ValidateRequest):
    app_version: str | None = Field(default=None, max_length=64)
    uptime_seconds: int | None = Field(default=None, ge=0, le=60 * 60 * 24 * 90)


class LicenseEnvelope(BaseModel):
    id: int
    status: str
    product: str
    expires_at: datetime | None
    max_devices: int


class ActivationResponse(BaseModel):
    status: str
    activation_token: str
    token_expires_at: datetime
    heartbeat_interval_seconds: int
    license: LicenseEnvelope
    device_id: str


class ValidateResponse(BaseModel):
    valid: bool
    code: str | None = None
    reason: str | None = None
    activation_token: str | None = None
    token_expires_at: datetime | None = None
    heartbeat_interval_seconds: int
    license: LicenseEnvelope | None = None
    device_id: str | None = None


class ResetDeviceRequest(BaseModel):
    device_id: str | None = Field(default=None, max_length=128)


class ExtendLicenseRequest(BaseModel):
    extra_days: int = Field(ge=1, le=3650)


class StatusChangeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class ActivationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    device_name: str
    device_fingerprint: str
    ip_address: str | None
    activated_at: datetime
    last_validated_at: datetime | None
    last_heartbeat_at: datetime | None


class LicenseSummary(BaseModel):
    id: int
    license_key: str
    product: str
    customer_name: str | None
    customer_email: str | None
    notes: str | None
    status: str
    computed_status: str
    max_devices: int
    activation_count: int
    expires_at: datetime | None
    created_at: datetime
    disabled_reason: str | None
    banned_reason: str | None


class LicenseDetail(LicenseSummary):
    activations: list[ActivationSummary]


class LicenseListResponse(BaseModel):
    total: int
    items: list[LicenseSummary]
    stats: dict[str, int]


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: str
    action: str
    license_id: int | None
    license_key_suffix: str | None
    ip_address: str | None
    detail: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    total: int
    items: list[AuditLogOut]


class DashboardActionResponse(BaseModel):
    ok: bool = True
    message: str
