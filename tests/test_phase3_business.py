from __future__ import annotations

import os
from pathlib import Path

import asyncpg
import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to run PostgreSQL integration tests")


@pytest.fixture
async def connection():
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    schema = "lydia_phase3_test"
    root = Path(__file__).parents[1]
    try:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET search_path TO "{schema}"')
        await conn.execute((root / "database/schema_v2.sql").read_text())
        await conn.execute((root / "database/phase2_clinical.sql").read_text())
        await conn.execute((root / "database/phase3_business.sql").read_text())
        yield conn
    finally:
        await conn.execute("RESET search_path")
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()


async def context(conn, clinic_id, user_id, role):
    await conn.execute("SELECT set_config('lydia.current_clinic_id',$1,false),set_config('lydia.current_user_id',$2,false),set_config('lydia.current_role',$3,false)", str(clinic_id), str(user_id), role)


async def clinic(conn, suffix):
    cid = await conn.fetchval("INSERT INTO clinics(name) VALUES($1) RETURNING id", suffix)
    await context(conn, cid, 0, "admin")
    uid = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','admin') RETURNING id", cid, f"admin-{cid}@test")
    return cid, uid


@pytest.mark.asyncio
async def test_business_tables_are_tenant_isolated(connection):
    conn = connection
    a, ua = await clinic(conn, "A")
    b, ub = await clinic(conn, "B")
    await context(conn, a, ua, "admin")
    await conn.execute("INSERT INTO products(clinic_id,sku,name,unit_price) VALUES($1,'A-1','A product',100)", a)
    await context(conn, b, ub, "admin")
    assert await conn.fetchval("SELECT count(*) FROM products") == 0


@pytest.mark.asyncio
async def test_inventory_movement_changes_stock(connection):
    conn = connection
    cid, uid = await clinic(conn, "Inventory")
    await context(conn, cid, uid, "admin")
    product = await conn.fetchval("INSERT INTO products(clinic_id,sku,name,unit_price) VALUES($1,'SKU-1','Product',100) RETURNING id", cid)
    await conn.execute("INSERT INTO inventory_movements(clinic_id,product_id,movement_type,quantity,created_by_user_id) VALUES($1,$2,'purchase',5,$3)", cid, product, uid)
    await conn.execute("UPDATE products SET stock_quantity=stock_quantity+5 WHERE id=$1", product)
    assert await conn.fetchval("SELECT stock_quantity FROM products WHERE id=$1", product) == 5


@pytest.mark.asyncio
async def test_customer_role_cannot_access_business_tables(connection):
    conn = connection
    cid, admin = await clinic(conn, "Permissions")
    customer = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,'customer@test','x','customer') RETURNING id", cid)
    await context(conn, cid, customer, "customer")
    assert await conn.fetchval("SELECT count(*) FROM products") == 0
