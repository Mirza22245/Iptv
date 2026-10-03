"""Lydia Core FastAPI application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_database, shutdown_database, startup_database
from app.routers.admin import router as dashboard_router
from app.routers.auth import router as auth_router
from app.routers.bookings import router as bookings_router
from app.routers.clinical import router as clinical_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    await startup_database()
    try:
        yield
    finally:
        await shutdown_database()


app = FastAPI(title="Lydia Core API", version="0.6.0", lifespan=lifespan)

cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(auth_router)
app.include_router(bookings_router)
app.include_router(dashboard_router)
app.include_router(clinical_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
async def ready() -> dict[str, str]:
    db = await get_database()
    try:
        async with db.healthcheck() as connection:
            await connection.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database_not_ready") from exc
    return {"status": "ready"}
