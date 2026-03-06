"""Reset failed outbound messages back to pending so they get retried."""
import asyncio, asyncpg, os

DB = os.getenv("DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB)
    result = await conn.execute("""
        UPDATE bot.messages
        SET payload = payload
            || '{"send_status": "pending"}'::jsonb
            || '{"send_attempts": 0}'::jsonb
            || '{"send_next_at": null}'::jsonb
            || '{"send_last_error": null}'::jsonb
        WHERE direction = 'outbound'
          AND payload->>'send_status' IN ('failed', 'pending')
          AND created_at > now() - interval '2 hours'
    """)
    print(f"Reset: {result}")
    await conn.close()

asyncio.run(main())