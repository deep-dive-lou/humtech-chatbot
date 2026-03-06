"""Check GHL credentials state for all tenants (shows structure, not raw values)."""
import asyncio, asyncpg, os
from datetime import datetime, timezone
from app.utils.crypto import decrypt_credentials

DB = os.getenv("DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB)

    rows = await conn.fetch("""
        SELECT tc.tenant_id, t.tenant_slug, tc.provider, tc.credentials, tc.updated_at
        FROM core.tenant_credentials tc
        JOIN core.tenants t ON t.tenant_id = tc.tenant_id
        ORDER BY tc.updated_at DESC
    """)

    for r in rows:
        try:
            creds = decrypt_credentials(bytes(r["credentials"]))
        except Exception as e:
            creds = {"decrypt_error": str(e)}

        has_access = bool(creds.get("access_token"))
        has_refresh = bool(creds.get("refresh_token"))
        expires_at = creds.get("expires_at", "missing")

        is_expired = True
        if expires_at and expires_at != "missing":
            try:
                exp = datetime.fromisoformat(expires_at)
                if exp.tzinfo is None:
                    from datetime import timezone
                    exp = exp.replace(tzinfo=timezone.utc)
                is_expired = datetime.now(timezone.utc) >= exp
            except Exception:
                pass

        print(f"tenant={r['tenant_slug']} | provider={r['provider']}")
        print(f"  has_access_token={has_access}  has_refresh_token={has_refresh}")
        print(f"  expires_at={expires_at}  is_expired={is_expired}")
        print(f"  updated_at={r['updated_at']}")
        print()

    await conn.close()

asyncio.run(main())