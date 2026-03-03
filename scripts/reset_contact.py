"""Reset a contact's conversation so the bot treats them as a fresh lead."""
import asyncio, asyncpg, os

DB = os.getenv("DATABASE_URL")
PHONE = "+447915262257"

async def main():
    conn = await asyncpg.connect(DB)

    contact_id = await conn.fetchval("""
        SELECT contact_id FROM bot.contacts
        WHERE channel_address = $1
        LIMIT 1
    """, PHONE)
    print(f"Contact: {contact_id}")

    # Delete messages first (FK dependency)
    deleted_msgs = await conn.execute("""
        DELETE FROM bot.messages
        WHERE conversation_id IN (
            SELECT conversation_id FROM bot.conversations
            WHERE contact_id = $1
        )
    """, contact_id)
    print(f"Deleted messages: {deleted_msgs}")

    # Delete all conversations — new_lead will create a fresh one
    deleted_convos = await conn.execute("""
        DELETE FROM bot.conversations
        WHERE contact_id = $1
    """, contact_id)
    print(f"Deleted conversations: {deleted_convos}")

    await conn.close()

asyncio.run(main())