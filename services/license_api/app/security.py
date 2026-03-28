from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import get_settings


LICENSE_KEY_PATTERN = re.compile(r"^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$")
LICENSE_KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ActivationTokenError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_license_key(raw: str) -> str:
    return str(raw or "").strip().upper()


def validate_license_key_format(raw: str) -> None:
    if not LICENSE_KEY_PATTERN.match(normalize_license_key(raw)):
        raise ValueError("License key format must be XXXX-XXXX-XXXX-XXXX")


def generate_license_key() -> str:
    groups = ["".join(secrets.choice(LICENSE_KEY_ALPHABET) for _ in range(4)) for _ in range(4)]
    return "-".join(groups)


def hash_license_key(raw: str) -> str:
    settings = get_settings()
    normalized = normalize_license_key(raw)
    validate_license_key_format(normalized)
    return hmac.new(settings.license_key_secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def build_activation_token(
    *,
    license_id: int,
    activation_id: int,
    license_key: str,
    device_id: str,
    device_fingerprint: str,
    product: str,
    license_status: str,
    expires_at: datetime | None,
) -> tuple[str, datetime]:
    settings = get_settings()
    now = utc_now()
    token_exp = now + timedelta(minutes=int(settings.activation_token_ttl_minutes))
    safe_expires_at = ensure_utc(expires_at)
    if safe_expires_at is not None:
        token_exp = min(token_exp, safe_expires_at)

    payload = {
        "iss": settings.activation_token_issuer,
        "sub": f"license:{license_id}",
        "license_id": int(license_id),
        "activation_id": int(activation_id),
        "license_key": normalize_license_key(license_key),
        "device_id": str(device_id),
        "device_fingerprint": str(device_fingerprint).strip().lower(),
        "product": str(product),
        "license_status": str(license_status),
        "iat": int(now.timestamp()),
        "exp": int(token_exp.timestamp()),
    }
    token = jwt.encode(payload, settings.activation_token_secret, algorithm="HS256")
    return token, token_exp


def decode_activation_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            str(token or "").strip(),
            settings.activation_token_secret,
            algorithms=["HS256"],
            issuer=settings.activation_token_issuer,
            options={"require": ["exp", "iat", "iss", "license_id", "activation_id", "device_id", "device_fingerprint"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ActivationTokenError("activation token expired") from exc
    except jwt.PyJWTError as exc:
        raise ActivationTokenError("invalid activation token") from exc
