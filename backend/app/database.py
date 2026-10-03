"""Lydia database pools and request-scoped RLS context."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg


DATABASE_URL = os.environ["DATABASE_URL"]
AUTH_DATABASE_URL = os.getenv("AUTH_DATABASE_URL", DATABASE_URL)


class Database:
    def __init__(self, dsn: str = DATABASE_URL, auth_dsn: str = AUTH_DATABASE_URL) -> None:
        self.dsn = dsn
        self.auth_dsn = auth_dsn
        self.pool: asyncpg.Pool | None = None
        self.auth_pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=1,
            max_size=int(os.getenv("DB_POOL_MAX", "10")),
            command_timeout=float(os.getenv("DB_COMMAND_TIMEOUT", "10")),
        )
        if self.auth_dsn == self.dsn:
            self.auth_pool = self.pool
        else:
            self.auth_pool = await asyncpg.create_pool(
                dsn=self.auth_dsn,
                min_size=1,
                max_size=int(os.getenv("AUTH_DB_POOL_MAX", "3")),
                command_timeout=float(os.getenv("DB_COMMAND_TIMEOUT", "10")),
            )

    async def close(self) -> None:
        if self.auth_pool is not None and self.auth_pool is not self.pool:
            await self.auth_pool.close()
        if self.pool is not None:
            await self.pool.close()
        self.pool = None
        self.auth_pool = None

    @asynccontextmanager
    async def transaction(
        self,
        *,
        clinic_id: int,
        user_id: int,
        role: str,
    ) -> AsyncIterator[asyncpg.Connection]:
        """Open a transaction and set tenant/RBAC context with SET LOCAL."""
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

    @asynccontextmanager
    async def auth_connection(self) -> AsyncIterator[asyncpg.Connection]:
        """Use the dedicated auth pool for pre-login identity lookup.

        In production AUTH_DATABASE_URL should point at a narrowly privileged
        auth role that can read/update only identity data. Keeping this path
        separate avoids weakening the RLS-protected runtime connection just to
        perform a pre-authentication lookup.
        """
        if self.auth_pool is None:
            raise RuntimeError("Auth database pool is not connected")
        async with self.auth_pool.acquire() as connection:
            yield connection


_db = Database()


async def get_database() -> Database:
    return _db


async def startup_database() -> None:
    await _db.connect()


async def shutdown_database() -> None:
    await _db.close()
