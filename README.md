# Ordering platform (web demo)

Multi-restaurant ordering platform. Customers order through a **WhatsApp-style chat** or a **web menu page**; orders land on a live **restaurant dashboard**; we manage every restaurant from a **super-admin panel**. The chat engine already speaks WhatsApp's message types and limits, so connecting the WhatsApp Cloud API later is an adapter (`backend/app/channels/whatsapp.py`), not a rewrite.

First restaurant: **Dash** (slug `dash`). Its menu is currently a **sample** built from examples in the original project brief; replace it with the real menu through the dashboard editor or the Excel import.

## Live links

Production: **https://ordering-demo-three.vercel.app**

### For customers (share these with the restaurant's customers / the client during a demo)

| Link | What it is | Who uses it |
|---|---|---|
| https://ordering-demo-three.vercel.app/r/dash/chat | **WhatsApp simulator.** Looks and behaves like the WhatsApp bot: lists, buttons, cart, checkout. Asks for a name and phone once, then the customer orders by tapping. Order updates from the restaurant appear in the chat. | Customers, and the client during a sales demo (open it on a phone or scan the QR code). |
| https://ordering-demo-three.vercel.app/r/dash | **Web menu page.** Browse categories, pick single/double and add-ons, cart, delivery or pickup, checkout. | Customers who prefer a normal ordering page (can be linked from Instagram/Facebook or a QR code on the table). |
| `https://ordering-demo-three.vercel.app/o/<token>` | **Order tracking page.** Live status (sent → accepted → preparing → out for delivery / ready → delivered). The link is generated automatically after a web-menu order. | The customer who placed that order. |

QR codes for the chat and menu links are in the dashboard (**الإعدادات** tab) and in the admin panel (**إدارة** on each restaurant).

### For the restaurant

| Link | What it is | Who uses it |
|---|---|---|
| https://ordering-demo-three.vercel.app/login | Login page for everyone with an account. | Restaurant owners, staff, and us. |
| https://ordering-demo-three.vercel.app/dashboard | **Restaurant dashboard.** Live board (new / in the kitchen / on the way-ready) with a beep for new orders, accept / reject / status buttons that message the customer, order history, menu (sold-out switches; full editing + Excel for owners), customer chats with a reply box, and settings (hours, delivery zones, fees, payment). | **Owner** (`dash`): everything incl. prices, menu and settings. **Staff** (`dash.staff`): orders, sold-out switches, open/closed switch, ETA. Best on the counter PC / second screen; press **تفعيل الصوت** once so the beep works. |

### For us (platform team)

| Link | What it is | Who uses it |
|---|---|---|
| https://ordering-demo-three.vercel.app/admin | **Super-admin panel.** Add restaurants (optionally copying another menu), trial / active / suspended / archived, add owner and staff accounts, reset passwords, "enter" any restaurant's dashboard, clear demo orders, export all data, permanent delete (archived only). | Platform owners only (`admin`). |
| https://ordering-demo-three.vercel.app/api/health | Health check, returns `{"ok":true}`. | Developers / uptime checks. |
| https://vercel.com/ammars-projects-79cd5d73/ordering-demo | Vercel project: deployments, logs, environment variables. | Developers. |
| https://supabase.com/dashboard/project/xzudsfgwwcqahwfulifr | Supabase project `ordering-demo`: the Postgres database. | Developers. |

### Accounts on production

| Username | Role | Can do |
|---|---|---|
| `admin` | super admin | Everything, across all restaurants. |
| `dash` | Dash owner | Dash's dashboard, menu, prices, settings, zones. |
| `dash.staff` | Dash staff | Day-to-day orders and availability. |

Passwords are **not** stored in this repo or anywhere else in plain text; they were typed by their owners. Reset a forgotten password from `/admin` → **إدارة** → **تغيير كلمة السر**.

### Demo script (5 minutes)

1. On a laptop: log in as `dash`, open the dashboard, press **تفعيل الصوت**.
2. On the client's phone: open the chat link (or scan the QR).
3. Client orders → the order appears on the dashboard with a beep → press **قبول** → the acceptance message appears in the client's chat → **ابدأ التحضير** → **خرج للتوصيل** / **جاهز للاستلام** → **تم التسليم**.
4. Show the menu tab: mark an item as sold out; it disappears from the bot immediately.
5. Afterwards: `/admin` → Dash → **مسح طلبات الديمو** to clear test orders.

