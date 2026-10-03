from __future__ import annotations

import os
from pathlib import Path

import asyncpg
import pytest


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to run PostgreSQL integration tests",
)


@pytest.fixture
async def database_connection():
    assert TEST_DATABASE_URL is not None
    connection = await asyncpg.connect(TEST_DATABASE_URL)
    schema_name = "lydia_test"

    try:
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        await connection.execute(f'CREATE SCHEMA "{schema_name}"')
        # Keep tests isolated from any pre-existing public tables.
        await connection.execute(f'SET search_path TO "{schema_name}"')

        schema_sql = Path(__file__).parents[1].joinpath("database", "schema_v2.sql").read_text()
        await connection.execute(schema_sql)
        yield connection
    finally:
        await connection.execute("RESET search_path")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        await connection.close()


async def set_admin_context(conn: asyncpg.Connection, clinic_id: int) -> None:
    await conn.execute(
        "SELECT set_config('lydia.current_clinic_id', $1, false), "
        "set_config('lydia.current_user_id', '0', false), "
        "set_config('lydia.current_role', 'admin', false)",
        str(clinic_id),
    )


@pytest.mark.asyncio
async def test_overlapping_staff_bookings_are_rejected(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_id = await conn.fetchval("INSERT INTO clinics (name) VALUES ('Test Clinic') RETURNING id")
    await set_admin_context(conn, clinic_id)
    customer_user_id = await conn.fetchval("INSERT INTO users (clinic_id, email, password_hash, role) VALUES ($1, 'customer@example.test', 'not-a-real-password', 'customer') RETURNING id", clinic_id)
    staff_user_id = await conn.fetchval("INSERT INTO users (clinic_id, email, password_hash, role) VALUES ($1, 'staff@example.test', 'not-a-real-password', 'staff') RETURNING id", clinic_id)
    customer_id = await conn.fetchval("INSERT INTO customers (clinic_id, user_id, first_name, last_name, email) VALUES ($1, $2, 'Test', 'Customer', 'customer@example.test') RETURNING id", clinic_id, customer_user_id)
    staff_id = await conn.fetchval("INSERT INTO staff (clinic_id, user_id, display_name) VALUES ($1, $2, 'Test Staff') RETURNING id", clinic_id, staff_user_id)
    service_id = await conn.fetchval("INSERT INTO services (clinic_id, name, price, duration_minutes) VALUES ($1, 'Test Service', 100.00, 60) RETURNING id", clinic_id)
    await conn.execute("INSERT INTO bookings (clinic_id, customer_id, service_id, staff_id, slot_range) VALUES ($1, $2, $3, $4, tstzrange($5, $6, '[)'))", clinic_id, customer_id, service_id, staff_id, "2026-07-01T10:00:00+00:00", "2026-07-01T11:00:00+00:00")
    with pytest.raises(asyncpg.exceptions.ExclusionViolationError):
        await conn.execute("INSERT INTO bookings (clinic_id, customer_id, service_id, staff_id, slot_range) VALUES ($1, $2, $3, $4, tstzrange($5, $6, '[)'))", clinic_id, customer_id, service_id, staff_id, "2026-07-01T10:30:00+00:00", "2026-07-01T11:30:00+00:00")


@pytest.mark.asyncio
async def test_adjacent_staff_bookings_are_allowed(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_id = await conn.fetchval("INSERT INTO clinics (name) VALUES ('Adjacent') RETURNING id")
    await set_admin_context(conn, clinic_id)
    customer_user_id = await conn.fetchval("INSERT INTO users (clinic_id, email, password_hash, role) VALUES ($1, 'c@example.test', 'x', 'customer') RETURNING id", clinic_id)
    staff_user_id = await conn.fetchval("INSERT INTO users (clinic_id, email, password_hash, role) VALUES ($1, 's@example.test', 'x', 'staff') RETURNING id", clinic_id)
    customer_id = await conn.fetchval("INSERT INTO customers (clinic_id, user_id, first_name, last_name, email) VALUES ($1, $2, 'A', 'B', 'c@example.test') RETURNING id", clinic_id, customer_user_id)
    staff_id = await conn.fetchval("INSERT INTO staff (clinic_id, user_id, display_name) VALUES ($1, $2, 'S') RETURNING id", clinic_id, staff_user_id)
    service_id = await conn.fetchval("INSERT INTO services (clinic_id, name, price, duration_minutes) VALUES ($1, 'S', 50, 30) RETURNING id", clinic_id)
    for start, end in [("2026-07-01T10:00:00+00:00", "2026-07-01T10:30:00+00:00"), ("2026-07-01T10:30:00+00:00", "2026-07-01T11:00:00+00:00")]:
        await conn.execute("INSERT INTO bookings (clinic_id, customer_id, service_id, staff_id, slot_range) VALUES ($1, $2, $3, $4, tstzrange($5, $6, '[)'))", clinic_id, customer_id, service_id, staff_id, start, end)
