"""Show the full conversation for a contact by phone number."""
import asyncio, asyncpg, os, json

DB = os.getenv("DATABASE_URL")
PHONE = "+447915262257"  # Louise

async def main():
    conn = await asyncpg.connect(DB)

    print("=== Conversation context ===")
    rows = await conn.fetch("""
        SELECT conv.conversation_id, conv.status, conv.context
        FROM bot.conversations conv
        JOIN bot.contacts c ON c.contact_id = conv.contact_id
        WHERE c.channel_address = $1
        ORDER BY conv.created_at DESC
        LIMIT 2
    """, PHONE)
    for r in rows:
        ctx = r["context"]
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        print(f"  conv_id={r['conversation_id']} status={r['status']}")
        print(f"  context: {json.dumps(ctx, default=str, indent=2)}")

    print("\n=== Messages in conversation ===")
    rows = await conn.fetch("""
        SELECT m.direction, m.text, m.created_at, m.payload->>'send_status' as send_status
        FROM bot.messages m
        JOIN bot.contacts c ON c.contact_id = m.contact_id
        WHERE c.channel_address = $1
        ORDER BY m.created_at ASC
    """, PHONE)
    for r in rows:
        print(f"  [{r['direction']}] {r['created_at'].strftime('%H:%M:%S')} | {r['text'][:120]}")

    await conn.close()

asyncio.run(main())
