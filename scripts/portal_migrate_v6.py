"""
Portal v6 schema migration — run locally with doadmin DATABASE_URL.

Usage:
  python scripts/portal_migrate_v6.py

Adds:
  - public.zone_type enum (signature, text, date)
  - portal.template_item_zones table (staff defines zones on template items)
  - portal.request_item_zones table (cloned to requests, client fills these)
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)


async def migrate():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        print("Running portal v6 migration...")

        # 1. Create zone_type enum (must be outside transaction)
        type_exists = await conn.fetchval(
            "SELECT 1 FROM pg_type WHERE typname = 'zone_type'"
        )
        if not type_exists:
            await conn.execute(
                "CREATE TYPE public.zone_type AS ENUM ('signature', 'text', 'date')"
            )
            print("  Created public.zone_type enum")
        else:
            print("  public.zone_type enum already exists")

        # 2. Create portal.template_item_zones
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS portal.template_item_zones (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                template_item_id UUID NOT NULL
                    REFERENCES portal.template_items(id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL,
                zone_type public.zone_type NOT NULL,
                label TEXT NOT NULL,
                page INT NOT NULL DEFAULT 0,
                x DOUBLE PRECISION NOT NULL,
                y DOUBLE PRECISION NOT NULL,
                w DOUBLE PRECISION NOT NULL,
                h DOUBLE PRECISION NOT NULL,
                sort_order INT NOT NULL DEFAULT 0,
                required BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        print("  Created portal.template_item_zones")

        # 3. Create portal.request_item_zones
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS portal.request_item_zones (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_item_id UUID NOT NULL
                    REFERENCES portal.doc_request_items(id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL,
                zone_type public.zone_type NOT NULL,
                label TEXT NOT NULL,
                page INT NOT NULL DEFAULT 0,
                x DOUBLE PRECISION NOT NULL,
                y DOUBLE PRECISION NOT NULL,
                w DOUBLE PRECISION NOT NULL,
                h DOUBLE PRECISION NOT NULL,
                sort_order INT NOT NULL DEFAULT 0,
                required BOOLEAN NOT NULL DEFAULT true,
                value TEXT,
                signature_file_key TEXT,
                filled_at TIMESTAMPTZ
            )
        """)
        print("  Created portal.request_item_zones")

        # 4. Grant permissions to humtech_bot
        for table in ["portal.template_item_zones", "portal.request_item_zones"]:
            await conn.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO humtech_bot"
            )
        print("  Grants applied")

        print("Portal v6 migration complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
