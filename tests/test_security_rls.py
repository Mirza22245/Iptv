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
        await connection.execute(f'SET search_path TO "{schema_name}"')
        root = Path(__file__).parents[1] / "database"
        await connection.execute((root / "schema_v2.sql").read_text())
        await connection.execute((root / "phase2_clinical.sql").read_text())
        yield connection
    finally:
        await connection.execute("RESET search_path")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        await connection.close()


async def set_context(conn: asyncpg.Connection, *, clinic_id: int | None, user_id: int | None, role: str | None) -> None:
    values = {
        "lydia.current_clinic_id": "" if clinic_id is None else str(clinic_id),
        "lydia.current_user_id": "" if user_id is None else str(user_id),
        "lydia.current_role": "" if role is None else role,
    }
    await conn.execute(
        "SELECT set_config('lydia.current_clinic_id', $1, false), set_config('lydia.current_user_id', $2, false), set_config('lydia.current_role', $3, false)",
        values["lydia.current_clinic_id"], values["lydia.current_user_id"], values["lydia.current_role"],
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
    insert_sql = "INSERT INTO bookings (clinic_id,customer_id,service_id,staff_id,slot_range) VALUES ($1,$2,$3,$4,tstzrange($5::text::timestamptz,$6::text::timestamptz,'[)'))"
    await set_context(conn, clinic_id=clinic_a, user_id=0, role="admin")
    await conn.execute(insert_sql, clinic_a, customer_a, service_a, staff_a, "2026-08-01T10:00:00+00:00", "2026-08-01T10:30:00+00:00")
    await conn.execute(insert_sql, clinic_a, customer_a2, service_a, staff_a, "2026-08-01T11:00:00+00:00", "2026-08-01T11:30:00+00:00")
    await set_context(conn, clinic_id=clinic_b, user_id=0, role="admin")
    await conn.execute(insert_sql, clinic_b, customer_b, service_b, staff_b, "2026-08-01T10:00:00+00:00", "2026-08-01T10:30:00+00:00")
    await set_context(conn, clinic_id=clinic_a, user_id=user_a, role="customer")
    assert [row["customer_id"] for row in await conn.fetch("SELECT customer_id FROM bookings ORDER BY id")] == [customer_a]
    await set_context(conn, clinic_id=clinic_a, user_id=staff_a_user, role="staff")
    assert [row["customer_id"] for row in await conn.fetch("SELECT customer_id FROM bookings ORDER BY id")] == [customer_a, customer_a2]
    await set_context(conn, clinic_id=clinic_b, user_id=staff_b_user, role="staff")
    assert [row["clinic_id"] for row in await conn.fetch("SELECT clinic_id FROM bookings")] == [clinic_b]


@pytest.mark.asyncio
async def test_missing_rls_context_returns_no_rows(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_id = await conn.fetchval("INSERT INTO clinics (name) VALUES ('Context') RETURNING id")
    await set_context(conn, clinic_id=clinic_id, user_id=0, role="admin")
    user_id = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'ctx@test','x','customer') RETURNING id", clinic_id)
    await conn.fetchval("INSERT INTO customers (clinic_id,user_id,first_name,last_name,email) VALUES ($1,$2,'C','T','ctx@test') RETURNING id", clinic_id, user_id)
    await set_context(conn, clinic_id=None, user_id=None, role=None)
    assert await conn.fetchval("SELECT COUNT(*) FROM customers") == 0


@pytest.mark.asyncio
async def test_audit_update_and_delete_are_blocked(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_id = await conn.fetchval("INSERT INTO clinics (name) VALUES ('Audit') RETURNING id")
    await set_context(conn, clinic_id=clinic_id, user_id=0, role="admin")
    admin_id = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'admin@test','x','admin') RETURNING id", clinic_id)
    await set_context(conn, clinic_id=clinic_id, user_id=admin_id, role="admin")
    audit_id = await conn.fetchval("INSERT INTO audit_logs (clinic_id,action,target_type,target_id,new_values) VALUES ($1,'TEST','booking',1,'{}') RETURNING id", clinic_id)
    with pytest.raises(asyncpg.exceptions.PostgresError) as update_error:
        await conn.execute("UPDATE audit_logs SET action='TAMPERED' WHERE id=$1", audit_id)
    assert update_error.value.sqlstate == "42501"
    with pytest.raises(asyncpg.exceptions.PostgresError) as delete_error:
        await conn.execute("DELETE FROM audit_logs WHERE id=$1", audit_id)
    assert delete_error.value.sqlstate == "42501"
    assert await conn.fetchval("SELECT action FROM audit_logs WHERE id=$1", audit_id) == "TEST"


async def _create_clinical_fixture(conn: asyncpg.Connection) -> tuple[int, int, int, int, int]:
    clinic_id = await conn.fetchval("INSERT INTO clinics (name) VALUES ('Clinical') RETURNING id")
    await set_context(conn, clinic_id=clinic_id, user_id=0, role="admin")
    admin_id = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'clinical-admin@test','x','admin') RETURNING id", clinic_id)
    staff_id = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'clinical-staff@test','x','staff') RETURNING id", clinic_id)
    customer_user_id = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'clinical-customer@test','x','customer') RETURNING id", clinic_id)
    customer_id = await conn.fetchval("INSERT INTO customers (clinic_id,user_id,first_name,last_name,email) VALUES ($1,$2,'Clinical','Customer','clinical-customer@test') RETURNING id", clinic_id, customer_user_id)
    await set_context(conn, clinic_id=clinic_id, user_id=staff_id, role="staff")
    journal_id = await conn.fetchval("INSERT INTO journal_notes (clinic_id,customer_id,author_id,assessment) VALUES ($1,$2,$3,'Original') RETURNING id", clinic_id, customer_id, staff_id)
    return clinic_id, admin_id, staff_id, customer_user_id, journal_id


