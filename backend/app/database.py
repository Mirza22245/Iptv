"""Lydia database connection and request-scoped RLS context."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg


DATABASE_URL = os.environ["DATABASE_URL"]


class Database:
    def __init__(self, dsn: str = DATABASE_URL) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=1,
            max_size=int(os.getenv("DB_POOL_MAX", "10")),
            command_timeout=float(os.getenv("DB_COMMAND_TIMEOUT", "10")),
        )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    @asynccontextmanager
    async def transaction(
        self,
        *,
        clinic_id: int,
        user_id: int,
        role: str,
    ) -> AsyncIterator[asyncpg.Connection]:
        """Open a transaction and set tenant/RBAC context with SET LOCAL.

        RLS context is transaction-local so a pooled connection cannot leak
        one request's tenant/user identity into the next request.
        """
        if self.pool is None:
            raise RuntimeError("Database pool is not connected")

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('lydia.current_clinic_id', $1, true)",
                    str(clinic_id),
                )
                await connection.execute(
                    "SELECT set_config('lydia.current_user_id', $1, true)",
                    str(user_id),
                )
                await connection.execute(
                    "SELECT set_config('lydia.current_role', $1, true)",
                    role,
                )
                yield connection

    @asynccontextmanager
    async def healthcheck(self) -> AsyncIterator[asyncpg.Connection]:
        if self.pool is None:
            raise RuntimeError("Database pool is not connected")
        async with self.pool.acquire() as connection:
            yield connection


_db = Database()


async def get_database() -> Database:
    return _db


async def startup_database() -> None:
    await _db.connect()


async def shutdown_database() -> None:
    await _db.close()
