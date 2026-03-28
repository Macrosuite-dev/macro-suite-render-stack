from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import get_db, resolved_database_url
from .deps import (
    get_admin_actor,
    get_client_ip,
    raise_api_error,
    require_admin_api_token,
    require_signed_client_request,
)
from .models import Activation, AuditLog, License, LicenseStatus
from .schemas import (
    ActivateRequest,
    ActivationResponse,
    AuditLogListResponse,
    DashboardActionResponse,
    ExtendLicenseRequest,
    GenerateLicenseRequest,
    GenerateLicenseResponse,
    HeartbeatRequest,
    LicenseEnvelope,
    LicenseListResponse,
    ResetDeviceRequest,
    StatusChangeRequest,
    ValidateRequest,
    ValidateResponse,
)
from .security import (
    ActivationTokenError,
    build_activation_token,
    decode_activation_token,
    ensure_utc,
    generate_license_key,
    hash_license_key,
    normalize_license_key,
    utc_now,
)
from .services.audit import record_audit
from .services.licensing import (
    current_license_state,
    extend_license,
    license_denial,
    query_licenses,
    serialize_license_detail,
    serialize_license_summary,
)


settings = get_settings()
root_logger = logging.getLogger()
log_level = logging.DEBUG if settings.api_environment == "development" else logging.INFO
if not root_logger.handlers:
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
else:
    root_logger.setLevel(log_level)

logger = logging.getLogger("macro_suite.license_api")
logger.setLevel(log_level)
app = FastAPI(title=settings.api_app_name, version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in [settings.dashboard_base_url, settings.resolved_public_base_url] if origin],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.on_event("startup")
def log_startup() -> None:
    logger.info(
        "license api startup env=%s base_url=%s dashboard_url=%s client_signatures=%s",
        settings.api_environment,
        settings.resolved_public_base_url or "(unset)",
        settings.dashboard_base_url or "(unset)",
        settings.require_client_signatures,
    )


def _license_envelope(license_obj: License) -> LicenseEnvelope:
    return LicenseEnvelope(
        id=license_obj.id,
        status=current_license_state(license_obj),
        product=license_obj.product,
        expires_at=ensure_utc(license_obj.expires_at),
        max_devices=license_obj.max_devices,
    )


def _validation_failure(
    code: str,
    message: str,
    *,
    license_obj: License | None = None,
    device_id: str | None = None,
) -> ValidateResponse:
    return ValidateResponse(
        valid=False,
        code=code,
        reason=message,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        license=_license_envelope(license_obj) if license_obj is not None else None,
        device_id=device_id,
    )


def _require_license_by_key(db: Session, raw_key: str) -> License:
    normalized = normalize_license_key(raw_key)
    try:
        key_hash = hash_license_key(normalized)
    except ValueError:
        raise_api_error(status.HTTP_404_NOT_FOUND, "invalid_key", "Invalid license key.")

    license_obj = db.execute(
        select(License).where(License.license_key_hash == key_hash).options(selectinload(License.activations))
    ).scalar_one_or_none()
    if license_obj is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "invalid_key", "Invalid license key.")
    return license_obj


def _require_license_by_id(db: Session, license_id: int) -> License:
    license_obj = db.execute(
        select(License).where(License.id == int(license_id)).options(selectinload(License.activations))
    ).scalar_one_or_none()
    if license_obj is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "license_not_found", "License not found.")
    return license_obj


def _remove_activations_from_license(license_obj: License, device_id: str | None = None) -> int:
    keep: list[Activation] = []
    removed = 0
    target_device = str(device_id or "").strip()
    for activation in list(license_obj.activations or []):
        if target_device and activation.device_id != target_device:
            keep.append(activation)
            continue
        removed += 1
    if removed:
        license_obj.activations = keep
    return removed


def _require_usable_license(license_obj: License) -> None:
    denial = license_denial(license_obj)
    if denial is not None:
        code, message = denial
        raise_api_error(status.HTTP_403_FORBIDDEN, code, message)


def _resolve_existing_activation(license_obj: License, device_id: str) -> Activation | None:
    for activation in license_obj.activations:
        if activation.device_id == device_id:
            return activation
    return None


def _touch_activation(activation: Activation, *, ip_address: str | None, heartbeat: bool = False) -> None:
    now = utc_now()
    activation.ip_address = ip_address
    activation.last_validated_at = now
    if heartbeat:
        activation.last_heartbeat_at = now


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return (
        "<html><body style='font-family:Segoe UI, sans-serif;padding:32px'>"
        "<h1>Macro Suite License API</h1>"
        "<p>This is the permanent licensing backend for Macro Suite.</p>"
        "<p>Health: <a href='/health'>/health</a></p>"
        "</body></html>"
    )


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "service": "license_api",
        "environment": settings.api_environment,
        "database_backend": "sqlite" if resolved_database_url.startswith("sqlite") else "postgresql",
        "base_url": settings.resolved_public_base_url,
        "dashboard_url": settings.dashboard_base_url,
        "client_signatures_required": settings.require_client_signatures,
    }


