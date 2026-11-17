"""Multi-tenancy, auth, admin, WhatsApp limits, Excel, hours."""

from __future__ import annotations

import datetime as dt
import io

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.engine.messages import Button, Buttons, LimitError, List, Row, Section, validate_payload
from app.main import app
from app.models import Message, Order
from app.services import hours

from .conftest import Api, Chat, order_zinger_delivery


def _second_restaurant(admin) -> Api:
    r = admin.post("/api/admin/restaurants", json={
        "name": "مطعم بي", "slug": "bee", "owner_username": "bee", "owner_password": "bee-pass-123", "copy_menu_from": 1,
    })
    assert r.status_code == 200, r.text
    c = Api(app)
    c.login("bee", "bee-pass-123")
    return c


def test_tenant_isolation(chat: Chat, admin, db):
    order_zinger_delivery(chat)
    chat.tap("confirm:yes")
    dash_order = db.scalar(select(Order.id))
    bee = _second_restaurant(admin)

    assert bee.get(f"/api/dash/orders/{dash_order}").status_code == 404
    assert bee.post(f"/api/dash/orders/{dash_order}/status", json={"status": "accepted"}).status_code == 404
    assert bee.patch("/api/dash/items/1", json={"available": False}).status_code == 404  # Dash's item
    assert bee.patch("/api/dash/variants/1", json={"price": 1}).status_code == 404
    assert bee.get("/api/dash/board").json()["orders"] == []
    assert bee.get("/api/dash/conversations/1/messages").status_code == 404
    bee_menu = bee.get("/api/dash/menu").json()
    assert bee_menu["categories"][0]["id"] != 1 and len(bee_menu["categories"]) == 8


def test_staff_cannot_edit_prices_or_settings(staff):
    assert staff.patch("/api/dash/items/1", json={"available": False}).status_code == 200
    assert staff.patch("/api/dash/variants/1", json={"price": 1}).status_code == 403
    assert staff.patch("/api/dash/settings", json={"accepting_orders": False}).status_code == 200
    assert staff.patch("/api/dash/settings", json={"delivery_fee": 0}).status_code == 422
    assert staff.post("/api/dash/categories", json={"name": "x"}).status_code == 403
    assert staff.get("/api/admin/restaurants").status_code == 403


def test_csrf_header_required():
    c = Api(app)
    c.login("dash", "dash-owner-1234")
    from fastapi.testclient import TestClient

    raw = TestClient(app, cookies=c.cookies)
    assert raw.patch("/api/dash/settings", json={"eta_minutes": 10}).status_code == 403
    assert raw.get("/api/dash/board").status_code == 200


def test_login_lockout_after_20_failures(client):
    for _ in range(20):
        assert client.post("/api/auth/login", json={"username": "dash", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "dash", "password": "dash-owner-1234"}).status_code == 429


def test_unauthenticated_dashboard_is_401(client):
    assert client.get("/api/dash/board").status_code == 401


def test_admin_lifecycle_enter_suspend_archive_delete(admin, client):
    bee = _second_restaurant(admin)
    rid = next(r["id"] for r in admin.get("/api/admin/restaurants").json()["restaurants"] if r["slug"] == "bee")

    # super admin "enters" the restaurant and uses its dashboard
    assert admin.get("/api/dash/board").status_code == 409
    assert admin.post(f"/api/admin/restaurants/{rid}/enter").json()["restaurant"]["slug"] == "bee"
    assert admin.get("/api/dash/board").status_code == 200
    assert admin.post("/api/dash/categories", json={"name": "قسم جديد"}).status_code == 200

    # suspended: bot answers "unavailable", menu empty, orders refused
    admin.patch(f"/api/admin/restaurants/{rid}", json={"status": "suspended"})
    c = Chat(client, slug="bee")
    c.text("اهلا")
    assert "غير متاحة" in c.body
    assert client.get("/api/public/r/bee").json()["available"] is False

    # delete requires archived + typed slug
    assert admin.post(f"/api/admin/restaurants/{rid}/delete", json={"confirm_slug": "bee"}).status_code == 409
    admin.patch(f"/api/admin/restaurants/{rid}", json={"status": "archived"})
    assert bee.get("/api/dash/board").status_code == 401  # archived restaurant users are locked out
    assert client.get("/api/public/r/bee").status_code == 404
    assert admin.get(f"/api/admin/restaurants/{rid}/export").status_code == 200
    assert admin.post(f"/api/admin/restaurants/{rid}/delete", json={"confirm_slug": "wrong"}).status_code == 422
    assert admin.post(f"/api/admin/restaurants/{rid}/delete", json={"confirm_slug": "bee"}).status_code == 200
    assert all(r["slug"] != "bee" for r in admin.get("/api/admin/restaurants").json()["restaurants"])


def test_clear_demo_orders(chat: Chat, admin, db):
    order_zinger_delivery(chat)
    chat.tap("confirm:yes")
    r = admin.post("/api/admin/restaurants/1/clear-demo").json()
    assert r == {"orders_deleted": 1, "conversations_deleted": 1}
    assert db.scalar(select(Order)) is None


def test_whatsapp_limits_enforced():
    with pytest.raises(LimitError):
        Buttons(body="x", buttons=[Button(f"b{i}", f"t{i}") for i in range(4)])
    with pytest.raises(LimitError):
        Button("b", "عنوان طويل جدا جدا أكتر من عشرين حرف")
    with pytest.raises(LimitError):
        List(body="x", button="b", sections=[Section("s", [Row(f"r{i}", f"t{i}") for i in range(11)])])


