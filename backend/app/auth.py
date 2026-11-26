"""Optional HTTP Basic Authentication for public deployment.

When AUTH_USERNAME and AUTH_PASSWORD are both set in the environment, every
request to a protected endpoint must include valid HTTP Basic credentials.
When neither is configured and REQUIRE_AUTH is false, authentication is disabled
for local development. If REQUIRE_AUTH is true or only one credential variable is
set, protected endpoints fail closed with HTTP 503.

Health-check endpoints (/health, /health/database) remain unauthenticated.
"""

import secrets

from fastapi import Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from backend.app.config import Settings, get_settings
from backend.app.errors import ApiError

_security = HTTPBasic(auto_error=False)
_BASIC_CHALLENGE_HEADER = {"WWW-Authenticate": 'Basic realm="Code-Mixed Lecture Notes"'}


def _secret_value(secret: object) -> str:
    if secret is None:
        return ""
    return secret.get_secret_value().strip()


def auth_is_configured(settings: Settings) -> bool:
    """Return True when both AUTH_USERNAME and AUTH_PASSWORD are non-empty."""
    return bool(_secret_value(settings.auth_username) and _secret_value(settings.auth_password))


def auth_is_misconfigured(settings: Settings) -> bool:
    """Return True when auth configuration is partial or missing while required."""
    has_user = bool(_secret_value(settings.auth_username))
    has_password = bool(_secret_value(settings.auth_password))
    if has_user != has_password:
        return True
    return settings.require_auth and not (has_user and has_password)


def require_auth(
    credentials: HTTPBasicCredentials | None = Depends(_security),
    settings: Settings = Depends(get_settings),
) -> None:
    """Enforce HTTP Basic Auth when configured or required for public deployment."""
    if auth_is_misconfigured(settings):
        raise ApiError(
            503,
            "auth_misconfigured",
            "Public access control is enabled but not fully configured.",
        )

    if not auth_is_configured(settings):
        return

    if credentials is None:
        raise ApiError(
            401,
            "authentication_required",
            "Authentication is required.",
            headers=_BASIC_CHALLENGE_HEADER,
        )

    username_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        _secret_value(settings.auth_username).encode("utf-8"),
    )
    password_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        _secret_value(settings.auth_password).encode("utf-8"),
    )
    if not (username_ok and password_ok):
        raise ApiError(
            401,
            "authentication_failed",
            "Invalid credentials.",
            headers=_BASIC_CHALLENGE_HEADER,
        )
