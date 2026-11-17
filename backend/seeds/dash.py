"""Seed the platform super admin and the "Dash" demo restaurant.

Usage (from backend/):  python -m seeds.dash
Idempotent: skips anything that already exists.

The menu below is a SAMPLE built from the examples in the original project brief
(categories, single/double prices, specials, add-ons). Replace it with
Dash's real menu via the dashboard editor or the Excel import.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Addon,
    Category,
    CategoryAddon,
    DeliveryZone,
    Item,
    ItemVariant,
    Restaurant,
    User,
)
from app.security import hash_password  # noqa: E402
from app.services import settings as settings_svc  # noqa: E402

SD = ("فردي", "دبل")

MENU = [
    ("فراخ مقلية", "burger", [
        ("زنجر", (95, 145)), ("كرسبي", (95, 145)), ("سبايسي زنجر", (99, 149)), ("تشيكن رانش", (105, 155)),
        ("تشيكن باربكيو", (105, 155)), ("تشيكن ماشروم", (110, 160)), ("تشيكن هالبينو", (105, 155)), ("تشيكن تشيز", (110, 160)),
    ]),
    ("بيف برجر", "burger", [
        ("كلاسيك برجر", (99, 149)), ("تشيز برجر", (105, 155)), ("ماشروم برجر", (115, 165)), ("باربكيو برجر", (110, 160)),
        ("سموكي برجر", (115, 165)), ("هالبينو برجر", (110, 160)), ("بيف بيكون برجر", (125, 175)), ("ترافل برجر", (129, 179)),
    ]),
    ("Specials", "special", [
        ("BIGY", 159), ("الكوتي", 169), ("Big Dash burger", 189), ("Big Dash crepe", 175),
    ]),
    ("كريب", "crepe", [
        ("كريب زنجر", 85), ("كريب كرسبي", 85), ("كريب فراخ باربكيو", 90), ("كريب شاورما فراخ", 90),
        ("كريب بانيه", 80), ("كريب سجق", 75), ("كريب لحمة مفرومة", 85), ("كريب هوت دوج", 75),
        ("كريب تونة", 80), ("كريب جبن مشكل", 70), ("كريب فاهيتا فراخ", 95), ("كريب كوردون بلو", 99),
    ]),
    ("Mix Frize Crepe", "crepe", [
        ("ميكس فرايز زنجر", 99), ("ميكس فرايز كرسبي", 99), ("ميكس فرايز سجق", 75),
        ("ميكس فرايز بانيه", 89), ("ميكس فرايز شاورما", 105), ("ميكس فرايز سوبريم", 109),
    ]),
    ("بيتزا", "pizza", [
        ("مارجريتا", 110), ("خضار", 115), ("سوبر سوبريم", 150), ("بيبروني", 145), ("فراخ باربكيو", 150),
        ("فراخ رانش", 150), ("سجق", 130), ("لحمة مفرومة", 140), ("تونة", 135), ("سي فود", 175),
        ("فور تشيز", 155), ("هوت دوج", 125), ("بيتزا Big Dash", 249),
    ]),
    ("Appetizers", None, [
        ("بطاطس", 39), ("بطاطس بالجبنة", 55), ("أصابع موتزاريلا", 69), ("أونيون رينجز", 49),
    ]),
    ("مشروبات", None, [("ماكسي كولا", 20)]),
]

ADDONS = [
    ("جبنة شيدر", 15), ("موتزاريلا", 20), ("بيكون", 30), ("ماشروم", 15), ("هالبينو", 10), ("صوص رانش", 10),
    ("صوص باربكيو", 10), ("صوص ترافل", 20), ("بصل مكرمل", 10), ("قطعة فراخ زيادة", 40), ("قطعة لحمة زيادة", 40),
    ("بيض", 10),
]
CRUST = ("كونو موتزاريلا", 25)  # crepe-only add-on

ZONES = [("قريب (أقل من 2 كم)", 15, 0), ("متوسط (2 - 5 كم)", 25, 0), ("بعيد (5 - 8 كم)", 35, 150)]


# Production: SEED_SKIP_USERS=1 seeds only the restaurant + menu. The first
# super admin is then created on the deployed site at /login (first-run
# setup), and restaurant users from the admin panel.
SKIP_USERS = os.environ.get("SEED_SKIP_USERS") == "1"


def seed_super_admin(db) -> None:
    if SKIP_USERS:
        return
    if get_settings().is_production:
        raise SystemExit("Dev accounts are not created in production; use SEED_SKIP_USERS=1")
    username, password = "admin", "admin-dev-1234"  # local development only
    if db.scalar(select(User).where(User.username == username)) is None:
        db.add(User(username=username, display_name="Platform admin", password_hash=hash_password(password), role="super_admin"))
        print(f"created super admin '{username}'")


def seed_dash(db) -> None:
    if db.scalar(select(Restaurant).where(Restaurant.slug == "dash")):
        print("restaurant 'dash' already exists, skipping")
        return
    r = Restaurant(slug="dash", name_ar="Dash", status="trial", demo_mode=True)
    db.add(r)
    db.flush()
    settings_svc.seed_defaults(db, r.id, {"eta_minutes": 35, "delivery_fee": 20})
    if not SKIP_USERS:
        # local development only; in production create users from /admin
        db.add(User(restaurant_id=r.id, username="dash", display_name="صاحب Dash", password_hash=hash_password("dash-owner-1234"), role="owner"))
        db.add(User(restaurant_id=r.id, username="dash.staff", display_name="كاشير Dash", password_hash=hash_password("dash-staff-1234"), role="staff"))

    addons = []
    for i, (name, price) in enumerate(ADDONS):
        a = Addon(restaurant_id=r.id, name_ar=name, price=Decimal(price), sort=i)
        db.add(a)
        addons.append(a)
    crust = Addon(restaurant_id=r.id, name_ar=CRUST[0], price=Decimal(CRUST[1]), sort=len(ADDONS))
    db.add(crust)
    db.flush()

    for ci, (cat_name, kind, items) in enumerate(MENU):
        cat = Category(restaurant_id=r.id, name_ar=cat_name, sort=ci)
        db.add(cat)
        db.flush()
        for ii, (name, price) in enumerate(items):
            item = Item(restaurant_id=r.id, category_id=cat.id, name_ar=name, sort=ii)
            if isinstance(price, tuple):
                item.variants = [ItemVariant(name_ar=SD[k], price=Decimal(p), sort=k) for k, p in enumerate(price)]
            else:
                item.variants = [ItemVariant(name_ar=None, price=Decimal(price), sort=0)]
            db.add(item)
        if kind in ("burger", "special", "crepe", "pizza"):
            for a in addons:
                db.add(CategoryAddon(category_id=cat.id, addon_id=a.id))
        if kind == "crepe":
            db.add(CategoryAddon(category_id=cat.id, addon_id=crust.id))

    for zi, (name, fee, min_order) in enumerate(ZONES):
        db.add(DeliveryZone(restaurant_id=r.id, name_ar=name, fee=Decimal(fee), min_order=Decimal(min_order), sort=zi))
    print("created restaurant 'dash' with sample menu")


def main() -> None:
    db = SessionLocal()
    try:
        seed_super_admin(db)
        seed_dash(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
