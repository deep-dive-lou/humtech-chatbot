"""Identify and close test/simulator conversations."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    import asyncpg
    url = os.environ["DATABASE_URL"].replace("humtech_bot", "doadmin")
    conn = await asyncpg.connect(url)
    try:
        # Count open conversations
        total = await conn.fetchval("SELECT COUNT(*) FROM bot.conversations WHERE status = 'open'")
        print(f"Total open conversations: {total}")

        # Show all open conversations with their contact info
        rows = await conn.fetch("""
            SELECT c.conversation_id::text, ct.display_name, ct.channel_address,
                   c.last_intent, c.created_at, c.updated_at,
                   c.context->'booked_booking'->>'slot' IS NOT NULL AS has_booking,
                   (SELECT COUNT(*) FROM bot.messages m
                    WHERE m.conversation_id = c.conversation_id AND m.direction = 'inbound') AS inbound_turns,
                   (SELECT COUNT(*) FROM bot.messages m
                    WHERE m.conversation_id = c.conversation_id AND m.direction = 'outbound') AS outbound_turns
            FROM bot.conversations c
            JOIN bot.contacts ct ON ct.contact_id = c.contact_id
            WHERE c.status = 'open'
            ORDER BY c.created_at DESC
        """)

        # Categorize: simulator contacts have fake phone numbers or are from test runs
        # The simulator uses channel_address patterns we can identify
        print(f"\n=== ALL OPEN CONVERSATIONS ({len(rows)}) ===")
        real = []
        test = []
        for r in rows:
            addr = r['channel_address'] or ''
            name = r['display_name'] or 'unknown'
            is_test = (
                addr.startswith('+1555')  # simulator fake numbers
                or addr.startswith('+15550')
                or addr.startswith('sim-')
                or 'debug' in name.lower()
                or 'test' in name.lower()
                or 'e2e' in name.lower()
                or addr == '+447915262257'  # Louise test contact
            )
            entry = {
                'id': r['conversation_id'][:8],
                'name': name,
                'addr': addr,
                'intent': r['last_intent'],
                'created': str(r['created_at'])[:16],
                'in': r['inbound_turns'],
                'out': r['outbound_turns'],
                'booking': r['has_booking'],
            }
            if is_test:
                test.append(entry)
            else:
                real.append(entry)

        print(f"\nREAL conversations: {len(real)}")
        for r in real:
            print(f"  {r['id']} | {r['name']:20s} | {r['addr']:15s} | in={r['in']} out={r['out']} | intent={r['intent']} | {r['created']}")

        print(f"\nTEST conversations (will close): {len(test)}")
        for t in test[:10]:
            print(f"  {t['id']} | {t['name']:20s} | {t['addr']:15s} | in={t['in']} out={t['out']} | intent={t['intent']} | {t['created']}")
        if len(test) > 10:
            print(f"  ... and {len(test) - 10} more")

        # Find remaining — conversations with no messages might also be noise
        no_msgs = [r for r in real if r['in'] == 0 and r['out'] == 0]
        if no_msgs:
            print(f"\nREAL with ZERO messages (likely orphaned): {len(no_msgs)}")
            for r in no_msgs:
                print(f"  {r['id']} | {r['name']:20s} | {r['addr']:15s} | {r['created']}")

    finally:
        await conn.close()

asyncio.run(main())
