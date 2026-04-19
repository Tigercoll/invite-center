from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional for bare stdlib tests
    def load_dotenv() -> None:
        return None

load_dotenv()


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
        return value if value > 0 else default
    except (AttributeError, ValueError):
        return default


def _csv_env(name: str) -> tuple[str, ...]:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return ()
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    db_path: Path
    session_secret: str
    app_token_secret: str
    admin_key: str
    admin_emails: tuple[str, ...]
    bootstrap_admin_email: str
    bootstrap_admin_password: str
    session_ttl_hours: int
    app_token_ttl_minutes: int
    reset_ttl_minutes: int
    base_url: str
    mail_api_url: str
    mail_api_token: str
    mail_from_name: str
    bootstrap_app_slug: str
    bootstrap_app_name: str


def get_settings() -> Settings:
    data_dir = Path(os.getenv("AUTH_CENTER_DATA_DIR", "./data")).resolve()
    db_path_raw = os.getenv("AUTH_CENTER_DB_PATH", str(data_dir / "auth_center.db"))
    db_path = Path(db_path_raw).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        host=os.getenv("AUTH_CENTER_HOST", "0.0.0.0").strip(),
        port=_int_env("AUTH_CENTER_PORT", 8010),
        data_dir=data_dir,
        db_path=db_path,
        session_secret=os.getenv("AUTH_CENTER_SESSION_SECRET", "change-me-session-secret").strip(),
        app_token_secret=os.getenv("AUTH_CENTER_APP_TOKEN_SECRET", "change-me-app-token-secret").strip(),
        admin_key=os.getenv("AUTH_CENTER_ADMIN_KEY", "change-me-admin-key").strip(),
        admin_emails=_csv_env("AUTH_CENTER_ADMIN_EMAILS"),
        bootstrap_admin_email=os.getenv("AUTH_CENTER_BOOTSTRAP_ADMIN_EMAIL", "").strip().lower(),
        bootstrap_admin_password=os.getenv("AUTH_CENTER_BOOTSTRAP_ADMIN_PASSWORD", "").strip(),
        session_ttl_hours=_int_env("AUTH_CENTER_SESSION_TTL_HOURS", 24 * 30),
        app_token_ttl_minutes=_int_env("AUTH_CENTER_APP_TOKEN_TTL_MINUTES", 60),
        reset_ttl_minutes=_int_env("AUTH_CENTER_RESET_TTL_MINUTES", 30),
        base_url=os.getenv("AUTH_CENTER_BASE_URL", "http://127.0.0.1:8010").strip().rstrip("/"),
        mail_api_url=os.getenv("MAIL_API_URL", "https://mail.tigerzsh.com/api/send_mail").strip(),
        mail_api_token=os.getenv("MAIL_API_TOKEN", "").strip(),
        mail_from_name=os.getenv("MAIL_FROM_NAME", "grok@tigerzsh.com").strip() or "grok@tigerzsh.com",
        bootstrap_app_slug=os.getenv("BOOTSTRAP_APP_SLUG", "grok2api").strip() or "grok2api",
        bootstrap_app_name=os.getenv("BOOTSTRAP_APP_NAME", "Grok2API").strip() or "Grok2API",
    )


settings = get_settings()
