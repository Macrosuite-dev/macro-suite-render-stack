from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class LicenseStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    banned = "banned"
    suspended = "suspended"
    revoked = "revoked"


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    license_key_plain: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    license_key_suffix: Mapped[str] = mapped_column(String(4))
    product: Mapped[str] = mapped_column(String(100), default="Macro Suite")
    customer_name: Mapped[str | None] = mapped_column(String(255), index=True)
    customer_email: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=LicenseStatus.active.value, index=True)
    max_devices: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_reason: Mapped[str | None] = mapped_column(String(255))
    banned_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    activations: Mapped[list["Activation"]] = relationship(back_populates="license", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="license")


class Activation(Base):
    __tablename__ = "activations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_id: Mapped[int] = mapped_column(ForeignKey("licenses.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(String(128))
    device_name: Mapped[str] = mapped_column(String(255))
    device_fingerprint: Mapped[str] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    license: Mapped[License] = relationship(back_populates="activations")

    __table_args__ = (
        UniqueConstraint("license_id", "device_id", name="uq_activations_license_device"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100), index=True)
    license_id: Mapped[int | None] = mapped_column(ForeignKey("licenses.id", ondelete="SET NULL"), nullable=True)
    license_key_suffix: Mapped[str | None] = mapped_column(String(4))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    license: Mapped[License | None] = relationship(back_populates="audit_logs")