@pytest.mark.asyncio
async def test_clinical_tenant_isolation_and_customer_read_scope(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_a, _, staff_a, customer_user_a, journal_a = await _create_clinical_fixture(conn)
    clinic_b = await conn.fetchval("INSERT INTO clinics (name) VALUES ('Other Clinical') RETURNING id")
    await set_context(conn, clinic_id=clinic_b, user_id=0, role="admin")
    staff_b = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'other-staff@test','x','staff') RETURNING id", clinic_b)
    customer_b_user = await conn.fetchval("INSERT INTO users (clinic_id,email,password_hash,role) VALUES ($1,'other-customer@test','x','customer') RETURNING id", clinic_b)
    customer_b = await conn.fetchval("INSERT INTO customers (clinic_id,user_id,first_name,last_name,email) VALUES ($1,$2,'Other','Customer','other-customer@test') RETURNING id", clinic_b, customer_b_user)
    await set_context(conn, clinic_id=clinic_b, user_id=staff_b, role="staff")
    journal_b = await conn.fetchval("INSERT INTO journal_notes (clinic_id,customer_id,author_id,assessment) VALUES ($1,$2,$3,'Other') RETURNING id", clinic_b, customer_b, staff_b)
    assert await conn.fetchval("SELECT COUNT(*) FROM journal_notes") == 1
    assert await conn.fetchval("SELECT id FROM journal_notes") == journal_b
    await set_context(conn, clinic_id=clinic_a, user_id=customer_user_a, role="customer")
    assert await conn.fetchval("SELECT id FROM journal_notes") == journal_a


@pytest.mark.asyncio
async def test_signed_journal_cannot_be_updated_or_deleted(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_id, admin_id, staff_id, _, journal_id = await _create_clinical_fixture(conn)
    await set_context(conn, clinic_id=clinic_id, user_id=staff_id, role="staff")
    await conn.execute("UPDATE journal_notes SET is_signed=TRUE, signed_at=CURRENT_TIMESTAMP, signed_by_id=$1 WHERE id=$2", staff_id, journal_id)
    with pytest.raises(asyncpg.exceptions.PostgresError):
        await conn.execute("UPDATE journal_notes SET assessment='Tampered' WHERE id=$1", journal_id)
    with pytest.raises(asyncpg.exceptions.PostgresError):
        await conn.execute("DELETE FROM journal_notes WHERE id=$1", journal_id)
    assert await conn.fetchval("SELECT assessment FROM journal_notes WHERE id=$1", journal_id) == "Original"
    await set_context(conn, clinic_id=clinic_id, user_id=admin_id, role="admin")
    with pytest.raises(asyncpg.exceptions.PostgresError):
        await conn.execute("DELETE FROM journal_notes WHERE id=$1", journal_id)
    assert await conn.fetchval("SELECT COUNT(*) FROM journal_notes WHERE id=$1", journal_id) == 1


@pytest.mark.asyncio
async def test_customer_cannot_insert_or_modify_clinical_records(database_connection: asyncpg.Connection) -> None:
    conn = database_connection
    clinic_id, _, staff_id, customer_user_id, journal_id = await _create_clinical_fixture(conn)
    customer_id = await conn.fetchval("SELECT customer_id FROM journal_notes WHERE id=$1", journal_id)
    await set_context(conn, clinic_id=clinic_id, user_id=customer_user_id, role="customer")
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await conn.execute("INSERT INTO journal_notes (clinic_id,customer_id,author_id,assessment) VALUES ($1,$2,$3,'Nope')", clinic_id, customer_id, customer_user_id)
    assert await conn.execute("UPDATE journal_notes SET assessment='Nope' WHERE id=$1", journal_id) == "UPDATE 0"
    assert await conn.fetchval("SELECT assessment FROM journal_notes WHERE id=$1", journal_id) == "Original"
