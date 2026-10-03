"""Admin and staff dashboard endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth import require_role
from app.database import Database, get_database

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/me")
async def dashboard_me(
    token_data: dict[str, Any] = Depends(require_role("customer", "staff", "admin", "superadmin")),
) -> dict[str, Any]:
    return {
        "user_id": int(token_data["sub"]),
        "clinic_id": int(token_data["clinic_id"]),
        "role": str(token_data["role"]),
    }


@router.get("/admin/overview")
async def admin_overview(
    token_data: dict[str, Any] = Depends(require_role("admin")),
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    clinic_id = int(token_data["clinic_id"])
    user_id = int(token_data["sub"])

    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=str(token_data["role"])) as conn:
        customers = await conn.fetchval("SELECT count(*) FROM customers WHERE clinic_id = $1", clinic_id)
        staff = await conn.fetchval("SELECT count(*) FROM staff WHERE clinic_id = $1 AND is_active", clinic_id)
        services = await conn.fetchval("SELECT count(*) FROM services WHERE clinic_id = $1 AND is_active", clinic_id)
        bookings = await conn.fetchval(
            "SELECT count(*) FROM bookings WHERE clinic_id = $1 AND status = 'confirmed'", clinic_id
        )
        upcoming = await conn.fetch(
            """
            SELECT b.id, lower(b.slot_range) AS slot_start, b.status,
                   c.first_name || ' ' || c.last_name AS customer_name,
                   s.name AS service_name,
                   st.display_name AS staff_name
            FROM bookings b
            JOIN customers c ON c.id = b.customer_id AND c.clinic_id = b.clinic_id
            JOIN services s ON s.id = b.service_id AND s.clinic_id = b.clinic_id
            JOIN staff st ON st.id = b.staff_id AND st.clinic_id = b.clinic_id
            WHERE b.clinic_id = $1 AND b.status = 'confirmed'
              AND lower(b.slot_range) >= CURRENT_TIMESTAMP
            ORDER BY lower(b.slot_range)
            LIMIT 20
            """,
            clinic_id,
        )

    return {
        "counts": {
            "customers": int(customers),
            "staff": int(staff),
            "services": int(services),
            "confirmed_bookings": int(bookings),
        },
        "upcoming": [dict(row) for row in upcoming],
    }


@router.get("/admin/customers")
async def admin_customers(
    token_data: dict[str, Any] = Depends(require_role("admin")),
    db: Database = Depends(get_database),
) -> list[dict[str, Any]]:
    clinic_id = int(token_data["clinic_id"])
    user_id = int(token_data["sub"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=str(token_data["role"])) as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.first_name, c.last_name, c.email, c.created_at,
                   u.is_active, u.role
            FROM customers c
            LEFT JOIN users u ON u.id = c.user_id AND u.clinic_id = c.clinic_id
            WHERE c.clinic_id = $1
            ORDER BY c.created_at DESC
            """,
            clinic_id,
        )
    return [dict(row) for row in rows]


@router.get("/admin/staff")
async def admin_staff(
    token_data: dict[str, Any] = Depends(require_role("admin")),
    db: Database = Depends(get_database),
) -> list[dict[str, Any]]:
    clinic_id = int(token_data["clinic_id"])
    user_id = int(token_data["sub"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=str(token_data["role"])) as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.display_name, s.is_active, u.email, u.role
            FROM staff s
            JOIN users u ON u.id = s.user_id AND u.clinic_id = s.clinic_id
            WHERE s.clinic_id = $1
            ORDER BY s.display_name
            """,
            clinic_id,
        )
    return [dict(row) for row in rows]


@router.get("/admin/services")
async def admin_services(
    token_data: dict[str, Any] = Depends(require_role("admin")),
    db: Database = Depends(get_database),
) -> list[dict[str, Any]]:
    clinic_id = int(token_data["clinic_id"])
    user_id = int(token_data["sub"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=str(token_data["role"])) as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, price, duration_minutes, is_active
            FROM services
            WHERE clinic_id = $1
            ORDER BY name
            """,
            clinic_id,
        )
    return [dict(row) for row in rows]


@router.get("/staff/today")
async def staff_today(
    token_data: dict[str, Any] = Depends(require_role("staff")),
    db: Database = Depends(get_database),
) -> list[dict[str, Any]]:
    clinic_id = int(token_data["clinic_id"])
    user_id = int(token_data["sub"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=str(token_data["role"])) as conn:
        rows = await conn.fetch(
            """
            SELECT b.id, lower(b.slot_range) AS slot_start, upper(b.slot_range) AS slot_end,
                   b.status, c.first_name || ' ' || c.last_name AS customer_name,
                   c.email AS customer_email, s.name AS service_name, s.price
            FROM bookings b
            JOIN customers c ON c.id = b.customer_id AND c.clinic_id = b.clinic_id
            JOIN services s ON s.id = b.service_id AND s.clinic_id = b.clinic_id
            JOIN staff st ON st.id = b.staff_id AND st.clinic_id = b.clinic_id
            WHERE b.clinic_id = $1 AND st.user_id = $2
              AND lower(b.slot_range) >= CURRENT_DATE
              AND lower(b.slot_range) < CURRENT_DATE + INTERVAL '1 day'
            ORDER BY lower(b.slot_range)
            """,
            clinic_id, user_id,
        )
    return [dict(row) for row in rows]
