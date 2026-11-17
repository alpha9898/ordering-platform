"""Deterministic ordering state machine (project brief, section 6).

Input: one normalized inbound message. Output: outgoing messages. The
conversation row is locked by the caller, so one message per customer is
processed at a time. Prices and availability are always read from the DB.

Reply ids are self-describing (e.g. "item:12", "zone:3") so a customer
tapping a button on an older message still does something sensible.
"""

from __future__ import annotations

import copy
import datetime as dt
import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Conversation, Customer, DeliveryZone, Item, Order, Restaurant
from ..services import hours, menu
from ..services.orders import ACTIVE_STATUSES, OrderError, active_zones, create_order, restaurant_available
from ..services.pricing import PricedCart, PricedLine, line_key, price_lines
from . import texts_ar as T
from .messages import (
    MAX_BODY,
    MAX_LIST_ROWS,
    MAX_ROW_DESCRIPTION,
    MAX_ROW_TITLE,
    Button,
    Buttons,
    Inbound,
    List,
    Outgoing,
    Row,
    Section,
    Text,
    fit,
)

HUMAN_SILENCE = dt.timedelta(minutes=30)
SEARCH_STOPWORDS = {"عايز", "عاوز", "عايزه", "ممكن", "اطلب", "واحد", "واحده", "لو", "سمحت", "من", "في", "انا", "عندكم", "فيه"}
MAX_FAILS = 2
MAX_ADDONS_PER_LINE = 10


@dataclass
class Ctx:
    db: Session
    restaurant: Restaurant
    settings: dict
    conv: Conversation
    customer: Customer | None
    now: dt.datetime

    @property
    def rid(self) -> int:
        return self.restaurant.id


