"""
Portal v5 schema migration — run locally with doadmin DATABASE_URL.

Usage:
  python scripts/portal_migrate_v5.py

Adds signature positioning columns so staff can define where
the client signs on a PDF, plus a signed_pdf_key for the merged result.

Columns added:
  portal.template_items:     sig_page, sig_x, sig_y, sig_w, sig_h
  portal.doc_request_items:  sig_page, sig_x, sig_y, sig_w, sig_h, signed_pdf_key
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
        print("Running portal v5 migration...")

        # 1. Signature position on template_items
        for col, typ in [
            ("sig_page", "INTEGER"),
            ("sig_x", "DOUBLE PRECISION"),
            ("sig_y", "DOUBLE PRECISION"),
            ("sig_w", "DOUBLE PRECISION"),
            ("sig_h", "DOUBLE PRECISION"),
        ]:
            await conn.execute(
                f"ALTER TABLE portal.template_items ADD COLUMN IF NOT EXISTS {col} {typ}"
            )
        print("  Added sig_page/x/y/w/h to portal.template_items")

        # 2. Signature position + signed PDF on doc_request_items
        for col, typ in [
            ("sig_page", "INTEGER"),
            ("sig_x", "DOUBLE PRECISION"),
            ("sig_y", "DOUBLE PRECISION"),
            ("sig_w", "DOUBLE PRECISION"),
            ("sig_h", "DOUBLE PRECISION"),
            ("signed_pdf_key", "TEXT"),
        ]:
            await conn.execute(
                f"ALTER TABLE portal.doc_request_items ADD COLUMN IF NOT EXISTS {col} {typ}"
            )
        print("  Added sig_page/x/y/w/h/signed_pdf_key to portal.doc_request_items")

        # 3. Re-grant permissions
        for table in ["portal.template_items", "portal.doc_request_items"]:
            await conn.execute(
                f"GRANT SELECT, INSERT, UPDATE ON {table} TO humtech_bot"
            )
        print("  Grants applied")

        print("Portal v5 migration complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
