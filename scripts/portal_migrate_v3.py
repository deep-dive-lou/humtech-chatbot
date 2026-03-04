"""
Portal v3 schema migration — run locally with doadmin DATABASE_URL.

Usage:
  python scripts/portal_migrate_v3.py

Adds:
  - 'cancelled' and 'completed' to public.request_status enum
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
        print("Running portal v3 migration...")

        # Check current enum values
        vals = await conn.fetch(
            """SELECT enumlabel FROM pg_enum
               JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
               WHERE pg_type.typname = 'request_status'
               ORDER BY enumsortorder"""
        )
        existing = {r["enumlabel"] for r in vals}
        print(f"Current request_status values: {existing}")

        # ALTER TYPE ... ADD VALUE must run outside a transaction.
        # asyncpg runs execute() outside implicit transactions by default.
        for new_val in ["cancelled", "completed"]:
            if new_val not in existing:
                await conn.execute(
                    f"ALTER TYPE public.request_status ADD VALUE '{new_val}'"
                )
                print(f"  Added: {new_val}")
            else:
                print(f"  Already exists: {new_val}")

        # Verify
        vals = await conn.fetch(
            """SELECT enumlabel FROM pg_enum
               JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
               WHERE pg_type.typname = 'request_status'
               ORDER BY enumsortorder"""
        )
        print(f"Final request_status values: {[r['enumlabel'] for r in vals]}")

        print("\nMigration complete.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