class Engine:
    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.d: dict = copy.deepcopy(ctx.conv.data or {})
        self.d.setdefault("cart", [])

    # ------------------------------------------------------------------ entry
    def handle(self, inb: Inbound) -> list[Outgoing]:
        out = self._dispatch(inb)
        self.ctx.conv.data = self.d  # reassign so the JSONB change is saved
        return out

    @property
    def state(self) -> str:
        return self.ctx.conv.state

    @state.setter
    def state(self, value: str) -> None:
        self.ctx.conv.state = value

    def _dispatch(self, inb: Inbound) -> list[Outgoing]:
        ctx = self.ctx
        if not restaurant_available(ctx.restaurant):
            self.state = "IDLE"
            return [Text(T.UNAVAILABLE)]

        rid_ = inb.id or ""
        text = T.normalize(inb.text) if inb.kind == "text" else ""

        # ---- global commands (work from any state)
        if rid_ == "cancel" or text in T.CANCEL_WORDS:
            return self.cancel()
        if rid_ == "human" or text in T.HUMAN_WORDS:
            return self.request_human()
        if rid_ == "menu" or text in T.MENU_WORDS:
            return self.main_menu()
        if rid_ == "cart:show" or text in T.CART_WORDS:
            return self.show_cart()
        if rid_ == "status" or text in T.STATUS_WORDS:
            return self.order_status()
        if rid_.startswith("cats:page:"):
            return self.main_menu(page=_int(rid_.rsplit(":", 1)[1]))
        if rid_.startswith("cat:"):
            return self.item_list(_int(rid_.split(":")[1]), page=_int(rid_.split(":")[3]) if rid_.count(":") == 3 else 0)
        if rid_.startswith("item:"):
            return self.select_item(_int(rid_.split(":", 1)[1]))
        if rid_ == "cart:add":
            return self.main_menu()

        # ---- state-specific input
        handler = getattr(self, f"on_{self.state.lower()}", None)
        if handler is not None:
            result = handler(rid_, text, inb)
            if result is not None:
                self.d["fails"] = 0
                return result
        elif self.state in ("IDLE", "HUMAN"):
            # new conversation, or the bot resumes after a human handoff
            return self.main_menu(greet=True)
        return self.invalid()

    # --------------------------------------------------------------- helpers
    def _open_error(self) -> list[Outgoing] | None:
        s, r = self.ctx.settings, self.ctx.restaurant
        if not s["accepting_orders"]:
            self.state = "IDLE"
            return [Text(T.NOT_ACCEPTING)]
        if not hours.is_open(s["working_hours"], r.timezone, self.ctx.now):
            self.state = "IDLE"
            return [Text(T.closed(r.name_ar, hours.describe_next_opening(s["working_hours"], r.timezone, self.ctx.now)))]
        return None

    def _priced_cart(self) -> PricedCart:
        cart = price_lines(self.ctx.db, self.ctx.rid, self.d["cart"])
        # keep the stored cart in sync with what is still orderable
        self.d["cart"] = [
            {"variant_id": ln.variant_id, "addon_ids": [a.id for a in ln.addons], "qty": ln.qty} for ln in cart.lines
        ]
        return cart

    def _cart_count(self) -> int:
        return sum(int(ln["qty"]) for ln in self.d["cart"])

    def _active_order(self) -> Order | None:
        if self.ctx.customer is None:
            return None
        return self.ctx.db.scalar(
            select(Order)
            .where(
                Order.restaurant_id == self.ctx.rid,
                Order.customer_id == self.ctx.customer.id,
                Order.status.in_(ACTIVE_STATUSES),
            )
            .order_by(Order.id.desc())
            .limit(1)
        )

    def _list(self, body: str, button: str, title: str, entries: list[Row], page: int, more_id: str, fixed: list[Row]) -> List:
        rows, fixed = _paginate(entries, page, fixed, more_id)
        sections = []
        if rows:
            sections.append(Section(title=fit(title, 24), rows=rows))
        if fixed:
            sections.append(Section(title="خيارات", rows=fixed))
        return List(body=fit(body, MAX_BODY), button=button, sections=sections)

    def _reset_checkout(self) -> None:
        for k in ("fulfillment", "zone_id", "address", "payment", "pending", "edit_key"):
            self.d.pop(k, None)

    # ------------------------------------------------------------ global flows
    def cancel(self) -> list[Outgoing]:
        self.d = {"cart": []}
        self.state = "IDLE"
        return [Text(T.CANCELLED)]

    def request_human(self) -> list[Outgoing]:
        conv = self.ctx.conv
        conv.human_requested_at = self.ctx.now
        conv.human_until = self.ctx.now + HUMAN_SILENCE
        self.state = "HUMAN"
        return [Text(T.human_requested(self.ctx.restaurant.name_ar))]

    def order_status(self) -> list[Outgoing]:
        order = self._active_order()
        if order is None:
            return [Text(T.NO_ACTIVE_ORDER)]
        return [Text(T.status_line(order.order_no, order.status))]

    def invalid(self) -> list[Outgoing]:
        self.d["fails"] = int(self.d.get("fails", 0)) + 1
        if self.d["fails"] >= MAX_FAILS:
            self.d["fails"] = 0
            return [
                Buttons(
                    body=T.STUCK,
                    buttons=[Button("human", "🙋 كلم موظف"), Button("menu", "📋 المنيو")],
                )
            ]
        return self.reprompt(prefix=T.INVALID)

    def reprompt(self, prefix: str | None = None) -> list[Outgoing]:
        st = self.state
        if st == "ITEM_LIST" and self.d.get("category_id"):
            return self.item_list(self.d["category_id"], self.d.get("page", 0), prefix=prefix)
        if st == "VARIANT":
            return self.ask_variant(prefix=prefix)
        if st == "ADDONS":
            return self.show_addons(self.d.get("page", 0), prefix=prefix)
        if st == "QTY":
            return self.ask_qty(prefix=prefix)
        if st in ("CART", "CART_LINE"):
            return self.show_cart(prefix=prefix)
        if st == "CART_EDIT":
            return self.edit_cart(self.d.get("page", 0))
        if st == "FULFILLMENT":
            return self.ask_fulfillment(prefix=prefix)
        if st == "ZONE":
            return self.ask_zone(self.d.get("page", 0), prefix=prefix)
        if st == "ADDRESS":
            return self.ask_address(prefix=prefix)
        if st == "PAYMENT":
            return self.ask_payment(prefix=prefix)
        if st == "CONFIRM":
            return self.summary(prefix=prefix)
        return self.main_menu(page=self.d.get("page", 0), prefix=prefix)

    # ---------------------------------------------------------------- browse
    def main_menu(self, page: int = 0, greet: bool = False, prefix: str | None = None) -> list[Outgoing]:
        err = self._open_error()
        if err:
            return err
        cats = menu.orderable_categories(self.ctx.db, self.ctx.rid)
        if not cats:
            self.state = "IDLE"
            return [Text(T.EMPTY_MENU)]
        entries = [Row(f"cat:{c.id}", fit(c.name_ar, MAX_ROW_TITLE)) for c in cats]
        fixed = []
        if self.d["cart"]:
            fixed.append(Row("cart:show", fit(f"🛒 السلة ({self._cart_count()})", MAX_ROW_TITLE), "راجع طلبك أو كمّل"))
        order = self._active_order()
        if order is not None:
            fixed.append(Row("status", "📦 حالة طلبي", fit(f"#{order.order_no}: {T.STATUS_AR[order.status]}", MAX_ROW_DESCRIPTION)))
        fixed.append(Row("human", "🙋 كلم موظف"))
        name = self.ctx.customer.name if self.ctx.customer else None
        body = T.greeting(name, self.ctx.restaurant.name_ar) if greet else "اختار القسم 👇"
        if prefix:
            body = f"{prefix}\n{body}"
        self.state = "MAIN_MENU"
        self.d["page"] = page
        return [self._list(body, "المنيو", "الأقسام", entries, page, "cats:page:", fixed)]

    def on_main_menu(self, rid_: str, text: str, inb: Inbound):
        if text and len(text) >= 2:
            return self.search(text)
        return None

    def search(self, text: str) -> list[Outgoing] | None:
        tokens = [t for t in text.split() if len(t) >= 2 and t not in SEARCH_STOPWORDS]
        if not tokens:
            return None
        matches = []
        for cat in menu.orderable_categories(self.ctx.db, self.ctx.rid):
            for item in cat.items:
                name = T.normalize(item.name_ar)
                if item.available and any(v.available for v in item.variants) and any(t in name for t in tokens):
                    matches.append(item)
        if not matches:
            return None
        rows = [_item_row(i) for i in matches[: MAX_LIST_ROWS - 1]]
        self.state = "MAIN_MENU"
        return [
            List(
                body=fit(f"لقيت {len(matches)} صنف 👇", MAX_BODY),
                button="النتايج",
                sections=[Section("نتايج البحث", rows), Section("خيارات", [Row("menu", "↩️ الأقسام")])],
            )
        ]

    def item_list(self, category_id: int, page: int = 0, prefix: str | None = None) -> list[Outgoing]:
        err = self._open_error()
        if err:
            return err
        items = menu.orderable_items(self.ctx.db, self.ctx.rid, category_id)
        if not items:
            return self.main_menu(prefix=T.ITEM_UNAVAILABLE)
        cat = items[0].category
        fixed = [Row("menu", "↩️ الأقسام")]
        if self.d["cart"]:
            fixed.append(Row("cart:show", fit(f"🛒 السلة ({self._cart_count()})", MAX_ROW_TITLE)))
        body = f"{cat.name_ar}\nاختار الصنف 👇"
        if prefix:
            body = f"{prefix}\n{body}"
        self.state = "ITEM_LIST"
        self.d.update(category_id=category_id, page=page)
        entries = [_item_row(i) for i in items]
        return [self._list(body, "الأصناف", cat.name_ar, entries, page, f"cat:{category_id}:page:", fixed)]

    def on_item_list(self, rid_: str, text: str, inb: Inbound):
        if text and len(text) >= 2:
            return self.search(text)
        return None

    # ----------------------------------------------------------- build a line
    def select_item(self, item_id: int) -> list[Outgoing]:
        err = self._open_error()
        if err:
            return err
        item = menu.get_item(self.ctx.db, self.ctx.rid, item_id)
        if item is None:
            return self.main_menu(prefix=T.ITEM_UNAVAILABLE)
        self.d["pending"] = {"item_id": item.id, "variant_id": None, "addon_ids": []}
        variants = menu.available_variants(item)
        if len(variants) == 1:
            self.d["pending"]["variant_id"] = variants[0].id
            return self.addons_or_qty(item)
        return self.ask_variant(item=item)

    def _pending_item(self) -> Item | None:
        p = self.d.get("pending")
        return menu.get_item(self.ctx.db, self.ctx.rid, p["item_id"]) if p else None

    def ask_variant(self, item: Item | None = None, prefix: str | None = None) -> list[Outgoing]:
        item = item or self._pending_item()
        if item is None:
            return self.main_menu(prefix=T.ITEM_UNAVAILABLE)
        variants = menu.available_variants(item)
        self.state = "VARIANT"
        body = f"{item.name_ar}\nتحب أنهي حجم؟"
        if item.description_ar:
            body = f"{item.name_ar}\n{item.description_ar}\nتحب أنهي حجم؟"
        if prefix:
            body = f"{prefix}\n{body}"
        if len(variants) <= 3:
            return [
                Buttons(
                    body=fit(body, MAX_BODY),
                    buttons=[Button(f"var:{v.id}", fit(f"{v.name_ar or item.name_ar} - {T.egp(v.price)}", 20)) for v in variants],
                )
            ]
        rows = [Row(f"var:{v.id}", fit(v.name_ar or item.name_ar, MAX_ROW_TITLE), T.egp(v.price)) for v in variants]
        return [self._list(body, "الأحجام", item.name_ar, rows, 0, "var:page:", [Row("menu", "↩️ الأقسام")])]

    def on_variant(self, rid_: str, text: str, inb: Inbound):
        item = self._pending_item()
        if item is None:
            return self.main_menu(prefix=T.ITEM_UNAVAILABLE)
        variants = menu.available_variants(item)
        chosen = None
        if rid_.startswith("var:"):
            chosen = next((v for v in variants if v.id == _int(rid_[4:])), None)
        elif text:
            chosen = next((v for v in variants if v.name_ar and T.normalize(v.name_ar) == text), None)
        if chosen is None:
            return None
        self.d["pending"]["variant_id"] = chosen.id
        return self.addons_or_qty(item)

    def addons_or_qty(self, item: Item) -> list[Outgoing]:
        if menu.addons_for_category(self.ctx.db, self.ctx.rid, item.category_id):
            return self.show_addons(0, item=item)
        return self.ask_qty(item=item)

    def _pending_title(self, item: Item) -> str:
        p = self.d["pending"]
        v = next((v for v in item.variants if v.id == p.get("variant_id")), None)
        return f"{item.name_ar} ({v.name_ar})" if v and v.name_ar else item.name_ar

    def show_addons(self, page: int, item: Item | None = None, prefix: str | None = None) -> list[Outgoing]:
        item = item or self._pending_item()
        if item is None or not self.d.get("pending", {}).get("variant_id"):
            return self.main_menu(prefix=T.ITEM_UNAVAILABLE)
        addons = menu.addons_for_category(self.ctx.db, self.ctx.rid, item.category_id)
        if not addons:
            return self.ask_qty(item=item)
        selected = set(self.d["pending"]["addon_ids"])
        entries = [
            Row(f"addon:{a.id}", fit(("✅ " if a.id in selected else "") + a.name_ar, MAX_ROW_TITLE), f"+{T.egp(p)}")
            for a, p in addons
        ]
        done = Row("addons:done", "✔️ تمام كده" if selected else "بدون إضافات", "كمّل واختار الكمية")
        body = f"{self._pending_title(item)}\nتحب تضيف حاجة؟ اختار إضافة واحدة كل مرة."
        names = [a.name_ar for a, _ in addons if a.id in selected]
        if names:
            body += "\nاخترت: " + "، ".join(names)
        if prefix:
            body = f"{prefix}\n{body}"
        self.state = "ADDONS"
        self.d["page"] = page
        return [self._list(body, "الإضافات", "الإضافات", entries, page, "addons:page:", [done])]

    def on_addons(self, rid_: str, text: str, inb: Inbound):
        item = self._pending_item()
        if item is None:
            return self.main_menu(prefix=T.ITEM_UNAVAILABLE)
        if rid_ == "addons:done" or text in {"بدون", "لا", "تمام", "خلاص"}:
            return self.ask_qty(item=item)
        if rid_.startswith("addons:page:"):
            return self.show_addons(_int(rid_.rsplit(":", 1)[1]), item=item)
        if rid_.startswith("addon:"):
            aid = _int(rid_[6:])
            allowed = {a.id for a, _ in menu.addons_for_category(self.ctx.db, self.ctx.rid, item.category_id)}
            if aid not in allowed:
                return None
            sel = self.d["pending"]["addon_ids"]
            if aid in sel:
                sel.remove(aid)
            elif len(sel) < MAX_ADDONS_PER_LINE:
                sel.append(aid)
            return self.show_addons(self.d.get("page", 0), item=item)
        return None

    def ask_qty(self, item: Item | None = None, prefix: str | None = None) -> list[Outgoing]:
        item = item or self._pending_item()
        p = self.d.get("pending")
        if item is None or not p or not p.get("variant_id"):
            return self.main_menu(prefix=T.ITEM_UNAVAILABLE)
        priced = price_lines(self.ctx.db, self.ctx.rid, [{"variant_id": p["variant_id"], "addon_ids": p["addon_ids"], "qty": 1}])
        if not priced.lines:
            return self.main_menu(prefix=T.ITEM_UNAVAILABLE)
        ln = priced.lines[0]
        body = f"{_line_label(ln)}\nالسعر: {T.egp(ln.each)} للواحدة\nكام واحدة؟ اختار أو اكتب رقم من 1 لـ 9"
        if prefix:
            body = f"{prefix}\n{body}"
        self.state = "QTY"
        return [Buttons(body=fit(body, MAX_BODY), buttons=[Button(f"qty:{n}", str(n)) for n in (1, 2, 3)])]

    def on_qty(self, rid_: str, text: str, inb: Inbound):
        n = None
        if rid_.startswith("qty:"):
            n = _int(rid_[4:])
        elif text.isdigit():
            n = int(text)
        if n is None or not 1 <= n <= 9:
            return None
        p = self.d.get("pending")
        if not p or not p.get("variant_id"):
            return self.main_menu()
        key = line_key(p["variant_id"], p["addon_ids"])
        for ln in self.d["cart"]:
            if line_key(ln["variant_id"], ln["addon_ids"]) == key:
                ln["qty"] = min(50, int(ln["qty"]) + n)
                break
        else:
            self.d["cart"].append({"variant_id": p["variant_id"], "addon_ids": sorted(p["addon_ids"]), "qty": n})
        self.d.pop("pending", None)
        return self.show_cart(prefix=T.ADDED)

    # ------------------------------------------------------------------ cart
    def show_cart(self, prefix: str | None = None) -> list[Outgoing]:
        cart = self._priced_cart()
        notes = []
        if cart.removed:
            notes.append("⚠️ شيلنا من السلة حاجات خلصت: " + "، ".join(cart.removed))
        if not cart.lines:
            pre = "\n".join([*([prefix] if prefix else []), *notes, T.CART_EMPTY])
            return self.main_menu(prefix=pre)
        body = "\n".join([*( [prefix] if prefix else []), *notes, "🛒 سلتك:", _cart_lines(cart), f"المجموع: {T.egp(cart.subtotal)}"])
        self.state = "CART"
        self._reset_checkout()
        return [
            Buttons(
                body=fit(body, MAX_BODY),
                buttons=[
                    Button("cart:checkout", "✅ إتمام الطلب"),
                    Button("cart:add", "➕ أضف صنف"),
                    Button("cart:edit", "✏️ تعديل السلة"),
                ],
            )
        ]

    def on_cart(self, rid_: str, text: str, inb: Inbound):
        if rid_ == "cart:checkout":
            return self.checkout()
        if rid_ == "cart:edit":
            return self.edit_cart(0)
        if rid_ == "cart:clear":
            return self.clear_cart()
        return self._checkout_ids(rid_, text, inb)

    def edit_cart(self, page: int) -> list[Outgoing]:
        cart = self._priced_cart()
        if not cart.lines:
            return self.main_menu(prefix=T.CART_EMPTY)
        entries = [
            Row(f"line:{_key_str(ln)}", fit(f"{ln.qty}× {ln.title}", MAX_ROW_TITLE), fit(_line_detail(ln), MAX_ROW_DESCRIPTION))
            for ln in cart.lines
        ]
        fixed = [Row("cart:clear", "🧹 فضّي السلة"), Row("cart:show", "↩️ رجوع للسلة")]
        self.state = "CART_EDIT"
        self.d["page"] = page
        return [self._list("اختار الصنف اللي عايز تعدله 👇", "السلة", "أصناف السلة", entries, page, "edit:page:", fixed)]

    def on_cart_edit(self, rid_: str, text: str, inb: Inbound):
        if rid_ == "cart:clear":
            return self.clear_cart()
        if rid_.startswith("edit:page:"):
            return self.edit_cart(_int(rid_.rsplit(":", 1)[1]))
        if rid_.startswith("line:"):
            key = rid_[5:]
            cart = self._priced_cart()
            ln = next((x for x in cart.lines if _key_str(x) == key), None)
            if ln is None:
                return self.edit_cart(0)
            self.d["edit_key"] = key
            self.state = "CART_LINE"
            return [
                Buttons(
                    body=fit(f"{ln.qty}× {_line_label(ln)}\n{T.egp(ln.line_total)}", MAX_BODY),
                    buttons=[
                        Button(f"inc:{key}", "➕ زوّد واحدة"),
                        Button(f"dec:{key}", "➖ قلّل واحدة"),
                        Button(f"del:{key}", "🗑️ شيل الصنف"),
                    ],
                )
            ]
        return None

    def on_cart_line(self, rid_: str, text: str, inb: Inbound):
        for op in ("inc", "dec", "del"):
            if rid_.startswith(op + ":"):
                key = rid_[len(op) + 1:]
                for ln in list(self.d["cart"]):
                    if _key_str_raw(ln) == key:
                        if op == "inc":
                            ln["qty"] = min(50, int(ln["qty"]) + 1)
                        elif op == "dec" and int(ln["qty"]) > 1:
                            ln["qty"] = int(ln["qty"]) - 1
                        else:
                            self.d["cart"].remove(ln)
                        return self.show_cart(prefix=T.EDITED)
                return self.show_cart()
        return self.on_cart_edit(rid_, text, inb)

    def clear_cart(self) -> list[Outgoing]:
        self.d["cart"] = []
        self._reset_checkout()
        return self.main_menu(prefix=T.CART_CLEARED)

    # -------------------------------------------------------------- checkout
    def checkout(self) -> list[Outgoing]:
        err = self._open_error()
        if err:
            return err
        cart = self._priced_cart()
        if not cart.lines or cart.removed:
            return self.show_cart()
        s = self.ctx.settings
        if s["delivery_enabled"] and s["pickup_enabled"]:
            return self.ask_fulfillment()
        if s["delivery_enabled"]:
            self.d["fulfillment"] = "delivery"
            return self.start_delivery()
        self.d["fulfillment"] = "pickup"
        return self.ask_payment()

    def ask_fulfillment(self, prefix: str | None = None) -> list[Outgoing]:
        self.state = "FULFILLMENT"
        body = "تحب الطلب توصيل ولا هتستلمه من المطعم؟"
        if prefix:
            body = f"{prefix}\n{body}"
        return [
            Buttons(
                body=body,
                buttons=[
                    Button("ful:delivery", "🛵 توصيل"),
                    Button("ful:pickup", "🏃 استلام من المطعم"),
                    Button("cart:show", "↩️ رجوع للسلة"),
                ],
            )
        ]

    def _checkout_ids(self, rid_: str, text: str, inb: Inbound):
        """Checkout replies are accepted from any checkout step (stale taps)."""
        if not self.d["cart"]:
            return None
        s = self.ctx.settings
        if rid_ == "ful:delivery" and s["delivery_enabled"]:
            self.d["fulfillment"] = "delivery"
            self.d.pop("zone_id", None)
            self.d.pop("address", None)
            return self.start_delivery()
        if rid_ == "ful:pickup" and s["pickup_enabled"]:
            self.d["fulfillment"] = "pickup"
            self.d.pop("zone_id", None)
            self.d.pop("address", None)
            return self.ask_payment()
        if rid_.startswith("zone:") and self.d.get("fulfillment") == "delivery":
            return self.choose_zone(_int(rid_[5:]))
        if rid_.startswith("zones:page:") and self.d.get("fulfillment") == "delivery":
            return self.ask_zone(_int(rid_.rsplit(":", 1)[1]))
        if rid_.startswith("pay:") and self.d.get("fulfillment") and (
            self.d["fulfillment"] == "pickup" or self.d.get("address")
        ):
            method = rid_[4:]
            if method in s["payment_methods"]:
                self.d["payment"] = method
                return self.summary()
        return None

    on_fulfillment = _checkout_ids

    def start_delivery(self) -> list[Outgoing]:
        if active_zones(self.ctx.db, self.ctx.rid):
            return self.ask_zone(0)
        self.d["zone_id"] = None
        return self._check_min_then_address(None)

    def ask_zone(self, page: int, prefix: str | None = None) -> list[Outgoing]:
        zones = active_zones(self.ctx.db, self.ctx.rid)
        if not zones:
            return self.start_delivery()
        entries = [Row(f"zone:{z.id}", fit(z.name_ar, MAX_ROW_TITLE), fit(_zone_desc(z), MAX_ROW_DESCRIPTION)) for z in zones]
        fixed = []
        if self.ctx.settings["pickup_enabled"]:
            fixed.append(Row("ful:pickup", "🏃 استلام بدل كده"))
        body = "اختار منطقتك 📍"
        if prefix:
            body = f"{prefix}\n{body}"
        self.state = "ZONE"
        self.d["page"] = page
        return [self._list(body, "المناطق", "مناطق التوصيل", entries, page, "zones:page:", fixed)]

    on_zone = _checkout_ids

    def choose_zone(self, zone_id: int) -> list[Outgoing] | None:
        zone = next((z for z in active_zones(self.ctx.db, self.ctx.rid) if z.id == zone_id), None)
        if zone is None:
            return self.ask_zone(0, prefix="المنطقة دي مش متاحة، اختار منطقة تانية")
        self.d["zone_id"] = zone.id
        return self._check_min_then_address(zone)

    def _check_min_then_address(self, zone: DeliveryZone | None) -> list[Outgoing]:
        s = self.ctx.settings
        cart = self._priced_cart()
        if zone is not None and zone.min_order > 0:
            min_order = zone.min_order
        else:
            min_order = _dec(s["min_order"])
        if cart.subtotal < min_order:
            where = f" لـ{zone.name_ar}" if zone else ""
            buttons = [Button("cart:add", "➕ أضف صنف")]
            if s["pickup_enabled"]:
                buttons.append(Button("ful:pickup", "🏃 استلام بدل كده"))
            buttons.append(Button("cart:show", "↩️ السلة"))
            self.state = "CART"
            return [
                Buttons(
                    body=f"الحد الأدنى للتوصيل{where} هو {T.egp(min_order)}، وسلتك {T.egp(cart.subtotal)}.",
                    buttons=buttons,
                )
            ]
        return self.ask_address()

    def ask_address(self, prefix: str | None = None) -> list[Outgoing]:
        self.state = "ADDRESS"
        cust = self.ctx.customer
        same_zone = cust is not None and (self.d.get("zone_id") is None or cust.last_zone_id == self.d.get("zone_id"))
        if cust is not None and cust.last_address and same_zone:
            body = f"نوصل على نفس العنوان؟\n📍 {cust.last_address}"
            if prefix:
                body = f"{prefix}\n{body}"
            return [
                Buttons(
                    body=fit(body, MAX_BODY),
                    buttons=[Button("addr:same", "✅ نفس العنوان"), Button("addr:new", "✏️ عنوان جديد")],
                )
            ]
        return [Text(f"{prefix}\n{T.ASK_ADDRESS}" if prefix else T.ASK_ADDRESS)]

    def on_address(self, rid_: str, text: str, inb: Inbound):
        cust = self.ctx.customer
        if rid_ == "addr:same" and cust is not None and cust.last_address:
            self.d["address"] = cust.last_address
            return self.ask_payment()
        if rid_ == "addr:new":
            return [Text(T.ASK_ADDRESS)]
        if inb.kind == "text" and inb.text.strip():
            addr = " ".join(inb.text.split())
            if len(addr) < 8:
                return [Text(T.ADDRESS_SHORT)]
            self.d["address"] = addr[:300]
            return self.ask_payment()
        return self._checkout_ids(rid_, text, inb)

    def ask_payment(self, prefix: str | None = None) -> list[Outgoing]:
        methods = self.ctx.settings["payment_methods"]
        if len(methods) == 1:
            self.d["payment"] = methods[0]
            return self.summary(prefix=prefix)
        self.state = "PAYMENT"
        body = "هتدفع إزاي؟"
        if prefix:
            body = f"{prefix}\n{body}"
        return [
            Buttons(
                body=body,
                buttons=[Button("pay:cod", "💵 كاش عند الاستلام"), Button("pay:wallet", "📱 محفظة / إنستاباي")],
            )
        ]

    on_payment = _checkout_ids

    def summary(self, prefix: str | None = None) -> list[Outgoing]:
        cart = self._priced_cart()
        if not cart.lines or cart.removed:
            return self.show_cart()
        s = self.ctx.settings
        lines = ["📋 ملخص طلبك:", _cart_lines(cart), f"المجموع: {T.egp(cart.subtotal)}"]
        total = cart.subtotal
        if self.d.get("fulfillment") == "delivery":
            zone = None
            if self.d.get("zone_id"):
                zone = next((z for z in active_zones(self.ctx.db, self.ctx.rid) if z.id == self.d["zone_id"]), None)
                if zone is None:
                    return self.ask_zone(0, prefix="المنطقة اتغيرت، اختارها تاني")
            fee = zone.fee if zone else _dec(s["delivery_fee"])
            total += fee
            lines += [f"التوصيل: {T.egp(fee)}", f"الإجمالي: {T.egp(total)}"]
            where = f"{zone.name_ar} - " if zone else ""
            lines.append(f"🛵 توصيل: {where}{self.d.get('address', '')}")
        else:
            lines += [f"الإجمالي: {T.egp(total)}", "🏃 استلام من المطعم"]
        lines.append(f"💵 الدفع: {T.PAYMENT_AR[self.d.get('payment', 'cod')]}")
        lines.append(f"⏱️ الوقت المتوقع: حوالي {s['eta_minutes']} دقيقة")
        if prefix:
            lines.insert(0, prefix)
        self.state = "CONFIRM"
        return [
            Buttons(
                body=fit("\n".join(lines), MAX_BODY),
                buttons=[
                    Button("confirm:yes", "✅ تأكيد الطلب"),
                    Button("cart:show", "✏️ تعديل"),
                    Button("cancel", "❌ إلغاء"),
                ],
            )
        ]

    def on_confirm(self, rid_: str, text: str, inb: Inbound):
        if rid_ != "confirm:yes" and text not in {"تاكيد", "اكد", "تمام", "ok"}:
            return self._checkout_ids(rid_, text, inb)
        cust = self.ctx.customer
        if cust is None:
            return None
        cart = self._priced_cart()
        try:
            order = create_order(
                self.ctx.db,
                restaurant=self.ctx.restaurant,
                settings=self.ctx.settings,
                customer=cust,
                lines=self.d["cart"],
                fulfillment=self.d.get("fulfillment", "pickup"),
                payment_method=self.d.get("payment", "cod"),
                channel=self.ctx.conv.channel,
                zone_id=self.d.get("zone_id"),
                address=self.d.get("address"),
                conversation_id=self.ctx.conv.id,
                priced=cart,
                now=self.ctx.now,
            )
        except OrderError as e:
            if e.code in ("closed", "not_accepting", "unavailable"):
                self.state = "CART"
                return [Text(e.message_ar)]
            if e.code in ("zone_required",):
                return self.ask_zone(0, prefix=e.message_ar)
            if e.code == "address_required":
                return self.ask_address(prefix=e.message_ar)
            return self.show_cart(prefix=e.message_ar)
        self.d = {"cart": [], "last_order_id": order.id}
        self.state = "IDLE"
        return [Text(T.order_placed(order.order_no, order.total, order.payment_method, self.ctx.settings["wallet_number"]))]


