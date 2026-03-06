"""
Update HumTech tenant bot settings with new persona fields.
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

NEW_BOT_FIELDS = {
    "assistant_name": "Ariyah",
    "business_name": "HumTech",
    "business_description": "a revenue acceleration consultancy that helps B2B businesses grow through AI-powered systems",
    "call_purpose": "a short discovery call to understand your current setup and see if there's a fit",
    "call_with": "Chris, our commercial director",
    "call_duration": "15 minutes",
    "tone": "Warm, professional, concise. Friendly but not overly casual. Never pushy — guide, don't pressure.",
    "key_objection_responses": {
        "what_is_this": "We help businesses like yours accelerate revenue using AI-powered systems. The call is just a quick chat to see if there's a fit — no pressure.",
        "is_this_sales": "It's not a sales pitch — it's a genuine conversation about your business and whether we can help. Takes about 15 minutes.",
        "too_busy": "Totally understand — we keep it short, just 15 minutes. Happy to find a time that works around your schedule.",
        "already_have_provider": "No worries — a lot of our clients had existing setups too. Might still be worth a quick chat to compare approaches.",
    },
}


async def main():
    import asyncpg

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Read current settings
        row = await conn.fetchrow(
            "SELECT tenant_id::text, settings FROM core.tenants WHERE tenant_slug = $1", TENANT_SLUG
        )
        if not row:
            print(f"ERROR: tenant '{TENANT_SLUG}' not found")
            return

        tenant_id = row["tenant_id"]
        settings = json.loads(row["settings"]) if row["settings"] else {}
        bot = settings.get("bot", {})

        print(f"Tenant: {TENANT_SLUG} ({tenant_id})")
        print(f"Current bot settings keys: {list(bot.keys())}")

        # Merge new fields (don't overwrite existing values)
        for key, value in NEW_BOT_FIELDS.items():
            if key not in bot or not bot[key]:
                bot[key] = value
                print(f"  SET {key} = {repr(value)[:80]}")
            else:
                print(f"  SKIP {key} (already set: {repr(bot[key])[:80]})")

        settings["bot"] = bot

        # Write back
        await conn.execute(
            "UPDATE core.tenants SET settings = $1::jsonb WHERE tenant_id = $2::uuid",
            json.dumps(settings),
            tenant_id,
        )
        print("\nDone — settings updated.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
