"""Quick DB check for bot contact metadata and message send status."""
import asyncio
import asyncpg
import os
import json

DB = os.getenv("DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB)

    print("=== Recent outbound messages ===")
    rows = await conn.fetch("""
        SELECT message_id,
               contact_id,
               created_at,
               payload->>'send_status' as status,
               payload->>'send_last_error' as err,
               payload->>'send_attempts' as attempts
        FROM bot.messages
        WHERE direction='outbound'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    for r in rows:
        print(dict(r))

    print("\n=== Recent contacts (metadata) ===")
    rows = await conn.fetch("""
        SELECT contact_id, channel_address, display_name, metadata
        FROM bot.contacts
        ORDER BY created_at DESC
        LIMIT 5
    """)
    for r in rows:
        print(dict(r))

    await conn.close()

asyncio.run(main())