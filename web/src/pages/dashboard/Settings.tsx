import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import { ApiError, del, get, patch, post } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { displayPhone } from "../../lib/format";
import type { Driver } from "../../lib/types";
import { Badge, Button, Card, Field, Input, Spinner, Switch, useToast } from "../../components/ui";
import { ShareLinks } from "../../components/ShareLinks";

const DAYS: [string, string][] = [
  ["sat", "السبت"],
  ["sun", "الأحد"],
  ["mon", "الاتنين"],
  ["tue", "التلات"],
  ["wed", "الأربع"],
  ["thu", "الخميس"],
  ["fri", "الجمعة"],
];

type S = {
  accepting_orders: boolean;
  working_hours: Record<string, [string, string][]>;
  eta_minutes: number;
  delivery_enabled: boolean;
  pickup_enabled: boolean;
  delivery_fee: number;
  min_order: number;
  payment_methods: string[];
  wallet_number: string;
  contact_phone: string;
  drivers: Driver[];
};
type Zone = { id?: number; name: string; fee: number; min_order: number; active: boolean; sort: number };

export default function SettingsPage() {
  const { me } = useAuth();
  const toast = useToast();
  const [s, setS] = useState<S | null>(null);
  const [openNow, setOpenNow] = useState(false);
  const [zones, setZones] = useState<Zone[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get("/dash/settings").then((r) => {
      setS(r.settings);
      setOpenNow(r.open_now);
    });
    get("/dash/zones").then((r) => setZones(r.zones));
  }, []);

  if (!s || !me?.restaurant)
    return (
      <div className="grid h-40 place-items-center text-muted">
        <Spinner />
      </div>
    );

  const save = async () => {
    setBusy(true);
    try {
      const { accepting_orders: _a, ...rest } = s;
      const r = await patch("/dash/settings", rest);
      setS(r.settings);
      setOpenNow(r.open_now);
      toast("الإعدادات اتحفظت ✅");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    } finally {
      setBusy(false);
    }
  };

  const setDay = (d: string, ranges: [string, string][]) => setS({ ...s, working_hours: { ...s.working_hours, [d]: ranges } });
  const togglePay = (m: string, on: boolean) => {
    const next = on ? [...new Set([...s.payment_methods, m])] : s.payment_methods.filter((x) => x !== m);
    if (next.length) setS({ ...s, payment_methods: next });
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Section title="روابط الديمو والطلب">
        <ShareLinks slug={me.restaurant.slug} />
      </Section>

      <Section title="الطلبات والتوصيل">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="الوقت المتوقع (دقيقة)">
            <Input type="number" min={1} max={300} value={s.eta_minutes} onChange={(e) => setS({ ...s, eta_minutes: Number(e.target.value) })} className="num" />
          </Field>
          <Field label="الحد الأدنى للتوصيل" hint="المناطق اللي ليها حد أدنى خاص بيتطبق عليها بتاعها">
            <Input type="number" min={0} value={s.min_order} onChange={(e) => setS({ ...s, min_order: Number(e.target.value) })} className="num" />
          </Field>
          <Field label="رسوم التوصيل الثابتة" hint={zones.some((z) => z.active) ? "مش مستخدمة: فيه مناطق توصيل مفعلة" : "بتتطبق لو مفيش مناطق"}>
            <Input type="number" min={0} value={s.delivery_fee} onChange={(e) => setS({ ...s, delivery_fee: Number(e.target.value) })} className="num" />
          </Field>
          <Field label="رقم تليفون المطعم">
            <Input dir="ltr" value={s.contact_phone} onChange={(e) => setS({ ...s, contact_phone: e.target.value })} />
          </Field>
        </div>
        <div className="mt-4 flex flex-wrap gap-6">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={s.delivery_enabled} onChange={(v) => setS({ ...s, delivery_enabled: v })} /> توصيل
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={s.pickup_enabled} onChange={(v) => setS({ ...s, pickup_enabled: v })} /> استلام من المطعم
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={s.payment_methods.includes("cod")} onChange={(v) => togglePay("cod", v)} /> كاش
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={s.payment_methods.includes("wallet")} onChange={(v) => togglePay("wallet", v)} /> محفظة / إنستاباي
          </label>
        </div>
        {s.payment_methods.includes("wallet") ? (
          <div className="mt-4 max-w-xs">
            <Field label="رقم المحفظة">
              <Input dir="ltr" value={s.wallet_number} onChange={(e) => setS({ ...s, wallet_number: e.target.value })} />
            </Field>
          </div>
        ) : null}
      </Section>

      <Section title="مواعيد العمل" extra={<Badge tone={openNow ? "ok" : "danger"}>{openNow ? "مفتوح دلوقتي" : "مقفول دلوقتي"}</Badge>}>
        <p className="mb-3 text-xs text-muted">لو المطعم بيقفل بعد نص الليل اكتب مثلًا من 12:00 لـ 02:00. البوت بيرد على العميل بميعاد الفتح الجاي لو مقفول.</p>
        <div className="space-y-2">
          {DAYS.map(([d, label]) => {
            const ranges = s.working_hours[d] ?? [];
            return (
              <div key={d} className="flex flex-wrap items-center gap-2 border-b border-line pb-2 last:border-0">
                <span className="w-16 text-sm font-semibold">{label}</span>
                {!ranges.length ? <Badge tone="danger">مقفول</Badge> : null}
                {ranges.map((r, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <Input type="time" value={r[0]} onChange={(e) => setDay(d, ranges.map((x, k) => (k === i ? [e.target.value, x[1]] : x)))} className="num h-9 w-28" />
                    <span className="text-muted">لـ</span>
                    <Input
                      type="time"
                      value={r[1] === "24:00" ? "23:59" : r[1]}
                      onChange={(e) => setDay(d, ranges.map((x, k) => (k === i ? [x[0], e.target.value] : x)))}
                      className="num h-9 w-28"
                    />
                    <button onClick={() => setDay(d, ranges.filter((_, k) => k !== i))} className="p-1 text-muted hover:text-danger" aria-label="شيل الفترة">
                      <Trash2 className="size-4" />
                    </button>
                  </span>
                ))}
                <span className="ms-auto flex gap-1">
                  <Button size="sm" tone="ghost" onClick={() => setDay(d, [...ranges, ["12:00", "02:00"]])}>
                    <Plus className="size-3.5" /> فترة
                  </Button>
                  <Button size="sm" tone="ghost" onClick={() => setDay(d, [["00:00", "24:00"]])}>
                    24 ساعة
                  </Button>
                </span>
              </div>
            );
          })}
        </div>
      </Section>

      <div className="sticky bottom-4 z-10 flex justify-end">
        <Button tone="primary" size="lg" loading={busy} onClick={save} className="shadow-lg">
          حفظ الإعدادات
        </Button>
      </div>

      <Zones zones={zones} setZones={setZones} />
      <Drivers key={JSON.stringify(s.drivers)} drivers={s.drivers ?? []} onSaved={setS} />
    </div>
  );
}

