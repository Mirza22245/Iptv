"""Clinical customer cards, journal notes, templates, consents and image metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth import require_role
from app.database import Database, get_database

router = APIRouter(prefix="/api/clinical", tags=["Clinical"])


class JournalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int = Field(gt=0)
    treatment: str | None = None
    area: str | None = None
    indication: str | None = None
    assessment: str | None = None
    plan: str | None = None
    products_used: str | None = None
    dosage: str | None = None
    lot_batch: str | None = None
    result: str | None = None
    complications: str | None = None
    aftercare: str | None = None


class JournalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    treatment: str | None = None
    area: str | None = None
    indication: str | None = None
    assessment: str | None = None
    plan: str | None = None
    products_used: str | None = None
    dosage: str | None = None
    lot_batch: str | None = None
    result: str | None = None
    complications: str | None = None
    aftercare: str | None = None


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    structure_json: dict[str, Any] = Field(default_factory=dict)


class ConsentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=50)
    signature_data: str = Field(min_length=1)


class ImageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int = Field(gt=0)
    journal_id: int | None = Field(default=None, gt=0)
    image_type: str
    file_path: str = Field(min_length=1, max_length=500)
    area: str | None = Field(default=None, max_length=100)
    is_published: bool = False


async def _customer_access(conn: asyncpg.Connection, customer_id: int, clinic_id: int, user_id: int, role: str) -> None:
    row = await conn.fetchrow(
        "SELECT id FROM customers WHERE id=$1 AND clinic_id=$2 AND ($3::text IN ('staff','admin','superadmin') OR user_id=$4)",
        customer_id, clinic_id, role, user_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")


@router.get("/customers")
async def list_customers(token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    async with db.transaction(clinic_id=int(token["clinic_id"]), user_id=int(token["sub"]), role=str(token["role"])) as conn:
        rows = await conn.fetch("SELECT id, first_name, last_name, email, created_at FROM customers WHERE clinic_id=$1 ORDER BY last_name, first_name", int(token["clinic_id"]))
        return [dict(row) for row in rows]


@router.get("/customers/{customer_id}")
async def customer_card(customer_id: int, token: dict[str, Any] = Depends(require_role("customer", "staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = int(token["clinic_id"]), int(token["sub"]), str(token["role"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        row = await conn.fetchrow("SELECT id, first_name, last_name, email, created_at FROM customers WHERE id=$1 AND clinic_id=$2", customer_id, clinic_id)
        if row is None or (role == "customer" and await conn.fetchval("SELECT user_id FROM customers WHERE id=$1", customer_id) != user_id):
            raise HTTPException(status_code=404, detail="Customer not found")
        return dict(row)


@router.get("/customers/{customer_id}/journals")
async def list_journals(customer_id: int, token: dict[str, Any] = Depends(require_role("customer", "staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = int(token["clinic_id"]), int(token["sub"]), str(token["role"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        await _customer_access(conn, customer_id, clinic_id, user_id, role)
        rows = await conn.fetch("SELECT * FROM journal_notes WHERE customer_id=$1 AND clinic_id=$2 ORDER BY created_at DESC", customer_id, clinic_id)
        return [dict(row) for row in rows]


@router.post("/journals", status_code=status.HTTP_201_CREATED)
async def create_journal(payload: JournalCreate, token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = int(token["clinic_id"]), int(token["sub"]), str(token["role"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        await _customer_access(conn, payload.customer_id, clinic_id, user_id, role)
        row = await conn.fetchrow(
            """INSERT INTO journal_notes (clinic_id, customer_id, author_id, treatment, area, indication, assessment, plan, products_used, dosage, lot_batch, result, complications, aftercare)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING *""",
            clinic_id, payload.customer_id, user_id, payload.treatment, payload.area, payload.indication, payload.assessment,
            payload.plan, payload.products_used, payload.dosage, payload.lot_batch, payload.result, payload.complications, payload.aftercare,
        )
        await conn.execute("INSERT INTO audit_logs (clinic_id, action, target_type, target_id, new_values, performed_by_user_id) VALUES ($1,'CREATE_JOURNAL','journal_note',$2,$3::jsonb,$4)", clinic_id, row["id"], "{}", user_id)
        return dict(row)


@router.put("/journals/{journal_id}")
async def update_journal(journal_id: int, payload: JournalUpdate, token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = int(token["clinic_id"]), int(token["sub"]), str(token["role"])
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields supplied")
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        journal = await conn.fetchrow("SELECT id, is_signed FROM journal_notes WHERE id=$1 AND clinic_id=$2", journal_id, clinic_id)
        if journal is None:
            raise HTTPException(status_code=404, detail="Journal not found")
        if journal["is_signed"]:
            raise HTTPException(status_code=403, detail="Signed journals are locked and cannot be modified")
        allowed = set(JournalUpdate.model_fields)
        fields = [key for key in values if key in allowed]
        assignments = ", ".join(f"{key}=${i+3}" for i, key in enumerate(fields))
        params = [journal_id, clinic_id, *[values[key] for key in fields]]
        await conn.execute(f"UPDATE journal_notes SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=$1 AND clinic_id=$2 AND is_signed=FALSE", *params)
        await conn.execute("INSERT INTO audit_logs (clinic_id, action, target_type, target_id, new_values, performed_by_user_id) VALUES ($1,'UPDATE_JOURNAL','journal_note',$2,$3::jsonb,$4)", clinic_id, journal_id, "{}", user_id)
        return {"success": True, "journal_id": journal_id}


@router.post("/journals/{journal_id}/sign")
async def sign_journal(journal_id: int, token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = int(token["clinic_id"]), int(token["sub"]), str(token["role"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        row = await conn.fetchrow("SELECT id, is_signed FROM journal_notes WHERE id=$1 AND clinic_id=$2", journal_id, clinic_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Journal not found")
        if row["is_signed"]:
            raise HTTPException(status_code=400, detail="Journal is already signed")
        signed_at = datetime.now(timezone.utc)
        await conn.execute("UPDATE journal_notes SET is_signed=TRUE, signed_at=$1, signed_by_id=$2, updated_at=$1 WHERE id=$3 AND clinic_id=$4 AND is_signed=FALSE", signed_at, user_id, journal_id, clinic_id)
        await conn.execute("INSERT INTO audit_logs (clinic_id, action, target_type, target_id, new_values, performed_by_user_id) VALUES ($1,'SIGN_JOURNAL','journal_note',$2,$3::jsonb,$4)", clinic_id, journal_id, "{}", user_id)
        return {"success": True, "journal_id": journal_id, "signed_at": signed_at}


@router.get("/templates")
async def list_templates(token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    async with db.transaction(clinic_id=int(token["clinic_id"]), user_id=int(token["sub"]), role=str(token["role"])) as conn:
        rows = await conn.fetch("SELECT id,title,structure_json,is_active,created_at FROM journal_templates WHERE clinic_id=$1 ORDER BY title", int(token["clinic_id"]))
        return [dict(row) for row in rows]


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(payload: TemplateCreate, token: dict[str, Any] = Depends(require_role("admin", "superadmin")), db: Database = Depends(get_database)):
    async with db.transaction(clinic_id=int(token["clinic_id"]), user_id=int(token["sub"]), role=str(token["role"])) as conn:
        row = await conn.fetchrow("INSERT INTO journal_templates (clinic_id,title,structure_json,created_by_user_id) VALUES ($1,$2,$3::jsonb,$4) RETURNING *", int(token["clinic_id"]), payload.title, payload.structure_json, int(token["sub"]))
        return dict(row)


@router.post("/consents", status_code=status.HTTP_201_CREATED)
async def create_consent(payload: ConsentCreate, token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = int(token["clinic_id"]), int(token["sub"]), str(token["role"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        await _customer_access(conn, payload.customer_id, clinic_id, user_id, role)
        row = await conn.fetchrow("INSERT INTO consents (clinic_id,customer_id,title,version,signature_data,signed_by_user_id) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *", clinic_id, payload.customer_id, payload.title, payload.version, payload.signature_data, user_id)
        return dict(row)


@router.get("/customers/{customer_id}/consents")
async def list_consents(customer_id: int, token: dict[str, Any] = Depends(require_role("customer", "staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = int(token["clinic_id"]), int(token["sub"]), str(token["role"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        await _customer_access(conn, customer_id, clinic_id, user_id, role)
        rows = await conn.fetch("SELECT id,title,version,signed_at,signed_by_user_id FROM consents WHERE clinic_id=$1 AND customer_id=$2 ORDER BY signed_at DESC", clinic_id, customer_id)
        return [dict(row) for row in rows]


@router.post("/images", status_code=status.HTTP_201_CREATED)
async def create_image(payload: ImageCreate, token: dict[str, Any] = Depends(require_role("staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    if payload.image_type not in {"before", "after"}:
        raise HTTPException(status_code=422, detail="image_type must be before or after")
    clinic_id, user_id, role = int(token["clinic_id"]), int(token["sub"]), str(token["role"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        await _customer_access(conn, payload.customer_id, clinic_id, user_id, role)
        row = await conn.fetchrow("INSERT INTO before_after_images (clinic_id,customer_id,journal_id,image_type,file_path,area,is_published,created_by_user_id) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id,customer_id,journal_id,image_type,file_path,area,is_published,created_at", clinic_id, payload.customer_id, payload.journal_id, payload.image_type, payload.file_path, payload.area, payload.is_published, user_id)
        return dict(row)


@router.get("/customers/{customer_id}/images")
async def list_images(customer_id: int, token: dict[str, Any] = Depends(require_role("customer", "staff", "admin", "superadmin")), db: Database = Depends(get_database)):
    clinic_id, user_id, role = int(token["clinic_id"]), int(token["sub"]), str(token["role"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        await _customer_access(conn, customer_id, clinic_id, user_id, role)
        rows = await conn.fetch("SELECT id,journal_id,image_type,file_path,area,is_published,created_at FROM before_after_images WHERE clinic_id=$1 AND customer_id=$2 ORDER BY created_at DESC", clinic_id, customer_id)
        return [dict(row) for row in rows]
