"""Web chat channel (the WhatsApp simulator).

Messages are already stored in the `messages` table by the caller; the
browser polls for them, so delivery is a no-op.
"""

from __future__ import annotations

from ..models import Conversation


class WebChannel:
    name = "web_chat"

    def deliver(self, conv: Conversation, payloads: list[dict]) -> None:
        return None
