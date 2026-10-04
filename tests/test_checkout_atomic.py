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
    schema = "lydia_checkout_test"
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
    await conn.execute(
        "SELECT set_config('lydia.current_clinic_id',$1,false),"
        "set_config('lydia.current_user_id',$2,false),"
        "set_config('lydia.current_role',$3,false)",
        str(clinic_id), str(user_id), role,
    )


async def fixture(conn):
    cid = await conn.fetchval("INSERT INTO clinics(name) VALUES($1) RETURNING id", "POS")
    await context(conn, cid, 0, "admin")
    uid = await conn.fetchval(
        "INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','admin') RETURNING id",
        cid, "pos-admin@test",
    )
    product = await conn.fetchval(
        "INSERT INTO products(clinic_id,sku,name,unit_price,stock_quantity) VALUES($1,'SKU-1','Product',100,5) RETURNING id",
        cid,
    )
    return cid, uid, product


@pytest.mark.asyncio
async def test_checkout_data_path_is_atomic_and_rls_scoped(connection):
    conn = connection
    cid, uid, product = await fixture(conn)
    await context(conn, cid, uid, "admin")

    await conn.execute(
        """INSERT INTO sales (clinic_id,status,subtotal,vat_total,total,created_by_user_id)
           VALUES ($1,'paid',100,25,125,$2)""",
        cid, uid,
    )
    sale_id = await conn.fetchval("SELECT max(id) FROM sales WHERE clinic_id=$1", cid)
    await conn.execute(
        """INSERT INTO sale_items
           (clinic_id,sale_id,product_id,description,quantity,unit_price,vat_rate,line_total)
           VALUES ($1,$2,$3,'Product',1,100,25,125)""",
        cid, sale_id, product,
    )
    await conn.execute(
        """UPDATE products SET stock_quantity=stock_quantity-1
           WHERE id=$1 AND clinic_id=$2""",
        product, cid,
    )
    await conn.execute(
        """INSERT INTO inventory_movements
           (clinic_id,product_id,movement_type,quantity,reference_type,reference_id,created_by_user_id)
           VALUES ($1,$2,'sale',-1,'sale',$3,$4)""",
        cid, product, sale_id, uid,
    )
    await conn.execute(
        """INSERT INTO payments
           (clinic_id,sale_id,method,amount,created_by_user_id)
           VALUES ($1,$2,'card',125,$3)""",
        cid, sale_id, uid,
    )
    assert await conn.fetchval("SELECT stock_quantity FROM products WHERE id=$1", product) == 4
    assert await conn.fetchval("SELECT status FROM sales WHERE id=$1", sale_id) == "paid"
    assert await conn.fetchval("SELECT COUNT(*) FROM payments WHERE sale_id=$1", sale_id) == 1

    await context(conn, cid, 0, "admin")
    other = await conn.fetchval("INSERT INTO clinics(name) VALUES('Other') RETURNING id")
    await context(conn, other, 0, "admin")
    assert await conn.fetchval("SELECT COUNT(*) FROM sales") == 0


@pytest.mark.asyncio
async def test_checkout_failure_can_rollback_all_business_rows(connection):
    conn = connection
    cid, uid, product = await fixture(conn)
    await context(conn, cid, uid, "admin")
    with pytest.raises(RuntimeError):
        async with conn.transaction():
            sale_id = await conn.fetchval(
                """INSERT INTO sales
                   (clinic_id,status,subtotal,vat_total,total,created_by_user_id)
                   VALUES ($1,'open',100,25,125,$2) RETURNING id""",
                cid, uid,
            )
            await conn.execute(
                """UPDATE products SET stock_quantity=stock_quantity-1
                   WHERE id=$1 AND clinic_id=$2""",
                product, cid,
            )
            await conn.execute(
                """INSERT INTO inventory_movements
                   (clinic_id,product_id,movement_type,quantity,reference_type,reference_id,created_by_user_id)
                   VALUES ($1,$2,'sale',-1,'sale',$3,$4)""",
                cid, product, sale_id, uid,
            )
            raise RuntimeError("force rollback")

    assert await conn.fetchval("SELECT COUNT(*) FROM sales WHERE clinic_id=$1", cid) == 0
    assert await conn.fetchval("SELECT stock_quantity FROM products WHERE id=$1", product) == 5
