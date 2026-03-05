from __future__ import annotations
import httpx
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.adapters.calendar.slots import get_stub_slots


BASE_URL = "https://services.leadconnectorhq.com"


async def get_free_slots(
    access_token: str,
    calendar_id: str,
    start_dt: datetime,
    end_dt: datetime,
    timezone: str = "Europe/London",
    user_id: Optional[str] = None,
) -> tuple[list[str], str | None]:
    """Fetch free slots from GHL calendar API. Returns (slots, trace_id)."""
    # Check for stub mode first (for deterministic testing)
    stub_slots = get_stub_slots()
    if stub_slots is not None:
        return stub_slots, "stub-trace-id"

    url = f"{BASE_URL}/calendars/{calendar_id}/free-slots"
    # GHL expects Unix timestamps in milliseconds
    params: dict[str, Any] = {
        "startDate": int(start_dt.timestamp() * 1000),
        "endDate": int(end_dt.timestamp() * 1000),
        "timezone": timezone,
    }
    if user_id:
        params["userId"] = user_id

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Version": "2021-07-28",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, params=params, headers=headers)

    if r.status_code == 401:
        raise RuntimeError("Unauthorized: check token + calendars.readonly scope")

    r.raise_for_status()
    data = r.json()
    trace_id = data.get("traceId")

    slots: list[str] = []

    for day, blob in data.items():
        if day == "traceId":
            continue
        if not isinstance(blob, dict):
            continue

        day_slots = blob.get("slots")
        if not isinstance(day_slots, list):
            continue

        # slots are strings like "2026-01-27T20:00:00Z"
        for s in day_slots:
            if isinstance(s, str):
                slots.append(s)

    # de-dupe while preserving order
    seen: set[str] = set()
    slots_out: list[str] = []
    for s in slots:
        if s not in seen:
            seen.add(s)
            slots_out.append(s)

    return slots_out, trace_id


BOOKING_STUB_ENABLED_KEY = "BOOKING_STUB"

LOAD_CONTACT_SQL = """
SELECT channel_address, metadata
FROM bot.contacts
WHERE contact_id = $1::uuid;
"""

LOAD_TENANT_CALENDAR_SQL = """
SELECT settings
FROM core.tenants
WHERE tenant_id = $1::uuid AND is_enabled = TRUE;
"""


