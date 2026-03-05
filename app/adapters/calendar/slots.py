"""
Provider-agnostic slot utilities.

These functions operate on ISO datetime strings only — no API calls,
no provider-specific logic. Used by all calendar adapters.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def get_stub_slots() -> list[str] | None:
    """
    Return stub slots from CALENDAR_STUB_SLOTS env var if set.

    Format: JSON array of ISO datetime strings, e.g.:
    CALENDAR_STUB_SLOTS='["2026-01-30T09:00:00Z","2026-01-30T14:00:00Z","2026-01-31T10:00:00Z"]'

    Returns None if env var is not set or empty.
    """
    raw = os.getenv("CALENDAR_STUB_SLOTS", "").strip()
    if not raw:
        return None
    try:
        slots = json.loads(raw)
        if isinstance(slots, list) and all(isinstance(s, str) for s in slots):
            return slots
        return None
    except json.JSONDecodeError:
        return None


def filter_slots_by_signals(
    slots: list[str],
    day: str | None,
    time_window: str | None,
    timezone: str = "Europe/London",
    explicit_date: int | None = None,
) -> list[str]:
    """
    Filter slots by day, time_window, and optional explicit_date signals.

    day: 'monday', 'tuesday', ..., 'today', 'tomorrow'
    time_window: 'morning' (before 12), 'afternoon' (12-17), 'evening' (17+)
    explicit_date: day-of-month integer (1-31), e.g. 6 from "Friday 6th"

    Slots are ISO strings in UTC (e.g., "2026-01-30T00:00:00Z").
    Filtering is done in tenant timezone, returns original ISO strings sorted chronologically.
    """
    tz = ZoneInfo(timezone)
    utc = ZoneInfo("UTC")
    now = datetime.now(tz)

    # Map day names to weekday integers (0=Monday)
    day_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    # Time window hour ranges (in local timezone)
    window_ranges = {
        "morning": (0, 12),
        "afternoon": (12, 17),
        "evening": (17, 24),
    }

    # Parse and convert slots to tenant timezone for filtering
    filtered: list[tuple[datetime, str]] = []
    for slot_iso in slots:
        try:
            slot_dt = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
            # Ensure timezone-aware (assume UTC if naive)
            if slot_dt.tzinfo is None:
                slot_dt = slot_dt.replace(tzinfo=utc)
            # Convert to tenant timezone for filtering
            slot_local = slot_dt.astimezone(tz)
        except ValueError:
            continue

        # Filter by day (using local date)
        if day:
            if day == "today":
                if slot_local.date() != now.date():
                    continue
            elif day == "tomorrow":
                if slot_local.date() != (now + timedelta(days=1)).date():
                    continue
            elif day in day_map:
                if slot_local.weekday() != day_map[day]:
                    continue

        # Filter by specific calendar date (day-of-month), e.g. "the 6th"
        if explicit_date is not None:
            if slot_local.day != explicit_date:
                continue

        # Filter by time window (using local hour)
        if time_window and time_window in window_ranges:
            start_hour, end_hour = window_ranges[time_window]
            if not (start_hour <= slot_local.hour < end_hour):
                continue

        filtered.append((slot_dt, slot_iso))

    # Sort chronologically and return original ISO strings
    filtered.sort(key=lambda x: x[0])
    return [slot_iso for _, slot_iso in filtered]


def pick_soonest_two_slots(
    slots: list[str],
    timezone: str = "Europe/London",
    contrast_pool: list[str] | None = None,
    target_hour: float | None = None,
) -> list[str]:
    """
    Pick exactly 2 slots:
      A = closest match to user preference (first from slots)
      B = contrasting morning/afternoon from contrast_pool, else next-closest from slots

    Slots are UTC ISO strings. Categorization uses tenant local time.
    Morning: hour < 12, Afternoon: 12 <= hour < 17, Evening: hour >= 17.
    Returns [] if slots is empty, sorted [A, B] chronologically.
    """
    if not slots:
        return []

    tz = ZoneInfo(timezone)
    utc = ZoneInfo("UTC")

    def parse_slot(slot_iso: str) -> tuple[datetime, datetime, str] | None:
        try:
            slot_dt = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
            if slot_dt.tzinfo is None:
                slot_dt = slot_dt.replace(tzinfo=utc)
            local_dt = slot_dt.astimezone(tz)
            return (slot_dt, local_dt, slot_iso)
        except ValueError:
            return None

    def get_time_category(local_dt: datetime) -> str:
        hour = local_dt.hour
        if hour < 12:
            return "morning"
        elif hour < 17:
            return "afternoon"
        return "evening"

    # Parse preference-matched slots
    parsed: list[tuple[datetime, datetime, str]] = []
    for slot_iso in slots:
        p = parse_slot(slot_iso)
        if p:
            parsed.append(p)

    if not parsed:
        return []

    # Sort by UTC time (chronological)
    parsed.sort(key=lambda x: x[0])

    # If target_hour is set, re-sort by proximity to that time of day then pick nearest 2
    if target_hour is not None:
        parsed.sort(key=lambda x: abs(x[1].hour + x[1].minute / 60 - target_hour))
        result = [iso for _, _, iso in parsed[:2]]
        result_parsed = [(datetime.fromisoformat(iso.replace("Z", "+00:00")), iso) for iso in result]
        result_parsed.sort(key=lambda x: x[0])
        return [iso for _, iso in result_parsed]

    # Slot A = first preference-matched slot (closest to user preference)
    slot_a_utc, slot_a_local, slot_a_iso = parsed[0]
    slot_a_category = get_time_category(slot_a_local)

    # Determine contrasting category
    if slot_a_category == "morning":
        contrast_category = "afternoon"
    elif slot_a_category == "afternoon":
        contrast_category = "morning"
    else:  # evening
        contrast_category = "morning"  # contrast evening with morning

    # Parse contrast pool (or use slots if not provided)
    pool = contrast_pool if contrast_pool else slots
    pool_parsed: list[tuple[datetime, datetime, str]] = []
    for slot_iso in pool:
        p = parse_slot(slot_iso)
        if p and p[2] != slot_a_iso:  # exclude slot A
            pool_parsed.append(p)

    pool_parsed.sort(key=lambda x: x[0])

    # Look for contrasting slot in pool
    slot_b_iso: str | None = None
    for utc_dt, local_dt, iso in pool_parsed:
        if get_time_category(local_dt) == contrast_category:
            slot_b_iso = iso
            break

    # Fallback: next chronological from preference-matched slots (excluding A)
    if not slot_b_iso and len(parsed) > 1:
        slot_b_iso = parsed[1][2]

    # Build result
    if slot_b_iso:
        # Sort A and B chronologically
        result = [slot_a_iso, slot_b_iso]
        result_parsed = [(datetime.fromisoformat(iso.replace("Z", "+00:00")), iso) for iso in result]
        result_parsed.sort(key=lambda x: x[0])
        return [iso for _, iso in result_parsed]

    # Only one slot available
    return [slot_a_iso]


def format_slots_for_display(slots: list[str], timezone: str = "Europe/London") -> list[str]:
    """
    Format slots for user-friendly display in tenant local time.

    Slots are UTC ISO strings (e.g., "2026-01-30T14:00:00Z").
    Output: "Friday 09:00" in tenant local time.
    """
    tz = ZoneInfo(timezone)
    utc = ZoneInfo("UTC")
    formatted: list[str] = []
    for slot_iso in slots:
        try:
            slot_dt = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
            if slot_dt.tzinfo is None:
                slot_dt = slot_dt.replace(tzinfo=utc)
            # Convert to tenant local time for display
            local_dt = slot_dt.astimezone(tz)
            formatted.append(local_dt.strftime("%A %H:%M"))
        except ValueError:
            continue
    return formatted


def filter_by_availability_windows(
    slots: list[str],
    availability: dict[str, list[dict[str, str]]] | None,
    timezone: str = "Europe/London",
) -> list[str]:
    """
    Filter slots by tenant-configured availability windows.

    availability format:
    {
        "mon": [{"start": "09:00", "end": "17:00"}],
        "tue": [{"start": "09:00", "end": "12:00"}, {"start": "14:00", "end": "17:00"}],
        ...
    }

    If availability is None or empty, returns all slots unfiltered.
    Slots are UTC ISO strings; filtering is done in tenant local time.
    """
    if not availability:
        return slots

    tz = ZoneInfo(timezone)
    utc = ZoneInfo("UTC")

    day_abbrev = {
        0: "mon", 1: "tue", 2: "wed", 3: "thu",
        4: "fri", 5: "sat", 6: "sun",
    }

    filtered: list[tuple[datetime, str]] = []
    for slot_iso in slots:
        try:
            slot_dt = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
            if slot_dt.tzinfo is None:
                slot_dt = slot_dt.replace(tzinfo=utc)
            local_dt = slot_dt.astimezone(tz)
        except ValueError:
            continue

        # Get day abbreviation
        day_key = day_abbrev.get(local_dt.weekday())
        if not day_key:
            continue

        # Get windows for this day
        windows = availability.get(day_key)
        if not windows:
            # No windows defined for this day = not available
            continue

        # Check if slot falls within any window
        slot_time = local_dt.strftime("%H:%M")
        in_window = False
        for window in windows:
            start = window.get("start", "00:00")
            end = window.get("end", "23:59")
            if start <= slot_time < end:
                in_window = True
                break

        if in_window:
            filtered.append((slot_dt, slot_iso))

    # Sort chronologically
    filtered.sort(key=lambda x: x[0])
    return [iso for _, iso in filtered]
