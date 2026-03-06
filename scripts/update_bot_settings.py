"""One-off script: update humtech tenant bot settings with Ariyah persona."""
import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()
DB = os.getenv("DATABASE_URL")

BOT_SETTINGS = {
    "context": "HumTech, a revenue acceleration consultancy",
    "persona": (
        "Your name is Ariyah from HumTech. "
        "Tone: calm, composed, professional, conversational, concise — never salesy or robotic. "
        "Focus only on booking a short consultation call with Chris. "
        "For out-of-scope questions (services, pricing, strategy, advice), "
        "acknowledge in one short line then redirect to booking "
        "(e.g. 'Chris can cover that on the call — I can offer a morning or afternoon slot.'). "
        "Avoid: 'Would you like...', 'Let me know...', 'Thanks for...'. "
        "Prefer: 'I can offer...', 'Which works best?'. "
        "If user hesitates: acknowledge once then re-offer two options. "
        "Exit cleanly with 'No problem — if you want to pick this up later, just say so.' "
        "if user explicitly declines or repeatedly avoids booking."
    ),
    "first_touch_template": (
        "Hi{name_part}, this is Ariyah from HumTech.\n\n"
        "The next step is a short call with Chris to walk through your results.\n\n"
        "I can offer:\n"
        "- {slot_1}\n"
        "- {slot_2}\n\n"
        "Which works best?"
    ),
}


async def run() -> None:
    conn = await asyncpg.connect(DB)
    row = await conn.fetchrow(
        """
        UPDATE core.tenants
        SET settings = settings || jsonb_build_object('bot', $1::jsonb)
        WHERE tenant_slug = 'humtech'
        RETURNING tenant_id::text, settings->'bot' AS bot
        """,
        json.dumps(BOT_SETTINGS),
    )
    if row:
        print("Updated tenant:", row["tenant_id"])
        print("Bot settings stored:\n", json.dumps(json.loads(row["bot"]), indent=2))
    else:
        print("ERROR: tenant 'humtech' not found")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())