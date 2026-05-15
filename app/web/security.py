"""Cookie + CSRF helpers for FastAPI."""

from __future__ import annotations

import hmac
import secrets

from fastapi import Request

from app.config import Settings

AUTH_COOKIE = "auth_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def cookie_kwargs(settings: Settings) -> dict[str, object]:
    """Return safe defaults for `response.set_cookie`."""
    return {
        "httponly": True,
        "secure": settings.is_production,
        "samesite": "lax",
        "max_age": settings.jwt_ttl_days * 24 * 3600,
        "path": "/",
    }


def issue_csrf_token() -> str:
    """Generate a fresh CSRF token (cryptographically random)."""
    return secrets.token_urlsafe(32)


def verify_csrf(request: Request) -> bool:
    """Double-submit cookie check.

    On any state-changing request the client must send the value of the
    `csrf_token` cookie back in the `X-CSRF-Token` header. Both must match.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    cookie_value = request.cookies.get(CSRF_COOKIE, "")
    header_value = request.headers.get(CSRF_HEADER, "")
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)