@app.post(
    "/v1/licenses/activate",
    response_model=ActivationResponse,
    dependencies=[Depends(require_signed_client_request)],
)
def activate_license(payload: ActivateRequest, request: Request, db: Session = Depends(get_db)) -> ActivationResponse:
    license_obj = _require_license_by_key(db, payload.license_key)
    _require_usable_license(license_obj)

    existing = _resolve_existing_activation(license_obj, payload.device_id)
    now = utc_now()

    if existing is not None:
        if existing.device_fingerprint != payload.device_fingerprint:
            raise_api_error(status.HTTP_409_CONFLICT, "device_mismatch", "Device fingerprint mismatch.")
        _touch_activation(existing, ip_address=get_client_ip(request))
        token, token_expires_at = build_activation_token(
            license_id=license_obj.id,
            activation_id=existing.id,
            license_key=license_obj.license_key_plain,
            device_id=existing.device_id,
            device_fingerprint=existing.device_fingerprint,
            product=license_obj.product,
            license_status=current_license_state(license_obj),
            expires_at=license_obj.expires_at,
        )
        db.add(existing)
        db.commit()
        return ActivationResponse(
            status="already_activated",
            activation_token=token,
            token_expires_at=token_expires_at,
            heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
            license=_license_envelope(license_obj),
            device_id=existing.device_id,
        )

    if len(license_obj.activations) >= int(license_obj.max_devices):
        if int(license_obj.max_devices) == 1:
            raise_api_error(status.HTTP_409_CONFLICT, "device_already_bound", "This license is already bound to another device.")
        raise_api_error(status.HTTP_409_CONFLICT, "device_limit_reached", "This license has no free device slots.")

    activation = Activation(
        license_id=license_obj.id,
        device_id=payload.device_id,
        device_name=payload.device_name,
        device_fingerprint=payload.device_fingerprint,
        ip_address=get_client_ip(request),
        last_validated_at=now,
        last_heartbeat_at=now,
    )
    db.add(activation)
    db.flush()
    token, token_expires_at = build_activation_token(
        license_id=license_obj.id,
        activation_id=activation.id,
        license_key=license_obj.license_key_plain,
        device_id=activation.device_id,
        device_fingerprint=activation.device_fingerprint,
        product=license_obj.product,
        license_status=current_license_state(license_obj),
        expires_at=license_obj.expires_at,
    )
    db.commit()
    return ActivationResponse(
        status="activated",
        activation_token=token,
        token_expires_at=token_expires_at,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        license=_license_envelope(license_obj),
        device_id=activation.device_id,
    )


@app.post(
    "/v1/licenses/validate",
    response_model=ValidateResponse,
    dependencies=[Depends(require_signed_client_request)],
)
def validate_license(payload: ValidateRequest, request: Request, db: Session = Depends(get_db)) -> ValidateResponse:
    try:
        claims = decode_activation_token(payload.activation_token)
    except ActivationTokenError as exc:
        detail = str(exc).strip().lower()
        code = "activation_token_expired" if "expired" in detail else "invalid_activation_token"
        return _validation_failure(code, str(exc))

    license_obj = _require_license_by_id(db, int(claims["license_id"]))
    denial = license_denial(license_obj)
    if denial is not None:
        code, message = denial
        return _validation_failure(code, message, license_obj=license_obj)

    activation = _resolve_existing_activation(license_obj, str(claims["device_id"]))
    if activation is None:
        return _validation_failure("activation_missing", "This activation is no longer available. Please activate again.", license_obj=license_obj)

    if payload.device_id != activation.device_id:
        return _validation_failure(
            "device_mismatch",
            "This license is already bound to another device.",
            license_obj=license_obj,
            device_id=activation.device_id,
        )
    if payload.device_fingerprint != activation.device_fingerprint:
        return _validation_failure(
            "device_fingerprint_mismatch",
            "This license is already bound to another device.",
            license_obj=license_obj,
            device_id=activation.device_id,
        )

    _touch_activation(activation, ip_address=get_client_ip(request))
    token, token_expires_at = build_activation_token(
        license_id=license_obj.id,
        activation_id=activation.id,
        license_key=license_obj.license_key_plain,
        device_id=activation.device_id,
        device_fingerprint=activation.device_fingerprint,
        product=license_obj.product,
        license_status=current_license_state(license_obj),
        expires_at=license_obj.expires_at,
    )
    db.add(activation)
    db.commit()
    return ValidateResponse(
        valid=True,
        code="ok",
        reason="ok",
        activation_token=token,
        token_expires_at=token_expires_at,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        license=_license_envelope(license_obj),
        device_id=activation.device_id,
    )


