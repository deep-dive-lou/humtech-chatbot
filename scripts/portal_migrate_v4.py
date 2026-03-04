"""
Portal v4 schema migration — run locally with doadmin DATABASE_URL.

Usage:
  python scripts/portal_migrate_v4.py

Adds:
  - 'signature' value to public.template_item_type enum
  - file_key column on portal.template_items (staff uploads doc to sign)
  - file_key column on portal.doc_request_items (cloned from template)
  - signature_file_key column on portal.doc_request_items (client's drawn signature)
  - Re-grants humtech_bot access
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
        print("Running portal v4 migration...")

        # 1. Add 'signature' to template_item_type enum (if not already present)
        vals = await conn.fetch(
            """SELECT enumlabel FROM pg_enum
               JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
               WHERE pg_type.typname = 'template_item_type'
               ORDER BY enumsortorder"""
        )
        existing = {r["enumlabel"] for r in vals}
        if "signature" not in existing:
            await conn.execute(
                "ALTER TYPE public.template_item_type ADD VALUE IF NOT EXISTS 'signature'"
            )
            print("  Added 'signature' to template_item_type enum")
        else:
            print("  'signature' already in template_item_type enum")

        # 2. Add file_key to template_items (for staff-uploaded docs to sign)
        await conn.execute(
            "ALTER TABLE portal.template_items ADD COLUMN IF NOT EXISTS file_key TEXT"
        )
        print("  Added file_key to portal.template_items")

        # 3. Add file_key to doc_request_items (cloned from template)
        await conn.execute(
            "ALTER TABLE portal.doc_request_items ADD COLUMN IF NOT EXISTS file_key TEXT"
        )
        print("  Added file_key to portal.doc_request_items")

        # 4. Add signature_file_key to doc_request_items (client's drawn signature PNG)
        await conn.execute(
            "ALTER TABLE portal.doc_request_items ADD COLUMN IF NOT EXISTS signature_file_key TEXT"
        )
        print("  Added signature_file_key to portal.doc_request_items")

        # 5. Re-grant permissions
        for table in ["portal.template_items", "portal.doc_request_items"]:
            await conn.execute(
                f"GRANT SELECT, INSERT, UPDATE ON {table} TO humtech_bot"
            )
        print("  Grants applied")

        print("Portal v4 migration complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
