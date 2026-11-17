from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import Principal, current_principal
from ..models import Restaurant, User
from ..security import SESSION_COOKIE, make_session_token, verify_password
from ..services import ratelimit

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


def set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=s.session_days * 86400,
        httponly=True,
        secure=s.is_production,
        samesite="lax",
        path="/",
    )


def principal_dict(db: Session, p: Principal) -> dict:
    r = db.get(Restaurant, p.restaurant_id) if p.restaurant_id else None
    return {
        "user": {
            "id": p.user.id,
            "username": p.user.username,
            "display_name": p.user.display_name,
            "role": p.user.role,
        },
        "restaurant": {"id": r.id, "slug": r.slug, "name": r.name_ar, "status": r.status, "demo_mode": r.demo_mode}
        if r
        else None,
        "can_manage": p.can_manage,
        "is_super": p.is_super,
    }


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    bucket = f"login_fail:{ratelimit.client_ip(request)}"
    if ratelimit.count(db, bucket, s.login_window_seconds) >= s.login_failures_per_window:
        raise HTTPException(status_code=429, detail="محاولات دخول كتير، استنى 5 دقايق")
    user = db.scalar(select(User).where(func.lower(User.username) == body.username.strip().lower()))
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        ratelimit.record(db, bucket)
        db.commit()
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة السر غلط")
    if user.restaurant_id is not None:
        r = db.get(Restaurant, user.restaurant_id)
        if r is None or r.status == "archived":
            raise HTTPException(status_code=403, detail="الحساب ده موقوف")
    set_session_cookie(response, make_session_token(user.id))
    return principal_dict(db, Principal(user=user, acting_restaurant_id=None))


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return principal_dict(db, p)
