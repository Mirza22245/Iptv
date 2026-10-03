from __future__ import annotations

import os

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from app.auth import create_access_token, verify_token


def test_create_and_verify_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    token = create_access_token({"sub": 42, "clinic_id": 7, "role": "customer"})

    payload = verify_token(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )

    assert payload["sub"] == 42
    assert payload["clinic_id"] == 7
    assert payload["role"] == "customer"


def test_expired_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    token = jwt.encode(
        {"sub": 42, "clinic_id": 7, "role": "customer", "exp": 0},
        "test-secret",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))

    assert exc_info.value.status_code == 401
