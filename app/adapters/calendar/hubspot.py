"""HubSpot calendar adapter — Scheduler API for slots, CRM Meetings API for cancel."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone as dt_tz
from typing import Any

import httpx

from app.adapters.calendar.slots import get_stub_slots

logger = logging.getLogger(__name__)

BASE_URL = "https://api.hubapi.com"
BOOKING_STUB_ENABLED_KEY = "BOOKING_STUB"


# ---------------------------------------------------------------------------
# Shared request helper
# ---------------------------------------------------------------------------

async def _hubspot_request(
    method: str,
    path: str,
    *,
    access_token: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 10.0,
    max_retries: int = 3,
) -> httpx.Response:
    """Make an authenticated HubSpot API request with 429 retry."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    url = f"{BASE_URL}{path}"

    for attempt in range(max_retries):
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method, url, headers=headers, params=params, json=json_body,
            )

        if resp.status_code == 429:
            wait = min(2 ** attempt, 10)
            logger.warning("HubSpot 429 rate limit on %s %s — retrying in %ds", method, path, wait)
            await asyncio.sleep(wait)
            continue

        return resp

    # Return last response if all retries exhausted
    return resp  # type: ignore[possibly-undefined]


# ---------------------------------------------------------------------------
# HubSpotCalendarAdapter
# ---------------------------------------------------------------------------