def test_every_engine_message_fits_whatsapp(client, db):
    """Walk every category, item, size and add-on page; every stored
    outgoing message must re-validate against WhatsApp limits."""
    menu = client.get("/api/public/r/dash").json()["menu"]
    chat = Chat(client)
    chat.text("اهلا")
    for cat in menu:
        for item in cat["items"]:
            chat.tap(f"cat:{cat['id']}")
            chat.tap(f"item:{item['id']}")
            if any(i.startswith("var:") for i in chat.ids()):
                chat.tap(next(i for i in chat.ids() if i.startswith("var:")))
            for _ in range(3):  # walk add-on pages
                more = [i for i in chat.ids() if i.startswith("addons:page:")]
                if not more:
                    break
                chat.tap(more[0])
    chat.tap("menu")
    payloads = [m.payload for m in db.scalars(select(Message).where(Message.direction == "out")).all()]
    assert len(payloads) > 100
    for p in payloads:
        validate_payload(p)


def test_excel_export_then_import_roundtrip(owner):
    data = owner.get("/api/dash/menu/export.xlsx").content
    before = owner.get("/api/dash/menu").json()
    preview = owner.post("/api/dash/menu/import", files={"file": ("m.xlsx", data)}).json()
    assert preview["error_count"] == 0 and preview["items"] == sum(len(c["items"]) for c in before["categories"])
    assert preview["addons"] == len(before["addons"])
    applied = owner.post("/api/dash/menu/import", params={"apply": True}, files={"file": ("m.xlsx", data)}).json()
    assert applied["applied"]
    after = owner.get("/api/dash/menu").json()
    assert [c["name"] for c in after["categories"]] == [c["name"] for c in before["categories"]]
    crepe = next(c for c in after["categories"] if c["name"] == "كريب")
    assert len(crepe["addons"]) == 13  # 12 shared + crust


def test_excel_with_errors_is_not_applied(owner):
    wb = Workbook()
    ws = wb.active
    ws.title = "الأصناف"
    ws.append(["القسم", "الصنف", "الحجم", "السعر", "الوصف", "متاح"])
    ws.append(["برجر", "تشيز", "فردي", "abc", "", "نعم"])
    ws.append(["برجر", "تشيز", "فردي", 99, "", "نعم"])
    ws.append(["برجر", "تشيز", "فردي", 100, "", "نعم"])
    buf = io.BytesIO()
    wb.save(buf)
    preview = owner.post("/api/dash/menu/import", files={"file": ("m.xlsx", buf.getvalue())}).json()
    assert preview["error_count"] == 2
    assert owner.post("/api/dash/menu/import", params={"apply": True}, files={"file": ("m.xlsx", buf.getvalue())}).status_code == 422
    assert len(owner.get("/api/dash/menu").json()["categories"]) == 8  # untouched


def test_hours_overnight_and_business_day():
    hours_cfg = {d: [["12:00", "02:00"]] for d in ("sat", "sun", "mon", "tue", "wed", "thu", "fri")}
    cairo = dt.timezone(dt.timedelta(hours=2))
    at_1am = dt.datetime(2026, 11, 18, 1, 0, tzinfo=cairo)
    at_3am = dt.datetime(2026, 11, 18, 3, 0, tzinfo=cairo)
    assert hours.is_open(hours_cfg, "Africa/Cairo", at_1am)
    assert not hours.is_open(hours_cfg, "Africa/Cairo", at_3am)
    assert hours.describe_next_opening(hours_cfg, "Africa/Cairo", at_3am) == "النهارده الساعة 12:00 م"
    assert hours.business_day("Africa/Cairo", "05:00", at_1am) == dt.date(2026, 11, 17)


def test_message_bodies_keep_line_breaks(chat):
    chat.text("اهلا")
    chat.tap(chat.row_id("مشروبات"))
    chat.tap(chat.row_id("ماكسي كولا"))
    chat.tap("qty:2")
    assert "🛒 سلتك:\n1) 2× ماكسي كولا" in chat.body


def test_first_run_setup_only_when_no_super_admin(client, db):
    from app.models import User

    assert client.get("/api/setup").json() == {"needs_setup": False}
    r = client.post("/api/setup", json={"username": "boss", "password": "long-enough-pw"})
    assert r.status_code == 409
    db.query(User).filter(User.role == "super_admin").delete()
    db.commit()
    assert client.get("/api/setup").json() == {"needs_setup": True}
    assert client.post("/api/setup", json={"username": "boss", "password": "short"}).status_code == 422
    r = client.post("/api/setup", json={"username": "boss", "password": "long-enough-pw"})
    assert r.status_code == 200 and r.json()["is_super"]
    assert client.get("/api/admin/restaurants").status_code == 200  # logged in
    assert client.post("/api/setup", json={"username": "boss2", "password": "long-enough-pw"}).status_code == 409


def test_session_key_from_database_when_env_unset(monkeypatch):
    from app import security
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "jwt_secret", None)
    monkeypatch.setattr(security, "_db_secret", None)
    token = security.make_session_token(1)
    assert len(security._db_secret) == 64
    assert security.read_session_token(token)["sub"] == "1"


def test_supabase_url_params_are_sanitized(monkeypatch):
    from app.config import Settings

    s = Settings(database_url="postgres://u:p@h:6543/postgres?sslmode=require&supa=base-pooler.x")
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@h:6543/postgres?sslmode=require"
