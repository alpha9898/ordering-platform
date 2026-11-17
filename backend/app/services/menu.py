"""Menu reads, always scoped to one restaurant."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Addon, Category, CategoryAddon, Item, ItemVariant


def money(v: Decimal | float | int | None) -> float:
    return float(v or 0)


def orderable_categories(db: Session, rid: int) -> list[Category]:
    """Active categories that have at least one orderable item."""
    cats = db.scalars(
        select(Category)
        .where(Category.restaurant_id == rid, Category.active.is_(True))
        .options(selectinload(Category.items).selectinload(Item.variants))
        .order_by(Category.sort, Category.id)
    ).all()
    return [c for c in cats if any(_orderable(i) for i in c.items)]


def _orderable(item: Item) -> bool:
    return item.available and any(v.available for v in item.variants)


def orderable_items(db: Session, rid: int, category_id: int) -> list[Item]:
    cat = db.scalar(
        select(Category)
        .where(Category.id == category_id, Category.restaurant_id == rid, Category.active.is_(True))
        .options(selectinload(Category.items).selectinload(Item.variants))
    )
    if cat is None:
        return []
    return [i for i in cat.items if _orderable(i)]


def get_item(db: Session, rid: int, item_id: int) -> Item | None:
    item = db.scalar(
        select(Item)
        .where(Item.id == item_id, Item.restaurant_id == rid)
        .options(selectinload(Item.variants), selectinload(Item.category))
    )
    if item is None or not _orderable(item) or not item.category.active:
        return None
    return item


def available_variants(item: Item) -> list[ItemVariant]:
    return [v for v in item.variants if v.available]


def addons_for_category(db: Session, rid: int, category_id: int) -> list[tuple[Addon, Decimal]]:
    rows = db.execute(
        select(Addon, CategoryAddon.price_override)
        .join(CategoryAddon, CategoryAddon.addon_id == Addon.id)
        .where(
            CategoryAddon.category_id == category_id,
            Addon.restaurant_id == rid,
            Addon.available.is_(True),
        )
        .order_by(Addon.sort, Addon.id)
    ).all()
    return [(a, override if override is not None else a.price) for a, override in rows]


def public_menu(db: Session, rid: int) -> list[dict]:
    """Full orderable menu for the web menu page."""
    out = []
    for cat in orderable_categories(db, rid):
        addons = [
            {"id": a.id, "name": a.name_ar, "price": money(p)} for a, p in addons_for_category(db, rid, cat.id)
        ]
        items = []
        for it in cat.items:
            if not _orderable(it):
                continue
            items.append(
                {
                    "id": it.id,
                    "name": it.name_ar,
                    "description": it.description_ar,
                    "image_url": it.image_url,
                    "variants": [
                        {"id": v.id, "name": v.name_ar, "price": money(v.price)} for v in available_variants(it)
                    ],
                }
            )
        out.append({"id": cat.id, "name": cat.name_ar, "addons": addons, "items": items})
    return out


def full_menu(db: Session, rid: int) -> dict:
    """Everything (incl. unavailable) for the dashboard editor."""
    cats = db.scalars(
        select(Category)
        .where(Category.restaurant_id == rid)
        .options(selectinload(Category.items).selectinload(Item.variants))
        .order_by(Category.sort, Category.id)
    ).all()
    addons = db.scalars(select(Addon).where(Addon.restaurant_id == rid).order_by(Addon.sort, Addon.id)).all()
    links = db.execute(
        select(CategoryAddon).join(Category, Category.id == CategoryAddon.category_id).where(Category.restaurant_id == rid)
    ).scalars().all()
    by_cat: dict[int, list[dict]] = {}
    for link in links:
        by_cat.setdefault(link.category_id, []).append(
            {"addon_id": link.addon_id, "price_override": None if link.price_override is None else money(link.price_override)}
        )
    return {
        "categories": [
            {
                "id": c.id,
                "name": c.name_ar,
                "sort": c.sort,
                "active": c.active,
                "addons": by_cat.get(c.id, []),
                "items": [
                    {
                        "id": i.id,
                        "category_id": i.category_id,
                        "name": i.name_ar,
                        "description": i.description_ar,
                        "image_url": i.image_url,
                        "available": i.available,
                        "sort": i.sort,
                        "variants": [
                            {"id": v.id, "name": v.name_ar, "price": money(v.price), "available": v.available, "sort": v.sort}
                            for v in i.variants
                        ],
                    }
                    for i in c.items
                ],
            }
            for c in cats
        ],
        "addons": [
            {"id": a.id, "name": a.name_ar, "price": money(a.price), "available": a.available, "sort": a.sort}
            for a in addons
        ],
    }
