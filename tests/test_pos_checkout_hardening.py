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
            await conn.execute("SELECT set_config('lydia.current_clinic_id',$1,false), set_config('lydia.current_user_id','0',false), set_config('lydia.current_role','admin',false)", str(clinic_id))
            user_id = await conn.fetchval("INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','admin') RETURNING id", clinic_id, f"receipt-{uuid.uuid4()}@test")
            product_id = await conn.fetchval("INSERT INTO products(clinic_id,sku,name,unit_price,vat_rate,stock_quantity) VALUES($1,$2,'Receipt product',100,25,5) RETURNING id", clinic_id, f"REC-{uuid.uuid4()}")

        token = {"clinic_id": clinic_id, "sub": user_id, "role": "admin"}
        payload = CheckoutIn(items=[CheckoutItemIn(product_id=product_id,description="Receipt product",quantity=1)], payment_method="cash")
        first = await checkout(payload=payload, idempotency_key="receipt-test-001", token=token, db=db)
        assert first["receipt_id"] == first["sale"]["id"]
        assert first["sale"]["receipt_number"] >= 1
    finally:
        await shutdown_database()
