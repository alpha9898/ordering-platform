"""Customer notifications when staff change an order's status."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..engine import texts_ar as T
from ..engine.messages import Text
from ..models import Conversation, Order, Restaurant
from .conversations import send


def notify_status(db: Session, order: Order, restaurant: Restaurant) -> bool:
    """Send the status message on the order's chat channel, if it has one.

    Web-menu orders have no chat; their tracking page polls the status.
    """
    text = T.status_notification(
        order.order_no, order.status, order.fulfillment, order.eta_minutes, order.reject_reason, restaurant.name_ar
    )
    if text is None or order.conversation_id is None:
        return False
    conv = db.get(Conversation, order.conversation_id)
    if conv is None:
        return False
    send(db, conv, [Text(text)], sender="bot")
    return True
