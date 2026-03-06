"""Create a test conversation that triggers a stalled alert, then clean up after."""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

async def main():
    import asyncpg
    url = os.environ["DATABASE_URL"].replace("humtech_bot", "doadmin")
    conn = await asyncpg.connect(url)

    action = sys.argv[1] if len(sys.argv) > 1 else "create"

    if action == "create":
        # Get humtech tenant_id
        tenant_id = await conn.fetchval(
            "SELECT tenant_id FROM core.tenants WHERE tenant_slug = 'humtech'"
        )

        # Create a test contact
        contact_id = await conn.fetchval("""
            INSERT INTO bot.contacts (tenant_id, channel, channel_address, display_name)
            VALUES ($1, 'sms', '+440000000000', 'Monitor Test')
            ON CONFLICT (tenant_id, channel, channel_address)
            DO UPDATE SET display_name = 'Monitor Test'
            RETURNING contact_id
        """, tenant_id)

        # Create a stalled conversation (last_inbound 3 hours ago, no outbound)
        stale_time = datetime.now(timezone.utc) - timedelta(hours=3)
        conv_id = await conn.fetchval("""
            INSERT INTO bot.conversations (tenant_id, contact_id, status, last_step, last_intent,
                                           context, last_inbound_at, created_at, updated_at)
            VALUES ($1, $2, 'open', 'start', 'engage', '{}', $3, $3, $3)
            RETURNING conversation_id
        """, tenant_id, contact_id, stale_time)

        print(f"Created test conversation: {conv_id}")
        print(f"Contact: Monitor Test (+440000000000)")
        print(f"last_inbound_at: {stale_time}")
        print("This should trigger a 'stalled' alert on the next monitor cycle (within 5 min)")

    elif action == "cleanup":
        result = await conn.execute("""
            UPDATE bot.conversations c
            SET status = 'closed', updated_at = now()
            FROM bot.contacts ct
            WHERE ct.contact_id = c.contact_id
              AND ct.channel_address = '+440000000000'
              AND c.status = 'open'
        """)
        print(f"Cleaned up: {result}")

    await conn.close()

asyncio.run(main())