function Section({ title, extra, children }: { title: string; extra?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="font-bold">{title}</h2>
        {extra}
      </div>
      {children}
    </Card>
  );
}

function Zones({ zones, setZones }: { zones: Zone[]; setZones: (z: Zone[]) => void }) {
  const toast = useToast();
  const [draft, setDraft] = useState({ name: "", fee: 20, min_order: 0 });
  const reload = async () => setZones((await get("/dash/zones")).zones);
  const run = async (fn: () => Promise<unknown>, msg: string) => {
    try {
      await fn();
      await reload();
      toast(msg);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    }
  };
  const move = (i: number, dir: -1 | 1) =>
    run(async () => {
      const order = [...zones];
      [order[i], order[i + dir]] = [order[i + dir], order[i]];
      await Promise.all(order.map((z, k) => (z.sort !== k ? patch(`/dash/zones/${z.id}`, { ...z, sort: k }) : null)));
    }, "الترتيب اتحفظ");

  return (
    <Section title="مناطق التوصيل">
      <p className="mb-3 text-xs text-muted">
        العميل بيختار منطقته من لستة، والرسوم والحد الأدنى بيتحسبوا لوحدهم. عدّل الاسم أو السعر واضغط حفظ؛ التغيير بيظهر في البوت وصفحة المنيو فورًا. لو مفيش مناطق مفعلة، بتتطبق رسوم
        التوصيل الثابتة.
      </p>
      {zones.length ? (
        <div className="mb-1 hidden grid-cols-[1fr_6rem_6rem_auto] gap-2 px-1 text-xs font-semibold text-muted sm:grid">
          <span>المنطقة</span>
          <span>الرسوم</span>
          <span>حد أدنى</span>
          <span />
        </div>
      ) : null}
      <div className="space-y-2">
        {zones.map((z, i) => (
          <ZoneRow
            key={z.id}
            zone={z}
            first={i === 0}
            last={i === zones.length - 1}
            onSave={(f) => run(() => patch(`/dash/zones/${z.id}`, { ...z, ...f }), "المنطقة اتحفظت ✅")}
            onToggle={(v) => run(() => patch(`/dash/zones/${z.id}`, { ...z, active: v }), v ? "المنطقة اتفعلت" : "المنطقة اتقفلت")}
            onDelete={() => confirm(`مسح منطقة ${z.name}؟ الطلبات القديمة هتفضل محفوظة باسم المنطقة.`) && run(() => del(`/dash/zones/${z.id}`), "اتمسحت")}
            onMove={(dir) => move(i, dir)}
          />
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-line pt-4">
        <Field label="منطقة جديدة">
          <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="مثلًا: شرق" />
        </Field>
        <Field label="الرسوم">
          <Input type="number" min={0} value={draft.fee} onChange={(e) => setDraft({ ...draft, fee: Number(e.target.value) })} className="num w-24" />
        </Field>
        <Field label="حد أدنى">
          <Input type="number" min={0} value={draft.min_order} onChange={(e) => setDraft({ ...draft, min_order: Number(e.target.value) })} className="num w-24" />
        </Field>
        <Button
          disabled={!draft.name.trim()}
          onClick={() =>
            run(async () => {
              await post("/dash/zones", { ...draft, active: true, sort: zones.length });
              setDraft({ name: "", fee: 20, min_order: 0 });
            }, "المنطقة اتضافت")
          }
        >
          <Plus className="size-4" /> إضافة
        </Button>
      </div>
    </Section>
  );
}

function ZoneRow({
  zone,
  first,
  last,
  onSave,
  onToggle,
  onDelete,
  onMove,
}: {
  zone: Zone;
  first: boolean;
  last: boolean;
  onSave: (f: { name: string; fee: number; min_order: number }) => void;
  onToggle: (v: boolean) => void;
  onDelete: () => void;
  onMove: (dir: -1 | 1) => void;
}) {
  const [f, setF] = useState({ name: zone.name, fee: zone.fee, min_order: zone.min_order });
  useEffect(() => setF({ name: zone.name, fee: zone.fee, min_order: zone.min_order }), [zone.name, zone.fee, zone.min_order]);
  const dirty = f.name.trim() !== zone.name || f.fee !== zone.fee || f.min_order !== zone.min_order;
  return (
    <div className={`grid grid-cols-2 items-center gap-2 rounded-xl border border-line p-2 sm:grid-cols-[1fr_6rem_6rem_auto] sm:border-0 sm:p-1 ${zone.active ? "" : "opacity-60"}`}>
      <Input aria-label="اسم المنطقة" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} className="col-span-2 sm:col-span-1" />
      <label className="block">
        <span className="mb-0.5 block text-[11px] text-muted sm:hidden">الرسوم</span>
        <Input aria-label="الرسوم" type="number" min={0} value={f.fee} onChange={(e) => setF({ ...f, fee: Number(e.target.value) })} className="num" />
      </label>
      <label className="block">
        <span className="mb-0.5 block text-[11px] text-muted sm:hidden">حد أدنى</span>
        <Input aria-label="الحد الأدنى" type="number" min={0} value={f.min_order} onChange={(e) => setF({ ...f, min_order: Number(e.target.value) })} className="num" />
      </label>
      <div className="col-span-2 flex items-center gap-1 sm:col-span-1">
        <Button size="sm" tone={dirty ? "primary" : "ghost"} disabled={!dirty || !f.name.trim()} onClick={() => onSave({ ...f, name: f.name.trim() })}>
          <Save className="size-4" /> حفظ
        </Button>
        <Switch checked={zone.active} label={`${zone.name} مفعلة`} onChange={onToggle} />
        <button onClick={() => onMove(-1)} disabled={first} className="p-1 text-muted hover:text-fg disabled:opacity-30" aria-label="لفوق">
          <ArrowUp className="size-4" />
        </button>
        <button onClick={() => onMove(1)} disabled={last} className="p-1 text-muted hover:text-fg disabled:opacity-30" aria-label="لتحت">
          <ArrowDown className="size-4" />
        </button>
        <button onClick={onDelete} className="p-1 text-muted hover:text-danger" aria-label="مسح">
          <Trash2 className="size-4" />
        </button>
      </div>
    </div>
  );
}

function Drivers({ drivers, onSaved }: { drivers: Driver[]; onSaved: (settings: S) => void }) {
  const toast = useToast();
  const [list, setList] = useState(drivers.map((d) => ({ name: d.name, phone: displayPhone(d.phone) })));
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const r = await patch("/dash/settings", { drivers: list.filter((d) => d.name.trim() || d.phone.trim()) });
      onSaved(r.settings);
      setList(r.settings.drivers.map((d: Driver) => ({ name: d.name, phone: displayPhone(d.phone) })));
      toast("الدليفري اتحفظوا ✅");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Section title="الدليفري">
      <p className="mb-3 text-xs text-muted">
        سجّل أسامي وأرقام الدليفري. على كل طلب توصيل هيظهر زرار باسم كل واحد: بيفتح شات واتساب معاه والطلب والعنوان ولينك الموقع جاهزين، وبيسجل الطلب عليه.
      </p>
      <div className="space-y-2">
        {list.map((d, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <Input aria-label="اسم الدليفري" placeholder="الاسم" value={d.name} onChange={(e) => setList(list.map((x, k) => (k === i ? { ...x, name: e.target.value } : x)))} className="max-w-48" />
            <Input
              aria-label="موبايل الدليفري"
              placeholder="01xxxxxxxxx"
              dir="ltr"
              inputMode="tel"
              value={d.phone}
              onChange={(e) => setList(list.map((x, k) => (k === i ? { ...x, phone: e.target.value } : x)))}
              className="num max-w-44 text-right"
            />
            <button onClick={() => setList(list.filter((_, k) => k !== i))} className="p-1 text-muted hover:text-danger" aria-label="شيل الدليفري">
              <Trash2 className="size-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <Button size="sm" tone="ghost" onClick={() => setList([...list, { name: "", phone: "" }])} disabled={list.length >= 20}>
          <Plus className="size-4" /> دليفري جديد
        </Button>
        <Button size="sm" tone="primary" loading={busy} onClick={save}>
          <Save className="size-4" /> حفظ الدليفري
        </Button>
      </div>
    </Section>
  );
}
