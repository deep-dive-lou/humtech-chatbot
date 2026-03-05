"""Calendar adapter factory — returns the correct adapter for a tenant's CRM."""
from __future__ import annotations

from typing import Any

import asyncpg

from app.adapters.calendar.base import CalendarAdapter


async def get_calendar_adapter(conn: asyncpg.Connection, tenant_id: str) -> CalendarAdapter:
    """Return a CalendarAdapter for the tenant's configured calendar provider."""
    from app.bot.tenants import load_tenant

    tenant = await load_tenant(conn, tenant_id)
    provider = tenant.get("calendar_adapter", "ghl")

    if provider == "hubspot":
        from app.adapters.calendar.hubspot import HubSpotCalendarAdapter
        return HubSpotCalendarAdapter(conn, tenant_id)

    from app.adapters.calendar.ghl import GHLCalendarAdapter
    return GHLCalendarAdapter(conn, tenant_id)
