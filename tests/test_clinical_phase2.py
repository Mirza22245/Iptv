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


async def context(conn: asyncpg.Connection, clinic_id: int | None, user_id: int | None, role: str | None) -> None:
    await conn.execute(
        "SELECT set_config('lydia.current_clinic_id',$1,false), set_config('lydia.current_user_id',$2,false), set_config('lydia.current_role',$3,false)",
        "" if clinic_id is None else str(clinic_id),
        "" if user_id is None else str(user_id),
        "" if role is None else role,
    )


async def make_clinic(conn: asyncpg.Connection, name: str):
    clinic = await conn.fetchval("INSERT INTO clinics(name) VALUES($1) RETURNING id", name)
    await context(conn, clinic, 0, "admin")
    staff = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','staff') RETURNING id", clinic, f"staff-{clinic}@test")
    customer_user = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','customer') RETURNING id", clinic, f"customer-{clinic}@test")
    customer = await conn.fetchval("INSERT INTO customers(clinic_id,user_id,first_name,last_name,email) VALUES($1,$2,'Test','Customer',$3) RETURNING id", clinic, customer_user, f"customer-{clinic}@test")
    return clinic, staff, customer_user, customer


@pytest.mark.asyncio
async def test_signed_journal_is_immutable(clinical_connection: asyncpg.Connection) -> None:
    conn = clinical_connection
    clinic, user, _, customer = await make_clinic(conn, "Clinical")
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
    clinic_a, user_a, _, customer_a = await make_clinic(conn, "A")
    clinic_b, user_b, _, customer_b = await make_clinic(conn, "B")

    await context(conn, clinic_a, user_a, "staff")
    await conn.execute("INSERT INTO journal_notes(clinic_id,customer_id,author_id,assessment) VALUES($1,$2,$3,'A')", clinic_a, customer_a, user_a)
    await context(conn, clinic_b, user_b, "staff")
    await conn.execute("INSERT INTO journal_notes(clinic_id,customer_id,author_id,assessment) VALUES($1,$2,$3,'B')", clinic_b, customer_b, user_b)

    rows = await conn.fetch("SELECT clinic_id,assessment FROM journal_notes ORDER BY id")
    assert [(row["clinic_id"], row["assessment"]) for row in rows] == [(clinic_b, "B")]


@pytest.mark.asyncio
async def test_missing_context_hides_phase2_records(clinical_connection: asyncpg.Connection) -> None:
    conn = clinical_connection
    clinic, user, _, customer = await make_clinic(conn, "Context")
    await context(conn, clinic, user, "staff")
    await conn.execute("INSERT INTO journal_notes(clinic_id,customer_id,author_id,assessment) VALUES($1,$2,$3,'secret')", clinic, customer, user)
    await conn.execute("INSERT INTO consents(clinic_id,customer_id,title,version,signature_data,signed_by_user_id) VALUES($1,$2,'Consent','1.0','sig',$3)", clinic, customer, user)
    await conn.execute("INSERT INTO before_after_images(clinic_id,customer_id,image_type,file_path,created_by_user_id) VALUES($1,$2,'before','customers/x/before.jpg',$3)", clinic, customer, user)

    await context(conn, None, None, None)
    assert await conn.fetchval("SELECT COUNT(*) FROM journal_notes") == 0
    assert await conn.fetchval("SELECT COUNT(*) FROM consents") == 0
    assert await conn.fetchval("SELECT COUNT(*) FROM before_after_images") == 0


@pytest.mark.asyncio
async def test_templates_are_staff_readable_but_admin_writable(clinical_connection: asyncpg.Connection) -> None:
    conn = clinical_connection
    clinic, staff, _, _ = await make_clinic(conn, "Templates")
    await context(conn, clinic, staff, "staff")
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await conn.execute("INSERT INTO journal_templates(clinic_id,title,structure_json,created_by_user_id) VALUES($1,'Nope','{}',$2)", clinic, staff)

    admin = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,'admin-templates@test','x','admin') RETURNING id", clinic)
    await context(conn, clinic, admin, "admin")
    template = await conn.fetchval("INSERT INTO journal_templates(clinic_id,title,structure_json,created_by_user_id) VALUES($1,'Standard','{}',$2) RETURNING id", clinic, admin)
    assert template is not None

    await context(conn, clinic, staff, "staff")
    assert await conn.fetchval("SELECT title FROM journal_templates WHERE id=$1", template) == "Standard"


@pytest.mark.asyncio
async def test_customer_cannot_create_journal_or_template(clinical_connection: asyncpg.Connection) -> None:
    conn = clinical_connection
    clinic, _, customer_user, customer = await make_clinic(conn, "Customer permissions")
    await context(conn, clinic, customer_user, "customer")
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await conn.execute("INSERT INTO journal_notes(clinic_id,customer_id,author_id,assessment) VALUES($1,$2,$3,'blocked')", clinic, customer, customer_user)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await conn.execute("INSERT INTO journal_templates(clinic_id,title,structure_json,created_by_user_id) VALUES($1,'blocked','{}',$2)", clinic, customer_user)


@pytest.mark.asyncio
async def test_consent_and_image_metadata_are_tenant_scoped(clinical_connection: asyncpg.Connection) -> None:
    conn = clinical_connection
    clinic_a, staff_a, _, customer_a = await make_clinic(conn, "Media A")
    clinic_b, staff_b, _, customer_b = await make_clinic(conn, "Media B")
    await context(conn, clinic_a, staff_a, "staff")
    consent = await conn.fetchval("INSERT INTO consents(clinic_id,customer_id,title,version,signature_data,signed_by_user_id) VALUES($1,$2,'Treatment','1.0','sig',$3) RETURNING id", clinic_a, customer_a, staff_a)
    image = await conn.fetchval("INSERT INTO before_after_images(clinic_id,customer_id,image_type,file_path,created_by_user_id) VALUES($1,$2,'before','customers/a/before.jpg',$3) RETURNING id", clinic_a, customer_a, staff_a)
    await context(conn, clinic_b, staff_b, "staff")
    assert await conn.fetchval("SELECT COUNT(*) FROM consents") == 0
    assert await conn.fetchval("SELECT COUNT(*) FROM before_after_images") == 0
    assert consent is not None and image is not None
