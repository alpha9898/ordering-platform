"""Public customer endpoints: restaurant + menu, web-menu orders, tracking."""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..models import Order, OrderItem, Restaurant
from ..services import hours, menu, ratelimit
from ..services import settings as settings_svc
from ..services.orders import OrderError, active_zones, create_order, restaurant_available, serialize, upsert_customer

router = APIRouter(prefix="/public", tags=["public"])


def normalize_phone(raw: str) -> str:
    digits = settings_svc.normalize_phone(raw)
    if digits is None:
        raise HTTPException(status_code=422, detail="رقم الموبايل مش صحيح")
    return digits


def get_restaurant(db: Session, slug: str) -> Restaurant:
    r = db.scalar(select(Restaurant).where(Restaurant.slug == slug))
    if r is None or r.status == "archived":
        raise HTTPException(status_code=404, detail="المطعم مش موجود")
    return r


def restaurant_public_info(db: Session, r: Restaurant) -> dict:
    s = settings_svc.get_all(db, r.id)
    open_now = hours.is_open(s["working_hours"], r.timezone)
    return {
        "slug": r.slug,
        "name": r.name_ar,
        "available": restaurant_available(r),
        "accepting_orders": s["accepting_orders"],
        "open_now": open_now,
        "opens": None if open_now else hours.describe_next_opening(s["working_hours"], r.timezone),
        "eta_minutes": s["eta_minutes"],
        "delivery_enabled": s["delivery_enabled"],
        "pickup_enabled": s["pickup_enabled"],
        "delivery_fee": float(s["delivery_fee"]),
        "min_order": float(s["min_order"]),
        "payment_methods": s["payment_methods"],
        "contact_phone": s["contact_phone"],
        "zones": [
            {"id": z.id, "name": z.name_ar, "fee": float(z.fee), "min_order": float(z.min_order)}
            for z in active_zones(db, r.id)
        ],
    }


@router.get("/r/{slug}")
def restaurant_menu(slug: str, db: Session = Depends(get_db)):
    r = get_restaurant(db, slug)
    info = restaurant_public_info(db, r)
    info["menu"] = menu.public_menu(db, r.id) if info["available"] else []
    return info


class LineIn(BaseModel):
    variant_id: int
    addon_ids: list[int] = Field(default_factory=list, max_length=20)
    qty: int = Field(ge=1, le=50)
    note: str | None = Field(default=None, max_length=200)


class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    phone: str = Field(min_length=6, max_length=20)


class OrderIn(BaseModel):
    customer: CustomerIn
    lines: list[LineIn] = Field(min_length=1, max_length=40)
    fulfillment: str
    zone_id: int | None = None
    address: str | None = Field(default=None, max_length=300)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    payment_method: str = "cod"
    notes: str | None = Field(default=None, max_length=500)


@router.post("/r/{slug}/orders")
def place_order(slug: str, body: OrderIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    ratelimit.hit(db, f"order_ip:{ratelimit.client_ip(request)}", s.orders_per_hour_ip, 3600)
    r = get_restaurant(db, slug)
    settings = settings_svc.get_all(db, r.id)
    customer = upsert_customer(db, r.id, normalize_phone(body.customer.phone), body.customer.name.strip())
    try:
        order = create_order(
            db,
            restaurant=r,
            settings=settings,
            customer=customer,
            lines=[ln.model_dump() for ln in body.lines],
            fulfillment=body.fulfillment,
            payment_method=body.payment_method,
            channel="web_menu",
            zone_id=body.zone_id,
            address=body.address,
            lat=body.lat,
            lng=body.lng,
            notes=body.notes,
        )
    except OrderError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": e.code, "message": e.message_ar, **e.extra}) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail="كمية غير صحيحة") from e
    db.commit()
    return {"order_no": order.order_no, "token": order.public_token, "total": float(order.total)}


@router.get("/orders/{token}")
def track_order(token: str, db: Session = Depends(get_db)):
    order = db.scalar(
        select(Order)
        .where(Order.public_token == token)
        .options(selectinload(Order.items).selectinload(OrderItem.addons), selectinload(Order.events))
    )
    if order is None:
        raise HTTPException(status_code=404, detail="الطلب مش موجود")
    r = db.get(Restaurant, order.restaurant_id)
    data = serialize(order, private=False)
    data["restaurant"] = {"slug": r.slug, "name": r.name_ar}
    return data