# --------------------------------------------------------------------- utils
def _int(v: str) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def _dec(v):
    from decimal import Decimal

    return Decimal(str(v))


def _paginate(entries: list[Row], page: int, fixed: list[Row], more_id: str) -> tuple[list[Row], list[Row]]:
    capacity = MAX_LIST_ROWS - len(fixed)
    if len(entries) <= capacity:
        return entries, fixed
    per_page = capacity - 1
    pages = math.ceil(len(entries) / per_page)
    page = page % pages if page >= 0 else 0
    chunk = entries[page * per_page:(page + 1) * per_page]
    more = Row(f"{more_id}{(page + 1) % pages}", "المزيد ⬅️", f"صفحة {page + 1} من {pages}")
    return chunk, [more, *fixed]


def _item_row(item: Item) -> Row:
    variants = [v for v in item.variants if v.available]
    if len(variants) == 1:
        desc = T.egp(variants[0].price)
    else:
        desc = " • ".join(f"{v.name_ar or ''} {T.egp(v.price)}".strip() for v in variants)
    if item.description_ar:
        desc = f"{desc} — {item.description_ar}"
    return Row(f"item:{item.id}", fit(item.name_ar, MAX_ROW_TITLE), fit(desc, MAX_ROW_DESCRIPTION))


def _line_label(ln: PricedLine) -> str:
    label = ln.title
    if ln.addons:
        label += " + " + " + ".join(a.name for a in ln.addons)
    return label


def _line_detail(ln: PricedLine) -> str:
    extra = " + ".join(a.name for a in ln.addons)
    return f"{T.egp(ln.line_total)}" + (f" • {extra}" if extra else "")


def _cart_lines(cart: PricedCart) -> str:
    out = []
    for i, ln in enumerate(cart.lines, 1):
        out.append(f"{i}) {ln.qty}× {ln.title} — {T.egp(ln.line_total)}")
        if ln.addons:
            out.append("   + " + "، ".join(a.name for a in ln.addons))
    text = "\n".join(out)
    return text if len(text) <= 800 else text[:790] + "\n…"


def _key_str(ln: PricedLine) -> str:
    return f"{ln.variant_id}-" + ".".join(str(a.id) for a in sorted(ln.addons, key=lambda a: a.id))


def _key_str_raw(ln: dict) -> str:
    return f"{int(ln['variant_id'])}-" + ".".join(str(a) for a in sorted(int(x) for x in ln["addon_ids"]))


def _zone_desc(z: DeliveryZone) -> str:
    desc = f"التوصيل {T.egp(z.fee)}"
    if z.min_order and z.min_order > 0:
        desc += f" • حد أدنى {T.egp(z.min_order)}"
    return desc
