import pytest


@pytest.mark.asyncio
async def test_checkout_assigns_persistent_receipt_number():
    from app.database import get_database, shutdown_database, startup_database
    from app.routers.pos_checkout import CheckoutIn, CheckoutItemIn, checkout
    import uuid

    await startup_database()
    db = await get_database()
    try:
        async with db.healthcheck() as conn:
            clinic_id = await conn.fetchval("INSERT INTO clinics(name) VALUES($1) RETURNING id", f"Receipt {uuid.uuid4()}")
            user_id = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','admin') RETURNING id", clinic_id, f"receipt-{uuid.uuid4()}@test")
            product_id = await conn.fetchval("INSERT INTO products(clinic_id,sku,name,unit_price,vat_rate,stock_quantity) VALUES($1,$2,'Receipt product',100,25,5) RETURNING id", clinic_id, f"REC-{uuid.uuid4()}")

        token = {"clinic_id": clinic_id, "sub": user_id, "role": "admin"}
        payload = CheckoutIn(items=[CheckoutItemIn(product_id=product_id,description="Receipt product",quantity=1)], payment_method="cash")
        first = await checkout(payload=payload, idempotency_key=f"receipt-test-{uuid.uuid4()}", token=token, db=db)
        assert first["receipt_id"] == first["sale"]["id"]
        assert first["sale"]["receipt_number"] >= 1
    finally:
        await shutdown_database()


@pytest.mark.asyncio
async def test_refund_marks_payment_and_restores_stock():
    from app.database import get_database, shutdown_database, startup_database
    from app.routers.pos_checkout import CheckoutIn, CheckoutItemIn, SaleActionIn, checkout, refund_sale
    import uuid

    await startup_database()
    db = await get_database()
    try:
        async with db.healthcheck() as conn:
            clinic_id = await conn.fetchval("INSERT INTO clinics(name) VALUES($1) RETURNING id", f"Refund {uuid.uuid4()}")
            user_id = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','admin') RETURNING id", clinic_id, f"refund-{uuid.uuid4()}@test")
            product_id = await conn.fetchval("INSERT INTO products(clinic_id,sku,name,unit_price,vat_rate,stock_quantity) VALUES($1,$2,'Refund product',100,25,2) RETURNING id", clinic_id, f"REF-{uuid.uuid4()}")
        token = {"clinic_id": clinic_id, "sub": user_id, "role": "admin"}
        payload = CheckoutIn(items=[CheckoutItemIn(product_id=product_id,description="Refund product",quantity=1)], payment_method="cash")
        result = await checkout(payload=payload, idempotency_key=f"refund-test-{uuid.uuid4()}", token=token, db=db)
        response = await refund_sale(result["sale"]["id"], SaleActionIn(reason="Customer requested refund"), token=token, db=db)
        assert response["status"] == "refunded"
        async with db.healthcheck() as conn:
            stock = await conn.fetchval("SELECT stock_quantity FROM products WHERE clinic_id=$1 AND id=$2", clinic_id, product_id)
            payment_status = await conn.fetchval("SELECT status FROM payments WHERE clinic_id=$1 AND sale_id=$2", clinic_id, result["sale"]["id"])
        assert stock == 2
        assert payment_status == "refunded"
    finally:
        await shutdown_database()


@pytest.mark.asyncio
async def test_void_restores_stock_and_records_audit():
    from app.database import get_database, shutdown_database, startup_database
    from app.routers.pos_checkout import CheckoutIn, CheckoutItemIn, SaleActionIn, checkout, void_sale
    import uuid

    await startup_database()
    db = await get_database()
    try:
        async with db.healthcheck() as conn:
            clinic_id = await conn.fetchval("INSERT INTO clinics(name) VALUES($1) RETURNING id", f"Void {uuid.uuid4()}")
            user_id = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','admin') RETURNING id", clinic_id, f"void-{uuid.uuid4()}@test")
            product_id = await conn.fetchval("INSERT INTO products(clinic_id,sku,name,unit_price,vat_rate,stock_quantity) VALUES($1,$2,'Void product',100,25,2) RETURNING id", clinic_id, f"VOID-{uuid.uuid4()}")
        token = {"clinic_id": clinic_id, "sub": user_id, "role": "admin"}
        payload = CheckoutIn(items=[CheckoutItemIn(product_id=product_id,description="Void product",quantity=1)], payment_method="invoice")
        result = await checkout(payload=payload, idempotency_key=f"void-test-{uuid.uuid4()}", token=token, db=db)
        response = await void_sale(result["sale"]["id"], SaleActionIn(reason="Test void"), token=token, db=db)
        assert response["status"] == "void"
        async with db.healthcheck() as conn:
            stock = await conn.fetchval("SELECT stock_quantity FROM products WHERE clinic_id=$1 AND id=$2", clinic_id, product_id)
            audit_action = await conn.fetchval("SELECT action FROM audit_logs WHERE clinic_id=$1 AND target_id=$2 ORDER BY id DESC LIMIT 1", clinic_id, result["sale"]["id"])
        assert stock == 2
        assert audit_action == "sale_voided"
    finally:
        await shutdown_database()
