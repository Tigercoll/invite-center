from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .db import Database
from .mailer import is_mail_enabled
from .services import AuthService

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
db = Database(settings.db_path)
svc = AuthService(db)


def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


async def require_admin(authorization: str | None = Header(default=None)) -> None:
    token = _bearer(authorization)
    if token == settings.admin_key:
        return
    if not token:
        raise HTTPException(401, "missing admin session")
    try:
        session = svc.verify_session(token)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    if not svc.is_admin_email(str(session.get("email") or "")):
        raise HTTPException(403, "admin access required")


def current_session(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = _bearer(authorization)
    if not token:
        raise HTTPException(401, "missing session token")
    try:
        return svc.verify_session(token)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc


class AppCreateRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=100)
    callback_url: str = Field(default="", max_length=500)


class AppUpdateRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64)
    enabled: bool | None = None
    callback_url: str | None = Field(default=None, max_length=500)


class InviteCreateRequest(BaseModel):
    app_slug: str = Field(..., min_length=2, max_length=64)
    email: str = Field(..., min_length=3, max_length=320)
    role: str = Field(default="member", max_length=50)
    target: str = Field(default="", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)
    note: str = Field(default="", max_length=200)
    expires_in_hours: int = Field(default=72, ge=1, le=24 * 30)
    send_email: bool = True


class ApplicationCreateRequest(BaseModel):
    app_slug: str = Field(..., min_length=2, max_length=64)
    email: str = Field(..., min_length=3, max_length=320)


class ApplicationApproveRequest(BaseModel):
    application_id: int = Field(..., ge=1)
    role: str = Field(default="member", max_length=50)
    target: str = Field(default="", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)
    note: str = Field(default="", max_length=500)
    expires_in_hours: int = Field(default=72, ge=1, le=24 * 30)


class ApplicationRejectRequest(BaseModel):
    application_id: int = Field(..., ge=1)
    note: str = Field(default="", max_length=500)


class RegisterRequest(BaseModel):
    invite_token: str = Field(..., min_length=10, max_length=200)
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    app_slug: str = Field(default="", max_length=64)
    return_to: str = Field(default="", max_length=1000)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    password: str = Field(..., min_length=8, max_length=200)


class AccessTokenRequest(BaseModel):
    app_slug: str = Field(..., min_length=2, max_length=64)


class UserAccessUpdateRequest(BaseModel):
    app_slug: str = Field(..., min_length=2, max_length=64)
    email: str = Field(..., min_length=3, max_length=320)
    role: str | None = Field(default=None, max_length=50)
    target: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


def page(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name)


