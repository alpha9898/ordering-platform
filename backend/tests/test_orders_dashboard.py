"""Order lifecycle, notifications, web-menu orders, human handoff."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models import Order

from .conftest import Chat, order_zinger_delivery


def _place_chat_order(chat: Chat) -> None:
    order_zinger_delivery(chat)
    chat.tap("confirm:yes")


def test_status_flow_notifies_customer_in_chat(chat: Chat, staff, db):
    _place_chat_order(chat)
    oid = db.scalar(select(Order.id))
    seen = len(chat.poll())

    r = staff.post(f"/api/dash/orders/{oid}/status", json={"status": "accepted"})
    assert r.status_code == 200 and r.json()["customer_notified"]
    msgs = chat.poll(after=0)[seen:]
    assert "تم قبول طلبك #1" in msgs[-1]["payload"]["body"] and "35 دقيقة" in msgs[-1]["payload"]["body"]

    assert staff.post(f"/api/dash/orders/{oid}/status", json={"status": "preparing"}).status_code == 200
    # delivery order can't be "ready for pickup"
    assert staff.post(f"/api/dash/orders/{oid}/status", json={"status": "ready_for_pickup"}).status_code == 409
    assert staff.post(f"/api/dash/orders/{oid}/status", json={"status": "out_for_delivery"}).status_code == 200
    assert "خرج للتوصيل" in chat.poll()[-1]["payload"]["body"]
    done = staff.post(f"/api/dash/orders/{oid}/status", json={"status": "completed"}).json()
    assert done["status"] == "completed" and done["payment_status"] == "paid"
    assert [e["status"] for e in done["events"]] == ["placed", "accepted", "preparing", "out_for_delivery", "completed"]


def test_illegal_transitions_are_409(chat: Chat, staff, db):
    _place_chat_order(chat)
    oid = db.scalar(select(Order.id))
    assert staff.post(f"/api/dash/orders/{oid}/status", json={"status": "completed"}).status_code == 409
    assert staff.post(f"/api/dash/orders/{oid}/status", json={"status": "rejected"}).status_code == 409  # needs reason
    r = staff.post(f"/api/dash/orders/{oid}/status", json={"status": "rejected", "reject_reason": "الصنف خلص"})
    assert r.status_code == 200
    assert "السبب: الصنف خلص" in chat.poll()[-1]["payload"]["body"]
    assert staff.post(f"/api/dash/orders/{oid}/status", json={"status": "accepted"}).status_code == 409


def test_cancel_only_before_preparing(chat: Chat, staff, db):
    _place_chat_order(chat)
    oid = db.scalar(select(Order.id))
    staff.post(f"/api/dash/orders/{oid}/status", json={"status": "accepted"})
    staff.post(f"/api/dash/orders/{oid}/status", json={"status": "preparing"})
    assert staff.post(f"/api/dash/orders/{oid}/status", json={"status": "cancelled"}).status_code == 409


def test_web_menu_order_ignores_client_prices(client, db):
    menu = client.get("/api/public/r/dash").json()
    burgers = next(c for c in menu["menu"] if c["name"] == "فراخ مقلية")
    zinger = burgers["items"][0]
    single = zinger["variants"][0]
    cheddar = next(a for a in burgers["addons"] if a["name"] == "جبنة شيدر")
    drinks = next(c for c in menu["menu"] if c["name"] == "مشروبات")
    body = {
        "customer": {"name": "منى", "phone": "+20 111 222 3333"},
        "lines": [
            {"variant_id": single["id"], "addon_ids": [cheddar["id"]], "qty": 2, "price": 1},
            # add-on not allowed on drinks -> dropped, can't change the price
            {"variant_id": drinks["items"][0]["variants"][0]["id"], "addon_ids": [cheddar["id"]], "qty": 1},
        ],
        "fulfillment": "pickup",
        "payment_method": "cod",
        "total": 1,
    }
    r = client.post("/api/public/r/dash/orders", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 2 * (95 + 15) + 20
    track = client.get(f"/api/public/orders/{r.json()['token']}").json()
    assert track["status"] == "placed" and "customer" not in track and "address" not in track
    order = db.scalar(select(Order))
    assert order.channel == "web_menu" and order.customer.phone == "201112223333"


def test_web_menu_delivery_requires_zone_and_address(client):
    menu = client.get("/api/public/r/dash").json()
    vid = menu["menu"][0]["items"][0]["variants"][0]["id"]
    base = {"customer": {"name": "منى", "phone": "01112223333"}, "lines": [{"variant_id": vid, "qty": 1}], "fulfillment": "delivery"}
    r = client.post("/api/public/r/dash/orders", json=base)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "zone_required"
    r = client.post("/api/public/r/dash/orders", json={**base, "zone_id": menu["zones"][0]["id"]})
    assert r.json()["detail"]["code"] == "address_required"
    r = client.post("/api/public/r/dash/orders", json={**base, "zone_id": menu["zones"][0]["id"], "address": "شارع 9 المعادي"})
    assert r.status_code == 200 and r.json()["total"] == 95 + 20


def test_human_handoff_silences_bot_and_staff_can_reply(chat: Chat, staff):
    chat.text("اهلا")
    chat.text("موظف")
    assert "هيرد عليك" in chat.body
    board = staff.get("/api/dash/board").json()
    assert len(board["human"]) == 1
    conv_id = board["human"][0]["id"]

    assert chat.text("لو سمحت عايز أعدل طلبي") == []  # bot stays quiet
    assert staff.post(f"/api/dash/conversations/{conv_id}/reply", json={"text": "أهلًا، تحت أمرك"}).status_code == 200
    last = chat.poll()[-1]
    assert last["sender"] == "staff" and last["payload"]["body"] == "أهلًا، تحت أمرك"

    assert staff.post(f"/api/dash/conversations/{conv_id}/resolve").status_code == 200
    assert staff.get("/api/dash/board").json()["human"] == []
    chat.text("اهلا")
    assert "اختار القسم" in chat.body  # bot is back


def test_history_search(chat: Chat, owner):
    _place_chat_order(chat)
    assert len(owner.get("/api/dash/orders", params={"q": "#1"}).json()["orders"]) == 1
    assert len(owner.get("/api/dash/orders", params={"q": "1012345"}).json()["orders"]) == 1
    assert owner.get("/api/dash/orders", params={"q": "999999"}).json()["orders"] == []


def test_order_numbers_are_daily_per_restaurant(client, admin, db):
    admin.post("/api/admin/restaurants", json={
        "name": "مطعم تاني", "slug": "second", "owner_username": "second", "owner_password": "second-pass-1", "copy_menu_from": 1,
    })
    for slug in ("dash", "second", "dash"):
        c = Chat(client, slug=slug)
        c.text("منيو")
        c.tap(c.row_id("مشروبات"))
        c.tap(c.row_id("ماكسي كولا"))
        c.tap("qty:1")
        c.tap("cart:checkout")
        c.tap("ful:pickup")
        c.tap("confirm:yes")
    nos = sorted((o.restaurant_id, o.order_no) for o in db.scalars(select(Order)).all())
    assert nos == [(1, 1), (1, 2), (2, 1)]
    assert {o.subtotal for o in db.scalars(select(Order)).all()} == {Decimal("20")}
