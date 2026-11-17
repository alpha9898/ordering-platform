"""Platform-level restaurant management (super admin)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    Addon,
    Category,
    CategoryAddon,
    Conversation,
    Customer,
    DeliveryZone,
    Item,
    ItemVariant,
    Order,
    OrderCounter,
    OrderItem,
    Restaurant,
    User,
)
from ..security import hash_password
from . import menu as menu_svc
from . import settings as settings_svc
from .orders import serialize


def create_restaurant(
    db: Session,
    *,
    name: str,
    slug: str,
    owner_username: str,
    owner_password: str,
    demo_mode: bool = True,
    copy_menu_from: int | None = None,
) -> Restaurant:
    r = Restaurant(name_ar=name.strip(), slug=slug, status="trial", demo_mode=demo_mode)
    db.add(r)
    db.flush()
    settings_svc.seed_defaults(db, r.id)
    db.add(
        User(
            restaurant_id=r.id,
            username=owner_username.strip().lower(),
            display_name=f"صاحب {name.strip()}",
            password_hash=hash_password(owner_password),
            role="owner",
        )
    )
    if copy_menu_from:
        copy_menu(db, copy_menu_from, r.id)
    db.flush()
    return r


def copy_menu(db: Session, src_id: int, dst_id: int) -> None:
    addon_map: dict[int, int] = {}
    for a in db.scalars(select(Addon).where(Addon.restaurant_id == src_id)).all():
        na = Addon(restaurant_id=dst_id, name_ar=a.name_ar, price=a.price, available=a.available, sort=a.sort)
        db.add(na)
        db.flush()
        addon_map[a.id] = na.id
    cats = db.scalars(
        select(Category).where(Category.restaurant_id == src_id).options(selectinload(Category.items).selectinload(Item.variants))
    ).all()
    for c in cats:
        nc = Category(restaurant_id=dst_id, name_ar=c.name_ar, sort=c.sort, active=c.active)
        db.add(nc)
        db.flush()
        for it in c.items:
            ni = Item(
                restaurant_id=dst_id,
                category_id=nc.id,
                name_ar=it.name_ar,
                description_ar=it.description_ar,
                image_url=it.image_url,
                available=it.available,
                sort=it.sort,
            )
            ni.variants = [ItemVariant(name_ar=v.name_ar, price=v.price, available=v.available, sort=v.sort) for v in it.variants]
            db.add(ni)
        for link in db.scalars(select(CategoryAddon).where(CategoryAddon.category_id == c.id)).all():
            db.add(CategoryAddon(category_id=nc.id, addon_id=addon_map[link.addon_id], price_override=link.price_override))
    db.flush()


def stats(db: Session, rid: int, tz_today: dt.date) -> dict:
    today = db.scalar(select(func.count()).select_from(Order).where(Order.restaurant_id == rid, Order.business_day == tz_today)) or 0
    month = db.scalar(
        select(func.count()).select_from(Order).where(
            Order.restaurant_id == rid, Order.business_day >= tz_today - dt.timedelta(days=30)
        )
    ) or 0
    revenue = db.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.restaurant_id == rid,
            Order.business_day >= tz_today - dt.timedelta(days=30),
            Order.status == "completed",
        )
    )
    demo = db.scalar(select(func.count()).select_from(Order).where(Order.restaurant_id == rid, Order.is_demo.is_(True))) or 0
    return {"orders_today": today, "orders_30d": month, "revenue_30d": float(revenue or 0), "demo_orders": demo}


def clear_demo(db: Session, rid: int) -> dict:
    orders = db.execute(delete(Order).where(Order.restaurant_id == rid, Order.is_demo.is_(True))).rowcount
    convs = db.execute(delete(Conversation).where(Conversation.restaurant_id == rid, Conversation.channel == "web_chat")).rowcount
    db.execute(
        delete(Customer).where(
            Customer.restaurant_id == rid,
            ~exists().where(Order.customer_id == Customer.id),
            ~exists().where(Conversation.customer_id == Customer.id),
        )
    )
    db.execute(
        delete(OrderCounter).where(
            OrderCounter.restaurant_id == rid,
            ~exists().where(Order.restaurant_id == rid, Order.business_day == OrderCounter.day),
        )
    )
    db.flush()
    return {"orders_deleted": orders, "conversations_deleted": convs}


def export(db: Session, rid: int) -> dict:
    r = db.get(Restaurant, rid)
    orders = db.scalars(
        select(Order)
        .where(Order.restaurant_id == rid)
        .options(selectinload(Order.items).selectinload(OrderItem.addons), selectinload(Order.events), selectinload(Order.customer))
        .order_by(Order.id)
    ).all()
    customers = db.scalars(select(Customer).where(Customer.restaurant_id == rid).order_by(Customer.id)).all()
    zones = db.scalars(select(DeliveryZone).where(DeliveryZone.restaurant_id == rid)).all()
    return {
        "exported_at": dt.datetime.now(dt.UTC).isoformat(),
        "restaurant": {"id": r.id, "slug": r.slug, "name": r.name_ar, "status": r.status, "created_at": r.created_at.isoformat()},
        "settings": settings_svc.get_all(db, rid),
        "menu": menu_svc.full_menu(db, rid),
        "zones": [{"name": z.name_ar, "fee": float(z.fee), "min_order": float(z.min_order), "active": z.active} for z in zones],
        "customers": [{"phone": c.phone, "name": c.name, "last_address": c.last_address} for c in customers],
        "orders": [serialize(o) for o in orders],
    }
