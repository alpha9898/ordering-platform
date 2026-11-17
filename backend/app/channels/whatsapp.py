"""WhatsApp Cloud API channel — placeholder for the next phase.

Plan when this is built:
- map the webhook's metadata.phone_number_id to a restaurant
- verify X-Hub-Signature-256, dedupe on messages.wa_message_id
- normalize incoming messages into engine.messages.Inbound
- deliver(): POST each payload to /{phone_number_id}/messages, converting
  Text/Buttons/List payloads to Meta's interactive message JSON
- outside the 24h window use approved templates for status updates
"""

from __future__ import annotations

import logging

from ..models import Conversation

log = logging.getLogger(__name__)


class WhatsAppChannel:
    name = "whatsapp"

    def deliver(self, conv: Conversation, payloads: list[dict]) -> None:
        log.warning("WhatsApp channel not connected yet; %d message(s) not sent", len(payloads))
