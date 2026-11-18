"""Tests run against a real Postgres database (ordering_test by default)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@localhost:54329/ordering_test")
os.environ["ENVIRONMENT"] = "test"
os.environ["CHAT_MSGS_PER_MIN"] = "1000"
os.environ["JWT_SECRET"] = "test-secret-0123456789-abcdefghijklmnop"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from seeds import dash as seed  # noqa: E402

TABLES = None


@pytest.fixture(scope="session", autouse=True)
def migrated():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_db(migrated):
    with engine.begin() as conn:
        names = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version', 'platform_secrets')")
        ).scalars().all()
        conn.execute(text(f"TRUNCATE {', '.join(names)} RESTART IDENTITY CASCADE"))
    db = SessionLocal()
    seed.seed_super_admin(db)
    seed.seed_dash(db)
    db.commit()
    db.close()
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


class Api(TestClient):
    """TestClient that sends the CSRF header on every request."""

    def request(self, method, url, **kw):
        headers = kw.pop("headers", None) or {}
        headers.setdefault("X-Requested-With", "fetch")
        return super().request(method, url, headers=headers, **kw)

    def login(self, username: str, password: str):
        r = self.post("/api/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def client():
    return Api(app)


@pytest.fixture
def owner(client):
    client.login("dash", "dash-owner-1234")
    return client


@pytest.fixture
def staff():
    c = Api(app)
    c.login("dash.staff", "dash-staff-1234")
    return c


@pytest.fixture
def admin():
    c = Api(app)
    c.login("admin", "admin-dev-1234")
    return c


class Chat:
    """Drives the web chat channel like a customer would."""

    def __init__(self, client: TestClient, slug: str = "dash", name: str = "أحمد", phone: str = "01012345678"):
        self.c = client
        self.slug = slug
        r = client.post(f"/api/chat/{slug}/start", json={"name": name, "phone": phone})
        assert r.status_code == 200, r.text
        self.sid = r.json()["session_id"]
        self.last: list[dict] = []

    def _send(self, kind: str, text: str = "", id: str | None = None) -> list[dict]:
        r = self.c.post(f"/api/chat/{self.slug}/send", json={"session_id": self.sid, "kind": kind, "text": text, "id": id})
        assert r.status_code == 200, r.text
        self.last = [m["payload"] for m in r.json()["messages"] if m["direction"] == "out"]
        return self.last

    def text(self, t: str):
        return self._send("text", t)

    def tap(self, reply_id: str, title: str = "x"):
        kind = "list" if reply_id.split(":")[0] in {"cat", "item", "addon", "addons", "zone", "line", "cats", "edit", "zones", "status", "menu", "human"} else "button"
        return self._send(kind, title, reply_id)

    def location(self, lat: float, lng: float):
        r = self.c.post(f"/api/chat/{self.slug}/send", json={"session_id": self.sid, "kind": "location", "lat": lat, "lng": lng})
        assert r.status_code == 200, r.text
        self.last = [m["payload"] for m in r.json()["messages"] if m["direction"] == "out"]
        return self.last

    def poll(self, after: int = 0) -> list[dict]:
        r = self.c.get(f"/api/chat/{self.slug}/messages", params={"session_id": self.sid, "after": after})
        return r.json()["messages"]

    # helpers on the last reply
    @property
    def body(self) -> str:
        return "\n".join(p.get("body", "") for p in self.last)

    def ids(self) -> list[str]:
        out = []
        for p in self.last:
            if p["type"] == "buttons":
                out += [b["id"] for b in p["buttons"]]
            if p["type"] == "list":
                out += [r["id"] for s in p["sections"] for r in s["rows"]]
        return out

    def row_id(self, title_contains: str) -> str:
        for p in self.last:
            if p["type"] == "list":
                for s in p["sections"]:
                    for r in s["rows"]:
                        if title_contains in r["title"]:
                            return r["id"]
            if p["type"] == "buttons":
                for b in p["buttons"]:
                    if title_contains in b["title"]:
                        return b["id"]
        raise AssertionError(f"{title_contains!r} not in {self.last}")


@pytest.fixture
def chat(client):
    return Chat(client)


def order_zinger_delivery(chat: Chat, address: str = "شارع التحرير عمارة 5 الدور التالت") -> None:
    """Zinger double + cheddar x2, delivery to zone 'شرق', typed address -> confirm screen."""
    chat.text("اهلا")
    chat.tap(chat.row_id("فراخ مقلية"))
    chat.tap(chat.row_id("زنجر"))
    chat.tap(chat.row_id("دبل"))
    chat.tap(chat.row_id("جبنة شيدر"))
    chat.tap("addons:done")
    chat.tap("qty:2")
    chat.tap("cart:checkout")
    chat.tap("ful:delivery")
    chat.tap(chat.row_id("شرق"))
    if "addr:same" in chat.ids():
        chat.tap("addr:new")
    chat.text(address)
