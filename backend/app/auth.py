"""JWT authentication and role authorization for Lydia Core."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "60"))

security = HTTPBearer(auto_error=True)


def _require_secret() -> str:
    if not SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is required")
    return SECRET_KEY


def create_access_token(data: dict[str, Any], *, expires_minutes: int | None = None) -> str:
    """Create a signed access token. Callers must provide sub, clinic_id and role."""
    required = {"sub", "clinic_id", "role"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"Missing token claims: {', '.join(sorted(missing))}")

    now = datetime.now(timezone.utc)
    expire = now + timedelta(
        minutes=expires_minutes if expires_minutes is not None else ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {**data, "iat": now, "exp": expire}
    return jwt.encode(payload, _require_secret(), algorithm=ALGORITHM)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            credentials.credentials,
            _require_secret(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "clinic_id", "role", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (jwt.InvalidTokenError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        payload["sub"] = int(payload["sub"])
        payload["clinic_id"] = int(payload["clinic_id"])
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("role") not in {"customer", "staff", "admin", "superadmin"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token role",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_role(*required_roles: str) -> Callable[..., dict[str, Any]]:
    """Require one of the supplied roles; superadmin is allowed everywhere."""
    allowed = set(required_roles)

    def role_dependency(payload: dict[str, Any] = Depends(verify_token)) -> dict[str, Any]:
        if payload.get("role") not in allowed and payload.get("role") != "superadmin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: requires role {sorted(allowed)}",
            )
        return payload

    return role_dependency
