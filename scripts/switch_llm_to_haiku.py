"""
Switch HumTech tenant LLM model to Claude Haiku.
Run locally with doadmin URL from .env.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TENANT_SLUG = "humtech"
NEW_MODEL = "claude-haiku-4-5-20251001"


async def main():
    import asyncpg

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT tenant_id::text, settings FROM core.tenants WHERE tenant_slug = $1",
            TENANT_SLUG,
        )
        if not row:
            print(f"ERROR: tenant '{TENANT_SLUG}' not found")
            return

        tenant_id = row["tenant_id"]
        settings = json.loads(row["settings"]) if row["settings"] else {}
        llm = settings.get("llm", {})

        old_model = llm.get("model", "(not set)")
        print(f"Tenant: {TENANT_SLUG} ({tenant_id})")
        print(f"Current LLM model: {old_model}")

        llm["model"] = NEW_MODEL
        settings["llm"] = llm

        await conn.execute(
            "UPDATE core.tenants SET settings = $1::jsonb WHERE tenant_id = $2::uuid",
            json.dumps(settings),
            tenant_id,
        )
        print(f"Updated LLM model: {old_model} -> {NEW_MODEL}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
