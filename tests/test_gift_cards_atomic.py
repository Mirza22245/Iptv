from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest

from app import business_gift_cards

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to run PostgreSQL integration tests")


@pytest.fixture
async def connection():
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    schema = "lydia_gift_card_test"
    root = Path(__file__).parents[1]
    try:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET search_path TO "{schema}"')
        await conn.execute((root / "database/schema_v2.sql").read_text())
        await conn.execute((root / "database/phase2_clinical.sql").read_text())
        await conn.execute((root / "database/phase3_business.sql").read_text())
        await conn.execute((root / "database/phase3_gift_cards.sql").read_text())
        yield conn
    finally:
        await conn.execute("RESET search_path")
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()


class TestDatabase:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def transaction(self, *, clinic_id: int, user_id: int, role: str):
        async with self.conn.transaction():
            await self.conn.execute(
                "SELECT set_config('lydia.current_clinic_id',$1,true), set_config('lydia.current_user_id',$2,true), set_config('lydia.current_role',$3,true)",
                str(clinic_id), str(user_id), role,
            )
            yield self.conn


async def clinic(conn, name: str):
    cid = await conn.fetchval("INSERT INTO clinics(name) VALUES($1) RETURNING id", name)
    await conn.execute(
        "SELECT set_config('lydia.current_clinic_id',$1,false), set_config('lydia.current_user_id','0',false), set_config('lydia.current_role','admin',false)",
        str(cid),
    )
    uid = await conn.fetchval(
        "INSERT INTO users(clinic_id,email,password_hash,role) VALUES($1,$2,'x','admin') RETURNING id",
        cid,
        f"gift-admin-{cid}@test",
    )
    return cid, uid


@pytest.mark.asyncio
async def test_purchase_redeem_refund_and_audit_are_atomic(connection):
    db = TestDatabase(connection)
    cid, uid = await clinic(connection, "Gift Cards")

    card = await business_gift_cards.purchase_gift_card(db, cid, uid, "admin", "LYDIA-001", Decimal("100"))
    assert card["balance"] == Decimal("100.00")
    assert await connection.fetchval("SELECT count(*) FROM gift_card_transactions WHERE gift_card_id=$1", card["id"]) == 1
    assert await connection.fetchval("SELECT count(*) FROM audit_logs WHERE target_type='gift_card' AND target_id=$1", card["id"]) == 1

    redeemed = await business_gift_cards.redeem_gift_card(db, cid, uid, "admin", "LYDIA-001", Decimal("40"), 1001)
    assert redeemed["balance"] == Decimal("60.00")

    refunded = await business_gift_cards.refund_gift_card(db, cid, uid, "admin", "LYDIA-001", Decimal("20"), 1001)
    assert refunded["balance"] == Decimal("80.00")
    assert await connection.fetchval("SELECT count(*) FROM audit_logs WHERE target_type='gift_card' AND target_id=$1", card["id"]) == 3


@pytest.mark.asyncio
async def test_failed_transaction_rolls_back_balance_and_transaction(connection, monkeypatch):
    db = TestDatabase(connection)
    cid, uid = await clinic(connection, "Rollback")
    card = await business_gift_cards.purchase_gift_card(db, cid, uid, "admin", "ROLLBACK-001", Decimal("100"))

    async def fail_audit(*args, **kwargs):
        raise RuntimeError("audit failure")

    monkeypatch.setattr(business_gift_cards, "_audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit failure"):
        await business_gift_cards.redeem_gift_card(db, cid, uid, "admin", "ROLLBACK-001", Decimal("25"), 2001)

    assert await connection.fetchval("SELECT balance FROM gift_cards WHERE id=$1", card["id"]) == Decimal("100.00")
    assert await connection.fetchval("SELECT count(*) FROM gift_card_transactions WHERE gift_card_id=$1", card["id"]) == 1


@pytest.mark.asyncio
async def test_gift_cards_are_tenant_isolated(connection):
    cid_a, uid_a = await clinic(connection, "Clinic A")
    db = TestDatabase(connection)
    await business_gift_cards.purchase_gift_card(db, cid_a, uid_a, "admin", "SAME-CODE", Decimal("50"))

    cid_b, uid_b = await clinic(connection, "Clinic B")
    await business_gift_cards.purchase_gift_card(db, cid_b, uid_b, "admin", "SAME-CODE", Decimal("70"))

    await connection.execute(
        "SELECT set_config('lydia.current_clinic_id',$1,false), set_config('lydia.current_user_id',$2,false), set_config('lydia.current_role','admin',false)",
        str(cid_a), str(uid_a),
    )
    assert await connection.fetchval("SELECT count(*) FROM gift_cards") == 1
    assert await connection.fetchval("SELECT balance FROM gift_cards WHERE code='SAME-CODE'") == Decimal("50.00")


@pytest.mark.asyncio
async def test_expired_card_cannot_be_redeemed(connection):
    db = TestDatabase(connection)
    cid, uid = await clinic(connection, "Expiry")
    card = await business_gift_cards.purchase_gift_card(
        db,
        cid,
        uid,
        "admin",
        "EXPIRED-001",
        Decimal("50"),
        datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    await connection.execute("UPDATE gift_cards SET expires_at=$1 WHERE id=$2", datetime.now(timezone.utc) - timedelta(seconds=1), card["id"])

    with pytest.raises(Exception, match="expired"):
        await business_gift_cards.redeem_gift_card(db, cid, uid, "admin", "EXPIRED-001", Decimal("10"), 3001)

    assert await connection.fetchval("SELECT status FROM gift_cards WHERE id=$1", card["id"]) == "expired"
    assert await connection.fetchval("SELECT count(*) FROM gift_card_transactions WHERE gift_card_id=$1 AND type='expire'", card["id"]) == 1


@pytest.mark.asyncio
async def test_reference_id_cannot_be_reused(connection):
    db = TestDatabase(connection)
    cid, uid = await clinic(connection, "Idempotency")
    await business_gift_cards.purchase_gift_card(db, cid, uid, "admin", "REF-001", Decimal("100"))
    await business_gift_cards.redeem_gift_card(db, cid, uid, "admin", "REF-001", Decimal("10"), 4001)

    with pytest.raises(Exception, match="already been used"):
        await business_gift_cards.redeem_gift_card(db, cid, uid, "admin", "REF-001", Decimal("10"), 4001)

    assert await connection.fetchval("SELECT balance FROM gift_cards WHERE clinic_id=$1 AND code='REF-001'", cid) == Decimal("90.00")
