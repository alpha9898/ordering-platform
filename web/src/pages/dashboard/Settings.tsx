import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { ApiError, del, get, patch, post } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { money } from "../../lib/format";
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
  const [draft, setDraft] = useState<Zone>({ name: "", fee: 20, min_order: 0, active: true, sort: zones.length });
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
  return (
    <Section title="مناطق التوصيل">
      <p className="mb-3 text-xs text-muted">العميل بيختار منطقته من لستة، والرسوم والحد الأدنى بيتحسبوا لوحدهم. لو مفيش مناطق، بتتطبق الرسوم الثابتة.</p>
      <div className="space-y-2">
        {zones.map((z) => (
          <div key={z.id} className="flex flex-wrap items-center gap-2 text-sm">
            <span className={`flex-1 font-semibold ${z.active ? "" : "text-muted line-through"}`}>{z.name}</span>
            <span className="num text-muted">توصيل {money(z.fee)}</span>
            {z.min_order ? <span className="num text-muted">· حد أدنى {money(z.min_order)}</span> : null}
            <Switch checked={z.active} label={`${z.name} مفعلة`} onChange={(v) => run(() => patch(`/dash/zones/${z.id}`, { ...z, active: v }), v ? "المنطقة اتفعلت" : "المنطقة اتقفلت")} />
            <button onClick={() => confirm(`مسح ${z.name}؟`) && run(() => del(`/dash/zones/${z.id}`), "اتمسحت")} className="p-1 text-muted hover:text-danger" aria-label="مسح">
              <Trash2 className="size-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-line pt-4">
        <Field label="منطقة جديدة">
          <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="مثلًا: مدينة نصر" />
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
              await post("/dash/zones", { ...draft, sort: zones.length });
              setDraft({ name: "", fee: 20, min_order: 0, active: true, sort: zones.length + 1 });
            }, "المنطقة اتضافت")
          }
        >
          <Plus className="size-4" /> إضافة
        </Button>
      </div>
    </Section>
  );
}