@app.post(
    "/v1/licenses/heartbeat",
    response_model=ValidateResponse,
    dependencies=[Depends(require_signed_client_request)],
)
def heartbeat_license(payload: HeartbeatRequest, request: Request, db: Session = Depends(get_db)) -> ValidateResponse:
    response = validate_license(
        ValidateRequest(
            activation_token=payload.activation_token,
            device_id=payload.device_id,
            device_fingerprint=payload.device_fingerprint,
        ),
        request=request,
        db=db,
    )
    if not response.valid:
        return response

    claims = decode_activation_token(response.activation_token or payload.activation_token)
    license_obj = _require_license_by_id(db, int(claims["license_id"]))
    activation = _resolve_existing_activation(license_obj, payload.device_id)
    if activation is not None:
        _touch_activation(activation, ip_address=get_client_ip(request), heartbeat=True)
        db.add(activation)
        db.commit()
    return response


@app.post(
    "/v1/admin/licenses/generate",
    response_model=GenerateLicenseResponse,
    dependencies=[Depends(require_admin_api_token)],
    status_code=status.HTTP_201_CREATED,
)
def generate_license(
    payload: GenerateLicenseRequest,
    request: Request,
    actor: str = Depends(get_admin_actor),
    db: Session = Depends(get_db),
) -> GenerateLicenseResponse:
    for _ in range(20):
        plain_key = generate_license_key()
        key_hash = hash_license_key(plain_key)
        existing = db.execute(select(License).where(License.license_key_hash == key_hash)).scalar_one_or_none()
        if existing is not None:
            continue
        expires_at = utc_now() + timedelta(days=int(payload.duration_days))
        license_obj = License(
            license_key_hash=key_hash,
            license_key_plain=plain_key,
            license_key_suffix=plain_key[-4:],
            product=payload.product,
            customer_name=payload.customer_name,
            customer_email=payload.customer_email,
            notes=payload.notes,
            status=LicenseStatus.active.value,
            max_devices=payload.max_devices,
            expires_at=expires_at,
        )
        db.add(license_obj)
        db.flush()
        record_audit(
            db,
            actor=actor,
            action="license.generate",
            license_obj=license_obj,
            ip_address=get_client_ip(request),
            detail=f"duration_days={payload.duration_days};max_devices={payload.max_devices}",
        )
        db.commit()
        return GenerateLicenseResponse(
            id=license_obj.id,
            license_key=plain_key,
            status=license_obj.status,
            expires_at=ensure_utc(license_obj.expires_at),
            max_devices=license_obj.max_devices,
            customer_name=license_obj.customer_name,
        )
    raise_api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "generation_failed", "Unable to generate a unique license key.")


@app.get(
    "/v1/admin/licenses",
    response_model=LicenseListResponse,
    dependencies=[Depends(require_admin_api_token)],
)
def list_licenses(
    search: str = Query(default=""),
    status_filter: str = Query(default="all", alias="status"),
    db: Session = Depends(get_db),
) -> LicenseListResponse:
    items = query_licenses(db, search=search, status_filter=status_filter)
    payload = [serialize_license_summary(item) for item in items]
    stats = {"total": len(payload), "active": 0, "disabled": 0, "banned": 0, "expired": 0}
    for item in payload:
        stats[item.computed_status] = stats.get(item.computed_status, 0) + 1
    return LicenseListResponse(total=len(payload), items=payload, stats=stats)


@app.get("/v1/admin/licenses/{license_id}", dependencies=[Depends(require_admin_api_token)])
def get_license_detail(license_id: int, db: Session = Depends(get_db)) -> dict:
    license_obj = _require_license_by_id(db, license_id)
    return serialize_license_detail(license_obj).model_dump()


@app.post(
    "/v1/admin/licenses/{license_id}/extend",
    response_model=DashboardActionResponse,
    dependencies=[Depends(require_admin_api_token)],
)
def admin_extend_license(
    license_id: int,
    payload: ExtendLicenseRequest,
    request: Request,
    actor: str = Depends(get_admin_actor),
    db: Session = Depends(get_db),
) -> DashboardActionResponse:
    license_obj = _require_license_by_id(db, license_id)
    extend_license(license_obj, payload.extra_days)
    record_audit(db, actor=actor, action="license.extend", license_obj=license_obj, ip_address=get_client_ip(request), detail=f"extra_days={payload.extra_days}")
    db.add(license_obj)
    db.commit()
    return DashboardActionResponse(message=f"License extended by {payload.extra_days} day(s).")


