from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


PASSWORD_ITERATIONS = 600_000


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_b64_encode(salt)}${_b64_encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations_s, salt_s, digest_s = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            _b64_decode(salt_s),
            int(iterations_s),
        )
        return hmac.compare_digest(digest, _b64_decode(digest_s))
    except Exception:
        return False


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    body = _b64_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64_encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_signed_token(token: str, secret: str) -> dict[str, Any] | None:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = _b64_encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64_decode(body))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def now_ts() -> int:
    return int(time.time())
