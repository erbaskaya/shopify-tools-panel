import hmac
import hashlib

from fastapi import Request
from fastapi.responses import Response

from core.config import settings


def make_session_token():
    secret = settings.SECRET_KEY.encode("utf-8")
    msg = b"shopify-tools-panel-auth"
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def is_logged_in(request: Request):
    cookie_value = request.cookies.get("panel_session")
    expected = make_session_token()
    return bool(cookie_value and hmac.compare_digest(cookie_value, expected))


def set_login_cookie(response: Response):
    response.set_cookie(
        "panel_session",
        make_session_token(),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=60 * 60 * 12,
    )


def clear_login_cookie(response: Response):
    response.delete_cookie("panel_session")