@app.post(
    "/v1/admin/licenses/{license_id}/disable",
    response_model=DashboardActionResponse,
    dependencies=[Depends(require_admin_api_token)],
)
def admin_disable_license(
    license_id: int,
    payload: StatusChangeRequest,
    request: Request,
    actor: str = Depends(get_admin_actor),
    db: Session = Depends(get_db),
) -> DashboardActionResponse:
    license_obj = _require_license_by_id(db, license_id)
    license_obj.status = LicenseStatus.disabled.value
    license_obj.disabled_reason = payload.reason or "Disabled by admin"
    record_audit(db, actor=actor, action="license.disable", license_obj=license_obj, ip_address=get_client_ip(request), detail=license_obj.disabled_reason)
    db.add(license_obj)
    db.commit()
    return DashboardActionResponse(message="License disabled.")


@app.post(
    "/v1/admin/licenses/{license_id}/ban",
    response_model=DashboardActionResponse,
    dependencies=[Depends(require_admin_api_token)],
)
def admin_ban_license(
    license_id: int,
    payload: StatusChangeRequest,
    request: Request,
    actor: str = Depends(get_admin_actor),
    db: Session = Depends(get_db),
) -> DashboardActionResponse:
    license_obj = _require_license_by_id(db, license_id)
    license_obj.status = LicenseStatus.banned.value
    license_obj.banned_reason = payload.reason or "Revoked by admin"
    removed = _remove_activations_from_license(license_obj)
    record_audit(
        db,
        actor=actor,
        action="license.ban",
        license_obj=license_obj,
        ip_address=get_client_ip(request),
        detail=f"{license_obj.banned_reason};removed={removed}",
    )
    db.add(license_obj)
    db.commit()
    return DashboardActionResponse(message="License revoked.")


@app.post(
    "/v1/admin/licenses/{license_id}/restore",
    response_model=DashboardActionResponse,
    dependencies=[Depends(require_admin_api_token)],
)
def admin_restore_license(
    license_id: int,
    request: Request,
    actor: str = Depends(get_admin_actor),
    db: Session = Depends(get_db),
) -> DashboardActionResponse:
    license_obj = _require_license_by_id(db, license_id)
    license_obj.status = LicenseStatus.active.value
    license_obj.disabled_reason = None
    license_obj.banned_reason = None
    record_audit(db, actor=actor, action="license.restore", license_obj=license_obj, ip_address=get_client_ip(request), detail="restored to active")
    db.add(license_obj)
    db.commit()
    return DashboardActionResponse(message="License restored.")


@app.post(
    "/v1/admin/licenses/{license_id}/reset-device",
    response_model=DashboardActionResponse,
    dependencies=[Depends(require_admin_api_token)],
)
def admin_reset_device(
    license_id: int,
    payload: ResetDeviceRequest,
    request: Request,
    actor: str = Depends(get_admin_actor),
    db: Session = Depends(get_db),
) -> DashboardActionResponse:
    license_obj = _require_license_by_id(db, license_id)
    removed = _remove_activations_from_license(license_obj, payload.device_id)
    record_audit(db, actor=actor, action="license.reset_device", license_obj=license_obj, ip_address=get_client_ip(request), detail=f"device_id={payload.device_id or '*'};removed={removed}")
    db.commit()
    return DashboardActionResponse(message=f"Removed {removed} activation(s).")


@app.post(
    "/v1/licenses/reset-device",
    response_model=DashboardActionResponse,
    dependencies=[Depends(require_admin_api_token)],
)
def admin_reset_device_by_key(
    payload: dict,
    request: Request,
    actor: str = Depends(get_admin_actor),
    db: Session = Depends(get_db),
) -> DashboardActionResponse:
    license_key = str(payload.get("license_key", "")).strip()
    if not license_key:
        raise_api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "missing_license_key", "license_key is required.")
    license_obj = _require_license_by_key(db, license_key)
    device_id = str(payload.get("device_id", "")).strip()
    removed = _remove_activations_from_license(license_obj, device_id)
    record_audit(db, actor=actor, action="license.reset_device", license_obj=license_obj, ip_address=get_client_ip(request), detail=f"device_id={device_id or '*'};removed={removed}")
    db.commit()
    return DashboardActionResponse(message=f"Removed {removed} activation(s).")


@app.get(
    "/v1/admin/audit-logs",
    response_model=AuditLogListResponse,
    dependencies=[Depends(require_admin_api_token)],
)
def list_audit_logs(limit: int = Query(default=200, ge=1, le=2000), db: Session = Depends(get_db)) -> AuditLogListResponse:
    rows = list(db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).scalars().all())
    return AuditLogListResponse(total=len(rows), items=rows)
