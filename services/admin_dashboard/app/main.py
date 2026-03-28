from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
settings = get_settings()
root_logger = logging.getLogger()
log_level = logging.DEBUG if settings.dashboard_environment == "development" else logging.INFO
if not root_logger.handlers:
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
else:
    root_logger.setLevel(log_level)

logger = logging.getLogger("macro_suite.admin_dashboard")
logger.setLevel(log_level)
RETRYABLE_UPSTREAM_STATUS_CODES = {502, 503, 504}

app = FastAPI(title=settings.dashboard_app_name, version="1.0.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.dashboard_session_secret,
    same_site="lax",
    https_only=settings.resolved_public_base_url.startswith("https://"),
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class LoginRequest(BaseModel):
    username: str
    password: str


def current_user(request: Request) -> str | None:
    return request.session.get("user")


def require_user(request: Request) -> str:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user


def _looks_like_html(text: str | None) -> bool:
    lowered = str(text or "").strip().lower()
    return lowered.startswith("<!doctype html") or lowered.startswith("<html") or "</html>" in lowered


def _friendly_upstream_message(status_code: int) -> str:
    if status_code in RETRYABLE_UPSTREAM_STATUS_CODES:
        return "License API is waking up. Please wait a few seconds and try again."
    return "Unable to reach the license API right now. Please refresh and try again."


def _extract_upstream_detail(response: httpx.Response) -> str:
    content_type = str(response.headers.get("content-type", "")).lower()
    if "application/json" in content_type:
        try:
            payload = response.json()
        except Exception:
            payload = None
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        if isinstance(detail, dict):
            message = str(detail.get("message", "")).strip()
            if message:
                return message
        if isinstance(detail, str):
            if _looks_like_html(detail):
                return _friendly_upstream_message(response.status_code)
            return detail.strip() or _friendly_upstream_message(response.status_code)
    return _friendly_upstream_message(response.status_code)


async def call_api(request: Request, method: str, path: str, *, json_body: dict | None = None, params: dict | None = None) -> dict:
    user = require_user(request)
    headers = {
        "X-Admin-Token": settings.license_api_admin_token,
        "X-Admin-Actor": user,
    }
    url = f"{settings.license_api_base_url.rstrip('/')}{path}"
    attempts = 3 if method.upper() == "GET" else 1
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = await client.request(method, url, headers=headers, json=json_body, params=params)
            except httpx.RequestError as exc:
                logger.warning("dashboard upstream request failed method=%s path=%s attempt=%s error=%s", method, path, attempt, exc)
                if attempt < attempts:
                    await asyncio.sleep(attempt * 2)
                    continue
                raise HTTPException(status_code=502, detail=_friendly_upstream_message(502)) from exc

            if response.status_code in RETRYABLE_UPSTREAM_STATUS_CODES and attempt < attempts:
                logger.warning(
                    "dashboard upstream retry method=%s path=%s attempt=%s status=%s",
                    method,
                    path,
                    attempt,
                    response.status_code,
                )
                await asyncio.sleep(attempt * 2)
                continue

            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=_extract_upstream_detail(response))

            if response.status_code == 204:
                return {}

            content_type = str(response.headers.get("content-type", "")).lower()
            if "application/json" not in content_type:
                logger.warning(
                    "dashboard upstream returned non-json method=%s path=%s status=%s content_type=%s",
                    method,
                    path,
                    response.status_code,
                    content_type or "(missing)",
                )
                raise HTTPException(status_code=502, detail="Invalid response from the license API. Please refresh and try again.")
            try:
                return response.json()
            except Exception as exc:
                logger.warning("dashboard upstream json decode failed method=%s path=%s error=%s", method, path, exc)
                raise HTTPException(status_code=502, detail="Invalid response from the license API. Please refresh and try again.") from exc
    raise HTTPException(status_code=502, detail=_friendly_upstream_message(502))


@app.on_event("startup")
async def log_startup() -> None:
    logger.info(
        "dashboard startup env=%s public_base=%s api_base=%s",
        settings.dashboard_environment,
        settings.resolved_public_base_url or "(unset)",
        settings.license_api_base_url,
    )


@app.get("/health")
async def health() -> dict:
    url = f"{settings.license_api_base_url.rstrip('/')}/health"
    api_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
        api_status = "ok" if response.status_code == 200 else f"http_{response.status_code}"
    except httpx.RequestError:
        api_status = "unreachable"
    return {
        "status": "ok",
        "service": "admin_dashboard",
        "environment": settings.dashboard_environment,
        "public_base_url": settings.resolved_public_base_url,
        "license_api_base_url": settings.license_api_base_url,
        "license_api_status": api_status,
    }


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if current_user(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "app_name": settings.dashboard_app_name})


@app.post("/session/login")
async def session_login(request: Request, payload: LoginRequest) -> dict:
    if not secrets.compare_digest(payload.username.strip(), settings.dashboard_admin_username):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if not secrets.compare_digest(payload.password, settings.dashboard_admin_password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    request.session["user"] = payload.username.strip()
    return {"ok": True}


@app.post("/session/logout")
async def session_logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.dashboard_app_name,
            "license_api_base_url": settings.license_api_base_url,
            "user": user,
        },
    )


@app.get("/api/licenses")
async def api_list_licenses(request: Request, search: str = "", status: str = "all") -> JSONResponse:
    payload = await call_api(request, "GET", "/v1/admin/licenses", params={"search": search, "status": status})
    return JSONResponse(payload)


@app.get("/api/licenses/{license_id}")
async def api_license_detail(request: Request, license_id: int) -> JSONResponse:
    payload = await call_api(request, "GET", f"/v1/admin/licenses/{license_id}")
    return JSONResponse(payload)


@app.post("/api/licenses/generate")
async def api_generate_license(request: Request) -> JSONResponse:
    payload = await request.json()
    result = await call_api(request, "POST", "/v1/admin/licenses/generate", json_body=payload)
    return JSONResponse(result)


@app.post("/api/licenses/{license_id}/extend")
async def api_extend_license(request: Request, license_id: int) -> JSONResponse:
    payload = await request.json()
    result = await call_api(request, "POST", f"/v1/admin/licenses/{license_id}/extend", json_body=payload)
    return JSONResponse(result)


@app.post("/api/licenses/{license_id}/disable")
async def api_disable_license(request: Request, license_id: int) -> JSONResponse:
    payload = await request.json()
    result = await call_api(request, "POST", f"/v1/admin/licenses/{license_id}/disable", json_body=payload)
    return JSONResponse(result)


@app.post("/api/licenses/{license_id}/ban")
async def api_ban_license(request: Request, license_id: int) -> JSONResponse:
    payload = await request.json()
    result = await call_api(request, "POST", f"/v1/admin/licenses/{license_id}/ban", json_body=payload)
    return JSONResponse(result)


@app.post("/api/licenses/{license_id}/restore")
async def api_restore_license(request: Request, license_id: int) -> JSONResponse:
    result = await call_api(request, "POST", f"/v1/admin/licenses/{license_id}/restore", json_body={})
    return JSONResponse(result)


@app.post("/api/licenses/{license_id}/reset-device")
async def api_reset_device(request: Request, license_id: int) -> JSONResponse:
    payload = await request.json()
    result = await call_api(request, "POST", f"/v1/admin/licenses/{license_id}/reset-device", json_body=payload)
    return JSONResponse(result)


@app.get("/api/audit-logs")
async def api_audit_logs(request: Request, limit: int = 100) -> JSONResponse:
    payload = await call_api(request, "GET", "/v1/admin/audit-logs", params={"limit": limit})
    return JSONResponse(payload)
