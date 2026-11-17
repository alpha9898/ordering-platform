"""Receive customer messages, run the engine, store + deliver replies."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..channels import get_channel
from ..engine.machine import HUMAN_SILENCE, Ctx, Engine
from ..engine.messages import Inbound, Outgoing, to_payload, validate_payload
from ..models import Conversation, Customer, Message, Restaurant
from . import settings as settings_svc


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def lock(db: Session, conv_id: int) -> Conversation:
    """Row lock = one message processed at a time per customer."""
    return db.scalar(select(Conversation).where(Conversation.id == conv_id).with_for_update())


def store(db: Session, conv: Conversation, direction: str, sender: str, payload: dict) -> Message:
    msg = Message(
        conversation_id=conv.id,
        restaurant_id=conv.restaurant_id,
        direction=direction,
        sender=sender,
        payload=payload,
    )
    db.add(msg)
    return msg


def send(db: Session, conv: Conversation, outs: list[Outgoing], sender: str = "bot") -> list[Message]:
    payloads = [to_payload(o) for o in outs]
    for p in payloads:
        validate_payload(p)  # never store something WhatsApp would reject
    msgs = [store(db, conv, "out", sender, p) for p in payloads]
    db.flush()
    get_channel(conv.channel).deliver(conv, payloads)
    return msgs


def bot_silenced(conv: Conversation, now: dt.datetime) -> bool:
    return conv.human_until is not None and conv.human_until > now


def receive(db: Session, restaurant: Restaurant, conv_id: int, inbound: Inbound, now: dt.datetime | None = None) -> list[Message]:
    now = now or now_utc()
    conv = lock(db, conv_id)
    in_msg = store(db, conv, "in", "customer", inbound.to_payload())
    conv.last_message_at = now
    db.flush()

    if bot_silenced(conv, now):
        return [in_msg]
    if conv.human_until is not None:  # handoff window over, bot resumes
        conv.human_until = None

    customer = db.get(Customer, conv.customer_id) if conv.customer_id else None
    ctx = Ctx(
        db=db,
        restaurant=restaurant,
        settings=settings_svc.get_all(db, restaurant.id),
        conv=conv,
        customer=customer,
        now=now,
    )
    outs = Engine(ctx).handle(inbound)
    return [in_msg, *send(db, conv, outs)]


def staff_reply(db: Session, conv: Conversation, text: str, now: dt.datetime | None = None) -> Message:
    from ..engine.messages import Text

    now = now or now_utc()
    conv.human_until = now + HUMAN_SILENCE  # keep the bot quiet while staff chat
    conv.state = "HUMAN"
    return send(db, conv, [Text(text)], sender="staff")[0]


def resolve_human(conv: Conversation) -> None:
    conv.human_requested_at = None
    conv.human_until = None
    conv.state = "IDLE"


def message_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "direction": m.direction,
        "sender": m.sender,
        "payload": m.payload,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }
