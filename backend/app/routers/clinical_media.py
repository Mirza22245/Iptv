"""Authenticated local media storage for clinical before/after images."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.auth import require_role
from app.database import Database, get_database

router = APIRouter(prefix="/api/clinical", tags=["Clinical Media"])

MEDIA_ROOT = Path(os.getenv("LYDIA_MEDIA_ROOT", "/app/storage")).resolve()
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@router.post("/customers/{customer_id}/images/upload", status_code=status.HTTP_201_CREATED)
async def upload_image(
    customer_id: int,
    image_type: str = Form(...),
    journal_id: int | None = Form(None),
    area: str | None = Form(None),
    file: UploadFile = File(...),
    token: dict = Depends(require_role("staff", "admin", "superadmin")),
    db: Database = Depends(get_database),
):
    if image_type not in {"before", "after"}:
        raise HTTPException(status_code=422, detail="image_type must be before or after")
    suffix = ALLOWED_TYPES.get(file.content_type or "")
    if suffix is None:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG and WebP images are supported")

    clinic_id = int(token["clinic_id"])
    user_id = int(token["sub"])
    role = str(token["role"])

    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        customer_exists = await conn.fetchval(
            "SELECT 1 FROM customers WHERE id=$1 AND clinic_id=$2",
            customer_id,
            clinic_id,
        )
        if not customer_exists:
            raise HTTPException(status_code=404, detail="Customer not found")
        if journal_id is not None:
            journal_exists = await conn.fetchval(
                "SELECT 1 FROM journal_notes WHERE id=$1 AND clinic_id=$2 AND customer_id=$3",
                journal_id,
                clinic_id,
                customer_id,
            )
            if not journal_exists:
                raise HTTPException(status_code=404, detail="Journal not found")

        relative = Path(str(clinic_id)) / str(customer_id) / f"{uuid4().hex}{suffix}"
        target = (MEDIA_ROOT / relative).resolve()
        if MEDIA_ROOT not in target.parents:
            raise HTTPException(status_code=400, detail="Invalid storage path")
        target.parent.mkdir(parents=True, exist_ok=True)

        total = 0
        try:
            with target.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit")
                    output.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

        row = await conn.fetchrow(
            """INSERT INTO before_after_images
            (clinic_id,customer_id,journal_id,image_type,file_path,area,is_published,created_by_user_id)
            VALUES ($1,$2,$3,$4,$5,$6,FALSE,$7)
            RETURNING id,customer_id,journal_id,image_type,area,created_at""",
            clinic_id,
            customer_id,
            journal_id,
            image_type,
            str(relative),
            area,
            user_id,
        )
        return {**dict(row), "file_url": f"/api/clinical/images/{row['id']}/file"}


@router.get("/images/{image_id}/file")
async def download_image(
    image_id: int,
    token: dict = Depends(require_role("customer", "staff", "admin", "superadmin")),
    db: Database = Depends(get_database),
):
    clinic_id = int(token["clinic_id"])
    user_id = int(token["sub"])
    role = str(token["role"])
    async with db.transaction(clinic_id=clinic_id, user_id=user_id, role=role) as conn:
        row = await conn.fetchrow(
            "SELECT id,customer_id,file_path FROM before_after_images WHERE id=$1 AND clinic_id=$2",
            image_id,
            clinic_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Image not found")
        if role == "customer":
            owns_customer = await conn.fetchval(
                "SELECT 1 FROM customers WHERE id=$1 AND clinic_id=$2 AND user_id=$3",
                row["customer_id"],
                clinic_id,
                user_id,
            )
            if not owns_customer:
                raise HTTPException(status_code=404, detail="Image not found")

    target = (MEDIA_ROOT / row["file_path"]).resolve()
    if MEDIA_ROOT not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")
    return FileResponse(target)
