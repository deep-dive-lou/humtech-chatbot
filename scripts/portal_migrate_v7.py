"""
Portal v7 schema migration — run locally with doadmin DATABASE_URL.

Usage:
  python scripts/portal_migrate_v7.py

Adds:
  - portal.tenants: sending_domain, sending_from_email, domain_verified columns
  - portal.templates: email_subject, email_body columns
  - portal.email_sends table (tracks every email sent)
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
        print("Running portal v7 migration...")

        # 1. Add email config columns to portal.tenants
        for col, typ in [
            ("sending_domain", "TEXT"),
            ("sending_from_email", "TEXT"),
            ("domain_verified", "BOOLEAN DEFAULT false"),
        ]:
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'portal' AND table_name = 'tenants' "
                "AND column_name = $1", col,
            )
            if not exists:
                await conn.execute(
                    f"ALTER TABLE portal.tenants ADD COLUMN {col} {typ}"
                )
                print(f"  Added portal.tenants.{col}")
            else:
                print(f"  portal.tenants.{col} already exists")

        # 2. Add email fields to portal.templates
        for col, typ in [
            ("email_subject", "TEXT"),
            ("email_body", "TEXT"),
        ]:
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'portal' AND table_name = 'templates' "
                "AND column_name = $1", col,
            )
            if not exists:
                await conn.execute(
                    f"ALTER TABLE portal.templates ADD COLUMN {col} {typ}"
                )
                print(f"  Added portal.templates.{col}")
            else:
                print(f"  portal.templates.{col} already exists")

        # 3. Create portal.email_sends table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS portal.email_sends (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id       UUID NOT NULL REFERENCES portal.tenants(id),
                request_id      UUID NOT NULL REFERENCES portal.doc_requests(id),
                recipient_email TEXT NOT NULL,
                from_email      TEXT NOT NULL,
                subject         TEXT NOT NULL,
                ses_message_id  TEXT,
                sent_at         TIMESTAMPTZ DEFAULT now()
            )
        """)
        print("  Created portal.email_sends")

        # 4. Grant permissions to humtech_bot
        await conn.execute(
            "GRANT SELECT, INSERT, UPDATE ON portal.tenants TO humtech_bot"
        )
        await conn.execute(
            "GRANT SELECT, INSERT ON portal.email_sends TO humtech_bot"
        )
        print("  Grants applied")

        print("Portal v7 migration complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
