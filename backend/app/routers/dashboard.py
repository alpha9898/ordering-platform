"""Restaurant dashboard API. Every query is filtered by the caller's
restaurant (deps.require_restaurant); ids from other restaurants 404."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import Principal, require_manager, require_restaurant
from ..engine.messages import LimitError
from ..models import (
    Addon,
    Category,
    CategoryAddon,
    Conversation,
    Customer,
    DeliveryZone,
    Item,
    ItemVariant,
    Message,
    Order,
    OrderItem,
    Restaurant,
)
from ..services import conversations as conv_svc
from ..services import hours, menu
from ..services import settings as settings_svc
from ..services.notify import notify_status
from ..services.orders import ACTIVE_STATUSES, TransitionError, driver_message, load_order, serialize, transition

router = APIRouter(prefix="/dash", tags=["dashboard"])

Ctx = tuple[Principal, Restaurant]


def _get_owned(db: Session, model, obj_id: int, rid: int):
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "restaurant_id", None) != rid:
        raise HTTPException(status_code=404, detail="not_found")
    return obj


def _variant_owned(db: Session, variant_id: int, rid: int) -> ItemVariant:
    v = db.get(ItemVariant, variant_id)
    if v is None or db.get(Item, v.item_id).restaurant_id != rid:
        raise HTTPException(status_code=404, detail="not_found")
    return v


def _actor(p: Principal) -> str:
    return f"{p.user.role}:{p.user.username}"


def _orders_query(rid: int):
    return (
        select(Order)
        .where(Order.restaurant_id == rid)
        .options(
            selectinload(Order.items).selectinload(OrderItem.addons),
            selectinload(Order.events),
            selectinload(Order.customer),
        )
    )


def _conv_summary(db: Session, c: Conversation) -> dict:
    cust = db.get(Customer, c.customer_id) if c.customer_id else None
    last = db.scalar(select(Message).where(Message.conversation_id == c.id).order_by(Message.id.desc()).limit(1))
    return {
        "id": c.id,
        "channel": c.channel,
        "state": c.state,
        "customer": {"name": cust.name, "phone": cust.phone} if cust else None,
        "human_requested_at": c.human_requested_at.isoformat() if c.human_requested_at else None,
        "bot_paused_until": c.human_until.isoformat() if c.human_until else None,
        "last_message": conv_svc.message_dict(last) if last else None,
        "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
    }


# ------------------------------------------------------------------- board
@router.get("/board")
def board(ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    _, r = ctx
    orders = db.scalars(_orders_query(r.id).where(Order.status.in_(ACTIVE_STATUSES)).order_by(Order.created_at)).all()
    human = db.scalars(
        select(Conversation)
        .where(Conversation.restaurant_id == r.id, Conversation.human_requested_at.is_not(None))
        .order_by(Conversation.human_requested_at)
    ).all()
    s = settings_svc.get_all(db, r.id)
    return {
        "orders": [serialize(o) for o in orders],
        "human": [_conv_summary(db, c) for c in human],
        "accepting_orders": s["accepting_orders"],
        "eta_minutes": s["eta_minutes"],
        "drivers": s["drivers"],
        "open_now": hours.is_open(s["working_hours"], r.timezone),
        "server_time": dt.datetime.now(dt.UTC).isoformat(),
    }


@router.get("/orders")
def list_orders(
    day: dt.date | None = None,
    q: str | None = None,
    status: str | None = None,
    ctx: Ctx = Depends(require_restaurant),
    db: Session = Depends(get_db),
):
    _, r = ctx
    stmt = _orders_query(r.id)
    if day is not None:
        stmt = stmt.where(Order.business_day == day)
    if status:
        stmt = stmt.where(Order.status == status)
    if q:
        q = q.strip().lstrip("#")
        conds = [Customer.phone.contains(q), Customer.name.ilike(f"%{q}%")]
        if q.isdigit():
            conds.append(Order.order_no == int(q))
        stmt = stmt.join(Customer, Customer.id == Order.customer_id).where(or_(*conds))
    orders = db.scalars(stmt.order_by(Order.created_at.desc()).limit(300)).all()
    return {"orders": [serialize(o) for o in orders]}


@router.get("/orders/{order_id}")
def get_order(order_id: int, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    order = load_order(db, ctx[1].id, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="not_found")
    return serialize(order)


class StatusIn(BaseModel):
    status: str
    reject_reason: str | None = Field(default=None, max_length=300)


@router.post("/orders/{order_id}/status")
def change_status(order_id: int, body: StatusIn, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    p, r = ctx
    order = db.scalar(
        select(Order).where(Order.id == order_id, Order.restaurant_id == r.id).with_for_update()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="not_found")
    order = load_order(db, r.id, order_id)
    try:
        transition(db, order, body.status, _actor(p), body.reject_reason)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    notified = notify_status(db, order, r)
    db.commit()
    data = serialize(load_order(db, r.id, order_id))
    data["customer_notified"] = notified
    return data


class DriverIn(BaseModel):
    phone: str | None = Field(default=None, max_length=32)  # None = share without assigning


DRIVER_STATUSES = ("accepted", "preparing", "out_for_delivery")


@router.post("/orders/{order_id}/driver")
def send_to_driver(order_id: int, body: DriverIn, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    """Record which driver got the order and return a ready WhatsApp link
    (wa.me with the order, address and map pin) for the dashboard to open."""
    _, r = ctx
    order = load_order(db, r.id, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="not_found")
    if order.fulfillment != "delivery" or order.status not in DRIVER_STATUSES:
        raise HTTPException(status_code=409, detail="الطلب ده مش جاهز للدليفري")
    text = driver_message(order, r.name_ar)
    target = ""
    if body.phone:
        phone = settings_svc.normalize_phone(body.phone)
        driver = next((d for d in settings_svc.get_all(db, r.id)["drivers"] if d["phone"] == phone), None)
        if driver is None:
            raise HTTPException(status_code=422, detail="الدليفري ده مش متسجل")
        order.driver_name, order.driver_phone = driver["name"], driver["phone"]
        order.driver_sent_at = dt.datetime.now(dt.UTC)
        target = driver["phone"]
        db.commit()
        order = load_order(db, r.id, order_id)
    return {"order": serialize(order), "whatsapp_url": f"https://wa.me/{target}?text={quote(text)}", "text": text}


@router.get("/customers/{phone}/orders")
def customer_orders(phone: str, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    stmt = _orders_query(ctx[1].id).join(Customer, Customer.id == Order.customer_id).where(Customer.phone == phone)
    return {"orders": [serialize(o) for o in db.scalars(stmt.order_by(Order.created_at.desc()).limit(50)).all()]}


# -------------------------------------------------------------------- menu
@router.get("/menu")
def get_menu(ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    return menu.full_menu(db, ctx[1].id)


class ItemPatch(BaseModel):
    available: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    category_id: int | None = None
    sort: int | None = None
    image_url: str | None = Field(default=None, max_length=500)


def _require_manage_for(body: BaseModel, p: Principal, staff_fields: set[str]) -> None:
    changed = set(body.model_dump(exclude_unset=True))
    if changed - staff_fields and not p.can_manage:
        raise HTTPException(status_code=403, detail="owner_only")


@router.patch("/items/{item_id}")
def patch_item(item_id: int, body: ItemPatch, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    p, r = ctx
    _require_manage_for(body, p, {"available"})
    item = _get_owned(db, Item, item_id, r.id)
    data = body.model_dump(exclude_unset=True)
    if "category_id" in data:
        _get_owned(db, Category, data["category_id"], r.id)
        item.category_id = data["category_id"]
    for field, attr in (("available", "available"), ("name", "name_ar"), ("description", "description_ar"), ("sort", "sort"), ("image_url", "image_url")):
        if field in data:
            setattr(item, attr, data[field])
    db.commit()
    return {"ok": True}


class VariantPatch(BaseModel):
    available: bool | None = None
    name: str | None = Field(default=None, max_length=40)
    price: Decimal | None = Field(default=None, ge=0, le=100000)
    sort: int | None = None


@router.patch("/variants/{variant_id}")
def patch_variant(variant_id: int, body: VariantPatch, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    p, r = ctx
    _require_manage_for(body, p, {"available"})
    v = _variant_owned(db, variant_id, r.id)
    data = body.model_dump(exclude_unset=True)
    for field, attr in (("available", "available"), ("name", "name_ar"), ("price", "price"), ("sort", "sort")):
        if field in data:
            setattr(v, attr, data[field] if field != "name" else (data[field] or None))
    db.commit()
    return {"ok": True}


class AddonPatch(BaseModel):
    available: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=60)
    price: Decimal | None = Field(default=None, ge=0, le=100000)
    sort: int | None = None


@router.patch("/addons/{addon_id}")
def patch_addon(addon_id: int, body: AddonPatch, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    p, r = ctx
    _require_manage_for(body, p, {"available"})
    a = _get_owned(db, Addon, addon_id, r.id)
    data = body.model_dump(exclude_unset=True)
    for field, attr in (("available", "available"), ("name", "name_ar"), ("price", "price"), ("sort", "sort")):
        if field in data:
            setattr(a, attr, data[field])
    db.commit()
    return {"ok": True}


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    sort: int = 0
    active: bool = True


@router.post("/categories")
def create_category(body: CategoryIn, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    c = Category(restaurant_id=ctx[1].id, name_ar=body.name.strip(), sort=body.sort, active=body.active)
    db.add(c)
    db.commit()
    return {"id": c.id}


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    sort: int | None = None
    active: bool | None = None


@router.patch("/categories/{category_id}")
def patch_category(category_id: int, body: CategoryPatch, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    p, r = ctx
    _require_manage_for(body, p, {"active"})
    c = _get_owned(db, Category, category_id, r.id)
    data = body.model_dump(exclude_unset=True)
    for field, attr in (("name", "name_ar"), ("sort", "sort"), ("active", "active")):
        if field in data:
            setattr(c, attr, data[field])
    db.commit()
    return {"ok": True}


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    c = _get_owned(db, Category, category_id, ctx[1].id)
    if db.scalar(select(func.count()).select_from(Item).where(Item.category_id == c.id)):
        raise HTTPException(status_code=409, detail="القسم فيه أصناف، انقلها أو امسحها الأول")
    db.delete(c)
    db.commit()
    return {"ok": True}


class CategoryAddonIn(BaseModel):
    addon_id: int
    price_override: Decimal | None = Field(default=None, ge=0, le=100000)


@router.put("/categories/{category_id}/addons")
def set_category_addons(category_id: int, body: list[CategoryAddonIn], ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    rid = ctx[1].id
    c = _get_owned(db, Category, category_id, rid)
    for link in body:
        _get_owned(db, Addon, link.addon_id, rid)
    db.execute(delete(CategoryAddon).where(CategoryAddon.category_id == c.id))
    for link in body:
        db.add(CategoryAddon(category_id=c.id, addon_id=link.addon_id, price_override=link.price_override))
    db.commit()
    return {"ok": True}


class VariantIn(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    price: Decimal = Field(ge=0, le=100000)
    available: bool = True


class ItemIn(BaseModel):
    category_id: int
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    image_url: str | None = Field(default=None, max_length=500)
    sort: int = 0
    variants: list[VariantIn] = Field(min_length=1, max_length=10)


@router.post("/items")
def create_item(body: ItemIn, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    rid = ctx[1].id
    _get_owned(db, Category, body.category_id, rid)
    item = Item(
        restaurant_id=rid,
        category_id=body.category_id,
        name_ar=body.name.strip(),
        description_ar=(body.description or "").strip() or None,
        image_url=body.image_url,
        sort=body.sort,
    )
    item.variants = [
        ItemVariant(name_ar=(v.name or "").strip() or None, price=v.price, available=v.available, sort=i)
        for i, v in enumerate(body.variants)
    ]
    db.add(item)
    db.commit()
    return {"id": item.id}


@router.delete("/items/{item_id}")
def delete_item(item_id: int, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    item = _get_owned(db, Item, item_id, ctx[1].id)
    db.delete(item)  # past orders keep their name/price snapshots
    db.commit()
    return {"ok": True}


@router.post("/items/{item_id}/variants")
def add_variant(item_id: int, body: VariantIn, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    item = _get_owned(db, Item, item_id, ctx[1].id)
    v = ItemVariant(item_id=item.id, name_ar=(body.name or "").strip() or None, price=body.price, available=body.available, sort=len(item.variants))
    db.add(v)
    db.commit()
    return {"id": v.id}


@router.delete("/variants/{variant_id}")
def delete_variant(variant_id: int, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    v = _variant_owned(db, variant_id, ctx[1].id)
    count = db.scalar(select(func.count()).select_from(ItemVariant).where(ItemVariant.item_id == v.item_id))
    if count <= 1:
        raise HTTPException(status_code=409, detail="لازم الصنف يفضل له سعر واحد على الأقل")
    db.delete(v)
    db.commit()
    return {"ok": True}


class AddonIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    price: Decimal = Field(ge=0, le=100000)
    category_ids: list[int] = Field(default_factory=list)
    sort: int = 0


@router.post("/addons")
def create_addon(body: AddonIn, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    rid = ctx[1].id
    a = Addon(restaurant_id=rid, name_ar=body.name.strip(), price=body.price, sort=body.sort)
    db.add(a)
    db.flush()
    for cid in set(body.category_ids):
        _get_owned(db, Category, cid, rid)
        db.add(CategoryAddon(category_id=cid, addon_id=a.id))
    db.commit()
    return {"id": a.id}


@router.delete("/addons/{addon_id}")
def delete_addon(addon_id: int, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    a = _get_owned(db, Addon, addon_id, ctx[1].id)
    db.delete(a)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- settings
@router.get("/settings")
def get_settings_(ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    _, r = ctx
    s = settings_svc.get_all(db, r.id)
    return {"settings": s, "open_now": hours.is_open(s["working_hours"], r.timezone)}


@router.patch("/settings")
def patch_settings(body: dict, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    p, r = ctx
    allowed = settings_svc.OWNER_KEYS if p.can_manage else settings_svc.STAFF_KEYS
    try:
        s = settings_svc.update(db, r.id, body, allowed)
    except settings_svc.SettingsError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    return {"settings": s, "open_now": hours.is_open(s["working_hours"], r.timezone)}


# ------------------------------------------------------------------- zones
class ZoneIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    fee: Decimal = Field(ge=0, le=100000)
    min_order: Decimal = Field(default=Decimal("0"), ge=0, le=100000)
    active: bool = True
    sort: int = 0


def _zone_dict(z: DeliveryZone) -> dict:
    return {"id": z.id, "name": z.name_ar, "fee": float(z.fee), "min_order": float(z.min_order), "active": z.active, "sort": z.sort}


@router.get("/zones")
def list_zones(ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    zones = db.scalars(select(DeliveryZone).where(DeliveryZone.restaurant_id == ctx[1].id).order_by(DeliveryZone.sort, DeliveryZone.id)).all()
    return {"zones": [_zone_dict(z) for z in zones]}


@router.post("/zones")
def create_zone(body: ZoneIn, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    z = DeliveryZone(restaurant_id=ctx[1].id, name_ar=body.name.strip(), fee=body.fee, min_order=body.min_order, active=body.active, sort=body.sort)
    db.add(z)
    db.commit()
    return _zone_dict(z)


@router.patch("/zones/{zone_id}")
def patch_zone(zone_id: int, body: ZoneIn, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    z = _get_owned(db, DeliveryZone, zone_id, ctx[1].id)
    z.name_ar, z.fee, z.min_order, z.active, z.sort = body.name.strip(), body.fee, body.min_order, body.active, body.sort
    db.commit()
    return _zone_dict(z)


@router.delete("/zones/{zone_id}")
def delete_zone(zone_id: int, ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    z = _get_owned(db, DeliveryZone, zone_id, ctx[1].id)
    db.delete(z)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------- conversations
@router.get("/conversations")
def list_conversations(needs_human: bool = False, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    stmt = select(Conversation).where(Conversation.restaurant_id == ctx[1].id)
    if needs_human:
        stmt = stmt.where(Conversation.human_requested_at.is_not(None))
    convs = db.scalars(stmt.order_by(Conversation.last_message_at.desc().nulls_last()).limit(100)).all()
    return {"conversations": [_conv_summary(db, c) for c in convs]}


@router.get("/conversations/{conv_id}/messages")
def conversation_messages(conv_id: int, after: int = 0, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    c = _get_owned(db, Conversation, conv_id, ctx[1].id)
    rows = db.scalars(select(Message).where(Message.conversation_id == c.id, Message.id > after).order_by(Message.id).limit(500)).all()
    return {"conversation": _conv_summary(db, c), "messages": [conv_svc.message_dict(m) for m in rows]}


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/conversations/{conv_id}/reply")
def reply(conv_id: int, body: ReplyIn, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    c = _get_owned(db, Conversation, conv_id, ctx[1].id)
    c = conv_svc.lock(db, c.id)
    try:
        msg = conv_svc.staff_reply(db, c, body.text.strip())
    except LimitError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    return conv_svc.message_dict(msg)


@router.post("/conversations/{conv_id}/resolve")
def resolve(conv_id: int, ctx: Ctx = Depends(require_restaurant), db: Session = Depends(get_db)):
    c = _get_owned(db, Conversation, conv_id, ctx[1].id)
    c = conv_svc.lock(db, c.id)
    conv_svc.resolve_human(c)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ excel import
from fastapi import File, UploadFile  # noqa: E402
from fastapi.responses import Response as RawResponse  # noqa: E402

from ..services import excel_import  # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD = 2 * 1024 * 1024


@router.get("/menu/export.xlsx")
def export_menu_xlsx(ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    data = excel_import.export_workbook(db, ctx[1].id)
    return RawResponse(
        content=data,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{ctx[1].slug}-menu.xlsx"'},
    )


@router.post("/menu/import")
async def import_menu(apply: bool = False, file: UploadFile = File(...), ctx: Ctx = Depends(require_manager), db: Session = Depends(get_db)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="الملف أكبر من 2 ميجا")
    parsed = excel_import.parse(data)
    summary = parsed.summary()
    if apply:
        if parsed.errors:
            raise HTTPException(status_code=422, detail={"message": "صلّح الأخطاء الأول", **summary})
        excel_import.apply(db, ctx[1].id, parsed)
        db.commit()
        summary["applied"] = True
    return summary
