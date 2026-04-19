from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from .config import settings


def is_mail_enabled() -> bool:
    return bool(settings.mail_api_url and settings.mail_api_token)


def _post_mail(payload: dict) -> None:
    if not is_mail_enabled():
        raise ValueError("MAIL_API_TOKEN is not configured")
    request = urllib.request.Request(
        settings.mail_api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.mail_api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "python-urllib/3.11",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status != 200:
                raise ValueError(f"mail api http {response.status}: {body}")
            data = json.loads(body or "{}")
            if str(data.get("status") or "").lower() != "ok":
                raise ValueError(f"mail api error: {body}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"mail api http {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"mail api url error: {exc.reason}") from exc


async def send_mail(
    *,
    to_mail: str,
    subject: str,
    content: str,
    is_html: bool = False,
    to_name: str = "",
) -> None:
    await asyncio.to_thread(
        _post_mail,
        {
            "from_name": settings.mail_from_name,
            "to_mail": to_mail,
            "to_name": to_name,
            "subject": subject,
            "content": content,
            "is_html": is_html,
        },
    )
