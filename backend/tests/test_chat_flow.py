"""End-to-end ordering through the web chat channel (real Postgres)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models import Conversation, ItemVariant, Order
from app.services import settings as settings_svc

from .conftest import Chat, order_zinger_delivery


def test_greeting_shows_categories_and_human(chat: Chat):
    chat.text("السلام عليكم")
    assert "أهلًا بيك يا أحمد في Dash" in chat.body
    ids = chat.ids()
    assert "human" in ids
    assert sum(1 for i in ids if i.startswith("cat:")) == 8


def test_full_delivery_order(chat: Chat, owner, db):
    order_zinger_delivery(chat)
    assert "📋 ملخص طلبك" in chat.body
    assert "الإجمالي: 335 ج" in chat.body  # 2 x (145 + 15) + 15 delivery
    chat.tap("confirm:yes")
    assert "رقم الطلب: #1" in chat.body

    order = db.scalar(select(Order))
    assert order.total == Decimal("335") and order.delivery_fee == Decimal("15")
    assert order.channel == "web_chat" and order.is_demo and order.status == "placed"
    assert order.zone_name_snapshot.startswith("قريب")
    assert order.items[0].variant_snapshot == "دبل" and order.items[0].addons[0].name_snapshot == "جبنة شيدر"

    board = owner.get("/api/dash/board").json()
    assert [o["order_no"] for o in board["orders"]] == [1]
    assert board["orders"][0]["customer"]["phone"] == "201012345678"


def test_pickup_skips_address_and_cod_only_skips_payment(chat: Chat, db):
    chat.text("منيو")
    chat.tap(chat.row_id("مشروبات"))
    chat.tap(chat.row_id("ماكسي كولا"))
    assert "كام واحدة" in chat.body  # single price, no add-ons -> straight to qty
    chat.text("٣")  # Arabic-Indic digit
    assert "3× ماكسي كولا — 60 ج" in chat.body
    chat.tap("cart:checkout")
    chat.tap("ful:pickup")
    assert "استلام من المطعم" in chat.body and "confirm:yes" in chat.ids()
    chat.tap("confirm:yes")
    order = db.scalar(select(Order))
    assert order.fulfillment == "pickup" and order.total == Decimal("60") and order.address_text is None


def test_same_item_same_addons_merge_and_cart_edit(chat: Chat):
    for _ in range(2):
        chat.tap("menu")
        chat.tap(chat.row_id("مشروبات"))
        chat.tap(chat.row_id("ماكسي كولا"))
        chat.tap("qty:1")
    assert "2× ماكسي كولا" in chat.body and chat.body.count("ماكسي كولا") == 1

    chat.tap("cart:edit")
    line = next(i for i in chat.ids() if i.startswith("line:"))
    chat.tap(line)
    chat.tap(next(i for i in chat.ids() if i.startswith("inc:")))
    assert "3× ماكسي كولا" in chat.body
    chat.tap("cart:edit")
    chat.tap(line)
    chat.tap(next(i for i in chat.ids() if i.startswith("del:")))
    assert "سلتك فاضية" in chat.body


def test_wallet_payment_step_when_enabled(chat: Chat, db):
    settings_svc.update(db, 1, {"payment_methods": ["cod", "wallet"], "wallet_number": "01000000000"}, settings_svc.OWNER_KEYS)
    db.commit()
    order_zinger_delivery(chat)
    assert {"pay:cod", "pay:wallet"} <= set(chat.ids())
    chat.tap("pay:wallet")
    assert "محفظة" in chat.body
    chat.tap("confirm:yes")
    assert "01000000000" in chat.body
    assert db.scalar(select(Order)).payment_method == "wallet"


def test_closed_and_not_accepting(chat: Chat, db):
    closed = {d: [] for d in settings_svc.WEEKDAYS}
    closed["sat"] = [["12:00", "13:00"]]
    settings_svc.update(db, 1, {"working_hours": closed}, settings_svc.OWNER_KEYS)
    db.commit()
    chat.text("اهلا")
    assert "مقفولين" in chat.body and "بنفتح" in chat.body and "السبت" in chat.body or "بكرة" in chat.body or "النهارده" in chat.body

    settings_svc.update(db, 1, {"working_hours": {d: [["00:00", "24:00"]] for d in settings_svc.WEEKDAYS}, "accepting_orders": False}, settings_svc.OWNER_KEYS)
    db.commit()
    chat.text("اهلا")
    assert "مش بيستقبل طلبات" in chat.body


def test_item_sold_out_between_selection_and_confirm(chat: Chat, owner, db):
    order_zinger_delivery(chat)
    variant = db.scalar(select(ItemVariant).where(ItemVariant.name_ar == "دبل", ItemVariant.item_id == 1))
    assert owner.patch(f"/api/dash/variants/{variant.id}", json={"available": False}).status_code == 200
    chat.tap("confirm:yes")
    assert "خلصت" in chat.body and "زنجر (دبل)" in chat.body
    assert db.scalar(select(Order)) is None


def test_below_zone_min_order_offers_alternatives(chat: Chat):
    chat.text("منيو")
    chat.tap(chat.row_id("مشروبات"))
    chat.tap(chat.row_id("ماكسي كولا"))
    chat.tap("qty:1")
    chat.tap("cart:checkout")
    chat.tap("ful:delivery")
    chat.tap(chat.row_id("بعيد"))
    assert "الحد الأدنى للتوصيل" in chat.body and "150 ج" in chat.body
    assert {"cart:add", "ful:pickup"} <= set(chat.ids())


def test_two_failed_inputs_offer_human(chat: Chat):
    chat.text("اهلا")
    chat.tap(chat.row_id("فراخ مقلية"))
    chat.tap(chat.row_id("زنجر"))
    chat.text("كلام مش مفهوم")
    assert "اختار من الاختيارات" in chat.body
    chat.text("تاني")
    assert "human" in chat.ids()


def test_stale_button_on_older_message_still_works(chat: Chat):
    chat.text("اهلا")
    chat.tap(chat.row_id("مشروبات"))
    cola = chat.row_id("ماكسي كولا")
    chat.tap(cola)
    chat.tap("qty:1")  # now in CART
    chat.tap(cola)  # tap the older list again
    assert "كام واحدة" in chat.body


def test_search_by_typing_item_name(chat: Chat):
    chat.text("اهلا")
    chat.text("عايز زنجر")
    titles = [r["title"] for p in chat.last if p["type"] == "list" for s in p["sections"] for r in s["rows"]]
    assert "زنجر" in titles and "سبايسي زنجر" in titles


def test_cancel_clears_cart(chat: Chat, db):
    chat.text("اهلا")
    chat.tap(chat.row_id("مشروبات"))
    chat.tap(chat.row_id("ماكسي كولا"))
    chat.tap("qty:1")
    chat.text("إلغاء")
    assert "اتلغى" in chat.body
    conv = db.scalar(select(Conversation))
    assert conv.state == "IDLE" and conv.data["cart"] == []


def test_returning_customer_gets_same_address_option(client, db):
    first = Chat(client)
    order_zinger_delivery(first, address="شارع النيل عمارة 10")
    first.tap("confirm:yes")
    second = Chat(client)  # new session, same phone
    second.text("اهلا")
    second.tap(second.row_id("مشروبات"))
    second.tap(second.row_id("ماكسي كولا"))
    second.tap("qty:3")
    second.tap("cart:checkout")
    second.tap("ful:delivery")
    second.tap(second.row_id("قريب"))
    assert "addr:same" in second.ids() and "شارع النيل عمارة 10" in second.body
    assert "📦 حالة طلبي" not in second.body
