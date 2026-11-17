import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Download, LogIn, LogOut, Plus, Settings2, Store, Trash2, UserPlus } from "lucide-react";
import { ApiError, get, patch, post } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { money } from "../../lib/format";
import { Badge, Button, Card, Empty, Field, Input, Modal, Spinner, Switch, inputCls, useToast } from "../../components/ui";
import { ShareLinks } from "../../components/ShareLinks";

type R = {
  id: number;
  slug: string;
  name: string;
  status: "trial" | "active" | "suspended" | "archived";
  demo_mode: boolean;
  accepting_orders: boolean;
  open_now: boolean;
  stats: { orders_today: number; orders_30d: number; revenue_30d: number; demo_orders: number };
  users?: { id: number; username: string; display_name: string | null; role: string; active: boolean }[];
};

const STATUS: Record<R["status"], { label: string; tone: "info" | "ok" | "warn" | "muted" }> = {
  trial: { label: "تجربة", tone: "info" },
  active: { label: "شغال", tone: "ok" },
  suspended: { label: "موقوف", tone: "warn" },
  archived: { label: "مؤرشف", tone: "muted" },
};

export default function Admin() {
  const { me, setMe, logout } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const [list, setList] = useState<R[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const load = useCallback(() => get("/admin/restaurants").then((r) => setList(r.restaurants)), []);
  useEffect(() => {
    load();
    document.title = "لوحة الإدارة";
  }, [load]);

  const enter = async (r: R) => {
    try {
      setMe(await post(`/admin/restaurants/${r.id}/enter`));
      nav("/dashboard");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    }
  };

  const visible = list?.filter((r) => showArchived || r.status !== "archived") ?? [];
  const totals = list?.reduce((t, r) => ({ today: t.today + r.stats.orders_today, month: t.month + r.stats.orders_30d }), { today: 0, month: 0 });

  return (
    <div className="min-h-dvh">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div>
            <div className="font-bold">لوحة الإدارة</div>
            <div className="text-xs text-muted">{me?.user.username}</div>
          </div>
          <Button
            size="sm"
            tone="ghost"
            className="ms-auto"
            onClick={async () => {
              await logout();
              nav("/login");
            }}
          >
            <LogOut className="size-4" /> خروج
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl space-y-5 p-4">
        <div className="grid grid-cols-3 gap-3">
          <Stat label="مطاعم" value={list?.filter((r) => r.status !== "archived").length ?? "–"} />
          <Stat label="طلبات النهارده" value={totals?.today ?? "–"} />
          <Stat label="طلبات آخر 30 يوم" value={totals?.month ?? "–"} />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-bold">المطاعم</h1>
          <label className="flex items-center gap-2 text-sm text-muted">
            <Switch checked={showArchived} onChange={setShowArchived} /> عرض المؤرشف
          </label>
          <Button tone="primary" className="ms-auto" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> مطعم جديد
          </Button>
        </div>

        {!list ? (
          <div className="grid h-40 place-items-center text-muted">
            <Spinner />
          </div>
        ) : !visible.length ? (
          <Card>
            <Empty icon={<Store className="size-8" />} title="مفيش مطاعم لسه" />
          </Card>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {visible.map((r) => (
              <Card key={r.id} className="p-4">
                <div className="mb-3 flex items-start gap-3">
                  <div className="grid size-11 place-items-center rounded-xl bg-primary-soft text-lg font-bold text-primary">{r.name.slice(0, 1)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold">{r.name}</span>
                      <Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge>
                      {r.demo_mode ? <Badge>ديمو</Badge> : null}
                    </div>
                    <div className="text-xs text-muted" dir="ltr">
                      /{r.slug}
                    </div>
                  </div>
                  <Badge tone={r.accepting_orders && r.open_now ? "ok" : "muted"}>{r.accepting_orders && r.open_now ? "مفتوح" : "مقفول"}</Badge>
                </div>
                <div className="mb-3 grid grid-cols-3 gap-2 text-center text-sm">
                  <MiniStat label="النهارده" value={r.stats.orders_today} />
                  <MiniStat label="30 يوم" value={r.stats.orders_30d} />
                  <MiniStat label="مبيعات 30 يوم" value={money(r.stats.revenue_30d)} />
                </div>
                <div className="flex gap-2">
                  <Button tone="primary" className="flex-1" onClick={() => enter(r)} disabled={r.status === "archived"}>
                    <LogIn className="size-4" /> ادخل الداشبورد
                  </Button>
                  <Button onClick={() => setOpenId(r.id)}>
                    <Settings2 className="size-4" /> إدارة
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </main>
      {creating ? <CreateModal restaurants={list ?? []} onClose={() => setCreating(false)} onCreated={load} /> : null}
      {openId ? <ManageModal id={openId} onClose={() => setOpenId(null)} onChanged={load} /> : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <Card className="p-4">
      <div className="num text-2xl font-bold">{value}</div>
      <div className="text-sm text-muted">{label}</div>
    </Card>
  );
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl bg-surface-2 p-2">
      <div className="num font-bold">{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}

function CreateModal({ restaurants, onClose, onCreated }: { restaurants: R[]; onClose: () => void; onCreated: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ name: "", slug: "", owner_username: "", owner_password: "", demo_mode: true, copy_menu_from: "" as number | "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await post("/admin/restaurants", { ...f, copy_menu_from: f.copy_menu_from || null });
      toast(`اتضاف ${f.name} ✅`);
      onCreated();
      onClose();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "حصلت مشكلة");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open onClose={onClose} title="مطعم جديد">
      <form onSubmit={submit} className="space-y-4">
        <Field label="اسم المطعم">
          <Input required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </Field>
        <Field label="الرابط (slug)" hint={`الشات هيبقى على /r/${f.slug || "slug"}/chat — حروف إنجليزي صغيرة وأرقام و -`}>
          <Input required dir="ltr" pattern="[a-z0-9-]{2,40}" value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value.toLowerCase() })} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="يوزر صاحب المطعم">
            <Input required dir="ltr" value={f.owner_username} onChange={(e) => setF({ ...f, owner_username: e.target.value.toLowerCase() })} autoComplete="off" />
          </Field>
          <Field label="كلمة السر" hint="8 حروف على الأقل">
            <Input required dir="ltr" type="password" minLength={8} value={f.owner_password} onChange={(e) => setF({ ...f, owner_password: e.target.value })} autoComplete="new-password" />
          </Field>
        </div>
        <Field label="ابدأ بمنيو منسوخ من (اختياري)" hint="مفيد للديمو: تقدر تعدله أو ترفع Excel بعدين">
          <select className={inputCls} value={f.copy_menu_from} onChange={(e) => setF({ ...f, copy_menu_from: e.target.value ? Number(e.target.value) : "" })}>
            <option value="">منيو فاضي</option>
            {restaurants.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={f.demo_mode} onChange={(v) => setF({ ...f, demo_mode: v })} /> وضع الديمو (الطلبات تتعلّم ديمو وتقدر تمسحها)
        </label>
        {err ? <p className="text-sm text-danger">{err}</p> : null}
        <Button tone="primary" size="lg" className="w-full" loading={busy}>
          إضافة المطعم
        </Button>
      </form>
    </Modal>
  );
}

function ManageModal({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const [r, setR] = useState<R | null>(null);
  const [newUser, setNewUser] = useState({ username: "", password: "", role: "staff", display_name: "" });
  const [confirmSlug, setConfirmSlug] = useState("");
  const load = useCallback(() => get(`/admin/restaurants/${id}`).then(setR), [id]);
  useEffect(() => {
    load();
  }, [load]);

  const run = async (fn: () => Promise<unknown>, msg: string, close = false) => {
    try {
      await fn();
      toast(msg);
      onChanged();
      if (close) onClose();
      else load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    }
  };

  if (!r)
    return (
      <Modal open onClose={onClose} title="…">
        <div className="grid h-40 place-items-center text-muted">
          <Spinner />
        </div>
      </Modal>
    );

  return (
    <Modal open onClose={onClose} title={r.name} wide>
      <div className="space-y-6">
        <section>
          <h3 className="mb-3 font-bold">الحالة</h3>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(STATUS) as R["status"][]).map((s) => (
              <button
                key={s}
                onClick={() => s !== r.status && run(() => patch(`/admin/restaurants/${id}`, { status: s }), `الحالة: ${STATUS[s].label}`)}
                className={`rounded-full border px-4 py-1.5 text-sm font-semibold ${r.status === s ? "border-primary bg-primary-soft text-primary" : "border-line"}`}
              >
                {STATUS[s].label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted">موقوف: البوت يرد "الخدمة غير متاحة" والداشبورد شغالة. مؤرشف: كل حاجة متقفلة بس البيانات محفوظة.</p>
          <label className="mt-3 flex items-center gap-2 text-sm">
            <Switch checked={r.demo_mode} onChange={(v) => run(() => patch(`/admin/restaurants/${id}`, { demo_mode: v }), v ? "وضع الديمو اتفعل" : "وضع الديمو اتقفل")} />
            وضع الديمو
          </label>
        </section>

        {r.status !== "archived" ? (
          <section>
            <h3 className="mb-3 font-bold">روابط الديمو</h3>
            <ShareLinks slug={r.slug} />
          </section>
        ) : null}

        <section>
          <h3 className="mb-3 font-bold">اليوزرز</h3>
          <ul className="mb-3 divide-y divide-line rounded-xl border border-line">
            {r.users?.map((u) => (
              <li key={u.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                <span className="font-semibold" dir="ltr">
                  {u.username}
                </span>
                <Badge tone={u.role === "owner" ? "primary" : "muted"}>{u.role === "owner" ? "صاحب المطعم" : "موظف"}</Badge>
                <span className="text-muted">{u.display_name}</span>
                <span className="ms-auto flex items-center gap-2">
                  <Button
                    size="sm"
                    tone="ghost"
                    onClick={() => {
                      const pw = prompt(`كلمة سر جديدة لـ ${u.username} (8 حروف على الأقل)`);
                      if (pw) run(() => patch(`/admin/users/${u.id}`, { password: pw }), "كلمة السر اتغيرت");
                    }}
                  >
                    تغيير كلمة السر
                  </Button>
                  <Switch checked={u.active} label="مفعل" onChange={(v) => run(() => patch(`/admin/users/${u.id}`, { active: v }), v ? "اتفعل" : "اتوقف")} />
                </span>
              </li>
            ))}
          </ul>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(() => post(`/admin/restaurants/${id}/users`, newUser), "اليوزر اتضاف").then(() => setNewUser({ username: "", password: "", role: "staff", display_name: "" }));
            }}
            className="flex flex-wrap items-end gap-2"
          >
            <Field label="يوزر">
              <Input required dir="ltr" value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value.toLowerCase() })} className="w-36" autoComplete="off" />
            </Field>
            <Field label="الاسم">
              <Input value={newUser.display_name} onChange={(e) => setNewUser({ ...newUser, display_name: e.target.value })} className="w-32" />
            </Field>
            <Field label="كلمة السر">
              <Input required dir="ltr" type="password" minLength={8} value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} className="w-36" autoComplete="new-password" />
            </Field>
            <Field label="الدور">
              <select className={`${inputCls} w-28`} value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
                <option value="staff">موظف</option>
                <option value="owner">صاحب المطعم</option>
              </select>
            </Field>
            <Button>
              <UserPlus className="size-4" /> إضافة
            </Button>
          </form>
        </section>

        <section className="space-y-3">
          <h3 className="font-bold">البيانات</h3>
          <div className="flex flex-wrap gap-2">
            <Button
              tone="neutral"
              disabled={!r.stats.demo_orders}
              onClick={() => confirm(`مسح ${r.stats.demo_orders} طلب ديمو ومحادثات الشات؟`) && run(() => post(`/admin/restaurants/${id}/clear-demo`), "طلبات الديمو اتمسحت")}
            >
              <Trash2 className="size-4" /> مسح طلبات الديمو ({r.stats.demo_orders})
            </Button>
            <a href={`/api/admin/restaurants/${id}/export`}>
              <Button tone="ghost">
                <Download className="size-4" /> تصدير كل البيانات (JSON)
              </Button>
            </a>
          </div>
          {r.status === "archived" ? (
            <div className="rounded-xl border border-danger p-4">
              <div className="mb-1 font-bold text-danger">مسح نهائي</div>
              <p className="mb-3 text-sm text-muted">كل حاجة هتتمسح ومش هترجع: المنيو، الطلبات، العملاء، اليوزرز. صدّر البيانات الأول. اكتب <b dir="ltr">{r.slug}</b> للتأكيد.</p>
              <div className="flex gap-2">
                <Input dir="ltr" value={confirmSlug} onChange={(e) => setConfirmSlug(e.target.value)} className="max-w-48" />
                <Button tone="danger" disabled={confirmSlug !== r.slug} onClick={() => run(() => post(`/admin/restaurants/${id}/delete`, { confirm_slug: confirmSlug }), "المطعم اتمسح نهائيًا", true)}>
                  مسح نهائي
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted">المسح النهائي متاح بس بعد الأرشفة.</p>
          )}
        </section>
      </div>
    </Modal>
  );
}
