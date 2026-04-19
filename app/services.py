from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from urllib.parse import quote

from .config import settings
from .db import Database
from .mailer import is_mail_enabled, send_mail
from .security import hash_password, now_ts, sign_payload, verify_password, verify_signed_token


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_slug(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "-")


def bool_int(value: bool) -> int:
    return 1 if value else 0


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


@dataclass
class AuthService:
    db: Database

    def bootstrap(self) -> None:
        self.db.initialize()
        with self.db.session() as conn:
            row = conn.execute("SELECT id FROM apps WHERE slug = ?", (settings.bootstrap_app_slug,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO apps (slug, name, enabled, callback_url, created_at) VALUES (?, ?, 1, '', ?)",
                    (settings.bootstrap_app_slug, settings.bootstrap_app_name, iso_now()),
                )
            admin_email = normalize_email(settings.bootstrap_admin_email)
            admin_password = str(settings.bootstrap_admin_password or "").strip()
            if admin_email and admin_password:
                user = conn.execute("SELECT * FROM users WHERE email = ?", (admin_email,)).fetchone()
                if user is None:
                    conn.execute(
                        "INSERT INTO users (email, password_hash, enabled, created_at) VALUES (?, ?, 1, ?)",
                        (admin_email, hash_password(admin_password), iso_now()),
                    )
                else:
                    conn.execute(
                        "UPDATE users SET password_hash = ?, enabled = 1 WHERE id = ?",
                        (hash_password(admin_password), user["id"]),
                    )

    def is_admin_email(self, email: str) -> bool:
        return normalize_email(email) in {
            normalize_email(item)
            for item in [*settings.admin_emails, settings.bootstrap_admin_email]
            if normalize_email(item)
        }

    def admin_notify_emails(self) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()
        for raw in [*settings.admin_emails, settings.bootstrap_admin_email]:
            email = normalize_email(raw)
            if not email or email in seen:
                continue
            seen.add(email)
            items.append(email)
        return items

    def list_apps(self) -> list[dict[str, Any]]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM apps ORDER BY id DESC").fetchall()
            return [dict(row) for row in rows]

    def create_app(self, slug: str, name: str, callback_url: str = "") -> dict[str, Any]:
        slug = normalize_slug(slug)
        name = str(name or "").strip()
        require(slug, "app slug is required")
        require(name, "app name is required")
        with self.db.session() as conn:
            conn.execute(
                "INSERT INTO apps (slug, name, enabled, callback_url, created_at) VALUES (?, ?, 1, ?, ?)",
                (slug, name, str(callback_url or "").strip(), iso_now()),
            )
            row = conn.execute("SELECT * FROM apps WHERE slug = ?", (slug,)).fetchone()
            return dict(row)

    def update_app(self, slug: str, *, enabled: bool | None = None, callback_url: str | None = None) -> dict[str, Any]:
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM apps WHERE slug = ?", (normalize_slug(slug),)).fetchone()
            require(row is not None, "app not found")
            enabled_value = row["enabled"] if enabled is None else bool_int(enabled)
            callback_value = row["callback_url"] if callback_url is None else str(callback_url).strip()
            conn.execute(
                "UPDATE apps SET enabled = ?, callback_url = ? WHERE id = ?",
                (enabled_value, callback_value, row["id"]),
            )
            updated = conn.execute("SELECT * FROM apps WHERE id = ?", (row["id"],)).fetchone()
            return dict(updated)

    def _get_app(self, conn, slug: str):
        row = conn.execute("SELECT * FROM apps WHERE slug = ?", (normalize_slug(slug),)).fetchone()
        require(row is not None, "app not found")
        require(bool(row["enabled"]), "app is disabled")
        return row

    def get_public_app(self, slug: str) -> dict[str, Any]:
        with self.db.session() as conn:
            app = self._get_app(conn, slug)
            return {
                "slug": app["slug"],
                "name": app["name"],
                "callback_url": app["callback_url"],
            }

    def list_invites(self, app_slug: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT i.*, a.slug AS app_slug, a.name AS app_name, a.callback_url
            FROM invites i
            JOIN apps a ON a.id = i.app_id
            WHERE i.used_at = ''
        """
        params: list[Any] = []
        if app_slug:
            query += " AND a.slug = ?"
            params.append(normalize_slug(app_slug))
        query += " ORDER BY i.id DESC"
        with self.db.session() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def _build_register_link(self, invite: dict[str, Any]) -> str:
        link = f"{settings.base_url}/register?token={quote(invite['invite_token'])}"
        app_slug = str(invite.get("app_slug") or "").strip()
        callback_url = str(invite.get("callback_url") or "").strip()
        if app_slug:
            link += f"&app_slug={quote(app_slug)}"
        if callback_url:
            link += f"&return_to={quote(callback_url, safe='')}"
        return link

    def _build_login_link(self, app_slug: str, callback_url: str = "") -> str:
        link = f"{settings.base_url}/login"
        query: list[str] = []
        if app_slug:
            query.append(f"app_slug={quote(app_slug, safe='')}")
        if callback_url:
            query.append(f"return_to={quote(callback_url, safe='')}")
        if query:
            link += "?" + "&".join(query)
        return link

    def _application_detail_query(self) -> str:
        return """
            SELECT ra.*, a.slug AS app_slug, a.name AS app_name, a.callback_url,
                   CASE WHEN u.id IS NULL THEN 0 ELSE 1 END AS has_account,
                   CASE WHEN au.id IS NULL THEN 0 ELSE 1 END AS has_access
            FROM registration_applications ra
            JOIN apps a ON a.id = ra.app_id
            LEFT JOIN users u ON u.email = ra.email
            LEFT JOIN app_users au ON au.user_id = u.id AND au.app_id = ra.app_id
        """

    def _row_to_application(self, row: Any) -> dict[str, Any]:
        item = dict(row)
        item["has_account"] = bool(item.get("has_account"))
        item["has_access"] = bool(item.get("has_access"))
        item["review_metadata"] = json.loads(item.pop("review_metadata_json") or "{}")
        return item

    def list_applications(self, status: str | None = None, app_slug: str | None = None) -> list[dict[str, Any]]:
        query = self._application_detail_query() + " WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND ra.status = ?"
            params.append(str(status).strip().lower())
        if app_slug:
            query += " AND a.slug = ?"
            params.append(normalize_slug(app_slug))
        query += " ORDER BY CASE ra.status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END, ra.id DESC"
        with self.db.session() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_application(row) for row in rows]

    async def send_new_application_admin_email(self, application: dict[str, Any]) -> None:
        recipients = self.admin_notify_emails()
        if not recipients:
            return
        app_name = application.get("app_name") or application.get("app_slug") or "App"
        admin_link = f"{settings.base_url}/admin"
        html = (
            f"<div style='font-family:Arial,sans-serif;line-height:1.7'>"
            f"<h2>有新的注册申请</h2>"
            f"<p>应用：<strong>{escape(str(app_name))}</strong></p>"
            f"<p>邮箱：<strong>{escape(str(application['email']))}</strong></p>"
            f"<p>提交时间：<strong>{escape(str(application.get('submitted_at') or ''))}</strong></p>"
            f"<p><a href='{escape(admin_link)}'>点击前往管理员后台审核</a></p>"
            f"</div>"
        )
        for email in recipients:
            await send_mail(
                to_mail=email,
                subject=f"[{app_name}] 新的注册申请",
                content=html,
                is_html=True,
            )

    async def submit_application(self, *, app_slug: str, email: str) -> dict[str, Any]:
        email = normalize_email(email)
        require("@" in email, "valid email is required")
        now = iso_now()
        created = False
        with self.db.session() as conn:
            app = self._get_app(conn, app_slug)
            existing = conn.execute(
                self._application_detail_query() + " WHERE ra.app_id = ? AND ra.email = ? AND ra.status = 'pending'",
                (app["id"], email),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    "UPDATE registration_applications SET submitted_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
                row = conn.execute(
                    self._application_detail_query() + " WHERE ra.id = ?",
                    (existing["id"],),
                ).fetchone()
                return self._row_to_application(row)

            conn.execute(
                "INSERT INTO registration_applications (app_id, email, status, submitted_at) VALUES (?, ?, 'pending', ?)",
                (app["id"], email, now),
            )
            created = True
            row = conn.execute(
                self._application_detail_query() + " WHERE ra.id = last_insert_rowid()",
            ).fetchone()
            item = self._row_to_application(row)
        if created and is_mail_enabled():
            await self.send_new_application_admin_email(item)
            with self.db.session() as conn:
                conn.execute(
                    "UPDATE registration_applications SET last_notified_at = ? WHERE id = ?",
                    (iso_now(), item["id"]),
                )
                row = conn.execute(
                    self._application_detail_query() + " WHERE ra.id = ?",
                    (item["id"],),
                ).fetchone()
                item = self._row_to_application(row)
        return item

    def _create_invite_record(
        self,
        conn,
        *,
        app: Any,
        email: str,
        role: str = "member",
        target: str = "",
        metadata: dict[str, Any] | None = None,
        note: str = "",
        expires_in_hours: int = 72,
    ) -> dict[str, Any]:
        invite_token = secrets.token_urlsafe(24)
        expires_at = (utc_now() + timedelta(hours=max(1, expires_in_hours))).replace(microsecond=0)
        metadata_json = json.dumps(metadata or {}, separators=(",", ":"))
        conn.execute(
            "INSERT INTO invites (app_id, email, invite_token, role, target, metadata_json, note, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                app["id"],
                email,
                invite_token,
                str(role or "member").strip() or "member",
                str(target or "").strip(),
                metadata_json,
                str(note or "").strip(),
                expires_at.isoformat().replace("+00:00", "Z"),
                iso_now(),
            ),
        )
        row = conn.execute(
            """
            SELECT i.*, a.slug AS app_slug, a.name AS app_name, a.callback_url
            FROM invites i JOIN apps a ON a.id = i.app_id
            WHERE i.invite_token = ?
            """,
            (invite_token,),
        ).fetchone()
        return dict(row)

    async def create_invite(
        self,
        *,
        app_slug: str,
        email: str,
        role: str = "member",
        target: str = "",
        metadata: dict[str, Any] | None = None,
        note: str = "",
        expires_in_hours: int = 72,
        send_email_now: bool = True,
    ) -> dict[str, Any]:
        email = normalize_email(email)
        require("@" in email, "valid email is required")
        with self.db.session() as conn:
            app = self._get_app(conn, app_slug)
            invite = self._create_invite_record(
                conn,
                app=app,
                email=email,
                role=role,
                target=target,
                metadata=metadata,
                note=note,
                expires_in_hours=expires_in_hours,
            )
        if send_email_now and is_mail_enabled():
            await self.send_invite_email(invite)
        return invite

    async def send_invite_email(self, invite: dict[str, Any]) -> None:
        link = self._build_register_link(invite)
        app_name = invite.get("app_name") or invite.get("app_slug") or "App"
        html = (
            f"<div style='font-family:Arial,sans-serif;line-height:1.7'>"
            f"<h2>{escape(app_name)} 邀请注册</h2>"
            f"<p>你已被邀请加入 {escape(app_name)}。</p>"
            f"<p>注册邮箱：<strong>{escape(invite['email'])}</strong></p>"
            f"<p><a href='{escape(link)}'>点击完成注册</a></p>"
            f"<p>如无法点击，请复制链接：{escape(link)}</p>"
            f"</div>"
        )
        await send_mail(to_mail=invite["email"], subject=f"{app_name} 邀请注册", content=html, is_html=True)

    async def send_application_approved_registration_email(self, application: dict[str, Any], invite: dict[str, Any]) -> None:
        link = self._build_register_link(invite)
        app_name = application.get("app_name") or application.get("app_slug") or "App"
        note = str(application.get("review_note") or "").strip()
        note_html = f"<p>审核备注：{escape(note)}</p>" if note else ""
        html = (
            f"<div style='font-family:Arial,sans-serif;line-height:1.7'>"
            f"<h2>{escape(app_name)} 申请已通过</h2>"
            f"<p>你的开通申请已通过审核，请使用下方链接完成注册。</p>"
            f"<p>注册邮箱：<strong>{escape(application['email'])}</strong></p>"
            f"{note_html}"
            f"<p><a href='{escape(link)}'>点击完成注册</a></p>"
            f"<p>如无法点击，请复制链接：{escape(link)}</p>"
            f"</div>"
        )
        await send_mail(to_mail=application["email"], subject=f"{app_name} 申请已通过", content=html, is_html=True)

    async def send_application_access_granted_email(self, application: dict[str, Any]) -> None:
        app_name = application.get("app_name") or application.get("app_slug") or "App"
        link = self._build_login_link(str(application.get("app_slug") or ""), str(application.get("callback_url") or ""))
        note = str(application.get("review_note") or "").strip()
        note_html = f"<p>审核备注：{escape(note)}</p>" if note else ""
        html = (
            f"<div style='font-family:Arial,sans-serif;line-height:1.7'>"
            f"<h2>{escape(app_name)} 已开通</h2>"
            f"<p>你的申请已通过，系统已直接为现有账号开通该应用访问权限。</p>"
            f"<p>登录邮箱：<strong>{escape(application['email'])}</strong></p>"
            f"{note_html}"
            f"<p><a href='{escape(link)}'>点击前往登录</a></p>"
            f"<p>如无法点击，请复制链接：{escape(link)}</p>"
            f"</div>"
        )
        await send_mail(to_mail=application["email"], subject=f"{app_name} 已开通", content=html, is_html=True)

    async def send_application_rejected_email(self, application: dict[str, Any]) -> None:
        app_name = application.get("app_name") or application.get("app_slug") or "App"
        note = str(application.get("review_note") or "").strip()
        note_html = f"<p>审核说明：{escape(note)}</p>" if note else ""
        html = (
            f"<div style='font-family:Arial,sans-serif;line-height:1.7'>"
            f"<h2>{escape(app_name)} 申请未通过</h2>"
            f"<p>很抱歉，你提交的开通申请本次未通过审核。</p>"
            f"<p>申请邮箱：<strong>{escape(application['email'])}</strong></p>"
            f"{note_html}"
            f"</div>"
        )
        await send_mail(to_mail=application["email"], subject=f"{app_name} 申请未通过", content=html, is_html=True)

    def get_invite(self, token: str) -> dict[str, Any]:
        with self.db.session() as conn:
            row = conn.execute(
                """
                SELECT i.*, a.slug AS app_slug, a.name AS app_name, a.callback_url
                FROM invites i JOIN apps a ON a.id = i.app_id
                WHERE i.invite_token = ?
                """,
                (token,),
            ).fetchone()
            require(row is not None, "invite not found")
            invite = dict(row)
        require(invite["used_at"] == "", "invite already used")
        require(parse_iso(invite["expires_at"]) > utc_now(), "invite expired")
        return invite

    def delete_invite(self, token: str) -> None:
        with self.db.session() as conn:
            conn.execute("DELETE FROM invites WHERE invite_token = ?", (token,))

    async def approve_application(
        self,
        *,
        application_id: int,
        role: str = "member",
        target: str = "",
        metadata: dict[str, Any] | None = None,
        note: str = "",
        reviewed_by: str = "admin",
        expires_in_hours: int = 72,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        next_role = str(role or "member").strip() or "member"
        next_target = str(target or "").strip()
        next_note = str(note or "").strip()
        next_metadata_json = json.dumps(metadata, separators=(",", ":"))
        reviewed_at = iso_now()
        delivery = "registration"
        invite: dict[str, Any] | None = None

        with self.db.session() as conn:
            row = conn.execute(
                self._application_detail_query() + " WHERE ra.id = ?",
                (int(application_id),),
            ).fetchone()
            require(row is not None, "application not found")
            application = self._row_to_application(row)
            require(application["status"] == "pending", "application is not pending")

            user = conn.execute("SELECT * FROM users WHERE email = ?", (application["email"],)).fetchone()
            if user is None:
                app = self._get_app(conn, application["app_slug"])
                invite = self._create_invite_record(
                    conn,
                    app=app,
                    email=application["email"],
                    role=next_role,
                    target=next_target,
                    metadata=metadata,
                    note=next_note,
                    expires_in_hours=expires_in_hours,
                )
                approved_invite_token = invite["invite_token"]
            else:
                delivery = "existing_user"
                conn.execute("UPDATE users SET enabled = 1 WHERE id = ?", (user["id"],))
                conn.execute(
                    """
                    INSERT INTO app_users (user_id, app_id, role, default_target, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, app_id)
                    DO UPDATE SET role=excluded.role, default_target=excluded.default_target, metadata_json=excluded.metadata_json
                    """,
                    (
                        user["id"],
                        application["app_id"],
                        next_role,
                        next_target,
                        next_metadata_json,
                        iso_now(),
                    ),
                )
                approved_invite_token = ""

            conn.execute(
                """
                UPDATE registration_applications
                SET status = 'approved',
                    review_note = ?,
                    review_role = ?,
                    review_target = ?,
                    review_metadata_json = ?,
                    approved_invite_token = ?,
                    reviewed_at = ?,
                    reviewed_by = ?
                WHERE id = ?
                """,
                (
                    next_note,
                    next_role,
                    next_target,
                    next_metadata_json,
                    approved_invite_token,
                    reviewed_at,
                    str(reviewed_by or "admin").strip() or "admin",
                    application["id"],
                ),
            )
            refreshed = conn.execute(
                self._application_detail_query() + " WHERE ra.id = ?",
                (application["id"],),
            ).fetchone()
            result = self._row_to_application(refreshed)
            result["delivery"] = delivery

        if is_mail_enabled():
            if delivery == "registration" and invite is not None:
                await self.send_application_approved_registration_email(result, invite)
            else:
                await self.send_application_access_granted_email(result)
            with self.db.session() as conn:
                conn.execute(
                    "UPDATE registration_applications SET last_notified_at = ? WHERE id = ?",
                    (iso_now(), result["id"]),
                )
        return result

    async def reject_application(
        self,
        *,
        application_id: int,
        note: str = "",
        reviewed_by: str = "admin",
    ) -> dict[str, Any]:
        reviewed_at = iso_now()
        with self.db.session() as conn:
            row = conn.execute(
                self._application_detail_query() + " WHERE ra.id = ?",
                (int(application_id),),
            ).fetchone()
            require(row is not None, "application not found")
            application = self._row_to_application(row)
            require(application["status"] == "pending", "application is not pending")
            conn.execute(
                """
                UPDATE registration_applications
                SET status = 'rejected',
                    review_note = ?,
                    review_role = '',
                    review_target = '',
                    review_metadata_json = '{}',
                    approved_invite_token = '',
                    reviewed_at = ?,
                    reviewed_by = ?
                WHERE id = ?
                """,
                (
                    str(note or "").strip(),
                    reviewed_at,
                    str(reviewed_by or "admin").strip() or "admin",
                    application["id"],
                ),
            )
            refreshed = conn.execute(
                self._application_detail_query() + " WHERE ra.id = ?",
                (application["id"],),
            ).fetchone()
            result = self._row_to_application(refreshed)

        if is_mail_enabled():
            await self.send_application_rejected_email(result)
            with self.db.session() as conn:
                conn.execute(
                    "UPDATE registration_applications SET last_notified_at = ? WHERE id = ?",
                    (iso_now(), result["id"]),
                )
        return result

    def register(self, *, invite_token: str, email: str, password: str) -> dict[str, Any]:
        require(len(password) >= 8, "password must be at least 8 characters")
        invite = self.get_invite(invite_token)
        email = normalize_email(email)
        require(email == normalize_email(invite["email"]), "email does not match invite")
        with self.db.session() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user is None:
                conn.execute(
                    "INSERT INTO users (email, password_hash, enabled, created_at) VALUES (?, ?, 1, ?)",
                    (email, hash_password(password), iso_now()),
                )
                user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            else:
                raise ValueError("account already exists, please log in instead of registering again")
            conn.execute(
                """
                INSERT INTO app_users (user_id, app_id, role, default_target, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, app_id)
                DO UPDATE SET role=excluded.role, default_target=excluded.default_target, metadata_json=excluded.metadata_json
                """,
                (
                    user["id"],
                    invite["app_id"],
                    invite["role"],
                    invite["target"],
                    invite["metadata_json"],
                    iso_now(),
                ),
            )
            conn.execute("UPDATE invites SET used_at = ? WHERE id = ?", (iso_now(), invite["id"]))
        return self.authenticate(email=email, password=password)

    def authenticate(self, *, email: str, password: str) -> dict[str, Any]:
        email = normalize_email(email)
        with self.db.session() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            require(user is not None, "invalid email or password")
            require(bool(user["enabled"]), "user is disabled")
            require(verify_password(password, user["password_hash"]), "invalid email or password")
            apps = conn.execute(
                """
                SELECT a.slug, a.name, a.callback_url, au.role, au.default_target, au.metadata_json
                FROM app_users au
                JOIN apps a ON a.id = au.app_id
                WHERE au.user_id = ? AND a.enabled = 1
                ORDER BY a.slug
                """,
                (user["id"],),
            ).fetchall()
        session_token = sign_payload(
            {
                "purpose": "session",
                "sub": user["id"],
                "email": user["email"],
                "iat": now_ts(),
                "exp": now_ts() + settings.session_ttl_hours * 3600,
            },
            settings.session_secret,
        )
        app_list = []
        for row in apps:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            app_list.append(item)
        return {"token": session_token, "user": {"email": user["email"], "apps": app_list}}

    def verify_session(self, token: str) -> dict[str, Any]:
        payload = verify_signed_token(token, settings.session_secret)
        require(payload is not None, "invalid session token")
        require(payload.get("purpose") == "session", "invalid session token")
        require(int(payload.get("exp", 0)) > now_ts(), "session expired")
        user_id = int(payload["sub"])
        with self.db.session() as conn:
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            require(user is not None and bool(user["enabled"]), "user not found")
            rows = conn.execute(
                """
                SELECT a.slug, a.name, a.callback_url, au.role, au.default_target, au.metadata_json
                FROM app_users au
                JOIN apps a ON a.id = au.app_id
                WHERE au.user_id = ? AND a.enabled = 1
                ORDER BY a.slug
                """,
                (user_id,),
            ).fetchall()
        apps = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            apps.append(item)
        return {"user_id": user_id, "email": user["email"], "apps": apps}

    def issue_app_token(self, session_token: str, app_slug: str) -> dict[str, Any]:
        session = self.verify_session(session_token)
        app_slug = normalize_slug(app_slug)
        app = next((item for item in session["apps"] if item["slug"] == app_slug), None)
        require(app is not None, "user has no access to this app")
        token = sign_payload(
            {
                "purpose": "app",
                "sub": session["user_id"],
                "email": session["email"],
                "app": app["slug"],
                "role": app["role"],
                "target": app["default_target"],
                "metadata": app["metadata"],
                "iat": now_ts(),
                "exp": now_ts() + settings.app_token_ttl_minutes * 60,
            },
            settings.app_token_secret,
        )
        return {"token": token, "claims": {"email": session["email"], **app}}

    def verify_app_token(self, token: str, app_slug: str | None = None) -> dict[str, Any]:
        payload = verify_signed_token(token, settings.app_token_secret)
        require(payload is not None, "invalid app token")
        require(payload.get("purpose") == "app", "invalid app token")
        require(int(payload.get("exp", 0)) > now_ts(), "app token expired")
        if app_slug:
            require(payload.get("app") == normalize_slug(app_slug), "token app mismatch")
        return payload

    async def request_password_reset(self, email: str, *, app_slug: str = "", return_to: str = "") -> None:
        email = normalize_email(email)
        with self.db.session() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user is None or not bool(user["enabled"]):
                return
            reset_token = secrets.token_urlsafe(24)
            expires_at = (utc_now() + timedelta(minutes=settings.reset_ttl_minutes)).replace(microsecond=0)
            conn.execute(
                "INSERT INTO password_resets (user_id, reset_token, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (user["id"], reset_token, expires_at.isoformat().replace("+00:00", "Z"), iso_now()),
            )
        if not is_mail_enabled():
            return
        link = f"{settings.base_url}/reset-password?token={quote(reset_token)}"
        app_slug = normalize_slug(app_slug)
        if app_slug:
            link += f"&app_slug={quote(app_slug, safe='')}"
        if return_to:
            link += f"&return_to={quote(str(return_to).strip(), safe='')}"
        html = (
            f"<div style='font-family:Arial,sans-serif;line-height:1.7'>"
            f"<h2>密码重置</h2>"
            f"<p>账号：<strong>{escape(email)}</strong></p>"
            f"<p><a href='{escape(link)}'>点击重置密码</a></p>"
            f"<p>有效期 {settings.reset_ttl_minutes} 分钟。</p>"
            f"</div>"
        )
        await send_mail(to_mail=email, subject="密码重置", content=html, is_html=True)

    def verify_reset_token(self, token: str) -> dict[str, Any]:
        with self.db.session() as conn:
            row = conn.execute(
                """
                SELECT pr.*, u.email
                FROM password_resets pr
                JOIN users u ON u.id = pr.user_id
                WHERE pr.reset_token = ?
                """,
                (token,),
            ).fetchone()
            require(row is not None, "reset token not found")
            data = dict(row)
        require(data["used_at"] == "", "reset token already used")
        require(parse_iso(data["expires_at"]) > utc_now(), "reset token expired")
        return data

    def reset_password(self, token: str, password: str) -> dict[str, Any]:
        require(len(password) >= 8, "password must be at least 8 characters")
        reset = self.verify_reset_token(token)
        with self.db.session() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), reset["user_id"]))
            conn.execute("UPDATE password_resets SET used_at = ? WHERE id = ?", (iso_now(), reset["id"]))
        return self.authenticate(email=reset["email"], password=password)

    def list_users(self, app_slug: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT u.email, u.enabled, u.created_at, a.slug AS app_slug, a.name AS app_name,
                   au.role, au.default_target, au.metadata_json
            FROM app_users au
            JOIN users u ON u.id = au.user_id
            JOIN apps a ON a.id = au.app_id
            WHERE 1=1
        """
        params: list[Any] = []
        if app_slug:
            query += " AND a.slug = ?"
            params.append(normalize_slug(app_slug))
        query += " ORDER BY u.id DESC"
        with self.db.session() as conn:
            rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            result.append(item)
        return result

    def update_user_access(
        self,
        *,
        app_slug: str,
        email: str,
        role: str | None = None,
        target: str | None = None,
        enabled: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        email = normalize_email(email)
        with self.db.session() as conn:
            app = self._get_app(conn, app_slug)
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            require(user is not None, "user not found")
            access = conn.execute(
                "SELECT * FROM app_users WHERE user_id = ? AND app_id = ?",
                (user["id"], app["id"]),
            ).fetchone()
            require(access is not None, "user has no access to this app")
            next_role = access["role"] if role is None else str(role or "member").strip() or "member"
            next_target = access["default_target"] if target is None else str(target or "").strip()
            next_metadata = access["metadata_json"] if metadata is None else json.dumps(metadata, separators=(",", ":"))
            conn.execute(
                "UPDATE app_users SET role = ?, default_target = ?, metadata_json = ? WHERE id = ?",
                (next_role, next_target, next_metadata, access["id"]),
            )
            if enabled is not None:
                conn.execute("UPDATE users SET enabled = ? WHERE id = ?", (bool_int(enabled), user["id"]))
            row = conn.execute(
                """
                SELECT u.email, u.enabled, u.created_at, a.slug AS app_slug, a.name AS app_name,
                       au.role, au.default_target, au.metadata_json
                FROM app_users au
                JOIN users u ON u.id = au.user_id
                JOIN apps a ON a.id = au.app_id
                WHERE au.id = ?
                """,
                (access["id"],),
            ).fetchone()
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        return item

    def remove_user_access(self, *, app_slug: str, email: str) -> None:
        email = normalize_email(email)
        with self.db.session() as conn:
            app = self._get_app(conn, app_slug)
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user is None:
                return
            conn.execute(
                "DELETE FROM app_users WHERE user_id = ? AND app_id = ?",
                (user["id"], app["id"]),
            )
