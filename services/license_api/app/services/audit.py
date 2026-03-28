from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog, License


def record_audit(
    db: Session,
    *,
    actor: str,
    action: str,
    license_obj: License | None = None,
    ip_address: str | None = None,
    detail: str | None = None,
) -> AuditLog:
    row = AuditLog(
        actor=str(actor or "system"),
        action=str(action),
        license_id=license_obj.id if license_obj is not None else None,
        license_key_suffix=license_obj.license_key_suffix if license_obj is not None else None,
        ip_address=ip_address,
        detail=detail,
    )
    db.add(row)
    return row
