"""Close all test/simulator conversations, keeping real leads open."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

KEEP_OPEN = {
    "+441200871229",   # Jill
    "+447500565858",   # Cornel
}

async def main():
    import asyncpg
    url = os.environ["DATABASE_URL"].replace("humtech_bot", "doadmin")
    conn = await asyncpg.connect(url)
    try:
        result = await conn.execute("""
            UPDATE bot.conversations c
            SET status = 'closed', updated_at = now()
            FROM bot.contacts ct
            WHERE ct.contact_id = c.contact_id
              AND c.status = 'open'
              AND ct.channel_address NOT IN (SELECT unnest($1::text[]))
        """, list(KEEP_OPEN))
        print(f"Result: {result}")

        remaining = await conn.fetch("""
            SELECT ct.display_name, ct.channel_address
            FROM bot.conversations c
            JOIN bot.contacts ct ON ct.contact_id = c.contact_id
            WHERE c.status = 'open'
        """)
        print(f"Remaining open: {len(remaining)}")
        for r in remaining:
            print(f"  {r['display_name']} | {r['channel_address']}")

    finally:
        await conn.close()

asyncio.run(main())
