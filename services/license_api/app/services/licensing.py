from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import Activation, License, LicenseStatus
from ..schemas import LicenseDetail, LicenseSummary
from ..security import ensure_utc, utc_now


def normalized_status_value(status: str | None) -> str:
    value = str(status or "").strip().lower()
    if value == LicenseStatus.revoked.value:
        return LicenseStatus.banned.value
    if value == LicenseStatus.suspended.value:
        return LicenseStatus.disabled.value
    return value or LicenseStatus.active.value


def current_license_state(license_obj: License) -> str:
    expires_at = ensure_utc(license_obj.expires_at)
    normalized = normalized_status_value(license_obj.status)
    if normalized == LicenseStatus.banned.value:
        return "banned"
    if normalized == LicenseStatus.disabled.value:
        return "disabled"
    if expires_at is not None and expires_at <= utc_now():
        return "expired"
    return "active"


def license_denial(license_obj: License) -> tuple[str, str] | None:
    computed = current_license_state(license_obj)
    if computed == "expired":
        return "expired_key", "This license has expired."
    if computed == "disabled":
        return "disabled_key", "This license is disabled."
    if computed == "banned":
        return "revoked_key", "This license has been revoked."
    return None


def query_licenses(db: Session, *, search: str = "", status_filter: str = "all") -> list[License]:
    stmt = select(License).options(selectinload(License.activations)).order_by(License.created_at.desc())
    if status_filter and status_filter != "all":
        if status_filter == "expired":
            stmt = stmt.where(License.expires_at.is_not(None), License.expires_at <= utc_now())
        elif status_filter == LicenseStatus.disabled.value:
            stmt = stmt.where(License.status.in_([LicenseStatus.disabled.value, LicenseStatus.suspended.value]))
        elif status_filter == LicenseStatus.banned.value:
            stmt = stmt.where(License.status.in_([LicenseStatus.banned.value, LicenseStatus.revoked.value]))
        else:
            stmt = stmt.where(License.status == status_filter)

    text = str(search or "").strip()
    if text:
        like = f"%{text}%"
        stmt = (
            stmt.outerjoin(Activation, Activation.license_id == License.id)
            .where(
                or_(
                    License.license_key_plain.ilike(like),
                    License.customer_name.ilike(like),
                    License.customer_email.ilike(like),
                    License.notes.ilike(like),
                    Activation.device_id.ilike(like),
                    Activation.device_name.ilike(like),
                )
            )
            .distinct()
        )
    return list(db.execute(stmt).scalars().unique().all())


def serialize_license_summary(license_obj: License) -> LicenseSummary:
    return LicenseSummary(
        id=license_obj.id,
        license_key=license_obj.license_key_plain,
        product=license_obj.product,
        customer_name=license_obj.customer_name,
        customer_email=license_obj.customer_email,
        notes=license_obj.notes,
        status=normalized_status_value(license_obj.status),
        computed_status=current_license_state(license_obj),
        max_devices=license_obj.max_devices,
        activation_count=len(license_obj.activations),
        expires_at=license_obj.expires_at,
        created_at=license_obj.created_at,
        disabled_reason=license_obj.disabled_reason,
        banned_reason=license_obj.banned_reason,
    )


def serialize_license_detail(license_obj: License) -> LicenseDetail:
    summary = serialize_license_summary(license_obj).model_dump()
    summary["activations"] = list(license_obj.activations)
    return LicenseDetail(**summary)


def extend_license(license_obj: License, extra_days: int) -> None:
    expires_at = ensure_utc(license_obj.expires_at)
    base = expires_at if expires_at and expires_at > utc_now() else utc_now()
    license_obj.expires_at = base + timedelta(days=int(extra_days))
