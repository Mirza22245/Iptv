from __future__ import annotations

import os
from pathlib import Path

import asyncpg
import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to run PostgreSQL security integration tests",
)


@pytest.fixture
async def database_connection():
    assert TEST_DATABASE_URL is not None
    connection = await asyncpg.connect(TEST_DATABASE_URL)
    schema_name = "lydia_security_test"
    try:
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        await connection.execute(f'CREATE SCHEMA "{schema_name}"')
        # schema_v2.sql uses CREATE TABLE IF NOT EXISTS. Keep public out of the
        # search path so tests cannot accidentally reuse production tables.
        await connection.execute(f'SET search_path TO "{schema_name}"')
        schema_sql = Path(__file__).parents[1].joinpath("database", "schema_v2.sql").read_text()
        await connection.execute(schema_sql)
        yield connection
    finally:
        await connection.execute("RESET search_path")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        await connection.close()


async def set_context(conn: asyncpg.Connection, *, clinic_id: int, user_id: int, role: str) -> None:
    await conn.execute(
        "SELECT set_config('lydia.current_clinic_id', $1, false), "
        "set_config('lydia.current_user_id', $2, false), "
        "set_config('lydia.current_role', $3, false)",
        str(clinic_id), str(user_id), role,
    )


@pytest.mark.asyncio
async def test_customer_isolated_from_other_customer_and_tenant(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_a = await conn.fetchval("INSERT INTO clinics (name) VALUES ('A') RETURNING id")
    clinic_b = await conn.fetchval("INSERT INTO clinics (name) VALUES ('B') RETURNING id")
    await set_context(conn, clinic_id=clinic_a, user_id=0, role="admin")
    user_a = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'a@test','x','customer') RETURNING id", clinic_a)
    user_a2 = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'a2@test','x','customer') RETURNING id", clinic_a)
    customer_a = await conn.fetchval("INSERT INTO customers (clinic_id,user_id,first_name,last_name,email) VALUES ($1,$2,'A','One','a@test') RETURNING id", clinic_a, user_a)
    customer_a2 = await conn.fetchval("INSERT INTO customers (clinic_id,user_id,first_name,last_name,email) VALUES ($1,$2,'A','Two','a2@test') RETURNING id", clinic_a, user_a2)
    service_a = await conn.fetchval("INSERT INTO services (clinic_id,name,price,duration_minutes) VALUES ($1,'A service',100,30) RETURNING id", clinic_a)
    staff_a_user = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'staff-a@test','x','staff') RETURNING id", clinic_a)
    staff_a = await conn.fetchval("INSERT INTO staff (clinic_id,user_id,display_name) VALUES ($1,$2,'Staff A') RETURNING id", clinic_a, staff_a_user)
    await set_context(conn, clinic_id=clinic_b, user_id=0, role="admin")
    user_b = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'b@test','x','customer') RETURNING id", clinic_b)
    customer_b = await conn.fetchval("INSERT INTO customers (clinic_id,user_id,first_name,last_name,email) VALUES ($1,$2,'B','One','b@test') RETURNING id", clinic_b, user_b)
    service_b = await conn.fetchval("INSERT INTO services (clinic_id,name,price,duration_minutes) VALUES ($1,'B service',200,30) RETURNING id", clinic_b)
    staff_b_user = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'staff-b@test','x','staff') RETURNING id", clinic_b)
    staff_b = await conn.fetchval("INSERT INTO staff (clinic_id,user_id,display_name) VALUES ($1,$2,'Staff B') RETURNING id", clinic_b, staff_b_user)
    insert_sql = "INSERT INTO bookings (clinic_id,customer_id,service_id,staff_id,slot_range) VALUES ($1,$2,$3,$4,tstzrange($5,$6,'[)'))"
    await set_context(conn, clinic_id=clinic_a, user_id=0, role="admin")
    await conn.execute(insert_sql, clinic_a, customer_a, service_a, staff_a, "2026-08-01T10:00:00+00:00", "2026-08-01T10:30:00+00:00")
    await conn.execute(insert_sql, clinic_a, customer_a2, service_a, staff_a, "2026-08-01T11:00:00+00:00", "2026-08-01T11:30:00+00:00")
    await set_context(conn, clinic_id=clinic_b, user_id=0, role="admin")
    await conn.execute(insert_sql, clinic_b, customer_b, service_b, staff_b, "2026-08-01T10:00:00+00:00", "2026-08-01T10:30:00+00:00")
    await set_context(conn, clinic_id=clinic_a, user_id=user_a, role="customer")
    visible = await conn.fetch("SELECT customer_id FROM bookings ORDER BY id")
    assert [row["customer_id"] for row in visible] == [customer_a]
    await set_context(conn, clinic_id=clinic_a, user_id=staff_a_user, role="staff")
    staff_visible = await conn.fetch("SELECT customer_id FROM bookings ORDER BY id")
    assert [row["customer_id"] for row in staff_visible] == [customer_a, customer_a2]
    await set_context(conn, clinic_id=clinic_b, user_id=staff_b_user, role="staff")
    tenant_visible = await conn.fetch("SELECT clinic_id FROM bookings")
    assert [row["clinic_id"] for row in tenant_visible] == [clinic_b]


@pytest.mark.asyncio
async def test_missing_rls_context_returns_no_rows(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_id = await conn.fetchval("INSERT INTO clinics (name) VALUES ('Context') RETURNING id")
    await set_context(conn, clinic_id=clinic_id, user_id=0, role="admin")
    user_id = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'ctx@test','x','customer') RETURNING id", clinic_id)
    await conn.fetchval("INSERT INTO customers (clinic_id,user_id,first_name,last_name,email) VALUES ($1,$2,'C','T','ctx@test') RETURNING id", clinic_id, user_id)
    await conn.execute("SELECT set_config('lydia.current_clinic_id', '', false)")
    await conn.execute("SELECT set_config('lydia.current_user_id', '', false)")
    await conn.execute("SELECT set_config('lydia.current_role', '', false)")
    assert await conn.fetchval("SELECT COUNT(*) FROM customers") == 0


@pytest.mark.asyncio
async def test_audit_update_and_delete_are_blocked(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_id = await conn.fetchval("INSERT INTO clinics (name) VALUES ('Audit') RETURNING id")
    admin_id = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'admin@test','x','admin') RETURNING id", clinic_id)
    await set_context(conn, clinic_id=clinic_id, user_id=admin_id, role="admin")
    audit_id = await conn.fetchval("INSERT INTO audit_logs (clinic_id,action,target_type,target_id,new_values) VALUES ($1,'TEST','booking',1,'{}') RETURNING id", clinic_id)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await conn.execute("UPDATE audit_logs SET action='TAMPERED' WHERE id=$1", audit_id)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await conn.execute("DELETE FROM audit_logs WHERE id=$1", audit_id)
    assert await conn.fetchval("SELECT action FROM audit_logs WHERE id=$1", audit_id) == "TEST"
