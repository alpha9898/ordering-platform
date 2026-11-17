"""Server-side pricing. Prices NEVER come from the client or the chat;
a cart only holds ids + quantities and is priced from the DB each time."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Addon, Category, CategoryAddon, Item, ItemVariant


@dataclass
class PricedAddon:
    id: int
    name: str
    price: Decimal


@dataclass
class PricedLine:
    variant_id: int
    item_id: int
    item_name: str
    variant_name: str | None
    unit_price: Decimal  # variant price, without add-ons
    addons: list[PricedAddon]
    qty: int
    note: str | None = None

    @property
    def each(self) -> Decimal:
        return self.unit_price + sum((a.price for a in self.addons), Decimal("0"))

    @property
    def line_total(self) -> Decimal:
        return self.each * self.qty

    @property
    def title(self) -> str:
        return f"{self.item_name} ({self.variant_name})" if self.variant_name else self.item_name


@dataclass
class PricedCart:
    lines: list[PricedLine] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)  # human-readable names of dropped items/add-ons

    @property
    def subtotal(self) -> Decimal:
        return sum((ln.line_total for ln in self.lines), Decimal("0"))


def line_key(variant_id: int, addon_ids: list[int]) -> tuple:
    return (int(variant_id), tuple(sorted(int(a) for a in addon_ids)))


def price_lines(db: Session, rid: int, lines: list[dict], max_qty: int = 50) -> PricedCart:
    """lines: [{variant_id, addon_ids, qty, note?}] -> priced cart.

    Unavailable items are dropped (reported in `removed`), unavailable or
    not-allowed add-ons are dropped from their line. Same variant + same
    add-ons are merged into one line.
    """
    cart = PricedCart()
    if not lines:
        return cart

    variant_ids = {int(ln["variant_id"]) for ln in lines}
    rows = db.execute(
        select(ItemVariant, Item, Category)
        .join(Item, Item.id == ItemVariant.item_id)
        .join(Category, Category.id == Item.category_id)
        .where(ItemVariant.id.in_(variant_ids), Item.restaurant_id == rid)
    ).all()
    variants = {v.id: (v, i, c) for v, i, c in rows}

    cat_ids = {c.id for _, _, c in rows}
    allowed: dict[tuple[int, int], tuple[Addon, Decimal]] = {}
    if cat_ids:
        for addon, link in db.execute(
            select(Addon, CategoryAddon)
            .join(CategoryAddon, CategoryAddon.addon_id == Addon.id)
            .where(CategoryAddon.category_id.in_(cat_ids), Addon.restaurant_id == rid)
        ).all():
            price = link.price_override if link.price_override is not None else addon.price
            allowed[(link.category_id, addon.id)] = (addon, price)

    merged: dict[tuple, PricedLine] = {}
    for ln in lines:
        qty = int(ln.get("qty", 1))
        if qty < 1 or qty > max_qty:
            raise ValueError("invalid quantity")
        found = variants.get(int(ln["variant_id"]))
        if found is None:
            cart.removed.append("صنف غير موجود")
            continue
        v, item, cat = found
        if not (v.available and item.available and cat.active):
            label = f"{item.name_ar} ({v.name_ar})" if v.name_ar else item.name_ar
            cart.removed.append(label)
            continue
        addons: list[PricedAddon] = []
        for aid in sorted({int(a) for a in ln.get("addon_ids", [])}):
            entry = allowed.get((cat.id, aid))
            if entry is None or not entry[0].available:
                if entry is not None:
                    cart.removed.append(f"إضافة {entry[0].name_ar}")
                continue
            addons.append(PricedAddon(id=aid, name=entry[0].name_ar, price=entry[1]))
        key = line_key(v.id, [a.id for a in addons])
        note = (ln.get("note") or "").strip()[:200] or None
        if key in merged and not note and not merged[key].note:
            merged[key].qty = min(max_qty, merged[key].qty + qty)
            continue
        if key in merged:
            key = key + (len(merged),)
        merged[key] = PricedLine(
            variant_id=v.id,
            item_id=item.id,
            item_name=item.name_ar,
            variant_name=v.name_ar,
            unit_price=v.price,
            addons=addons,
            qty=qty,
            note=note,
        )
    cart.lines = list(merged.values())
    return cart
