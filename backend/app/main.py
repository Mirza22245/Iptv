"""Lydia Core FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.database import get_database, shutdown_database, startup_database
from app.routers.auth import router as auth_router
from app.routers.bookings import router as bookings_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    await startup_database()
    try:
        yield
    finally:
        await shutdown_database()


app = FastAPI(
    title="Lydia Core API",
    version="0.3.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(bookings_router)


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
