"""Lydia business layer: POS, inventory, reporting and integration controls."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth import require_role
from app.database import Database, get_database

router = APIRouter(prefix="/api/business", tags=["Business"])


def ctx(token: dict[str, Any]) -> tuple[int, int, str]:
    return int(token["clinic_id"]), int(token["sub"]), str(token["role"])


class ProductIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    unit_price: Decimal = Field(ge=0)
    vat_rate: Decimal = Field(default=Decimal("25"), ge=0, le=100)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)


class StockMovementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(gt=0)
    movement_type: str
    quantity: Decimal
    unit_cost: Decimal | None = Field(default=None, ge=0)
    note: str | None = None


class SaleItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int | None = Field(default=None, gt=0)
    service_id: int | None = Field(default=None, gt=0)
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    vat_rate: Decimal = Field(default=Decimal("25"), ge=0, le=100)


class SaleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int | None = Field(default=None, gt=0)
    items: list[SaleItemIn] = Field(min_length=1)


class PaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: str
    amount: Decimal = Field(gt=0)
    external_reference: str | None = None


class IntegrationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    external_account_id: str | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)


@router.get("/products")
async def products(token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = ctx(token)
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        rows = await conn.fetch("SELECT * FROM products WHERE clinic_id=$1 AND is_active ORDER BY name", clinic_id)
        return [dict(r) for r in rows]


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductIn, token: dict[str, Any] = Depends(require_role("admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = ctx(token)
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        try:
            row = await conn.fetchrow("INSERT INTO products (clinic_id,sku,name,description,unit_price,vat_rate,reorder_level) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *", clinic_id, payload.sku, payload.name, payload.description, payload.unit_price, payload.vat_rate, payload.reorder_level)
        except Exception as exc:
            raise HTTPException(409, "SKU already exists") from exc
        return dict(row)


@router.post("/inventory/movements", status_code=status.HTTP_201_CREATED)
async def stock_movement(payload: StockMovementIn, token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    if payload.movement_type not in {"purchase", "sale", "adjustment", "return", "waste"} or payload.quantity == 0:
        raise HTTPException(422, "Invalid inventory movement")
    clinic_id, user_id, role = ctx(token)
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        product = await conn.fetchrow("SELECT id,stock_quantity FROM products WHERE id=$1 AND clinic_id=$2 FOR UPDATE", payload.product_id, clinic_id)
        if not product:
            raise HTTPException(404, "Product not found")
        new_stock = Decimal(product["stock_quantity"]) + payload.quantity
        if new_stock < 0:
            raise HTTPException(409, "Insufficient stock")
        row = await conn.fetchrow("INSERT INTO inventory_movements (clinic_id,product_id,movement_type,quantity,unit_cost,note,created_by_user_id) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *", clinic_id, payload.product_id, payload.movement_type, payload.quantity, payload.unit_cost, payload.note, user_id)
        await conn.execute("UPDATE products SET stock_quantity=$1 WHERE id=$2 AND clinic_id=$3", new_stock, payload.product_id, clinic_id)
        return dict(row)


@router.post("/sales", status_code=status.HTTP_201_CREATED)
async def create_sale(payload: SaleIn, token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = ctx(token)
    subtotal = sum((i.quantity * i.unit_price for i in payload.items), Decimal("0"))
    vat = sum((i.quantity * i.unit_price * i.vat_rate / Decimal("100") for i in payload.items), Decimal("0"))
    total = subtotal + vat
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        if payload.customer_id is not None and not await conn.fetchval("SELECT 1 FROM customers WHERE id=$1 AND clinic_id=$2", payload.customer_id, clinic_id):
            raise HTTPException(404, "Customer not found")
        sale = await conn.fetchrow("INSERT INTO sales (clinic_id,customer_id,status,subtotal,vat_total,total,created_by_user_id) VALUES ($1,$2,'open',$3,$4,$5,$6) RETURNING *", clinic_id, payload.customer_id, subtotal, vat, total, user_id)
        for item in payload.items:
            if (item.product_id is None) == (item.service_id is None):
                raise HTTPException(422, "Each sale item must reference exactly one product or service")
            if item.product_id is not None:
                p = await conn.fetchrow("SELECT stock_quantity FROM products WHERE id=$1 AND clinic_id=$2 FOR UPDATE", item.product_id, clinic_id)
                if not p or Decimal(p["stock_quantity"]) < item.quantity:
                    raise HTTPException(409, "Insufficient stock for product")
                await conn.execute("UPDATE products SET stock_quantity=stock_quantity-$1 WHERE id=$2 AND clinic_id=$3", item.quantity, item.product_id, clinic_id)
                await conn.execute("INSERT INTO inventory_movements (clinic_id,product_id,movement_type,quantity,reference_type,reference_id,note,created_by_user_id) VALUES ($1,$2,'sale',$3,'sale',$4,'POS sale',$5)", clinic_id, item.product_id, -item.quantity, sale["id"], user_id)
            elif not await conn.fetchval("SELECT 1 FROM services WHERE id=$1 AND clinic_id=$2 AND is_active", item.service_id, clinic_id):
                raise HTTPException(404, "Service not found")
            line_total = item.quantity * item.unit_price * (Decimal("1") + item.vat_rate / Decimal("100"))
            await conn.execute("INSERT INTO sale_items (clinic_id,sale_id,product_id,service_id,description,quantity,unit_price,vat_rate,line_total) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)", clinic_id, sale["id"], item.product_id, item.service_id, item.description, item.quantity, item.unit_price, item.vat_rate, line_total)
        return dict(sale)


@router.post("/sales/{sale_id}/payments", status_code=status.HTTP_201_CREATED)
async def pay_sale(sale_id: int, payload: PaymentIn, token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    if payload.method not in {"card", "swish", "cash", "invoice", "other"}:
        raise HTTPException(422, "Invalid payment method")
    clinic_id, user_id, role = ctx(token)
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        sale = await conn.fetchrow("SELECT total FROM sales WHERE id=$1 AND clinic_id=$2 AND status='open' FOR UPDATE", sale_id, clinic_id)
        if not sale:
            raise HTTPException(404, "Open sale not found")
        paid = await conn.fetchval("SELECT COALESCE(SUM(amount),0) FROM payments WHERE sale_id=$1 AND clinic_id=$2 AND status='completed'", sale_id, clinic_id)
        if Decimal(paid) + payload.amount > Decimal(sale["total"]):
            raise HTTPException(409, "Payment exceeds remaining balance")
        payment = await conn.fetchrow("INSERT INTO payments (clinic_id,sale_id,method,amount,external_reference,created_by_user_id) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *", clinic_id, sale_id, payload.method, payload.amount, payload.external_reference, user_id)
        remaining = Decimal(sale["total"]) - Decimal(paid) - payload.amount
        if remaining == 0:
            await conn.execute("UPDATE sales SET status='paid',paid_at=CURRENT_TIMESTAMP WHERE id=$1 AND clinic_id=$2", sale_id, clinic_id)
        return dict(payment)



class CheckoutItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int | None = Field(default=None, gt=0)
    service_id: int | None = Field(default=None, gt=0)
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    vat_rate: Decimal = Field(default=Decimal("25"), ge=0, le=100)


class CheckoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int | None = Field(default=None, gt=0)
    items: list[CheckoutItemIn] = Field(min_length=1)
    payment_method: str
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    external_reference: str | None = None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


@router.post("/checkout", status_code=status.HTTP_201_CREATED)
async def checkout(
    payload: CheckoutIn,
    token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")),
    db: Database = Depends(get_database),
):
    if payload.payment_method not in {"card", "swish", "cash", "invoice", "other"}:
        raise HTTPException(422, "Invalid payment method")

    clinic_id, user_id, role = ctx(token)
    subtotal = _money(sum((item.quantity * item.unit_price for item in payload.items), Decimal("0")))
    vat_total = _money(sum((item.quantity * item.unit_price * item.vat_rate / Decimal("100") for item in payload.items), Decimal("0")))
    total = _money(subtotal + vat_total - payload.discount_amount)
    if total < 0:
        raise HTTPException(422, "discount_amount exceeds order total")

    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        if payload.customer_id is not None:
            exists = await conn.fetchval("SELECT 1 FROM customers WHERE id=$1 AND clinic_id=$2", payload.customer_id, clinic_id)
            if not exists:
                raise HTTPException(404, "Customer not found")

        for item in payload.items:
            if (item.product_id is None) == (item.service_id is None):
                raise HTTPException(422, "Each checkout item must reference exactly one product or service")

        sale = await conn.fetchrow(
            """INSERT INTO sales (clinic_id,customer_id,status,subtotal,vat_total,total,created_by_user_id)
               VALUES ($1,$2,'open',$3,$4,$5,$6)
               RETURNING id,created_at""",
            clinic_id, payload.customer_id, subtotal, vat_total, total, user_id,
        )

        for item in payload.items:
            line_total = _money(item.quantity * item.unit_price * (Decimal("1") + item.vat_rate / Decimal("100")))
            if item.product_id is not None:
                product = await conn.fetchrow(
                    """SELECT id,stock_quantity FROM products
                       WHERE id=$1 AND clinic_id=$2 AND is_active FOR UPDATE""",
                    item.product_id, clinic_id,
                )
                if not product:
                    raise HTTPException(404, "Product not found")
                if Decimal(product["stock_quantity"]) < item.quantity:
                    raise HTTPException(409, f"Insufficient stock for product {item.product_id}")
                await conn.execute(
                    "INSERT INTO sale_items (clinic_id,sale_id,product_id,description,quantity,unit_price,vat_rate,line_total) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                    clinic_id, sale["id"], item.product_id, item.description, item.quantity, item.unit_price, item.vat_rate, line_total,
                )
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
            else:
                exists = await conn.fetchval(
                    "SELECT 1 FROM services WHERE id=$1 AND clinic_id=$2 AND is_active",
                    item.service_id, clinic_id,
                )
                if not exists:
                    raise HTTPException(404, "Service not found")
                await conn.execute(
                    "INSERT INTO sale_items (clinic_id,sale_id,service_id,description,quantity,unit_price,vat_rate,line_total) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                    clinic_id, sale["id"], item.service_id, item.description, item.quantity, item.unit_price, item.vat_rate, line_total,
                )

        payment_status = "pending" if payload.payment_method == "invoice" else "completed"
        payment = await conn.fetchrow(
            """INSERT INTO payments
               (clinic_id,sale_id,method,amount,external_reference,status,created_by_user_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               RETURNING id,method,amount,status,created_at""",
            clinic_id, sale["id"], payload.payment_method, total,
            payload.external_reference, payment_status, user_id,
        )

        sale_status = "open" if payment_status == "pending" else "paid"
        await conn.execute(
            "UPDATE sales SET status=$1,paid_at=CASE WHEN $1='paid' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=$2 AND clinic_id=$3",
            sale_status, sale["id"], clinic_id,
        )

        audit = await conn.fetchrow(
            """INSERT INTO audit_logs
               (clinic_id,action,target_type,target_id,new_values,performed_by_user_id)
               VALUES ($1,'checkout_completed','sale',$2,$3::jsonb,$4)
               RETURNING id,performed_at""",
            clinic_id, sale["id"],
            __import__("json").dumps({
                "payment_method": payload.payment_method,
                "amount": str(total),
                "status": payment_status,
            }),
            user_id,
        )

        return {
            "sale": {"id": sale["id"], "status": sale_status},
            "payment": dict(payment),
            "financials": {
                "subtotal": subtotal,
                "vat_total": vat_total,
                "discount": payload.discount_amount,
                "total": total,
            },
            "audit_id": audit["id"],
            "created_at": sale["created_at"],
        }


@router.get("/reports/z")
async def z_report(
    report_date: date | None = None,
    token: dict[str, Any] = Depends(require_role("admin", "superadmin")),
    db: Database = Depends(get_database),
):
    target = report_date or datetime.now(timezone.utc).date()
    clinic_id, user_id, role = ctx(token)

    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        summary = await conn.fetchrow(
            """SELECT
                 COUNT(*) FILTER (WHERE status='paid')::bigint AS paid_sales,
                 COALESCE(SUM(subtotal) FILTER (WHERE status='paid'),0) AS subtotal,
                 COALESCE(SUM(vat_total) FILTER (WHERE status='paid'),0) AS vat_total,
                 COALESCE(SUM(total) FILTER (WHERE status='paid'),0) AS total,
                 COUNT(*) FILTER (WHERE status='refunded')::bigint AS refunded_sales,
                 COALESCE(SUM(total) FILTER (WHERE status='refunded'),0) AS refunded_total
               FROM sales
               WHERE clinic_id=$1
                 AND created_at >= $2::date
                 AND created_at < ($2::date + INTERVAL '1 day')""",
            clinic_id, target,
        )
        methods = await conn.fetch(
            """SELECT method,COALESCE(SUM(amount),0) AS amount
               FROM payments
               WHERE clinic_id=$1 AND status='completed'
                 AND created_at >= $2::date
                 AND created_at < ($2::date + INTERVAL '1 day')
               GROUP BY method ORDER BY method""",
            clinic_id, target,
        )
        method_totals = {row["method"]: row["amount"] for row in methods}
        snapshot = await conn.fetchrow(
            """INSERT INTO report_snapshots
               (clinic_id,report_type,period_start,period_end,data)
               VALUES ($1,'z_report',$2,$2,$3::jsonb)
               RETURNING id,created_at""",
            clinic_id, target,
            __import__("json").dumps({
                "paid_sales": int(summary["paid_sales"]),
                "subtotal": str(summary["subtotal"]),
                "vat_total": str(summary["vat_total"]),
                "total": str(summary["total"]),
                "refunded_sales": int(summary["refunded_sales"]),
                "refunded_total": str(summary["refunded_total"]),
                "payment_methods": {k: str(v) for k, v in method_totals.items()},
            }),
        )
        return {
            "report_type": "z_report",
            "date": target,
            "summary": dict(summary),
            "payment_methods": method_totals,
            "snapshot_id": snapshot["id"],
            "created_at": snapshot["created_at"],
        }


@router.get("/reports/sales")
async def sales_report(start: date, end: date, token: dict[str, Any] = Depends(require_role("admin", "superadmin")), db: Database = Depends(get_database)):
    if end < start:
        raise HTTPException(422, "end must be on or after start")
    clinic_id, user_id, role = ctx(token)
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        summary = await conn.fetchrow("SELECT COUNT(*) AS sales_count, COALESCE(SUM(subtotal),0) subtotal, COALESCE(SUM(vat_total),0) vat_total, COALESCE(SUM(total),0) total FROM sales WHERE clinic_id=$1 AND status='paid' AND created_at >= $2 AND created_at < ($3::date + INTERVAL '1 day')", clinic_id, start, end)
        by_method = await conn.fetch("SELECT method, COALESCE(SUM(amount),0) amount FROM payments WHERE clinic_id=$1 AND status='completed' AND created_at >= $2 AND created_at < ($3::date + INTERVAL '1 day') GROUP BY method ORDER BY method", clinic_id, start, end)
        return {"period":{"start":start,"end":end},"summary":dict(summary),"payments_by_method":[dict(r) for r in by_method]}


@router.get("/reports/dashboard")
async def business_dashboard(token: dict[str, Any] = Depends(require_role("admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = ctx(token)
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        today = await conn.fetchrow("SELECT COUNT(*) sales_count, COALESCE(SUM(total),0) revenue FROM sales WHERE clinic_id=$1 AND status='paid' AND created_at::date=CURRENT_DATE", clinic_id)
        low = await conn.fetch("SELECT id,sku,name,stock_quantity,reorder_level FROM products WHERE clinic_id=$1 AND is_active AND stock_quantity <= reorder_level ORDER BY stock_quantity", clinic_id)
        return {"today":dict(today),"low_stock":[dict(r) for r in low]}


@router.get("/integrations")
async def integrations(token: dict[str, Any] = Depends(require_role("admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = ctx(token)
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        rows = await conn.fetch("SELECT provider,status,external_account_id,last_sync_at,last_error FROM integration_connections WHERE clinic_id=$1 ORDER BY provider", clinic_id)
        return [dict(r) for r in rows]


@router.put("/integrations/{provider}")
async def configure_integration(provider: str, payload: IntegrationIn, token: dict[str, Any] = Depends(require_role("admin", "superadmin")), db: Database = Depends(get_database)):
    if provider != payload.provider or provider not in {"bokadirekt","meridiq","stripe","swish","other"}:
        raise HTTPException(422, "Unsupported integration provider")
    clinic_id, user_id, role = ctx(token)
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        row = await conn.fetchrow("INSERT INTO integration_connections (clinic_id,provider,status,external_account_id,settings_json) VALUES ($1,$2,'configured',$3,$4::jsonb) ON CONFLICT (clinic_id,provider) DO UPDATE SET status='configured',external_account_id=EXCLUDED.external_account_id,settings_json=EXCLUDED.settings_json RETURNING provider,status,external_account_id,last_sync_at,last_error", clinic_id, provider, payload.external_account_id, __import__('json').dumps(payload.settings_json))
        return dict(row)
