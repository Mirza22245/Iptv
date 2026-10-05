"""Atomic Lydia gift-card operations with request-scoped RLS context."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status

from app.database import Database


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


async def _audit(conn: Any, clinic_id: int, user_id: int, action: str, card_id: int, values: dict[str, Any]) -> None:
    import json
    await conn.execute("""INSERT INTO audit_logs
       (clinic_id, action, target_type, target_id, new_values, performed_by_user_id)
       VALUES ($1,$2,'gift_card',$3,$4::jsonb,$5)""", clinic_id, action, card_id, json.dumps(values, default=str), user_id)


async def purchase_gift_card(db: Database, clinic_id: int, user_id: int, role: str, code: str, initial_amount: Decimal, expires_at: datetime | None = None) -> dict[str, Any]:
    amount = _money(initial_amount)
    if amount <= 0: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "initial_amount must be greater than zero")
    code = code.strip()
    if not code: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "code must not be empty")
    if expires_at is not None and expires_at <= datetime.now(timezone.utc): raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expires_at must be in the future")
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        if await conn.fetchval("SELECT 1 FROM gift_cards WHERE clinic_id=$1 AND code=$2", clinic_id, code): raise HTTPException(status.HTTP_409_CONFLICT, "Gift card code already exists")
        card = await conn.fetchrow("""INSERT INTO gift_cards (clinic_id, code, initial_amount, balance, status, expires_at) VALUES ($1,$2,$3,$3,'active',$4) RETURNING id, clinic_id, code, initial_amount, balance, status, expires_at, created_at, updated_at""", clinic_id, code, amount, expires_at)
        await conn.execute("""INSERT INTO gift_card_transactions (clinic_id,gift_card_id,type,amount,created_by_user_id) VALUES ($1,$2,'purchase',$3,$4)""", clinic_id, card["id"], amount, user_id)
        await _audit(conn, clinic_id, user_id, "gift_card_purchased", card["id"], {"amount": amount, "code": code})
        return dict(card)


async def get_gift_card_balance(db: Database, clinic_id: int, user_id: int, role: str, code: str) -> dict[str, Any]:
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        card = await conn.fetchrow("""SELECT id, clinic_id, code, initial_amount, balance, status, expires_at, created_at, updated_at FROM gift_cards WHERE clinic_id=$1 AND code=$2 FOR UPDATE""", clinic_id, code)
        if not card: raise HTTPException(status.HTTP_404_NOT_FOUND, "Gift card not found")
        now = datetime.now(timezone.utc)
        if card["status"] == "active" and card["expires_at"] is not None and card["expires_at"] <= now:
            await conn.execute("UPDATE gift_cards SET status='expired', updated_at=CURRENT_TIMESTAMP WHERE id=$1 AND clinic_id=$2", card["id"], clinic_id)
            await conn.execute("INSERT INTO gift_card_transactions (clinic_id,gift_card_id,type,amount,created_by_user_id) VALUES ($1,$2,'expire',$3,$4)", clinic_id, card["id"], card["balance"], user_id)
            await _audit(conn, clinic_id, user_id, "gift_card_expired", card["id"], {"balance": card["balance"]})
            card = await conn.fetchrow("SELECT id, clinic_id, code, initial_amount, balance, status, expires_at, created_at, updated_at FROM gift_cards WHERE id=$1 AND clinic_id=$2", card["id"], clinic_id)
        return dict(card)


async def redeem_gift_card(db: Database, clinic_id: int, user_id: int, role: str, code: str, amount: Decimal, reference_id: int | None = None) -> dict[str, Any]:
    amount = _money(amount)
    if amount <= 0: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "amount must be greater than zero")
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        if reference_id is not None and await conn.fetchval("SELECT 1 FROM gift_card_transactions WHERE clinic_id=$1 AND type='redeem' AND reference_id=$2", clinic_id, reference_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Redeem reference_id has already been used")
        card = await conn.fetchrow("""SELECT id, code, balance, status, expires_at FROM gift_cards WHERE clinic_id=$1 AND code=$2 FOR UPDATE""", clinic_id, code)
        if not card: raise HTTPException(status.HTTP_404_NOT_FOUND, "Gift card not found")
        now = datetime.now(timezone.utc)
        if card["status"] == "active" and card["expires_at"] is not None and card["expires_at"] <= now:
            await conn.execute("UPDATE gift_cards SET status='expired', updated_at=CURRENT_TIMESTAMP WHERE id=$1 AND clinic_id=$2", card["id"], clinic_id)
            await conn.execute("INSERT INTO gift_card_transactions (clinic_id,gift_card_id,type,amount,created_by_user_id) VALUES ($1,$2,'expire',$3,$4)", clinic_id, card["id"], card["balance"], user_id)
            await _audit(conn, clinic_id, user_id, "gift_card_expired", card["id"], {"balance": card["balance"]})
            raise HTTPException(status.HTTP_409_CONFLICT, "Gift card has expired")
        if card["status"] != "active": raise HTTPException(status.HTTP_409_CONFLICT, f"Gift card is not active (status: {card['status']})")
        balance = Decimal(card["balance"])
        if amount > balance: raise HTTPException(status.HTTP_409_CONFLICT, "Insufficient gift card balance")
        new_balance = _money(balance - amount)
        new_status = "depleted" if new_balance == 0 else "active"
        updated = await conn.fetchrow("""UPDATE gift_cards SET balance=$1,status=$2,updated_at=CURRENT_TIMESTAMP WHERE id=$3 AND clinic_id=$4 RETURNING id, clinic_id, code, initial_amount, balance, status, expires_at, created_at, updated_at""", new_balance, new_status, card["id"], clinic_id)
        await conn.execute("""INSERT INTO gift_card_transactions (clinic_id,gift_card_id,type,amount,reference_id,created_by_user_id) VALUES ($1,$2,'redeem',$3,$4,$5)""", clinic_id, card["id"], amount, reference_id, user_id)
        await _audit(conn, clinic_id, user_id, "gift_card_redeemed", card["id"], {"amount": amount, "balance": new_balance, "reference_id": reference_id})
        return dict(updated)


async def refund_gift_card(db: Database, clinic_id: int, user_id: int, role: str, code: str, amount: Decimal, reference_id: int | None = None) -> dict[str, Any]:
    amount = _money(amount)
    if amount <= 0: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "amount must be greater than zero")
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        if reference_id is not None and await conn.fetchval("SELECT 1 FROM gift_card_transactions WHERE clinic_id=$1 AND type='refund' AND reference_id=$2", clinic_id, reference_id): raise HTTPException(status.HTTP_409_CONFLICT, "Refund reference_id has already been used")
        card = await conn.fetchrow("SELECT id, code, balance, initial_amount, status FROM gift_cards WHERE clinic_id=$1 AND code=$2 FOR UPDATE", clinic_id, code)
        if not card: raise HTTPException(status.HTTP_404_NOT_FOUND, "Gift card not found")
        if card["status"] == "expired": raise HTTPException(status.HTTP_409_CONFLICT, "Expired gift card cannot be refunded")
        balance = Decimal(card["balance"]); initial = Decimal(card["initial_amount"]); new_balance = _money(balance + amount)
        if new_balance > initial: raise HTTPException(status.HTTP_409_CONFLICT, "Refund amount exceeds original gift card value")
        updated = await conn.fetchrow("""UPDATE gift_cards SET balance=$1,status='active',updated_at=CURRENT_TIMESTAMP WHERE id=$2 AND clinic_id=$3 RETURNING id, clinic_id, code, initial_amount, balance, status, expires_at, created_at, updated_at""", new_balance, card["id"], clinic_id)
        await conn.execute("""INSERT INTO gift_card_transactions (clinic_id,gift_card_id,type,amount,reference_id,created_by_user_id) VALUES ($1,$2,'refund',$3,$4,$5)""", clinic_id, card["id"], amount, reference_id, user_id)
        await _audit(conn, clinic_id, user_id, "gift_card_refunded", card["id"], {"amount": amount, "balance": new_balance, "reference_id": reference_id})
        return dict(updated)
