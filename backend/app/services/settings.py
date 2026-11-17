"""Per-restaurant settings stored in the `settings` table (key -> JSONB).

Nothing here is hardcoded per restaurant: DEFAULTS only fill keys a
restaurant has not set yet.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import Setting

ALL_DAY = [["00:00", "24:00"]]
WEEKDAYS = ["sat", "sun", "mon", "tue", "wed", "thu", "fri"]

DEFAULTS: dict[str, Any] = {
    "accepting_orders": True,
    # weekday -> list of [open, close]; close <= open means "past midnight"
    "working_hours": {d: ALL_DAY for d in WEEKDAYS},
    "eta_minutes": 35,
    "delivery_enabled": True,
    "pickup_enabled": True,
    "delivery_fee": 20,  # used when the restaurant has no active zones
    "min_order": 0,
    "payment_methods": ["cod"],
    "wallet_number": "",
    "business_day_starts": "05:00",
    "contact_phone": "",
}

# What each role may change from the dashboard
STAFF_KEYS = {"accepting_orders", "eta_minutes"}
OWNER_KEYS = set(DEFAULTS)


class SettingsError(ValueError):
    pass


def get_all(db: Session, restaurant_id: int) -> dict[str, Any]:
    out = copy.deepcopy(DEFAULTS)
    rows = db.scalars(select(Setting).where(Setting.restaurant_id == restaurant_id)).all()
    for row in rows:
        out[row.key] = row.value
    return out


def _hhmm(v: Any) -> str:
    if not isinstance(v, str) or len(v) != 5 or v[2] != ":":
        raise SettingsError(f"invalid time {v!r}")
    h, m = int(v[:2]), int(v[3:])
    if not (0 <= h <= 24 and 0 <= m < 60) or (h == 24 and m != 0):
        raise SettingsError(f"invalid time {v!r}")
    return v


def validate(key: str, value: Any) -> Any:
    if key not in DEFAULTS:
        raise SettingsError(f"unknown setting {key}")
    if key in {"accepting_orders", "delivery_enabled", "pickup_enabled"}:
        if not isinstance(value, bool):
            raise SettingsError(f"{key} must be true/false")
    elif key == "eta_minutes":
        if not isinstance(value, int) or not 1 <= value <= 300:
            raise SettingsError("eta_minutes must be 1..300")
    elif key in {"delivery_fee", "min_order"}:
        try:
            d = Decimal(str(value))
        except Exception as e:  # noqa: BLE001
            raise SettingsError(f"{key} must be a number") from e
        if d < 0 or d > 100000:
            raise SettingsError(f"{key} out of range")
        value = float(d)
    elif key == "payment_methods":
        if not isinstance(value, list) or not value or any(v not in ("cod", "wallet") for v in value):
            raise SettingsError("payment_methods must be a non-empty subset of cod, wallet")
        value = [v for v in ("cod", "wallet") if v in value]
    elif key == "working_hours":
        if not isinstance(value, dict):
            raise SettingsError("working_hours must be an object")
        clean = {}
        for d in WEEKDAYS:
            ranges = value.get(d, [])
            if not isinstance(ranges, list):
                raise SettingsError("working_hours ranges must be lists")
            clean[d] = [[_hhmm(r[0]), _hhmm(r[1])] for r in ranges]
        value = clean
    elif key == "business_day_starts":
        value = _hhmm(value)
    elif key in {"wallet_number", "contact_phone"}:
        if not isinstance(value, str) or len(value) > 40:
            raise SettingsError(f"{key} must be a short string")
    return value


def update(db: Session, restaurant_id: int, changes: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    for key, value in changes.items():
        if key not in allowed:
            raise SettingsError(f"not allowed to change {key}")
        clean = validate(key, value)
        stmt = insert(Setting).values(restaurant_id=restaurant_id, key=key, value=clean)
        stmt = stmt.on_conflict_do_update(index_elements=["restaurant_id", "key"], set_={"value": clean})
        db.execute(stmt)
    db.flush()
    return get_all(db, restaurant_id)


def seed_defaults(db: Session, restaurant_id: int, overrides: dict[str, Any] | None = None) -> None:
    values = copy.deepcopy(DEFAULTS)
    values.update(overrides or {})
    update(db, restaurant_id, values, OWNER_KEYS)
