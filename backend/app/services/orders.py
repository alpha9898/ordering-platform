"""Order creation (server-side totals) and the order lifecycle."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from ..engine.messages import valid_coords
from ..models import (
    Customer,
    DeliveryZone,
    Order,
    OrderCounter,
    OrderItem,
    OrderItemAddon,
    OrderStatusEvent,
    Restaurant,
)
from ..security import new_public_token
from . import hours
from .menu import money
from .pricing import PricedCart, price_lines

ACTIVE_STATUSES = ("placed", "accepted", "preparing", "out_for_delivery", "ready_for_pickup")
FINAL_STATUSES = ("completed", "rejected", "cancelled")

TRANSITIONS: dict[str, set[str]] = {
    "placed": {"accepted", "rejected", "cancelled"},
    "accepted": {"preparing", "cancelled"},
    "preparing": {"out_for_delivery", "ready_for_pickup"},
    "out_for_delivery": {"completed"},
    "ready_for_pickup": {"completed"},
}


class OrderError(Exception):
    def __init__(self, code: str, message_ar: str, extra: dict | None = None):
        super().__init__(code)
        self.code = code
        self.message_ar = message_ar
        self.extra = extra or {}


def restaurant_available(r: Restaurant) -> bool:
    return r.status in ("trial", "active")


def check_open(r: Restaurant, settings: dict, now: dt.datetime | None = None) -> None:
    if not restaurant_available(r):
        raise OrderError("unavailable", "الخدمة غير متاحة حاليًا")
    if not settings["accepting_orders"]:
        raise OrderError("not_accepting", "المطعم مش بيستقبل طلبات دلوقتي")
    if not hours.is_open(settings["working_hours"], r.timezone, now):
        when = hours.describe_next_opening(settings["working_hours"], r.timezone, now)
        msg = f"المطعم مقفول دلوقتي، بنفتح {when}" if when else "المطعم مقفول دلوقتي"
        raise OrderError("closed", msg, {"opens": when})


def active_zones(db: Session, rid: int) -> list[DeliveryZone]:
    return list(
        db.scalars(
            select(DeliveryZone)
            .where(DeliveryZone.restaurant_id == rid, DeliveryZone.active.is_(True))
            .order_by(DeliveryZone.sort, DeliveryZone.id)
        ).all()
    )


def delivery_terms(db: Session, rid: int, settings: dict, zone_id: int | None) -> tuple[DeliveryZone | None, Decimal, Decimal]:
    """-> (zone, fee, min_order). Raises if a needed zone is missing."""
    zones = active_zones(db, rid)
    if zones:
        zone = next((z for z in zones if z.id == zone_id), None)
        if zone is None:
            raise OrderError("zone_required", "اختار منطقة التوصيل")
        min_order = zone.min_order if zone.min_order > 0 else Decimal(str(settings["min_order"]))
        return zone, zone.fee, min_order
    return None, Decimal(str(settings["delivery_fee"])), Decimal(str(settings["min_order"]))


def upsert_customer(db: Session, rid: int, phone: str, name: str | None) -> Customer:
    cust = db.scalar(select(Customer).where(Customer.restaurant_id == rid, Customer.phone == phone))
    if cust is None:
        cust = Customer(restaurant_id=rid, phone=phone, name=name)
        db.add(cust)
        db.flush()
    elif name and cust.name != name:
        cust.name = name
    return cust


def _next_order_no(db: Session, rid: int, day: dt.date) -> int:
    stmt = (
        insert(OrderCounter)
        .values(restaurant_id=rid, day=day, last_no=1)
        .on_conflict_do_update(
            index_elements=["restaurant_id", "day"], set_={"last_no": OrderCounter.last_no + 1}
        )
        .returning(OrderCounter.last_no)
    )
    return db.execute(stmt).scalar_one()


def create_order(
    db: Session,
    *,
    restaurant: Restaurant,
    settings: dict,
    customer: Customer,
    lines: list[dict],
    fulfillment: str,
    payment_method: str,
    channel: str,
    zone_id: int | None = None,
    address: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    notes: str | None = None,
    conversation_id: int | None = None,
    priced: PricedCart | None = None,
    now: dt.datetime | None = None,
) -> Order:
    rid = restaurant.id
    check_open(restaurant, settings, now)

    if fulfillment == "delivery" and not settings["delivery_enabled"]:
        raise OrderError("no_delivery", "التوصيل مش متاح حاليًا")
    if fulfillment == "pickup" and not settings["pickup_enabled"]:
        raise OrderError("no_pickup", "الاستلام من المطعم مش متاح حاليًا")
    if fulfillment not in ("delivery", "pickup"):
        raise OrderError("bad_fulfillment", "اختار توصيل أو استلام")
    if payment_method not in settings["payment_methods"]:
        raise OrderError("bad_payment", "طريقة الدفع دي مش متاحة")

    cart = priced or price_lines(db, rid, lines)
    if cart.removed:
        raise OrderError(
            "items_changed",
            "في أصناف خلصت أو اتغيرت: " + "، ".join(cart.removed),
            {"removed": cart.removed},
        )
    if not cart.lines:
        raise OrderError("empty", "السلة فاضية")

    zone = None
    fee = Decimal("0")
    if fulfillment == "delivery":
        zone, fee, min_order = delivery_terms(db, rid, settings, zone_id)
        if cart.subtotal < min_order:
            raise OrderError(
                "below_min",
                f"الحد الأدنى للتوصيل {money(min_order):g} ج",
                {"min_order": money(min_order)},
            )
        address = (address or "").strip()
        if len(address) < 5:
            raise OrderError("address_required", "اكتب العنوان بالتفصيل")
        if (lat is None) != (lng is None) or (lat is not None and not valid_coords(lat, lng)):
            raise OrderError("bad_location", "الموقع مش صحيح")
    else:
        lat = lng = None

    day = hours.business_day(restaurant.timezone, settings["business_day_starts"], now)
    order = Order(
        restaurant_id=rid,
        order_no=_next_order_no(db, rid, day),
        business_day=day,
        public_token=new_public_token(),
        customer_id=customer.id,
        conversation_id=conversation_id,
        channel=channel,
        fulfillment=fulfillment,
        zone_id=zone.id if zone else None,
        zone_name_snapshot=zone.name_ar if zone else None,
        address_text=address if fulfillment == "delivery" else None,
        lat=Decimal(str(round(float(lat), 6))) if lat is not None else None,
        lng=Decimal(str(round(float(lng), 6))) if lng is not None else None,
        subtotal=cart.subtotal,
        delivery_fee=fee,
        total=cart.subtotal + fee,
        payment_method=payment_method,
        status="placed",
        notes=(notes or "").strip()[:500] or None,
        eta_minutes=int(settings["eta_minutes"]),
        is_demo=restaurant.demo_mode,
    )
    for ln in cart.lines:
        oi = OrderItem(
            item_id=ln.item_id,
            variant_id=ln.variant_id,
            name_snapshot=ln.item_name,
            variant_snapshot=ln.variant_name,
            unit_price=ln.unit_price,
            qty=ln.qty,
            line_total=ln.line_total,
            note=ln.note,
        )
        oi.addons = [OrderItemAddon(addon_id=a.id, name_snapshot=a.name, price=a.price) for a in ln.addons]
        order.items.append(oi)
    order.events.append(OrderStatusEvent(status="placed", actor="customer"))
    db.add(order)

    if fulfillment == "delivery":
        customer.last_address = address
        customer.last_zone_id = zone.id if zone else None
        customer.last_lat = order.lat  # cleared when the new address has no pin
        customer.last_lng = order.lng
    db.flush()
    return order


class TransitionError(Exception):
    pass


def transition(db: Session, order: Order, new_status: str, actor: str, reject_reason: str | None = None) -> Order:
    allowed = TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise TransitionError(f"{order.status} -> {new_status} not allowed")
    if new_status == "out_for_delivery" and order.fulfillment != "delivery":
        raise TransitionError("pickup orders cannot go out for delivery")
    if new_status == "ready_for_pickup" and order.fulfillment != "pickup":
        raise TransitionError("delivery orders are not picked up")
    if new_status == "rejected":
        reject_reason = (reject_reason or "").strip()
        if not reject_reason:
            raise TransitionError("reject_reason required")
        order.reject_reason = reject_reason[:300]
    order.status = new_status
    order.events.append(OrderStatusEvent(status=new_status, actor=actor))
    if new_status == "completed" and order.payment_method == "cod":
        order.payment_status = "paid"
    db.flush()
    return order


def load_order(db: Session, rid: int, order_id: int) -> Order | None:
    return db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.restaurant_id == rid)
        .options(
            selectinload(Order.items).selectinload(OrderItem.addons),
            selectinload(Order.events),
            selectinload(Order.customer),
        )
    )


def serialize(order: Order, *, private: bool = True) -> dict:
    data = {
        "id": order.id,
        "order_no": order.order_no,
        "business_day": order.business_day.isoformat(),
        "status": order.status,
        "channel": order.channel,
        "fulfillment": order.fulfillment,
        "zone": order.zone_name_snapshot,
        "subtotal": money(order.subtotal),
        "delivery_fee": money(order.delivery_fee),
        "total": money(order.total),
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "reject_reason": order.reject_reason,
        "eta_minutes": order.eta_minutes,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "items": [
            {
                "name": it.name_snapshot,
                "variant": it.variant_snapshot,
                "unit_price": money(it.unit_price),
                "qty": it.qty,
                "line_total": money(it.line_total),
                "note": it.note,
                "addons": [{"name": a.name_snapshot, "price": money(a.price)} for a in it.addons],
            }
            for it in order.items
        ],
        "events": [{"status": e.status, "at": e.created_at.isoformat() if e.created_at else None} for e in order.events],
    }
    if private:
        data.update(
            {
                "customer": {"name": order.customer.name, "phone": order.customer.phone} if order.customer else None,
                "address": order.address_text,
                "location": {"lat": float(order.lat), "lng": float(order.lng)} if order.lat is not None else None,
                "driver": {
                    "name": order.driver_name,
                    "phone": order.driver_phone,
                    "sent_at": order.driver_sent_at.isoformat() if order.driver_sent_at else None,
                }
                if order.driver_sent_at
                else None,
                "notes": order.notes,
                "is_demo": order.is_demo,
                "conversation_id": order.conversation_id,
                "public_token": order.public_token,
            }
        )
    return data


def maps_url(lat, lng) -> str:
    return f"https://www.google.com/maps?q={float(lat):.6f},{float(lng):.6f}"


def local_phone(phone: str | None) -> str:
    if phone and phone.startswith("20") and len(phone) == 12:
        return "0" + phone[2:]
    return phone or ""


def driver_message(order: Order, restaurant_name: str) -> str:
    """Ready-to-send WhatsApp text for the delivery driver."""
    lines = [f"🛵 طلب توصيل #{order.order_no} — {restaurant_name}"]
    if order.customer:
        lines.append(f"👤 العميل: {order.customer.name or '-'}")
        lines.append(f"📞 {local_phone(order.customer.phone)}")
    if order.zone_name_snapshot:
        lines.append(f"📍 المنطقة: {order.zone_name_snapshot}")
    if order.address_text:
        lines.append(f"🏠 العنوان: {order.address_text}")
    if order.lat is not None and order.lng is not None:
        lines.append(f"🗺️ الموقع: {maps_url(order.lat, order.lng)}")
    lines.append("🍔 الطلب:")
    for it in order.items:
        name = f"{it.name_snapshot} ({it.variant_snapshot})" if it.variant_snapshot else it.name_snapshot
        extra = " + " + "، ".join(a.name_snapshot for a in it.addons) if it.addons else ""
        lines.append(f"• {it.qty}× {name}{extra}")
    if order.notes:
        lines.append(f"📝 {order.notes}")
    total = f"{money(order.total):g} ج"
    if order.payment_method == "cod":
        lines.append(f"💵 المطلوب تحصيله: {total} (كاش)")
    else:
        lines.append(f"💳 الدفع: محفظة ({total})")
    return "\n".join(lines)
