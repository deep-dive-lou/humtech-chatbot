import asyncio, asyncpg, os, json

DB = os.getenv("DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB)

    print("=== Louise's GHL event payload (full) ===")
    rows = await conn.fetch("""
        SELECT inbound_event_id, event_type, channel_address, received_at, payload
        FROM bot.inbound_events
        WHERE channel_address = '+447915262257'
        ORDER BY received_at DESC
        LIMIT 3
    """)
    for r in rows:
        d = dict(r)
        p = d['payload']
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                pass
        print(f"  {d['received_at']} | {d['event_type']}")
        print(f"  payload: {json.dumps(p, default=str, indent=2)}")
        print()

    await conn.close()

asyncio.run(main())