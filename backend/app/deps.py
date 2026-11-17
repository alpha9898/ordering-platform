"""Auth + tenant scoping dependencies.

Every dashboard endpoint goes through `require_restaurant`, which returns
the ONE restaurant the caller may act on. Queries must filter by it.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import Restaurant, User
from .security import SESSION_COOKIE, read_session_token


@dataclass
class Principal:
    user: User
    acting_restaurant_id: int | None  # super admin "entered" a restaurant

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def is_super(self) -> bool:
        return self.user.role == "super_admin"

    @property
    def restaurant_id(self) -> int | None:
        return self.acting_restaurant_id if self.is_super else self.user.restaurant_id

    @property
    def can_manage(self) -> bool:
        """Owner-level rights inside the restaurant (menu edits, settings)."""
        return self.user.role in ("owner", "super_admin")


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    payload = read_session_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="not_authenticated")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="not_authenticated")
    if user.restaurant_id is not None:
        r = db.get(Restaurant, user.restaurant_id)
        if r is None or r.status == "archived":
            raise HTTPException(status_code=401, detail="restaurant_archived")
    return Principal(user=user, acting_restaurant_id=payload.get("act") if user.role == "super_admin" else None)


def require_super(p: Principal = Depends(current_principal)) -> Principal:
    if not p.is_super:
        raise HTTPException(status_code=403, detail="forbidden")
    return p


def require_restaurant(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> tuple[Principal, Restaurant]:
    rid = p.restaurant_id
    if rid is None:
        raise HTTPException(status_code=409, detail="no_restaurant_selected")
    r = db.get(Restaurant, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="restaurant_not_found")
    return p, r


def require_manager(ctx: tuple[Principal, Restaurant] = Depends(require_restaurant)) -> tuple[Principal, Restaurant]:
    if not ctx[0].can_manage:
        raise HTTPException(status_code=403, detail="owner_only")
    return ctx
