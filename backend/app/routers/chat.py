"""Web chat channel API used by the WhatsApp simulator page."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..engine.messages import Inbound
from ..models import Conversation, Message
from ..services import conversations as conv_svc
from ..services import ratelimit
from ..services.orders import upsert_customer
from .public import get_restaurant, normalize_phone

router = APIRouter(prefix="/chat", tags=["chat"])


def _conv(db: Session, restaurant_id: int, session_id: str) -> Conversation:
    conv = db.scalar(
        select(Conversation).where(
            Conversation.restaurant_id == restaurant_id,
            Conversation.channel == "web_chat",
            Conversation.customer_key == session_id,
        )
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return conv


class StartIn(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=2, max_length=60)
    phone: str = Field(min_length=6, max_length=20)


@router.post("/{slug}/start")
def start(slug: str, body: StartIn, request: Request, db: Session = Depends(get_db)):
    r = get_restaurant(db, slug)
    if body.session_id:
        existing = db.scalar(
            select(Conversation).where(
                Conversation.restaurant_id == r.id,
                Conversation.channel == "web_chat",
                Conversation.customer_key == body.session_id,
            )
        )
        if existing is not None:
            return {"session_id": existing.customer_key, "messages": _messages(db, existing.id, 0)}
    ratelimit.hit(db, f"chat_start:{ratelimit.client_ip(request)}", get_settings().chat_starts_per_hour_ip, 3600)
    customer = upsert_customer(db, r.id, normalize_phone(body.phone), body.name.strip())
    conv = Conversation(
        restaurant_id=r.id,
        channel="web_chat",
        customer_key=uuid.uuid4().hex,
        customer_id=customer.id,
        state="IDLE",
        data={"cart": []},
    )
    db.add(conv)
    db.commit()
    return {"session_id": conv.customer_key, "messages": []}


class SendIn(BaseModel):
    session_id: str = Field(max_length=64)
    kind: str = Field(pattern="^(text|button|list)$")
    text: str = Field(default="", max_length=1000)
    id: str | None = Field(default=None, max_length=200)


@router.post("/{slug}/send")
def send(slug: str, body: SendIn, db: Session = Depends(get_db)):
    r = get_restaurant(db, slug)
    conv = _conv(db, r.id, body.session_id)
    ratelimit.hit(db, f"chat_msg:{conv.id}", get_settings().chat_msgs_per_min, 60)
    if body.kind == "text" and not body.text.strip():
        raise HTTPException(status_code=422, detail="empty message")
    if body.kind != "text" and not body.id:
        raise HTTPException(status_code=422, detail="reply id required")
    msgs = conv_svc.receive(db, r, conv.id, Inbound(kind=body.kind, text=body.text.strip(), id=body.id))
    db.commit()
    return {"messages": [conv_svc.message_dict(m) for m in msgs]}


def _messages(db: Session, conv_id: int, after: int) -> list[dict]:
    rows = db.scalars(
        select(Message).where(Message.conversation_id == conv_id, Message.id > after).order_by(Message.id).limit(200)
    ).all()
    return [conv_svc.message_dict(m) for m in rows]


@router.get("/{slug}/messages")
def messages(slug: str, session_id: str, after: int = 0, db: Session = Depends(get_db)):
    r = get_restaurant(db, slug)
    conv = _conv(db, r.id, session_id)
    return {"messages": _messages(db, conv.id, after)}
