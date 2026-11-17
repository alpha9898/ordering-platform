"""ORM models. Every tenant-owned table carries restaurant_id."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

RESTAURANT_STATUSES = ("trial", "active", "suspended", "archived")
USER_ROLES = ("super_admin", "owner", "staff")
ORDER_STATUSES = (
    "placed",
    "accepted",
    "preparing",
    "out_for_delivery",
    "ready_for_pickup",
    "completed",
    "rejected",
    "cancelled",
)
CHANNELS = ("web_chat", "web_menu", "whatsapp")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


def _now_col() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Restaurant(Base):
    __tablename__ = "restaurants"
    __table_args__ = (CheckConstraint(_in("status", RESTAURANT_STATUSES), name="restaurant_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="trial")
    demo_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Africa/Cairo")
    created_at: Mapped[dt.datetime] = _now_col()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("role", USER_ROLES), name="user_role"),
        CheckConstraint(
            "(role = 'super_admin' AND restaurant_id IS NULL) OR "
            "(role <> 'super_admin' AND restaurant_id IS NOT NULL)",
            name="user_role_restaurant",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"))
    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = _now_col()


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), index=True)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    items: Mapped[list[Item]] = relationship(back_populates="category", order_by="Item.sort, Item.id")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)
    description_ar: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    category: Mapped[Category] = relationship(back_populates="items")
    variants: Mapped[list[ItemVariant]] = relationship(
        back_populates="item", order_by="ItemVariant.sort, ItemVariant.id", cascade="all, delete-orphan"
    )


class ItemVariant(Base):
    """Every item has >=1 variant; single-price items have one with name_ar NULL."""

    __tablename__ = "item_variants"
    __table_args__ = (CheckConstraint("price >= 0", name="variant_price_nonneg"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    name_ar: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    item: Mapped[Item] = relationship(back_populates="variants")


class Addon(Base):
    __tablename__ = "addons"
    __table_args__ = (CheckConstraint("price >= 0", name="addon_price_nonneg"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), index=True)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CategoryAddon(Base):
    __tablename__ = "category_addons"

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)
    addon_id: Mapped[int] = mapped_column(ForeignKey("addons.id", ondelete="CASCADE"), primary_key=True)
    price_override: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("restaurant_id", "phone", name="customer_phone_per_restaurant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    last_address: Mapped[str | None] = mapped_column(Text)
    last_zone_id: Mapped[int | None] = mapped_column(ForeignKey("delivery_zones.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = _now_col()


class DeliveryZone(Base):
    __tablename__ = "delivery_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), index=True)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    min_order: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=Decimal("0"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Conversation(Base):
    """Per-customer chat state (replaces the Redis conv:{phone} key)."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "channel", "customer_key", name="conversation_key"),
        CheckConstraint(_in("channel", CHANNELS), name="conversation_channel"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_key: Mapped[str] = mapped_column(String(80), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="IDLE")
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    human_requested_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    human_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _now_col()


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id_id", "conversation_id", "id"),
        CheckConstraint("direction IN ('in', 'out')", name="message_direction"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    sender: Mapped[str] = mapped_column(String(10), nullable=False)  # customer | bot | staff
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    wa_message_id: Mapped[str | None] = mapped_column(String(128), unique=True)  # dedupe Meta retries
    created_at: Mapped[dt.datetime] = _now_col()


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("fulfillment IN ('delivery', 'pickup')", name="order_fulfillment"),
        CheckConstraint("payment_method IN ('cod', 'wallet')", name="order_payment_method"),
        CheckConstraint(
            "payment_status IN ('unpaid', 'proof_received', 'paid')", name="order_payment_status"
        ),
        CheckConstraint(_in("status", ORDER_STATUSES), name="order_status"),
        CheckConstraint(_in("channel", CHANNELS), name="order_channel"),
        UniqueConstraint("restaurant_id", "business_day", "order_no", name="order_no_per_day"),
        Index("ix_orders_restaurant_status_created", "restaurant_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"))
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    business_day: Mapped[dt.date] = mapped_column(Date, nullable=False)
    public_token: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    fulfillment: Mapped[str] = mapped_column(String(20), nullable=False)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("delivery_zones.id", ondelete="SET NULL"))
    zone_name_snapshot: Mapped[str | None] = mapped_column(Text)
    address_text: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unpaid")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="placed")
    reject_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    eta_minutes: Mapped[int | None] = mapped_column(Integer)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = _now_col()
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer: Mapped[Customer] = relationship()
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", order_by="OrderItem.id", cascade="all, delete-orphan"
    )
    events: Mapped[list[OrderStatusEvent]] = relationship(
        order_by="OrderStatusEvent.id", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("qty > 0", name="order_item_qty_pos"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int | None] = mapped_column(Integer)
    variant_id: Mapped[int | None] = mapped_column(Integer)
    half_item_id: Mapped[int | None] = mapped_column(Integer)  # reserved for half-and-half
    name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    variant_snapshot: Mapped[str | None] = mapped_column(Text)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order] = relationship(back_populates="items")
    addons: Mapped[list[OrderItemAddon]] = relationship(
        order_by="OrderItemAddon.id", cascade="all, delete-orphan"
    )


class OrderItemAddon(Base):
    __tablename__ = "order_item_addons"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("order_items.id", ondelete="CASCADE"), index=True)
    addon_id: Mapped[int | None] = mapped_column(Integer)
    name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)


class OrderStatusEvent(Base):
    __tablename__ = "order_status_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now_col()


class OrderCounter(Base):
    __tablename__ = "order_counters"

    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    last_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Setting(Base):
    __tablename__ = "settings"

    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)


class RateHit(Base):
    """Sliding-window counters for login lockout and public rate limits."""

    __tablename__ = "rate_hits"
    __table_args__ = (Index("ix_rate_hits_bucket_created", "bucket", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bucket: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[dt.datetime] = _now_col()


class PlatformSecret(Base):
    """Secrets generated inside the database (e.g. the session signing key),
    so no person or deploy tool ever has to handle them."""

    __tablename__ = "platform_secrets"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
