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
            """
            SELECT id
            FROM customers
            WHERE user_id = $1 AND clinic_id = $2
            """,
            user_id,
            clinic_id,
        )
        if customer_id is None:
            raise HTTPException(status_code=403, detail="Customer profile not found for this user")

        service = await conn.fetchrow(
            """
            SELECT price, duration_minutes
            FROM services
            WHERE id = $1 AND clinic_id = $2 AND is_active = TRUE
            """,
            request.service_id,
            clinic_id,
        )
        if service is None:
            raise HTTPException(status_code=404, detail="Service not found or inactive")

        # Validate the selected staff member inside the same tenant and ensure inactive staff
        # cannot receive new bookings. The composite FK in the schema provides the final
        # same-clinic integrity guarantee at INSERT time.
        staff_exists = await conn.fetchval(
            """
            SELECT 1
            FROM staff
            WHERE id = $1 AND clinic_id = $2 AND is_active = TRUE
            """,
            request.staff_id,
            clinic_id,
        )
        if staff_exists is None:
            raise HTTPException(status_code=404, detail="Staff member not found or inactive")

        slot_start = request.slot_start
        slot_end = slot_start + timedelta(minutes=int(service["duration_minutes"]))

        try:
            async with conn.transaction():
                booking_id = await conn.fetchval(
                    """
                    INSERT INTO bookings (
                        clinic_id, customer_id, service_id, staff_id, slot_range, status
                    )
                    VALUES ($1, $2, $3, $4, tstzrange($5, $6, '[)'), 'confirmed')
                    RETURNING id
                    """,
                    clinic_id,
                    customer_id,
                    request.service_id,
                    request.staff_id,
                    slot_start,
                    slot_end,
                )

                await conn.execute(
                    """
                    INSERT INTO audit_logs (
                        clinic_id, action, target_type, target_id, new_values,
                        performed_by_user_id
                    )
                    VALUES ($1, 'CREATE_BOOKING', 'booking', $2, $3::jsonb, $4)
                    """,
                    clinic_id,
                    booking_id,
                    '{"status":"confirmed"}',
                    user_id,
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
