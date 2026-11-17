"""Super-admin API: manage restaurants and their users."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, require_super
from ..models import RESTAURANT_STATUSES, Restaurant, User
from ..security import hash_password, make_session_token
from ..services import hours
from ..services import restaurants as svc
from ..services import settings as settings_svc
from .auth import principal_dict, set_session_cookie

router = APIRouter(prefix="/admin", tags=["admin"])

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,40}$")


def _slug(v: str) -> str:
    v = v.strip().lower()
    if not SLUG_RE.match(v):
        raise ValueError("slug: حروف إنجليزي صغيرة وأرقام و - بس")
    return v


def _username(v: str) -> str:
    v = v.strip().lower()
    if not USERNAME_RE.match(v):
        raise ValueError("اسم المستخدم: 3-40 حرف إنجليزي/أرقام")
    return v


def _restaurant(db: Session, rid: int) -> Restaurant:
    r = db.get(Restaurant, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="not_found")
    return r


def _user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role, "active": u.active}


def _restaurant_dict(db: Session, r: Restaurant) -> dict:
    s = settings_svc.get_all(db, r.id)
    today = hours.business_day(r.timezone, s["business_day_starts"])
    return {
        "id": r.id,
        "slug": r.slug,
        "name": r.name_ar,
        "status": r.status,
        "demo_mode": r.demo_mode,
        "created_at": r.created_at.isoformat(),
        "accepting_orders": s["accepting_orders"],
        "open_now": hours.is_open(s["working_hours"], r.timezone),
        "stats": svc.stats(db, r.id, today),
    }


@router.get("/restaurants")
def list_restaurants(p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    rs = db.scalars(select(Restaurant).order_by(Restaurant.created_at)).all()
    return {"restaurants": [_restaurant_dict(db, r) for r in rs]}


class RestaurantIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    slug: str
    owner_username: str
    owner_password: str = Field(min_length=8, max_length=200)
    demo_mode: bool = True
    copy_menu_from: int | None = None

    @field_validator("slug")
    @classmethod
    def _v_slug(cls, v: str) -> str:
        return _slug(v)

    @field_validator("owner_username")
    @classmethod
    def _v_user(cls, v: str) -> str:
        return _username(v)


@router.post("/restaurants")
def create_restaurant(body: RestaurantIn, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    if db.scalar(select(Restaurant).where(Restaurant.slug == body.slug)):
        raise HTTPException(status_code=409, detail="الـ slug ده مستخدم")
    if db.scalar(select(User).where(func.lower(User.username) == body.owner_username)):
        raise HTTPException(status_code=409, detail="اسم المستخدم ده مستخدم")
    if body.copy_menu_from is not None:
        _restaurant(db, body.copy_menu_from)
    r = svc.create_restaurant(
        db,
        name=body.name,
        slug=body.slug,
        owner_username=body.owner_username,
        owner_password=body.owner_password,
        demo_mode=body.demo_mode,
        copy_menu_from=body.copy_menu_from,
    )
    db.commit()
    return _restaurant_dict(db, r)


@router.get("/restaurants/{rid}")
def get_restaurant(rid: int, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    r = _restaurant(db, rid)
    users = db.scalars(select(User).where(User.restaurant_id == r.id).order_by(User.id)).all()
    data = _restaurant_dict(db, r)
    data["users"] = [_user_dict(u) for u in users]
    return data


class RestaurantPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    slug: str | None = None
    status: str | None = None
    demo_mode: bool | None = None

    @field_validator("slug")
    @classmethod
    def _v_slug(cls, v: str | None) -> str | None:
        return v if v is None else _slug(v)


@router.patch("/restaurants/{rid}")
def patch_restaurant(rid: int, body: RestaurantPatch, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    r = _restaurant(db, rid)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in RESTAURANT_STATUSES:
        raise HTTPException(status_code=422, detail="invalid status")
    if "slug" in data and data["slug"] != r.slug and db.scalar(select(Restaurant).where(Restaurant.slug == data["slug"])):
        raise HTTPException(status_code=409, detail="الـ slug ده مستخدم")
    for field, attr in (("name", "name_ar"), ("slug", "slug"), ("status", "status"), ("demo_mode", "demo_mode")):
        if field in data:
            setattr(r, attr, data[field])
    db.commit()
    return _restaurant_dict(db, r)


@router.post("/restaurants/{rid}/enter")
def enter(rid: int, response: Response, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    r = _restaurant(db, rid)
    set_session_cookie(response, make_session_token(p.user.id, acting_restaurant_id=r.id))
    return principal_dict(db, Principal(user=p.user, acting_restaurant_id=r.id))


@router.post("/exit")
def exit_restaurant(response: Response, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    set_session_cookie(response, make_session_token(p.user.id))
    return principal_dict(db, Principal(user=p.user, acting_restaurant_id=None))


@router.post("/restaurants/{rid}/clear-demo")
def clear_demo(rid: int, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    _restaurant(db, rid)
    result = svc.clear_demo(db, rid)
    db.commit()
    return result


@router.get("/restaurants/{rid}/export")
def export(rid: int, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    r = _restaurant(db, rid)
    return Response(
        content=json.dumps(svc.export(db, rid), ensure_ascii=False, indent=1),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{r.slug}-export.json"'},
    )


class DeleteIn(BaseModel):
    confirm_slug: str


@router.post("/restaurants/{rid}/delete")
def delete_restaurant(rid: int, body: DeleteIn, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    r = _restaurant(db, rid)
    if r.status != "archived":
        raise HTTPException(status_code=409, detail="لازم المطعم يتأرشف الأول")
    if body.confirm_slug != r.slug:
        raise HTTPException(status_code=422, detail="اكتب الـ slug بالظبط للتأكيد")
    db.delete(r)  # cascades to everything owned by the restaurant
    db.commit()
    return {"ok": True}


class UserIn(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(pattern="^(owner|staff)$")
    display_name: str | None = Field(default=None, max_length=60)

    @field_validator("username")
    @classmethod
    def _v_user(cls, v: str) -> str:
        return _username(v)


@router.post("/restaurants/{rid}/users")
def create_user(rid: int, body: UserIn, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    r = _restaurant(db, rid)
    if db.scalar(select(User).where(func.lower(User.username) == body.username)):
        raise HTTPException(status_code=409, detail="اسم المستخدم ده مستخدم")
    u = User(
        restaurant_id=r.id,
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(u)
    db.commit()
    return _user_dict(u)


class UserPatch(BaseModel):
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=60)
    role: str | None = Field(default=None, pattern="^(owner|staff)$")


@router.patch("/users/{uid}")
def patch_user(uid: int, body: UserPatch, p: Principal = Depends(require_super), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if u is None or u.role == "super_admin":
        raise HTTPException(status_code=404, detail="not_found")
    data = body.model_dump(exclude_unset=True)
    if "password" in data:
        u.password_hash = hash_password(data["password"])
    for field in ("active", "display_name", "role"):
        if field in data:
            setattr(u, field, data[field])
    db.commit()
    return _user_dict(u)