app = FastAPI(title="Invite Center", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def startup() -> None:
    svc.bootstrap()


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login")


@app.get("/login", include_in_schema=False)
async def login_page():
    return page("login.html")


@app.get("/logout", include_in_schema=False)
async def logout_page():
    return page("logout.html")


@app.get("/apply", include_in_schema=False)
async def apply_page():
    return page("apply.html")


@app.get("/register", include_in_schema=False)
async def register_page():
    return page("register.html")


@app.get("/launch", include_in_schema=False)
async def launch_page():
    return page("launch.html")


@app.get("/forgot-password", include_in_schema=False)
async def forgot_page():
    return page("forgot-password.html")


@app.get("/reset-password", include_in_schema=False)
async def reset_page():
    return page("reset-password.html")


@app.get("/admin", include_in_schema=False)
async def admin_page():
    return page("admin.html")


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/api/meta")
async def meta():
    return {
        "base_url": settings.base_url,
        "mail_enabled": is_mail_enabled(),
        "bootstrap_app_slug": settings.bootstrap_app_slug,
    }


@app.get("/api/auth/app")
async def auth_app(slug: str = Query(..., min_length=2, max_length=64)):
    try:
        return {"status": "ok", "app": svc.get_public_app(slug)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/auth/applications")
async def auth_submit_application(payload: ApplicationCreateRequest):
    try:
        return {"status": "ok", "item": await svc.submit_application(**payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/auth/invite")
async def auth_invite(token: str = Query(...)):
    try:
        return {"status": "ok", "invite": svc.get_invite(token)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/auth/register")
async def auth_register(payload: RegisterRequest):
    try:
        return {"status": "ok", **svc.register(**payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/auth/login")
async def auth_login(payload: LoginRequest):
    try:
        return {"status": "ok", **svc.authenticate(**payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/auth/me")
async def auth_me(session: dict[str, Any] = Depends(current_session)):
    return {"status": "ok", **session}


@app.post("/api/auth/access-token")
async def auth_access_token(payload: AccessTokenRequest, authorization: str | None = Header(default=None)):
    try:
        result = svc.issue_app_token(_bearer(authorization), payload.app_slug)
        return {"status": "ok", **result}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/auth/verify")
async def auth_verify(authorization: str | None = Header(default=None), app_slug: str | None = Query(default=None)):
    try:
        claims = svc.verify_app_token(_bearer(authorization), app_slug)
        return {"status": "ok", "claims": claims}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/auth/password/forgot")
async def auth_password_forgot(payload: ForgotPasswordRequest):
    await svc.request_password_reset(
        payload.email,
        app_slug=payload.app_slug,
        return_to=payload.return_to,
    )
    return {"status": "ok", "message": "If the account exists, reset instructions have been sent."}


@app.get("/api/auth/password/reset/verify")
async def auth_password_reset_verify(token: str = Query(...)):
    try:
        data = svc.verify_reset_token(token)
        return {"status": "ok", "email": data["email"]}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/auth/password/reset")
async def auth_password_reset(payload: ResetPasswordRequest):
    try:
        return {"status": "ok", **svc.reset_password(payload.token, payload.password)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/admin/apps", dependencies=[Depends(require_admin)])
async def admin_apps():
    return {"status": "ok", "items": svc.list_apps()}


@app.get("/api/admin/me", dependencies=[Depends(require_admin)])
async def admin_me(session: dict[str, Any] = Depends(current_session)):
    return {
        "status": "ok",
        "email": session["email"],
        "is_admin": svc.is_admin_email(session["email"]),
        "apps": session["apps"],
    }


@app.post("/api/admin/apps", dependencies=[Depends(require_admin)])
async def admin_apps_create(payload: AppCreateRequest):
    try:
        return {"status": "ok", "item": svc.create_app(**payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.patch("/api/admin/apps", dependencies=[Depends(require_admin)])
async def admin_apps_update(payload: AppUpdateRequest):
    try:
        return {"status": "ok", "item": svc.update_app(**payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/admin/applications", dependencies=[Depends(require_admin)])
async def admin_applications(
    status: str | None = Query(default=None),
    app_slug: str | None = Query(default=None),
):
    return {"status": "ok", "items": svc.list_applications(status=status, app_slug=app_slug)}


@app.post("/api/admin/applications/approve", dependencies=[Depends(require_admin)])
async def admin_applications_approve(payload: ApplicationApproveRequest):
    try:
        item = await svc.approve_application(**payload.model_dump())
        return {"status": "ok", "item": item, "mail_enabled": is_mail_enabled()}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/admin/applications/reject", dependencies=[Depends(require_admin)])
async def admin_applications_reject(payload: ApplicationRejectRequest):
    try:
        item = await svc.reject_application(**payload.model_dump())
        return {"status": "ok", "item": item, "mail_enabled": is_mail_enabled()}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/admin/invites", dependencies=[Depends(require_admin)])
async def admin_invites(app_slug: str | None = Query(default=None)):
    return {"status": "ok", "items": svc.list_invites(app_slug)}


@app.post("/api/admin/invites", dependencies=[Depends(require_admin)])
async def admin_invites_create(payload: InviteCreateRequest):
    try:
        params = payload.model_dump()
        params["send_email_now"] = params.pop("send_email", True)
        invite = await svc.create_invite(**params)
        return {"status": "ok", "item": invite, "mail_enabled": is_mail_enabled()}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/admin/invites/resend", dependencies=[Depends(require_admin)])
async def admin_invites_resend(token: str = Query(...)):
    try:
        invite = svc.get_invite(token)
        await svc.send_invite_email(invite)
        return {"status": "ok"}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/admin/invites", dependencies=[Depends(require_admin)])
async def admin_invites_delete(token: str = Query(...)):
    svc.delete_invite(token)
    return {"status": "ok"}


@app.get("/api/admin/users", dependencies=[Depends(require_admin)])
async def admin_users(app_slug: str | None = Query(default=None)):
    return {"status": "ok", "items": svc.list_users(app_slug)}


@app.patch("/api/admin/users", dependencies=[Depends(require_admin)])
async def admin_users_update(payload: UserAccessUpdateRequest):
    try:
        return {"status": "ok", "item": svc.update_user_access(**payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/admin/users", dependencies=[Depends(require_admin)])
async def admin_users_delete(app_slug: str = Query(...), email: str = Query(...)):
    svc.remove_user_access(app_slug=app_slug, email=email)
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception):
    return JSONResponse({"error": str(exc)}, status_code=500)
