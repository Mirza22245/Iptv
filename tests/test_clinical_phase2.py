from __future__ import annotations

import os
from pathlib import Path

import asyncpg
import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to run PostgreSQL integration tests")


@pytest.fixture
async def clinical_connection():
    assert TEST_DATABASE_URL
    connection = await asyncpg.connect(TEST_DATABASE_URL)
    schema_name = "lydia_clinical_test"
    try:
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        await connection.execute(f'CREATE SCHEMA "{schema_name}"')
        await connection.execute(f'SET search_path TO "{schema_name}"')
        root = Path(__file__).parents[1]
        await connection.execute((root / "database/schema_v2.sql").read_text())
        await connection.execute((root / "database/phase2_clinical.sql").read_text())
        yield connection
    finally:
        await connection.execute("RESET search_path")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        await connection.close()


async def context(conn: asyncpg.Connection, clinic_id: int, user_id: int, role: str) -> None:
    await conn.execute(
        "SELECT set_config('lydia.current_clinic_id',$1,false), set_config('lydia.current_user_id',$2,false), set_config('lydia.current_role',$3,false)",
        str(clinic_id), str(user_id), role,
    )


@pytest.mark.asyncio
async def test_signed_journal_is_immutable(clinical_connection: asyncpg.Connection) -> None:
    conn = clinical_connection
    clinic = await conn.fetchval("INSERT INTO clinics(name) VALUES('Clinical') RETURNING id")
    await context(conn, clinic, 0, "admin")
    user = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,'staff@test','x','staff') RETURNING id", clinic)
    customer_user = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,'customer@test','x','customer') RETURNING id", clinic)
    customer = await conn.fetchval("INSERT INTO customers(clinic_id,user_id,first_name,last_name,email) VALUES($1,$2,'Test','Customer','customer@test') RETURNING id", clinic, customer_user)

    await context(conn, clinic, user, "staff")
    journal = await conn.fetchval("INSERT INTO journal_notes(clinic_id,customer_id,author_id,assessment) VALUES($1,$2,$3,'Original') RETURNING id", clinic, customer, user)
    await conn.execute("UPDATE journal_notes SET is_signed=true,signed_at=CURRENT_TIMESTAMP,signed_by_id=$1 WHERE id=$2", user, journal)

    with pytest.raises(asyncpg.exceptions.PostgresError) as update_error:
        await conn.execute("UPDATE journal_notes SET assessment='Tampered' WHERE id=$1", journal)
    assert update_error.value.sqlstate == "42501"

    with pytest.raises(asyncpg.exceptions.PostgresError) as delete_error:
        await conn.execute("DELETE FROM journal_notes WHERE id=$1", journal)
    assert delete_error.value.sqlstate == "42501"

    assert await conn.fetchval("SELECT assessment FROM journal_notes WHERE id=$1", journal) == "Original"


@pytest.mark.asyncio
async def test_clinical_records_are_tenant_isolated(clinical_connection: asyncpg.Connection) -> None:
    conn = clinical_connection
    clinic_a = await conn.fetchval("INSERT INTO clinics(name) VALUES('A') RETURNING id")
    clinic_b = await conn.fetchval("INSERT INTO clinics(name) VALUES('B') RETURNING id")

    await context(conn, clinic_a, 0, "admin")
    user_a = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,'a-staff@test','x','staff') RETURNING id", clinic_a)
    customer_a = await conn.fetchval("INSERT INTO customers(clinic_id,first_name,last_name,email) VALUES($1,'A','Customer','a@test') RETURNING id", clinic_a)
    await context(conn, clinic_b, 0, "admin")
    user_b = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,'b-staff@test','x','staff') RETURNING id", clinic_b)
    customer_b = await conn.fetchval("INSERT INTO customers(clinic_id,first_name,last_name,email) VALUES($1,'B','Customer','b@test') RETURNING id", clinic_b)

    await context(conn, clinic_a, user_a, "staff")
    await conn.execute("INSERT INTO journal_notes(clinic_id,customer_id,author_id,assessment) VALUES($1,$2,$3,'A')", clinic_a, customer_a, user_a)
    await context(conn, clinic_b, user_b, "staff")
    await conn.execute("INSERT INTO journal_notes(clinic_id,customer_id,author_id,assessment) VALUES($1,$2,$3,'B')", clinic_b, customer_b, user_b)

    rows = await conn.fetch("SELECT clinic_id,assessment FROM journal_notes ORDER BY id")
    assert rows == [{"clinic_id": clinic_b, "assessment": "B"}]
