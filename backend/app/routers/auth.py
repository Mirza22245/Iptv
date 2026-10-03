"""Customer registration and login endpoints."""

from __future__ import annotations

from typing import Any

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.auth import create_access_token
from app.database import Database, get_database

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinic_id: int = Field(gt=0)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_customer(
    payload: RegisterRequest,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    if db.pool is None:
        raise HTTPException(status_code=503, detail="database_not_ready")

    password_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()

    async with db.pool.acquire() as conn:
        async with conn.transaction():
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
                    payload.clinic_id, str(payload.email).lower(), password_hash,
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
                payload.last_name.strip(), str(payload.email).lower(),
            )

    return {"success": True, "user_id": int(user_id), "customer_id": int(customer_id)}


@router.post("/login")
async def login(
    payload: LoginRequest,
    db: Database = Depends(get_database),
) -> dict[str, str]:
    if db.pool is None:
        raise HTTPException(status_code=503, detail="database_not_ready")

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            """
            SELECT id, clinic_id, password_hash, role, is_active
            FROM users
            WHERE lower(email) = lower($1)
            """,
            str(payload.email),
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
