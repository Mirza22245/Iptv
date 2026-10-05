"""Idempotent deployment migration/seed runner for hosted Lydia environments."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
DATABASE_DIR = ROOT / "database"

SCHEMA_FILES = [
    DATABASE_DIR / "schema_v2.sql",
    DATABASE_DIR / "phase2_clinical.sql",
    DATABASE_DIR / "phase3_business.sql",
    DATABASE_DIR / "phase3_gift_cards.sql",
]


async def main() -> None:
    dsn = os.environ["DATABASE_URL"]
    seed_demo = os.getenv("LYDIA_SEED_DEMO", "false").lower() == "true"
    conn = await asyncpg.connect(dsn)
    try:
        for path in SCHEMA_FILES:
            await conn.execute(path.read_text(encoding="utf-8"))
        if seed_demo:
            await conn.execute((DATABASE_DIR / "local_seed.sql").read_text(encoding="utf-8"))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
