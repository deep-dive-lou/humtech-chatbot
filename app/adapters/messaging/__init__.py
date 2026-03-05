"""Messaging adapter factory — returns the correct adapter for a tenant's messaging provider."""
from __future__ import annotations

from typing import Any

import asyncpg

from app.adapters.messaging.base import MessagingAdapter


async def get_messaging_adapter(conn: asyncpg.Connection, tenant_id: str) -> MessagingAdapter:
    """Return a MessagingAdapter for the tenant's configured messaging provider."""
    from app.bot.tenants import load_tenant

    tenant = await load_tenant(conn, tenant_id)
    provider = tenant.get("messaging_adapter", "ghl")

    if provider == "twilio":
        from app.adapters.messaging.twilio import TwilioMessagingAdapter
        return TwilioMessagingAdapter(conn, tenant_id)

    from app.adapters.messaging.ghl import GHLMessagingAdapter
    return GHLMessagingAdapter(conn, tenant_id)
