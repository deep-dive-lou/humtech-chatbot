"""Quick verification of monitoring views."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    import asyncpg
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        # Conversation summary
        rows = await conn.fetch("SELECT * FROM monitoring.conversation_summary LIMIT 3")
        print(f"conversation_summary: {len(rows)} rows (showing up to 3)")
        for r in rows:
            print(f"  {r['contact_name']} | {r['status']} | in={r['inbound_turns']} out={r['outbound_turns']} | booking={r['has_booking']} | intent={r['last_intent']}")

        # Daily funnel
        rows = await conn.fetch("SELECT * FROM monitoring.daily_funnel ORDER BY day DESC LIMIT 5")
        print(f"\ndaily_funnel: {len(rows)} rows")
        for r in rows:
            print(f"  {r['day']} | total={r['total_conversations']} booked={r['booked']} declined={r['declined']} human={r['wants_human']} engaged={r['engaged']}")

        # Active alerts
        rows = await conn.fetch("SELECT * FROM monitoring.active_alerts WHERE alert_type IS NOT NULL")
        print(f"\nactive_alerts (flagged): {len(rows)} rows")
        for r in rows:
            print(f"  {r['contact_name']} | {r['alert_type']} | turns={r['inbound_turns']} | intent={r['last_intent']}")

        # Send health
        rows = await conn.fetch("SELECT send_status, COUNT(*) as cnt FROM monitoring.send_health GROUP BY send_status")
        print(f"\nsend_health summary:")
        for r in rows:
            print(f"  {r['send_status']}: {r['cnt']}")

    finally:
        await conn.close()

asyncio.run(main())
