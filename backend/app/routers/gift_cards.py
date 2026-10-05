"""Lydia gift-card API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth import require_role
from app.business_gift_cards import (
    get_gift_card_balance,
    purchase_gift_card,
    redeem_gift_card,
    refund_gift_card,
)
from app.database import Database, get_database

router = APIRouter(prefix="/api/gift-cards", tags=["Gift Cards"])


def ctx(token: dict[str, Any]) -> tuple[int, int, str]:
    return int(token["clinic_id"]), int(token["sub"]), str(token["role"])


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=64)
    initial_amount: Decimal = Field(gt=0)
    expires_at: datetime | None = None


class GiftCardAmountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=0)
    reference_id: int | None = Field(default=None, gt=0)


@router.post("/purchase", status_code=status.HTTP_201_CREATED)
async def api_purchase(
    payload: PurchaseRequest,
    token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")),
    db: Database = Depends(get_database),
):
    clinic_id, user_id, role = ctx(token)
    return await purchase_gift_card(db, clinic_id, user_id, role, payload.code, payload.initial_amount, payload.expires_at)


@router.get("/balance/{code}")
async def api_balance(
    code: str,
    token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")),
    db: Database = Depends(get_database),
):
    clinic_id, user_id, role = ctx(token)
    return await get_gift_card_balance(db, clinic_id, user_id, role, code)


@router.post("/redeem")
async def api_redeem(
    payload: GiftCardAmountRequest,
    token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")),
    db: Database = Depends(get_database),
):
    clinic_id, user_id, role = ctx(token)
    return await redeem_gift_card(db, clinic_id, user_id, role, payload.code, payload.amount, payload.reference_id)


@router.post("/refund")
async def api_refund(
    payload: GiftCardAmountRequest,
    token: dict[str, Any] = Depends(require_role("admin", "superadmin")),
    db: Database = Depends(get_database),
):
    clinic_id, user_id, role = ctx(token)
    return await refund_gift_card(db, clinic_id, user_id, role, payload.code, payload.amount, payload.reference_id)