def _resolve_ghl_contact_id(
    contact_row: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> str | None:
    """Extract GHL contactId from contact metadata or booking metadata."""
    # Caller-provided metadata (e.g. from event payload)
    if metadata:
        for key in ("contactId", "ghl_contact_id", "contact_id"):
            val = metadata.get(key)
            if isinstance(val, str) and val:
                return val

    # Contact record metadata
    if contact_row:
        cmeta = contact_row.get("metadata")
        if isinstance(cmeta, dict):
            for key in ("contactId", "ghl_contact_id", "contact_id"):
                val = cmeta.get(key)
                if isinstance(val, str) and val:
                    return val

    return None


async def book_slot(
    tenant_id: str,
    slot_iso: str,
    contact_id: str,
    conversation_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Book a slot via the GHL Calendar Events API.

    POST https://services.leadconnectorhq.com/calendars/events

    Falls back to stub mode when BOOKING_STUB env var is set (for testing).
    On 401: refreshes the token once and retries.
    """
    import logging
    from app.db import get_pool
    from app.adapters.ghl.auth import get_valid_token

    logger = logging.getLogger(__name__)

    # Stub mode for testing
    if os.getenv(BOOKING_STUB_ENABLED_KEY):
        booking_id = f"stub-{uuid.uuid4().hex[:12]}"
        return {
            "success": True,
            "booking_id": booking_id,
            "slot": slot_iso,
            "tenant_id": tenant_id,
            "contact_id": contact_id,
            "conversation_id": conversation_id,
        }

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Load contact record for GHL contactId resolution
        contact_row = await conn.fetchrow(LOAD_CONTACT_SQL, contact_id)
        contact_dict = dict(contact_row) if contact_row else None

        ghl_contact_id = _resolve_ghl_contact_id(contact_dict, metadata)
        if not ghl_contact_id:
            return {
                "success": False,
                "error": "no_ghl_contact_id",
                "detail": "Could not resolve GHL contactId from contact metadata",
            }

        # Load calendar settings from tenant
        tenant_row = await conn.fetchrow(LOAD_TENANT_CALENDAR_SQL, tenant_id)
        if not tenant_row:
            return {"success": False, "error": "tenant_not_found"}

        raw_settings = tenant_row["settings"]
        if isinstance(raw_settings, str):
            raw_settings = json.loads(raw_settings)
        settings = raw_settings if isinstance(raw_settings, dict) else {}
        cal = settings.get("calendar") or {}
        calendar_id = cal.get("calendar_id")
        tz = settings.get("timezone") or cal.get("timezone") or "Europe/London"

        if not calendar_id:
            return {"success": False, "error": "missing_calendar_id"}

        # Parse slot times
        slot_dt = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
        if slot_dt.tzinfo is None:
            slot_dt = slot_dt.replace(tzinfo=ZoneInfo("UTC"))
        slot_duration = int(cal.get("slot_duration_minutes") or 60)
        end_dt = slot_dt + timedelta(minutes=slot_duration)

        body: dict[str, Any] = {
            "calendarId": calendar_id,
            "contactId": ghl_contact_id,
            "startTime": slot_dt.isoformat(),
            "endTime": end_dt.isoformat(),
            "timezone": tz,
            "title": "Appointment (bot-booked)",
        }

        # Get valid token (handles refresh internally)
        access_token = await get_valid_token(conn, tenant_id)

        # Add locationId only if stored — Private Integration tokens are location-scoped
        # so omitting it lets GHL infer the location from the token
        cred_row = await conn.fetchval(
            "SELECT credentials FROM core.tenant_credentials "
            "WHERE tenant_id = $1::uuid AND provider = 'ghl'",
            tenant_id,
        )
        if cred_row:
            from app.utils.crypto import decrypt_credentials as _decrypt
            try:
                cred_data = _decrypt(bytes(cred_row))
                location_id = cred_data.get("location_id")
                if location_id:
                    body["locationId"] = location_id
            except Exception:
                pass

    # API call (outside DB connection — no need to hold it during HTTP)
    url = f"{BASE_URL}/calendars/events/appointments"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": "2021-07-28",
    }

    logger.info(json.dumps({
        "event": "ghl_book_slot_request",
        "tenant_id": tenant_id,
        "calendar_id": calendar_id,
        "contact_id": ghl_contact_id,
        "start_time": body["startTime"],
    }))

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=body, headers=headers)

        # On 401: refresh token once and retry
        if resp.status_code == 401:
            logger.info(json.dumps({
                "event": "ghl_book_slot_401_retry",
                "tenant_id": tenant_id,
            }))
            async with pool.acquire() as conn:
                access_token = await get_valid_token(conn, tenant_id)
            headers["Authorization"] = f"Bearer {access_token}"
            resp = await client.post(url, json=body, headers=headers)

    logger.info(json.dumps({
        "event": "ghl_book_slot_response",
        "tenant_id": tenant_id,
        "status": resp.status_code,
        "body": resp.text[:500],
    }))

    if resp.status_code not in (200, 201):
        return {
            "success": False,
            "error": f"ghl_api_error:{resp.status_code}",
            "detail": resp.text[:300],
        }

    data = resp.json()
    booking_id = data.get("id") or data.get("eventId") or f"ghl-{uuid.uuid4().hex[:12]}"

    return {
        "success": True,
        "booking_id": booking_id,
        "slot": slot_iso,
        "tenant_id": tenant_id,
        "contact_id": contact_id,
        "conversation_id": conversation_id,
        "raw_response": data,
    }


async def cancel_booking(
    tenant_id: str,
    booking_id: str,
) -> dict[str, Any]:
    """
    Cancel a booking via the GHL Calendar Events API.

    DELETE https://services.leadconnectorhq.com/calendars/events/{booking_id}

    On 401: refreshes the token once and retries.
    """
    import logging
    from app.db import get_pool
    from app.adapters.ghl.auth import get_valid_token

    logger = logging.getLogger(__name__)

    pool = await get_pool()
    async with pool.acquire() as conn:
        access_token = await get_valid_token(conn, tenant_id)

    url = f"{BASE_URL}/calendars/events/{booking_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Version": "2021-07-28",
    }

    logger.info(json.dumps({
        "event": "ghl_cancel_booking_request",
        "tenant_id": tenant_id,
        "booking_id": booking_id,
    }))

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.delete(url, headers=headers)

        if resp.status_code == 401:
            logger.info(json.dumps({
                "event": "ghl_cancel_booking_401_retry",
                "tenant_id": tenant_id,
            }))
            async with pool.acquire() as conn:
                access_token = await get_valid_token(conn, tenant_id)
            headers["Authorization"] = f"Bearer {access_token}"
            resp = await client.delete(url, headers=headers)

    logger.info(json.dumps({
        "event": "ghl_cancel_booking_response",
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "status": resp.status_code,
    }))

    if resp.status_code in (200, 204):
        return {"success": True, "booking_id": booking_id}

    return {
        "success": False,
        "error": f"ghl_api_error:{resp.status_code}",
        "detail": resp.text[:300],
    }


# ---------------------------------------------------------------------------
# Adapter class — wraps free functions behind CalendarAdapter protocol
# ---------------------------------------------------------------------------

class GHLCalendarAdapter:
    """GHL calendar adapter. Handles credential loading internally."""

    def __init__(self, conn: Any, tenant_id: str):
        self.conn = conn
        self.tenant_id = tenant_id

    async def get_free_slots(
        self, *, start_dt: datetime, end_dt: datetime, timezone: str
    ) -> tuple[list[str], str | None]:
        from app.bot.tenants import load_tenant, load_tenant_credentials, get_calendar_settings

        tenant = await load_tenant(self.conn, self.tenant_id)
        cal = get_calendar_settings(tenant)
        calendar_id = cal.get("calendar_id")
        if not calendar_id:
            return [], None

        credentials = await load_tenant_credentials(self.conn, self.tenant_id, provider="ghl")
        ghl_creds = credentials.get("ghl", {})
        access_token = ghl_creds.get("access_token")
        if not access_token:
            raise RuntimeError("No GHL access token available")

        return await get_free_slots(access_token, calendar_id, start_dt, end_dt, timezone)

    async def book_slot(
        self,
        *,
        slot_iso: str,
        contact_id: str,
        conversation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await book_slot(self.tenant_id, slot_iso, contact_id, conversation_id, metadata)

    async def cancel_booking(self, *, booking_id: str) -> dict[str, Any]:
        return await cancel_booking(self.tenant_id, booking_id)
