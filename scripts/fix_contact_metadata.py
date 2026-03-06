"""
Fix contacts with empty metadata by backfilling contactId from inbound_events.
Also resets any 'failed' outbound messages for those contacts back to 'pending'
so they get retried.
"""
import asyncio
import asyncpg
import os
import json

DB = os.getenv("DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB)

    # Find contacts with empty metadata that have a corresponding inbound event with contactId
    print("=== Finding contacts with missing contactId ===")
    rows = await conn.fetch("""
        SELECT DISTINCT
            c.contact_id,
            c.channel_address,
            c.display_name,
            ie.payload->>'contactId' AS ghl_contact_id
        FROM bot.contacts c
        JOIN bot.inbound_events ie
          ON ie.tenant_id = c.tenant_id
         AND ie.channel_address = c.channel_address
        WHERE (c.metadata IS NULL OR c.metadata = '{}'::jsonb)
          AND ie.payload->>'contactId' IS NOT NULL
    """)

    if not rows:
        print("No contacts to fix.")
        await conn.close()
        return

    for r in rows:
        contact_id = r["contact_id"]
        ghl_id = r["ghl_contact_id"]
        print(f"  Patching {r['display_name']} ({r['channel_address']}) → contactId={ghl_id}")

        # Update contact metadata
        await conn.execute("""
            UPDATE bot.contacts
            SET metadata = jsonb_build_object('contactId', $2::text),
                updated_at = now()
            WHERE contact_id = $1::uuid
        """, contact_id, ghl_id)

        # Reset failed outbound messages back to pending (attempt 0)
        reset = await conn.execute("""
            UPDATE bot.messages
            SET payload = payload
                || '{"send_status": "pending"}'::jsonb
                || '{"send_attempts": 0}'::jsonb
                || '{"send_next_at": null}'::jsonb
                || '{"send_last_error": null}'::jsonb
            WHERE contact_id = $1::uuid
              AND direction = 'outbound'
              AND payload->>'send_status' = 'failed'
        """, contact_id)
        print(f"  → Reset messages: {reset}")

    print("\nDone.")
    await conn.close()

asyncio.run(main())