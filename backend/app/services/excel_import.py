"""Menu <-> Excel.

Workbook format (same for export, template and import):
  Sheet "الأصناف": القسم | الصنف | الحجم | السعر | الوصف | متاح
      one row per price; an item with فردي/دبل has two rows.
  Sheet "الإضافات": الإضافة | السعر | الأقسام | متاح
      الأقسام = category names separated by "،" or "," — or "الكل".

Import replaces the restaurant's whole menu (past orders keep their
snapshots). Preview first: nothing is written while there are errors.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..models import Addon, Category, CategoryAddon, Item, ItemVariant
from .menu import full_menu

ITEMS_SHEET = "الأصناف"
ADDONS_SHEET = "الإضافات"
ITEM_HEADERS = ["القسم", "الصنف", "الحجم", "السعر", "الوصف", "متاح"]
ADDON_HEADERS = ["الإضافة", "السعر", "الأقسام", "متاح"]
ALL_WORD = "الكل"
MAX_ROWS = 3000

_ALIASES = {
    "القسم": "category", "category": "category",
    "الصنف": "item", "item": "item",
    "الحجم": "variant", "variant": "variant", "size": "variant",
    "السعر": "price", "price": "price",
    "الوصف": "description", "description": "description",
    "متاح": "available", "available": "available",
    "الإضافة": "addon", "الاضافة": "addon", "addon": "addon",
    "الأقسام": "categories", "الاقسام": "categories", "categories": "categories",
}
_YES = {"", "نعم", "اه", "أه", "ايوه", "yes", "y", "true", "1", "متاح"}
_NO = {"لا", "no", "n", "false", "0", "غير متاح", "خلص"}


@dataclass
class ParsedVariant:
    name: str | None
    price: Decimal
    available: bool


@dataclass
class ParsedItem:
    category: str
    name: str
    description: str | None
    variants: list[ParsedVariant] = field(default_factory=list)


@dataclass
class ParsedAddon:
    name: str
    price: Decimal
    categories: list[str]
    available: bool


@dataclass
class ParseResult:
    categories: list[str] = field(default_factory=list)
    items: list[ParsedItem] = field(default_factory=list)
    addons: list[ParsedAddon] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "categories": len(self.categories),
            "items": len(self.items),
            "variants": sum(len(i.variants) for i in self.items),
            "addons": len(self.addons),
            "errors": self.errors[:100],
            "error_count": len(self.errors),
            "preview": [
                {
                    "category": c,
                    "items": [
                        {
                            "name": i.name,
                            "variants": [{"name": v.name, "price": float(v.price), "available": v.available} for v in i.variants],
                        }
                        for i in self.items
                        if i.category == c
                    ][:50],
                }
                for c in self.categories
            ],
        }


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).split())


def _price(raw: str) -> Decimal | None:
    raw = raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")).replace("ج", "").replace("EGP", "").strip()
    try:
        d = Decimal(raw)
    except InvalidOperation:
        return None
    return d if 0 <= d <= 100000 else None


def _bool(raw: str) -> bool | None:
    v = raw.strip().lower()
    if v in _YES:
        return True
    if v in _NO:
        return False
    return None


def _columns(header_row) -> dict[str, int]:
    cols = {}
    for idx, v in enumerate(header_row):
        key = _ALIASES.get(_cell(v).strip().lower()) or _ALIASES.get(_cell(v).strip())
        if key and key not in cols:
            cols[key] = idx
    return cols


def parse(data: bytes) -> ParseResult:
    res = ParseResult()
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        res.errors.append({"sheet": "-", "row": 0, "message": "الملف مش Excel صالح (.xlsx)"})
        return res

    ws = wb[ITEMS_SHEET] if ITEMS_SHEET in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True, max_row=MAX_ROWS + 1))
    if not rows:
        res.errors.append({"sheet": ws.title, "row": 1, "message": "الشيت فاضي"})
        return res
    cols = _columns(rows[0])
    missing = [h for h, k in (("القسم", "category"), ("الصنف", "item"), ("السعر", "price")) if k not in cols]
    if missing:
        res.errors.append({"sheet": ws.title, "row": 1, "message": "أعمدة ناقصة: " + "، ".join(missing)})
        return res

    def get(row, key):
        i = cols.get(key)
        return _cell(row[i]) if i is not None and i < len(row) else ""

    items: dict[tuple[str, str], ParsedItem] = {}
    for n, row in enumerate(rows[1:], start=2):
        if not any(_cell(v) for v in row):
            continue
        cat, name, var, price_raw = get(row, "category"), get(row, "item"), get(row, "variant"), get(row, "price")
        err = lambda m: res.errors.append({"sheet": ws.title, "row": n, "message": m})  # noqa: E731
        if not cat:
            err("القسم فاضي")
            continue
        if not name:
            err("اسم الصنف فاضي")
            continue
        price = _price(price_raw)
        if price is None:
            err(f"السعر مش رقم صحيح: «{price_raw}»")
            continue
        avail = _bool(get(row, "available"))
        if avail is None:
            err("عمود متاح لازم يكون نعم أو لا")
            continue
        if len(name) > 80 or len(cat) > 60 or len(var) > 40:
            err("الاسم طويل زيادة")
            continue
        if cat not in res.categories:
            res.categories.append(cat)
        key = (cat, name)
        if key not in items:
            items[key] = ParsedItem(category=cat, name=name, description=get(row, "description") or None)
            res.items.append(items[key])
        item = items[key]
        vname = var or None
        if any(v.name == vname for v in item.variants):
            err(f"الحجم «{var or 'بدون حجم'}» متكرر للصنف {name}")
            continue
        if item.variants and (vname is None) != (item.variants[0].name is None):
            err(f"الصنف {name}: يا كل الأسطر ليها حجم يا مفيش حجم خالص")
            continue
        if len(item.variants) >= 10:
            err(f"الصنف {name}: أقصى حاجة 10 أحجام")
            continue
        item.variants.append(ParsedVariant(name=vname, price=price, available=avail))

    if not res.items and not res.errors:
        res.errors.append({"sheet": ws.title, "row": 2, "message": "مفيش أصناف في الشيت"})

    if ADDONS_SHEET in wb.sheetnames:
        ws = wb[ADDONS_SHEET]
        rows = list(ws.iter_rows(values_only=True, max_row=MAX_ROWS + 1))
        if rows:
            cols = _columns(rows[0])
            if "addon" not in cols or "price" not in cols:
                res.errors.append({"sheet": ws.title, "row": 1, "message": "أعمدة ناقصة: الإضافة، السعر"})
            else:
                seen = set()
                for n, row in enumerate(rows[1:], start=2):
                    if not any(_cell(v) for v in row):
                        continue
                    err = lambda m: res.errors.append({"sheet": ws.title, "row": n, "message": m})  # noqa: E731
                    name, price = get(row, "addon"), _price(get(row, "price"))
                    if not name:
                        err("اسم الإضافة فاضي")
                        continue
                    if price is None:
                        err("السعر مش رقم صحيح")
                        continue
                    if name in seen:
                        err(f"الإضافة «{name}» متكررة")
                        continue
                    avail = _bool(get(row, "available"))
                    if avail is None:
                        err("عمود متاح لازم يكون نعم أو لا")
                        continue
                    raw_cats = get(row, "categories")
                    if raw_cats.strip() == ALL_WORD:
                        cats = list(res.categories)
                    else:
                        cats = [c.strip() for c in re.split(r"[،,]", raw_cats) if c.strip()]
                        unknown = [c for c in cats if c not in res.categories]
                        if unknown:
                            err("أقسام مش موجودة في شيت الأصناف: " + "، ".join(unknown))
                            continue
                    seen.add(name)
                    res.addons.append(ParsedAddon(name=name, price=price, categories=cats, available=avail))
    return res


def apply(db: Session, rid: int, parsed: ParseResult) -> None:
    if parsed.errors:
        raise ValueError("cannot apply a workbook with errors")
    db.execute(delete(Category).where(Category.restaurant_id == rid))  # cascades items, variants, links
    db.execute(delete(Addon).where(Addon.restaurant_id == rid))
    cat_ids: dict[str, int] = {}
    for i, name in enumerate(parsed.categories):
        c = Category(restaurant_id=rid, name_ar=name, sort=i)
        db.add(c)
        db.flush()
        cat_ids[name] = c.id
    for i, it in enumerate(parsed.items):
        item = Item(restaurant_id=rid, category_id=cat_ids[it.category], name_ar=it.name, description_ar=it.description, sort=i)
        item.variants = [ItemVariant(name_ar=v.name, price=v.price, available=v.available, sort=k) for k, v in enumerate(it.variants)]
        db.add(item)
    for i, ad in enumerate(parsed.addons):
        a = Addon(restaurant_id=rid, name_ar=ad.name, price=ad.price, available=ad.available, sort=i)
        db.add(a)
        db.flush()
        for c in ad.categories:
            db.add(CategoryAddon(category_id=cat_ids[c], addon_id=a.id))
    db.flush()


def export_workbook(db: Session, rid: int) -> bytes:
    """Current menu in the import format (also used as the template)."""
    data = full_menu(db, rid)
    wb = Workbook()
    ws = wb.active
    ws.title = ITEMS_SHEET
    ws.sheet_view.rightToLeft = True
    ws.append(ITEM_HEADERS)
    cat_names = {c["id"]: c["name"] for c in data["categories"]}
    for c in data["categories"]:
        for it in c["items"]:
            for v in it["variants"]:
                ws.append([c["name"], it["name"], v["name"] or "", v["price"], it["description"] or "", "نعم" if (v["available"] and it["available"]) else "لا"])
    if ws.max_row == 1:  # empty menu -> example rows
        ws.append(["برجر", "تشيز برجر", "فردي", 99, "", "نعم"])
        ws.append(["برجر", "تشيز برجر", "دبل", 149, "", "نعم"])
        ws.append(["مشروبات", "كولا", "", 20, "", "نعم"])

    wa = wb.create_sheet(ADDONS_SHEET)
    wa.sheet_view.rightToLeft = True
    wa.append(ADDON_HEADERS)
    links: dict[int, list[str]] = {}
    for c in data["categories"]:
        for link in c["addons"]:
            links.setdefault(link["addon_id"], []).append(cat_names[c["id"]])
    for a in data["addons"]:
        wa.append([a["name"], a["price"], "، ".join(links.get(a["id"], [])), "نعم" if a["available"] else "لا"])
    if wa.max_row == 1:
        wa.append(["جبنة شيدر", 15, "برجر", "نعم"])

    for sheet, widths in ((ws, [18, 26, 10, 10, 30, 8]), (wa, [22, 10, 40, 8])):
        for i, w in enumerate(widths):
            sheet.column_dimensions[chr(65 + i)].width = w
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="128C7E")
        sheet.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
