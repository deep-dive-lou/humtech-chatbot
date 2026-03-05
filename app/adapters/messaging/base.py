"""Messaging adapter protocol — all messaging adapters implement this interface."""
from __future__ import annotations

from typing import Any, Protocol


class MessagingAdapter(Protocol):
    async def send_message(
        self,
        *,
        channel: str,
        to_address: str,
        text: str,
        message_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a message. Returns dict with 'success' bool + details."""
        ...
