"""Customer registration and login endpoints."""

from __future__ import annotations

import re
from typing import Any

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import create_access_token
from app.database import Database, get_database

router = APIRouter(prefix="/api/auth", tags=["Auth"])


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    # EmailStr intentionally rejects special-use domains such as .local.
    # Lydia's local development environment uses lydia.local addresses, so
    # validate the shape here while still accepting those development emails.
    if not _EMAIL_RE.fullmatch(email):
        raise ValueError("Enter a valid email address")
    return email


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinic_id: int = Field(gt=0)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_customer(
    payload: RegisterRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if db.pool is None:
        raise HTTPException(status_code=503, detail="database_not_ready")

    password_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()

    # Registration is a controlled provisioning operation. It establishes a
    # tenant context before touching RLS-protected identity/customer tables.
    async with db.transaction(clinic_id=payload.clinic_id, user_id=0, role="admin") as conn:
        clinic_exists = await conn.fetchval(
            "SELECT 1 FROM clinics WHERE id = $1", payload.clinic_id
        )
        if clinic_exists is None:
            raise HTTPException(status_code=404, detail="Clinic not found")

        try:
            user_id = await conn.fetchval(
                """
                INSERT INTO users (clinic_id, email, password_hash, role, is_active)
                VALUES ($1, $2, $3, 'customer', TRUE)
                RETURNING id
                """,
                payload.clinic_id, payload.email,
            )
        except asyncpg.exceptions.UniqueViolationError as exc:
            raise HTTPException(status_code=409, detail="Email already registered") from exc

        customer_id = await conn.fetchval(
            """
            INSERT INTO customers (clinic_id, user_id, first_name, last_name, email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            payload.clinic_id, user_id, payload.first_name.strip(),
            payload.last_name.strip(), payload.email,
        )

    return {"success": True, "user_id": int(user_id), "customer_id": int(customer_id)}


@router.post("/login")
async def login(
    payload: LoginRequest,
    db: Database = Depends(get_database),
) -> dict[str, str]:
    if db.pool is None:
        raise HTTPException(status_code=503, detail="database_not_ready")

    # Pre-authentication has no tenant context yet. The exact email is bound
    # transaction-locally so RLS permits only that single identity row.
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('lydia.login_email', $1, true)",
                payload.email,
            )
            user = await conn.fetchrow(
                """
                SELECT id, clinic_id, password_hash, role, is_active
                FROM users
                WHERE lower(email) = lower($1)
                """,
                payload.email,
            )

    if user is None or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not bcrypt.checkpw(payload.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "sub": str(user["id"]),
        "clinic_id": int(user["clinic_id"]),
        "role": user["role"],
    })
    return {"access_token": token, "token_type": "bearer"}
