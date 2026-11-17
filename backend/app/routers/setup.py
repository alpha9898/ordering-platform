"""First-run setup: create the platform's first super admin.

Only works while no super admin exists, so the owner of a fresh
deployment picks their own credentials and nobody else ever handles them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal
from ..models import User
from ..security import hash_password, make_session_token
from ..services import ratelimit
from .admin import _username
from .auth import principal_dict, set_session_cookie

router = APIRouter(prefix="/setup", tags=["setup"])


def _needs_setup(db: Session) -> bool:
    return not db.scalar(select(func.count()).select_from(User).where(User.role == "super_admin"))


@router.get("")
def status(db: Session = Depends(get_db)):
    return {"needs_setup": _needs_setup(db)}


class SetupIn(BaseModel):
    username: str
    password: str = Field(min_length=10, max_length=200)
    display_name: str | None = Field(default=None, max_length=60)

    @field_validator("username")
    @classmethod
    def _v_user(cls, v: str) -> str:
        return _username(v)


@router.post("")
def create_first_admin(body: SetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ratelimit.hit(db, f"setup:{ratelimit.client_ip(request)}", 10, 3600)
    db.execute(text("SELECT pg_advisory_xact_lock(7311)"))  # serialize concurrent attempts
    if not _needs_setup(db):
        raise HTTPException(status_code=409, detail="الإعداد اتعمل قبل كده، سجّل دخول")
    if db.scalar(select(User).where(func.lower(User.username) == body.username)):
        raise HTTPException(status_code=409, detail="اسم المستخدم ده مستخدم")
    user = User(
        username=body.username,
        display_name=body.display_name or "Platform admin",
        password_hash=hash_password(body.password),
        role="super_admin",
    )
    db.add(user)
    db.commit()
    set_session_cookie(response, make_session_token(user.id))
    return principal_dict(db, Principal(user=user, acting_restaurant_id=None))
