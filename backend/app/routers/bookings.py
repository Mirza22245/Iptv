"""Customer booking endpoints with database-enforced overlap protection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import require_role
from app.database import Database, get_database

router = APIRouter(prefix="/api/portal", tags=["Bookings"])


class BookingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    slot_start: datetime

    @field_validator("slot_start")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("slot_start must include a timezone")
        return value.astimezone(timezone.utc)


class BookingResponse(BaseModel):
    success: bool
    booking_id: int
    slot_start: datetime
    slot_end: datetime
    price: Decimal


@router.post("/bookings", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    request: BookingCreateRequest,
    token_data: dict[str, Any] = Depends(require_role("customer")),
    db: Database = Depends(get_database),
) -> BookingResponse:
    user_id = int(token_data["sub"])
    clinic_id = int(token_data["clinic_id"])

    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=str(token_data["role"])) as conn:
        customer_id = await conn.fetchval(
            "SELECT id FROM customers WHERE user_id = $1 AND clinic_id = $2",
            user_id, clinic_id,
        )
        if customer_id is None:
            raise HTTPException(status_code=403, detail="Customer profile not found for this user")

        service = await conn.fetchrow(
            """
            SELECT price, duration_minutes FROM services
            WHERE id = $1 AND clinic_id = $2 AND is_active = TRUE
            """,
            request.service_id, clinic_id,
        )
        if service is None:
            raise HTTPException(status_code=404, detail="Service not found or inactive")

        staff_exists = await conn.fetchval(
            """
            SELECT 1 FROM staff
            WHERE id = $1 AND clinic_id = $2 AND is_active = TRUE
            """,
            request.staff_id, clinic_id,
        )
        if staff_exists is None:
            raise HTTPException(status_code=404, detail="Staff member not found or inactive")

        slot_start = request.slot_start
        slot_end = slot_start + timedelta(minutes=int(service["duration_minutes"]))

        try:
            booking_id = await conn.fetchval(
                """
                INSERT INTO bookings (clinic_id, customer_id, service_id, staff_id, slot_range, status)
                VALUES ($1, $2, $3, $4, tstzrange($5, $6, '[)'), 'confirmed')
                RETURNING id
                """,
                clinic_id, customer_id, request.service_id, request.staff_id,
                slot_start, slot_end,
            )
            await conn.execute(
                """
                INSERT INTO audit_logs
                    (clinic_id, action, target_type, target_id, new_values, performed_by_user_id)
                VALUES ($1, 'CREATE_BOOKING', 'booking', $2, $3::jsonb, $4)
                """,
                clinic_id, booking_id, '{"status":"confirmed"}', user_id,
            )
        except asyncpg.exceptions.ExclusionViolationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This time slot is already booked for the selected staff member",
            ) from exc

        return BookingResponse(
            success=True,
            booking_id=int(booking_id),
            slot_start=slot_start,
            slot_end=slot_end,
            price=Decimal(service["price"]),
        )


@router.get("/bookings")
async def list_customer_bookings(
    token_data: dict[str, Any] = Depends(require_role("customer")),
    db: Database = Depends(get_database),
) -> list[dict[str, Any]]:
    user_id = int(token_data["sub"])
    clinic_id = int(token_data["clinic_id"])

    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=str(token_data["role"])) as conn:
        rows = await conn.fetch(
            """
            SELECT b.id, b.status,
                   lower(b.slot_range) AS slot_start,
                   upper(b.slot_range) AS slot_end,
                   s.name AS service_name,
                   s.price,
                   st.display_name AS staff_name
            FROM bookings b
            JOIN services s ON s.id = b.service_id AND s.clinic_id = b.clinic_id
            JOIN staff st ON st.id = b.staff_id AND st.clinic_id = b.clinic_id
            WHERE b.clinic_id = $1
              AND b.customer_id IN (
                  SELECT c.id FROM customers c
                  WHERE c.user_id = $2 AND c.clinic_id = $1
              )
            ORDER BY lower(b.slot_range) DESC
            """,
            clinic_id, user_id,
        )
        return [dict(row) for row in rows]


@router.delete("/bookings/{booking_id}")
async def cancel_booking(
    booking_id: int,
    token_data: dict[str, Any] = Depends(require_role("customer")),
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    user_id = int(token_data["sub"])
    clinic_id = int(token_data["clinic_id"])

    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=str(token_data["role"])) as conn:
        row = await conn.fetchrow(
            """
            SELECT b.id
            FROM bookings b
            JOIN customers c ON c.id = b.customer_id AND c.clinic_id = b.clinic_id
            WHERE b.id = $1
              AND b.clinic_id = $2
              AND c.user_id = $3
              AND b.status <> 'cancelled'
            FOR UPDATE
            """,
            booking_id, clinic_id, user_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Booking not found or already cancelled")

        await conn.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = $1 AND clinic_id = $2",
            booking_id, clinic_id,
        )
        await conn.execute(
            """
            INSERT INTO audit_logs
                (clinic_id, action, target_type, target_id, new_values, performed_by_user_id)
            VALUES ($1, 'CANCEL_BOOKING', 'booking', $2, '{"status":"cancelled"}'::jsonb, $3)
            """,
            clinic_id, booking_id, user_id,
        )

    return {"success": True, "booking_id": booking_id, "status": "cancelled"}
