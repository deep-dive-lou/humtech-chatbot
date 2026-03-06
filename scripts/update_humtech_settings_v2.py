"""
Update HumTech tenant settings with corrected values.
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
        bot = settings.get("bot", {})
        llm = settings.get("llm", {})

        print(f"Tenant: {TENANT_SLUG} ({tenant_id})")
        print()

        # --- Bot settings updates ---
        updates = {
            "context": "HumTech, an innovated tech company, offering a revenue growth engine.",
            "call_with": "Chris, our sales and operations director",
            "call_duration": "30 minutes",
            "business_description": "a revenue growth engine that helps B2B businesses grow through AI-powered systems and on demand multi disciplinary team",
            "first_touch_template": "Hi {name_part}, this is Ariyah from HumTech.\n\nThe next step is a short call with Chris to walk through your results.\n\nI can offer:\n- {slot_1}\n- {slot_2}\n\nWhich works best?",
            "persona": "",  # Clear old persona — redundant with new fields
            "key_objection_responses": {
                "too_busy": "Totally understand \u2014 we keep it short, just 30 minutes. Happy to find a time that works around your schedule.",
                "what_is_this": "We help businesses like yours accelerate revenue using AI-powered systems. The call is just a quick chat to see if there's a fit \u2014 no pressure.",
                "is_this_sales": "It's not a sales pitch \u2014 it's a genuine conversation about your business and whether we can help. Takes about 30 minutes.",
                "already_have_provider": "No worries \u2014 a lot of our clients had existing setups too. Might still be worth a quick chat to compare approaches.",
            },
        }

        for key, value in updates.items():
            old = bot.get(key)
            bot[key] = value
            old_display = repr(old)[:60] if old else "(empty)"
            new_display = repr(value)[:60]
            print(f"  bot.{key}: {old_display} -> {new_display}")

        settings["bot"] = bot

        # --- LLM settings updates ---
        llm["temperature"] = 0.2
        print(f"  llm.temperature: {0.0} -> {0.2}")
        settings["llm"] = llm

        # Write back
        await conn.execute(
            "UPDATE core.tenants SET settings = $1::jsonb WHERE tenant_id = $2::uuid",
            json.dumps(settings),
            tenant_id,
        )
        print("\nDone -- settings updated.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
