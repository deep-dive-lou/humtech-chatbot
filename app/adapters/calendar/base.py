"""Calendar adapter protocol — all calendar adapters implement this interface."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


class CalendarAdapter(Protocol):
    async def get_free_slots(
        self, *, start_dt: datetime, end_dt: datetime, timezone: str
    ) -> tuple[list[str], str | None]:
        """Fetch available slots. Returns (ISO slot strings, trace_id)."""
        ...

    async def book_slot(
        self,
        *,
        slot_iso: str,
        contact_id: str,
        conversation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Book a slot. Returns dict with 'success' bool + details."""
        ...

    async def cancel_booking(self, *, booking_id: str) -> dict[str, Any]:
        """Cancel a booking. Returns dict with 'success' bool."""
        ...