Before a meeting, open the site once if it has been idle for a week (Supabase's free tier pauses idle projects).

## How it works

```
backend/app/
  engine/        state machine, WhatsApp-limited message types, Arabic texts
  channels/      web (now) and whatsapp (stub) delivery adapters
  services/      pricing, orders, menu, settings, hours, notify, excel import, restaurants
  routers/       auth, setup, public, chat, dashboard, admin
backend/alembic/ migrations          backend/seeds/dash.py  Dash sample menu (+ local dev accounts)
backend/tests/   pytest against real Postgres
web/             React + Vite + Tailwind (RTL Arabic)
api/index.py     Vercel serverless entry          vercel.json  Vercel config
```

- **Multi-tenant:** every tenant table carries `restaurant_id`; every dashboard query is scoped to the caller's restaurant (other restaurants' ids return 404). Removing a restaurant means suspend / archive; permanent delete needs archive + typing the slug.
- **Prices are server-side only:** carts hold ids and quantities; totals are recomputed from the DB at confirmation. Sold-out items are removed with an explanation.
- **WhatsApp-ready:** every bot message is validated against WhatsApp limits (3 buttons, 10 list rows, title lengths) before it is stored.
- **Serverless-friendly:** conversation state and the per-customer lock live in Postgres (`conversations` row + `SELECT … FOR UPDATE`), no worker, and the dashboard / chat poll every 2–3 s instead of SSE.

## Local development

Requires Python 3.12+, Node 20+, PostgreSQL 16+.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
npm --prefix web install
cp backend/.env.example backend/.env          # local-only values + dev seed accounts
```

Postgres (this repo uses a project-local cluster on port 54329):

```bash
LC_ALL=en_US.UTF-8 pg_ctl -D .pgdata -o "-p 54329 -k /tmp" -l .pgdata/server.log start
createdb -h localhost -p 54329 -U postgres ordering
createdb -h localhost -p 54329 -U postgres ordering_test
```

Schema + seed, then run the API and the web app (two terminals):

```bash
cd backend && ../.venv/bin/alembic upgrade head && ../.venv/bin/python -m seeds.dash && cd ..
.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000 --reload
npm --prefix web run dev                      # http://localhost:5173 (proxies /api to :8000)
```

Local development login accounts are listed in `backend/.env.example` (they exist only in your local database).

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

Runs against the `ordering_test` database (dropped and migrated on each run). Covers full chat orders, delivery zones and minimums, closed hours, sold-out-before-confirm, price tampering, lifecycle 409s, customer notifications, human handoff, tenant isolation, roles, CSRF, login lockout, admin lifecycle, first-run setup, Excel import/export, and a contract test that every bot message fits WhatsApp's limits.

## Deploy (Vercel + Supabase)

The Vercel project is connected to this GitHub repo:

- **Push to `main`** → automatic production deploy to https://ordering-demo-three.vercel.app
- **Push to any other branch / open a PR** → automatic preview build with its own URL. Previews have **no database** (the Supabase connection is set for Production only), so they only show that the build works; use local development to test features.
- Manual deploy from the repo root, if ever needed: `vercel deploy --prod --scope ammars-projects-79cd5d73`

Schema changes: add an Alembic migration, then apply it to Supabase (`cd backend && ../.venv/bin/alembic upgrade <current>:head --sql` gives the SQL).

Current setup: Supabase project `ordering-demo` (eu-central-1) + Vercel project `ordering-demo` (functions in `fra1`). No secret is ever typed or copied by hand:

- **Session signing key** is generated inside the database by a migration (`platform_secrets`); `JWT_SECRET` is optional.
- **Database URL** comes from the Supabase → Vercel integration (`POSTGRES_URL`, transaction pooler). Unknown query params are stripped and pooling is disabled automatically on Vercel.
- **First admin account** is created on the live site: `/login` shows a one-time setup form while no super admin exists. Restaurant owners/staff are then added from `/admin`.
- **RLS** is enabled on every table, so Supabase's public REST API cannot read app data; the app connects as the table owner.

Fresh environment from scratch:

1. Create a Supabase project and apply the schema (`alembic upgrade head --sql`, or `alembic upgrade head` with a direct `DATABASE_URL`).
2. Seed restaurants/menus without accounts: `SEED_SKIP_USERS=1 ENVIRONMENT=production python -m seeds.dash` (or load menus with the Excel import later).
3. Create and link the Vercel project (`vercel project add …`, `vercel link`), set `ENVIRONMENT=production`, then in Supabase → Integrations → Vercel connect the project so `POSTGRES_URL` is synced.
4. `vercel deploy --prod`, open `/login` and create the admin account right away.
5. Smoke test: chat on a phone, dashboard on a laptop, place an order, accept it, watch the chat update.

Notes: Vercel Hobby is for non-commercial use — move to Pro (or run the same app on a VPS with uvicorn) once a restaurant pays. Supabase free projects pause after a week idle.

## Next (after the demo)

WhatsApp channel (map `phone_number_id` → restaurant, verify signatures, dedupe on `messages.wa_message_id`, templates outside the 24 h window), invite links so restaurant owners set their own passwords, wallet screenshot flow, kitchen ticket printing, analytics, and the rest of the original roadmap.
