"""Transactional POS checkout with RLS, idempotency and server-side pricing."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.auth import require_role
from app.database import Database, get_database

router = APIRouter(prefix="/api/business", tags=["Business"])


class CheckoutItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int | None = Field(default=None, gt=0)
    service_id: int | None = Field(default=None, gt=0)
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)


class CheckoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int | None = Field(default=None, gt=0)
    items: list[CheckoutItemIn] = Field(min_length=1)
    payment_method: str
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    external_reference: str | None = None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _fingerprint(payload: CheckoutIn) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _response(sale: dict[str, Any], payment: dict[str, Any], audit: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "sale": sale,
        "payment": payment,
        "receipt_id": sale["id"],
        "audit": audit,
    }


@router.post("/checkout", status_code=status.HTTP_201_CREATED)
async def checkout(
    payload: CheckoutIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")),
    db: Database = Depends(get_database),
):
    if payload.payment_method not in {"card", "swish", "cash", "invoice", "other"}:
        raise HTTPException(422, "Invalid payment method")

    clinic_id = int(token["clinic_id"])
    user_id = int(token["sub"])
    role = str(token["role"])
    fingerprint = _fingerprint(payload)
    subtotal = Decimal("0")
    vat_total = Decimal("0")
    line_data: list[dict[str, Any]] = []

    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        existing = await conn.fetchrow(
            """SELECT id, idempotency_fingerprint, status, subtotal, vat_total, total, currency, created_at, paid_at
               FROM sales WHERE clinic_id=$1 AND idempotency_key=$2 FOR UPDATE""",
            clinic_id, idempotency_key,
        )
        if existing:
            if existing["idempotency_fingerprint"] != fingerprint:
                raise HTTPException(409, "Idempotency-Key was already used with a different checkout")
            payment = await conn.fetchrow(
                """SELECT id,method,amount,status,external_reference,created_at
                   FROM payments WHERE clinic_id=$1 AND sale_id=$2 ORDER BY id LIMIT 1""",
                clinic_id, existing["id"],
            )
            audit = await conn.fetchrow(
                """SELECT id,performed_at FROM audit_logs
                   WHERE clinic_id=$1 AND target_type='sale' AND target_id=$2 AND action='checkout_completed'
                   ORDER BY id LIMIT 1""",
                clinic_id, existing["id"],
            )
            body = _response(dict(existing), dict(payment) if payment else {}, dict(audit) if audit else None)
            return JSONResponse(status_code=200, content=jsonable_encoder(body))

        if payload.customer_id is not None:
            exists = await conn.fetchval(
                "SELECT 1 FROM customers WHERE id=$1 AND clinic_id=$2", payload.customer_id, clinic_id
            )
            if not exists:
                raise HTTPException(404, "Customer not found")

        for item in payload.items:
            if (item.product_id is None) == (item.service_id is None):
                raise HTTPException(422, "Each checkout item must reference exactly one product or service")

            if item.product_id is not None:
                product = await conn.fetchrow(
                    """SELECT id,name,unit_price,vat_rate,stock_quantity FROM products
                       WHERE id=$1 AND clinic_id=$2 AND is_active FOR UPDATE""",
                    item.product_id, clinic_id,
                )
                if not product:
                    raise HTTPException(404, "Product not found")
                if Decimal(product["stock_quantity"]) < item.quantity:
                    raise HTTPException(409, f"Insufficient stock for product {item.product_id}")
                unit_price = Decimal(product["unit_price"])
                vat_rate = Decimal(product["vat_rate"])
                line_total = _money(item.quantity * unit_price * (Decimal("1") + vat_rate / Decimal("100")))
                subtotal += item.quantity * unit_price
                vat_total += item.quantity * unit_price * vat_rate / Decimal("100")
                line_data.append({"item": item, "unit_price": unit_price, "vat_rate": vat_rate, "line_total": line_total})
            else:
                service = await conn.fetchrow(
                    "SELECT id,name,price FROM services WHERE id=$1 AND clinic_id=$2 AND is_active",
                    item.service_id, clinic_id,
                )
                if not service:
                    raise HTTPException(404, "Service not found")
                unit_price = Decimal(service["price"])
                vat_rate = Decimal("25")
                line_total = _money(item.quantity * unit_price * (Decimal("1") + vat_rate / Decimal("100")))
                subtotal += item.quantity * unit_price
                vat_total += item.quantity * unit_price * vat_rate / Decimal("100")
                line_data.append({"item": item, "unit_price": unit_price, "vat_rate": vat_rate, "line_total": line_total})

        subtotal = _money(subtotal)
        vat_total = _money(vat_total)
        total = _money(subtotal + vat_total - payload.discount_amount)
        if total <= 0:
            raise HTTPException(422, "Checkout total must be greater than zero")

        sale = await conn.fetchrow(
            """INSERT INTO sales
               (clinic_id,customer_id,status,subtotal,vat_total,total,currency,created_by_user_id,idempotency_key,idempotency_fingerprint)
               VALUES ($1,$2,'open',$3,$4,$5,'SEK',$6,$7,$8)
               RETURNING id,clinic_id,status,subtotal,vat_total,total,currency,created_at,paid_at,idempotency_key""",
            clinic_id, payload.customer_id, subtotal, vat_total, total, user_id, idempotency_key, fingerprint,
        )

        for data in line_data:
            item = data["item"]
            await conn.execute(
                """INSERT INTO sale_items
                   (clinic_id,sale_id,product_id,service_id,description,quantity,unit_price,vat_rate,line_total)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                clinic_id, sale["id"], item.product_id, item.service_id, item.description,
                item.quantity, data["unit_price"], data["vat_rate"], data["line_total"],
            )
            if item.product_id is not None:
                await conn.execute(
                    "UPDATE products SET stock_quantity=stock_quantity-$1 WHERE id=$2 AND clinic_id=$3",
                    item.quantity, item.product_id, clinic_id,
                )
                await conn.execute(
                    """INSERT INTO inventory_movements
                       (clinic_id,product_id,movement_type,quantity,reference_type,reference_id,note,created_by_user_id)
                       VALUES ($1,$2,'sale',$3,'sale',$4,'POS checkout',$5)""",
                    clinic_id, item.product_id, -item.quantity, sale["id"], user_id,
                )

        payment_status = "pending" if payload.payment_method == "invoice" else "completed"
        payment = await conn.fetchrow(
            """INSERT INTO payments
               (clinic_id,sale_id,method,amount,external_reference,status,created_by_user_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               RETURNING id,method,amount,status,external_reference,created_at""",
            clinic_id, sale["id"], payload.payment_method, total, payload.external_reference, payment_status, user_id,
        )
        sale_status = "open" if payment_status == "pending" else "paid"
        await conn.execute(
            "UPDATE sales SET status=$1,paid_at=CASE WHEN $1='paid' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=$2 AND clinic_id=$3",
            sale_status, sale["id"], clinic_id,
        )
        sale = await conn.fetchrow(
            """SELECT id,clinic_id,status,subtotal,vat_total,total,currency,created_at,paid_at,idempotency_key
               FROM sales WHERE id=$1 AND clinic_id=$2""",
            sale["id"], clinic_id,
        )
        audit = await conn.fetchrow(
            """INSERT INTO audit_logs
               (clinic_id,action,target_type,target_id,new_values,performed_by_user_id)
               VALUES ($1,'checkout_completed','sale',$2,$3::jsonb,$4)
               RETURNING id,performed_at""",
            clinic_id, sale["id"],
            json.dumps({"payment_method": payload.payment_method, "amount": str(total), "idempotency_key": idempotency_key}),
            user_id,
        )
        return _response(dict(sale), dict(payment), dict(audit))
