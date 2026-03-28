from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from .config import get_settings


ADMIN_HEADER_NAME = "X-Admin-Token"
ADMIN_ACTOR_HEADER_NAME = "X-Admin-Actor"
CLIENT_TS_HEADER = "X-Client-Timestamp"
CLIENT_NONCE_HEADER = "X-Client-Nonce"
CLIENT_SIG_HEADER = "X-Client-Signature"

_NONCE_CACHE: dict[str, int] = {}
_NONCE_LOCK = threading.Lock()


def raise_api_error(status_code: int, code: str, message: str) -> None:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is None:
        return None
    return request.client.host


def has_admin_access(token: str | None) -> bool:
    settings = get_settings()
    candidate = str(token or "").strip()
    return bool(candidate) and secrets.compare_digest(candidate, settings.admin_api_token)


def require_admin_api_token(
    x_admin_token: Annotated[str | None, Header(alias=ADMIN_HEADER_NAME)] = None,
) -> None:
    if not has_admin_access(x_admin_token):
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "admin_auth_failed", "Admin authentication failed.")


def get_admin_actor(
    x_admin_actor: Annotated[str | None, Header(alias=ADMIN_ACTOR_HEADER_NAME)] = None,
) -> str:
    text = str(x_admin_actor or "").strip()
    return text or "dashboard"


def _canonical_payload(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}".encode("utf-8")


def _expected_signature(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    settings = get_settings()
    return hmac.new(
        settings.client_shared_secret.encode("utf-8"),
        _canonical_payload(method, path, timestamp, nonce, body),
        hashlib.sha256,
    ).hexdigest()


def _store_nonce_once(nonce: str, now_ts: int, ttl_seconds: int) -> None:
    cutoff = now_ts - ttl_seconds
    with _NONCE_LOCK:
        for key in list(_NONCE_CACHE.keys()):
            if _NONCE_CACHE.get(key, 0) < cutoff:
                _NONCE_CACHE.pop(key, None)
        if nonce in _NONCE_CACHE:
            raise_api_error(status.HTTP_409_CONFLICT, "replay_detected", "Replay detected.")
        _NONCE_CACHE[nonce] = now_ts


async def require_signed_client_request(
    request: Request,
    x_client_timestamp: Annotated[str | None, Header(alias=CLIENT_TS_HEADER)] = None,
    x_client_nonce: Annotated[str | None, Header(alias=CLIENT_NONCE_HEADER)] = None,
    x_client_signature: Annotated[str | None, Header(alias=CLIENT_SIG_HEADER)] = None,
) -> None:
    settings = get_settings()
    if not settings.require_client_signatures:
        return

    if not x_client_timestamp or not x_client_nonce or not x_client_signature:
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "missing_signature", "Missing client signature headers.")

    try:
        ts_int = int(x_client_timestamp)
    except Exception:
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "invalid_signature", "Invalid client timestamp.")

    now_ts = int(time.time())
    if abs(now_ts - ts_int) > int(settings.client_signature_ttl_seconds):
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "signature_expired", "Client timestamp outside allowed window.")

    body = await request.body()
    expected = _expected_signature(request.method, request.url.path, x_client_timestamp, x_client_nonce, body)
    if not secrets.compare_digest(expected, x_client_signature):
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "invalid_signature", "Invalid client signature.")

    _store_nonce_once(x_client_nonce, now_ts, int(settings.client_signature_ttl_seconds))
