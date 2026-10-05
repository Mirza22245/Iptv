from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to run PostgreSQL integration tests",
)


@pytest.mark.asyncio
async def test_checkout_uses_server_price_and_is_idempotent():
    from app.database import get_database, shutdown_database, startup_database
    from app.routers.pos_checkout import CheckoutIn, CheckoutItemIn, checkout

    await startup_database()
    db = await get_database()
    try:
        clinic_id = None
        user_id = None
        product_id = None
        async with db.healthcheck() as conn:
            clinic_id = await conn.fetchval(
                "INSERT INTO clinics(name) VALUES($1) RETURNING id",
                f"POS hardening {uuid.uuid4()}",
            )
            await conn.execute(
                "SELECT set_config('lydia.current_clinic_id',$1,false), set_config('lydia.current_user_id','0',false), set_config('lydia.current_role','admin',false)",
                str(clinic_id),
            )
            user_id = await conn.fetchval(
                "INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','admin') RETURNING id",
                clinic_id,
                f"pos-hardening-{uuid.uuid4()}@test",
            )
            product_id = await conn.fetchval(
                """INSERT INTO products(clinic_id,sku,name,unit_price,vat_rate,stock_quantity)
                   VALUES($1,$2,'Server priced product',100,25,5) RETURNING id""",
                clinic_id,
                f"POS-{uuid.uuid4()}",
            )

        token = {"clinic_id": clinic_id, "sub": user_id, "role": "admin"}
        payload = CheckoutIn(
            items=[
                CheckoutItemIn(
                    product_id=product_id,
                    description="Product",
                    quantity=1,
                    unit_price=999,
                    vat_rate=0,
                )
            ],
            payment_method="card",
            discount_amount=0,
        )

        first = await checkout(
            payload=payload,
            idempotency_key="pos-hardening-001",
            token=token,
            db=db,
        )
        assert first["sale"]["subtotal"] == 100
        assert first["sale"]["vat_total"] == 25
        assert first["sale"]["total"] == 125
        assert first["payment"]["amount"] == 125
        assert first["receipt_id"] == first["sale"]["id"]

        second = await checkout(
            payload=payload,
            idempotency_key="pos-hardening-001",
            token=token,
            db=db,
        )
        assert second.status_code == 200

        async with db.transaction(clinic_id=clinic_id, user_id=user_id, role="admin") as conn:
            assert await conn.fetchval("SELECT COUNT(*) FROM sales WHERE clinic_id=$1", clinic_id) == 1
            assert await conn.fetchval("SELECT COUNT(*) FROM payments WHERE clinic_id=$1", clinic_id) == 1
            assert await conn.fetchval("SELECT COUNT(*) FROM inventory_movements WHERE clinic_id=$1", clinic_id) == 1
            assert await conn.fetchval("SELECT stock_quantity FROM products WHERE id=$1", product_id) == 4

    finally:
        await shutdown_database()