class HubSpotCalendarAdapter:
    """Calendar adapter for HubSpot Scheduler API."""

    def __init__(self, conn: Any, tenant_id: str):
        self.conn = conn
        self.tenant_id = tenant_id

    async def get_free_slots(
        self, *, start_dt: datetime, end_dt: datetime, timezone: str
    ) -> tuple[list[str], str | None]:
        """Fetch available meeting slots from HubSpot Scheduler."""
        # Stub mode for testing
        stub_slots = get_stub_slots()
        if stub_slots is not None:
            return stub_slots, "stub-trace-id"

        from app.bot.tenants import load_tenant, load_tenant_credentials, get_calendar_settings

        tenant = await load_tenant(self.conn, self.tenant_id)
        cal = get_calendar_settings(tenant)
        meeting_link_slug = cal.get("calendar_id")  # stored in calendar_id field
        if not meeting_link_slug:
            logger.error("No meeting_link_slug (calendar_id) for tenant %s", self.tenant_id)
            return [], None

        credentials = await load_tenant_credentials(self.conn, self.tenant_id, provider="hubspot")
        hs_creds = credentials.get("hubspot", {})
        access_token = hs_creds.get("access_token")
        if not access_token:
            raise RuntimeError("No HubSpot access token available")

        # Determine which month offsets we need to cover start_dt..end_dt
        now = datetime.now(dt_tz.utc)
        start_offset = max(0, (start_dt.year - now.year) * 12 + (start_dt.month - now.month))
        end_offset = max(0, (end_dt.year - now.year) * 12 + (end_dt.month - now.month))
        offsets = list(range(start_offset, end_offset + 1))
        if not offsets:
            offsets = [0]

        trace_id = uuid.uuid4().hex[:12]
        all_slots: list[str] = []

        for offset in offsets:
            path = f"/scheduler/v3/meetings/meeting-links/book/availability-page/{meeting_link_slug}"
            params: dict[str, Any] = {"timezone": timezone}
            if offset > 0:
                params["monthOffset"] = offset

            resp = await _hubspot_request("GET", path, access_token=access_token, params=params)

            if resp.status_code == 401:
                raise RuntimeError("HubSpot 401 Unauthorized — check private app token")

            if resp.status_code != 200:
                logger.error(
                    "HubSpot availability error: %d %s",
                    resp.status_code, resp.text[:300],
                )
                continue

            data = resp.json()

            # Parse slots from linkAvailabilityByDuration
            avail_by_duration = data.get("linkAvailabilityByDuration", {})
            for duration_key, duration_data in avail_by_duration.items():
                availabilities = duration_data.get("availabilities", [])
                for slot in availabilities:
                    start_ms = slot.get("startMillisUtc")
                    if start_ms is None:
                        continue
                    # Convert milliseconds to ISO string
                    slot_dt = datetime.fromtimestamp(start_ms / 1000, tz=dt_tz.utc)
                    # Filter to requested range
                    if start_dt <= slot_dt <= end_dt:
                        all_slots.append(slot_dt.strftime("%Y-%m-%dT%H:%M:%SZ"))

        # Deduplicate and sort
        seen: set[str] = set()
        unique_slots: list[str] = []
        for s in all_slots:
            if s not in seen:
                seen.add(s)
                unique_slots.append(s)
        unique_slots.sort()

        logger.info(
            "HubSpot get_free_slots: tenant=%s slug=%s slots=%d trace=%s",
            self.tenant_id, meeting_link_slug, len(unique_slots), trace_id,
        )
        return unique_slots, trace_id

    async def book_slot(
        self,
        *,
        slot_iso: str,
        contact_id: str,
        conversation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Book a meeting via HubSpot Scheduler API."""
        # Stub mode
        if os.getenv(BOOKING_STUB_ENABLED_KEY):
            booking_id = f"stub-{uuid.uuid4().hex[:12]}"
            return {
                "success": True,
                "booking_id": booking_id,
                "slot": slot_iso,
                "tenant_id": self.tenant_id,
                "contact_id": contact_id,
                "conversation_id": conversation_id,
            }

        from app.bot.tenants import load_tenant, load_tenant_credentials, get_calendar_settings

        tenant = await load_tenant(self.conn, self.tenant_id)
        cal = get_calendar_settings(tenant)
        meeting_link_slug = cal.get("calendar_id")
        settings = tenant.get("settings") or {}
        cal_settings = settings.get("calendar") or {}
        tz = settings.get("timezone") or cal_settings.get("timezone") or "Europe/London"
        slot_duration = int(cal_settings.get("slot_duration_minutes") or 30)

        credentials = await load_tenant_credentials(self.conn, self.tenant_id, provider="hubspot")
        hs_creds = credentials.get("hubspot", {})
        access_token = hs_creds.get("access_token")
        if not access_token:
            return {"success": False, "error": "No HubSpot access token available"}

        # Load contact details for email
        contact_row = await self.conn.fetchrow(
            "SELECT display_name, metadata FROM bot.contacts WHERE contact_id = $1::uuid",
            contact_id,
        )
        if not contact_row:
            return {"success": False, "error": f"Contact not found: {contact_id}"}

        contact_meta = contact_row["metadata"]
        if isinstance(contact_meta, str):
            contact_meta = json.loads(contact_meta)
        contact_meta = contact_meta or {}

        email = contact_meta.get("email")
        if not email:
            return {"success": False, "error": "Contact has no email — required for HubSpot booking"}

        display_name = contact_row["display_name"] or ""
        name_parts = display_name.split(None, 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Convert slot ISO to milliseconds
        slot_dt = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
        start_ms = int(slot_dt.timestamp() * 1000)
        duration_ms = slot_duration * 60 * 1000

        body = {
            "slug": meeting_link_slug,
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "startTime": start_ms,
            "duration": duration_ms,
            "timezone": tz,
            "locale": "en-gb",
        }

        resp = await _hubspot_request(
            "POST",
            "/scheduler/v3/meetings/meeting-links/book",
            access_token=access_token,
            json_body=body,
            params={"timezone": tz},
            timeout=15.0,
        )

        if resp.status_code not in (200, 201):
            logger.error(
                "HubSpot booking failed: %d %s", resp.status_code, resp.text[:300],
            )
            return {
                "success": False,
                "error": f"HubSpot booking failed: {resp.status_code}",
                "detail": resp.text[:300],
            }

        data = resp.json()
        # Extract meeting ID — HubSpot returns the created meeting object
        booking_id = str(data.get("id") or data.get("meetingId") or data.get("calendarEventId") or "")

        logger.info(
            "HubSpot booking success: tenant=%s booking=%s slot=%s contact=%s",
            self.tenant_id, booking_id, slot_iso, contact_id,
        )
        return {
            "success": True,
            "booking_id": booking_id,
            "slot": slot_iso,
            "tenant_id": self.tenant_id,
            "contact_id": contact_id,
            "conversation_id": conversation_id,
            "raw_response": data,
        }

    async def cancel_booking(self, *, booking_id: str) -> dict[str, Any]:
        """Cancel a meeting via HubSpot CRM Meetings API."""
        from app.bot.tenants import load_tenant_credentials

        credentials = await load_tenant_credentials(self.conn, self.tenant_id, provider="hubspot")
        hs_creds = credentials.get("hubspot", {})
        access_token = hs_creds.get("access_token")
        if not access_token:
            return {"success": False, "error": "No HubSpot access token available"}

        resp = await _hubspot_request(
            "DELETE",
            f"/crm/v3/objects/meetings/{booking_id}",
            access_token=access_token,
            timeout=15.0,
        )

        if resp.status_code in (200, 204):
            logger.info("HubSpot cancel success: booking=%s", booking_id)
            return {"success": True, "booking_id": booking_id}

        logger.error(
            "HubSpot cancel failed: %d %s", resp.status_code, resp.text[:300],
        )
        return {
            "success": False,
            "error": f"HubSpot cancel failed: {resp.status_code}",
            "detail": resp.text[:300],
            "booking_id": booking_id,
        }
