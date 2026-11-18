"""Delivery zones, customer location and sending orders to drivers."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.main import app
from app.models import Customer, Order

from .conftest import Api, Chat

CAIRO = (30.044420, 31.235712)


def _to_address_step(chat: Chat, zone: str = "شرق") -> None:
    chat.text("اهلا")
    chat.tap(chat.row_id("فراخ مقلية"))
    chat.tap(chat.row_id("زنجر"))
    chat.tap(chat.row_id("دبل"))
    chat.tap("addons:done")
    chat.tap("qty:1")
    chat.tap("cart:checkout")
    chat.tap("ful:delivery")
    chat.tap(chat.row_id(zone))


def test_zones_are_east_and_west(client):
    zones = client.get("/api/public/r/dash").json()["zones"]
    assert [(z["name"], z["fee"]) for z in zones] == [("شرق", 20.0), ("غرب", 30.0)]


def test_location_then_details_saves_pin_on_order_and_customer(chat: Chat, owner, db):
    _to_address_step(chat)
    assert chat.last[0]["type"] == "location_request" and "ابعت موقعك" in chat.body
    chat.location(*CAIRO)
    assert "وصلنا موقعك" in chat.body
    chat.text("عمارة 5 الدور 3 شقة 7")
    assert "📍 موقعك على الخريطة وصل للمطعم" in chat.body and "الإجمالي: 165 ج" in chat.body
    chat.tap("confirm:yes")
    order = db.scalar(select(Order))
    assert (order.lat, order.lng) == (Decimal("30.044420"), Decimal("31.235712"))
    assert order.address_text == "عمارة 5 الدور 3 شقة 7"
    cust = db.scalar(select(Customer))
    assert cust.last_lat == order.lat
    assert owner.get(f"/api/dash/orders/{order.id}").json()["location"] == {"lat": CAIRO[0], "lng": CAIRO[1]}


def test_details_required_after_location(chat: Chat):
    _to_address_step(chat)
    chat.location(*CAIRO)
    chat.text("5")
    assert "تفاصيل أكتر" in chat.body


def test_invalid_location_is_rejected(chat: Chat, client):
    _to_address_step(chat)
    for bad in ({"lat": 200, "lng": 31}, {"lat": 30}):
        r = client.post("/api/chat/dash/send", json={"session_id": chat.sid, "kind": "location", **bad})
        assert r.status_code == 422


def test_returning_customer_reuses_pin_and_new_typed_address_clears_it(client, db):
    first = Chat(client)
    _to_address_step(first)
    first.location(*CAIRO)
    first.text("عمارة 5 الدور 3")
    first.tap("confirm:yes")

    second = Chat(client)
    _to_address_step(second)
    assert "addr:same" in second.ids() and "ومعاه موقعك على الخريطة" in second.body
    second.tap("addr:same")
    assert "📍 موقعك على الخريطة" in second.body
    second.tap("confirm:yes")
    assert db.scalars(select(Order).order_by(Order.id)).all()[-1].lat == Decimal("30.044420")

    third = Chat(client)
    _to_address_step(third)
    third.tap("addr:new")
    assert third.last[0]["type"] == "location_request"
    third.text("شارع النيل عمارة 10")
    third.tap("confirm:yes")
    db.expire_all()
    assert db.scalars(select(Order).order_by(Order.id)).all()[-1].lat is None
    assert db.scalar(select(Customer)).last_lat is None


def test_location_outside_checkout_is_not_accepted(chat: Chat):
    chat.text("اهلا")
    chat.location(*CAIRO)
    assert "اختار من الاختيارات" in chat.body


def test_web_menu_order_with_location(client, db):
    menu = client.get("/api/public/r/dash").json()
    vid = menu["menu"][0]["items"][0]["variants"][0]["id"]
    base = {
        "customer": {"name": "منى", "phone": "01112223333"},
        "lines": [{"variant_id": vid, "qty": 1}],
        "fulfillment": "delivery",
        "zone_id": menu["zones"][1]["id"],
        "address": "عمارة 9 الدور 2",
    }
    assert client.post("/api/public/r/dash/orders", json={**base, "lat": 30.1}).status_code == 409  # lat without lng
    assert client.post("/api/public/r/dash/orders", json={**base, "lat": 95, "lng": 31}).status_code == 422
    r = client.post("/api/public/r/dash/orders", json={**base, "lat": CAIRO[0], "lng": CAIRO[1]})
    assert r.status_code == 200 and r.json()["total"] == 95 + 30  # west zone
    assert db.scalar(select(Order)).lat == Decimal("30.044420")


def test_owner_edits_zone_and_bot_uses_it_immediately(chat: Chat, owner):
    zone = owner.get("/api/dash/zones").json()["zones"][0]
    r = owner.patch(f"/api/dash/zones/{zone['id']}", json={"name": "شرق البلد", "fee": 25, "min_order": 0, "active": True, "sort": 0})
    assert r.status_code == 200
    chat.text("اهلا")
    chat.tap(chat.row_id("مشروبات"))
    chat.tap(chat.row_id("ماكسي كولا"))
    chat.tap("qty:1")
    chat.tap("cart:checkout")
    chat.tap("ful:delivery")
    rows = [(r["title"], r["description"]) for p in chat.last if p["type"] == "list" for s in p["sections"] for r in s["rows"]]
    assert ("شرق البلد", "التوصيل 25 ج") in rows


def test_drivers_setting_owner_only_and_validated(owner, staff):
    r = owner.patch("/api/dash/settings", json={"drivers": [{"name": " أحمد ", "phone": "010 1111 2222"}]})
    assert r.status_code == 200 and r.json()["settings"]["drivers"] == [{"name": "أحمد", "phone": "201011112222"}]
    assert staff.patch("/api/dash/settings", json={"drivers": []}).status_code == 422
    assert owner.patch("/api/dash/settings", json={"drivers": [{"name": "x", "phone": "12"}]}).status_code == 422
    dup = [{"name": "a", "phone": "01011112222"}, {"name": "b", "phone": "201011112222"}]
    assert owner.patch("/api/dash/settings", json={"drivers": dup}).status_code == 422
    assert staff.get("/api/dash/board").json()["drivers"] == [{"name": "أحمد", "phone": "201011112222"}]


def test_send_to_driver_records_driver_and_builds_whatsapp_link(chat: Chat, owner, staff, admin, db):
    owner.patch("/api/dash/settings", json={"drivers": [{"name": "أحمد", "phone": "01011112222"}]})
    _to_address_step(chat)
    chat.location(*CAIRO)
    chat.text("عمارة 5 الدور 3")
    chat.tap("confirm:yes")
    oid = db.scalar(select(Order.id))

    assert staff.post(f"/api/dash/orders/{oid}/driver", json={"phone": "01011112222"}).status_code == 409  # not accepted yet
    staff.post(f"/api/dash/orders/{oid}/status", json={"status": "accepted"})
    assert staff.post(f"/api/dash/orders/{oid}/driver", json={"phone": "01099999999"}).status_code == 422  # unknown driver

    r = staff.post(f"/api/dash/orders/{oid}/driver", json={"phone": "01011112222"}).json()
    assert r["whatsapp_url"].startswith("https://wa.me/201011112222?text=")
    assert "https://www.google.com/maps?q=30.044420,31.235712" in r["text"]
    assert "المطلوب تحصيله: 165 ج (كاش)" in r["text"] and "📞 01012345678" in r["text"]
    assert r["order"]["driver"]["name"] == "أحمد"

    share = staff.post(f"/api/dash/orders/{oid}/driver", json={}).json()
    assert share["whatsapp_url"].startswith("https://wa.me/?text=")
    assert share["order"]["driver"]["name"] == "أحمد"  # sharing doesn't change the assignment

    admin.post("/api/admin/restaurants", json={
        "name": "مطعم تاني", "slug": "other", "owner_username": "other", "owner_password": "other-pass-1",
    })
    other = Api(app)
    other.login("other", "other-pass-1")
    assert other.post(f"/api/dash/orders/{oid}/driver", json={}).status_code == 404


def test_pickup_orders_cannot_go_to_driver(chat: Chat, staff, db):
    chat.text("منيو")
    chat.tap(chat.row_id("مشروبات"))
    chat.tap(chat.row_id("ماكسي كولا"))
    chat.tap("qty:1")
    chat.tap("cart:checkout")
    chat.tap("ful:pickup")
    chat.tap("confirm:yes")
    oid = db.scalar(select(Order.id))
    staff.post(f"/api/dash/orders/{oid}/status", json={"status": "accepted"})
    assert staff.post(f"/api/dash/orders/{oid}/driver", json={}).status_code == 409
