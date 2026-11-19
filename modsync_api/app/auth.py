"""Token authentication helpers and FastAPI dependencies."""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status

from .config import Settings
from .deps import get_settings

BEARER_PREFIX = "bearer "


def extract_bearer_token(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith(BEARER_PREFIX):
        return authorization[len(BEARER_PREFIX) :].strip()
    return ""


def tokens_match(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def verify_http_token(
    provided: str | None,
    expected: str,
    *,
    missing_detail: str,
    invalid_detail: str,
    www_authenticate: str | None = None,
) -> None:
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=missing_detail,
        )
    if not tokens_match(provided, expected):
        headers = {"WWW-Authenticate": www_authenticate} if www_authenticate else None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=invalid_detail,
            headers=headers,
        )


def require_client_auth(
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(default=None),
) -> None:
    verify_http_token(
        extract_bearer_token(authorization),
        settings.client_token,
        missing_detail="MODSYNC_CLIENT_TOKEN must be configured",
        invalid_detail="Invalid or missing client token",
        www_authenticate="Bearer",
    )


def require_admin_auth(
    settings: Settings = Depends(get_settings),
    x_admin_token: str | None = Header(default=None),
) -> None:
    verify_http_token(
        x_admin_token,
        settings.admin_token,
        missing_detail="MODSYNC_ADMIN_TOKEN must be configured to use /api/reload",
        invalid_detail="Invalid or missing X-Admin-Token",
    )
