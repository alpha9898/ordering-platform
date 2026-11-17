"""Channel adapters. The engine never talks to a channel directly; it
returns Outgoing messages and `services.conversations.send` stores them and
hands them to the conversation's channel for delivery."""

from __future__ import annotations

from typing import Protocol

from ..models import Conversation


class Channel(Protocol):
    name: str

    def deliver(self, conv: Conversation, payloads: list[dict]) -> None: ...


def get_channel(name: str) -> Channel:
    from .web import WebChannel
    from .whatsapp import WhatsAppChannel

    channels: dict[str, Channel] = {"web_chat": WebChannel(), "whatsapp": WhatsAppChannel()}
    if name not in channels:
        raise ValueError(f"no channel {name}")
    return channels[name]
