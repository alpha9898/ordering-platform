import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Bike, Check, Clock, MapPin, MessageCircle, Minus, Plus, ShoppingBag, Trash2, X } from "lucide-react";
import { ApiError, get, post } from "../../lib/api";
import { money } from "../../lib/format";
import { geoErrorText, getPosition, mapsPin, type Coords } from "../../lib/geo";
import { useLocalStorage } from "../../lib/hooks";
import { Badge, Button, Field, Input, Modal, Spinner, inputCls } from "../../components/ui";

type Variant = { id: number; name: string | null; price: number };
type MItem = { id: number; name: string; description: string | null; image_url: string | null; variants: Variant[] };
type MCat = { id: number; name: string; addons: { id: number; name: string; price: number }[]; items: MItem[] };
type Info = {
  slug: string;
  name: string;
  available: boolean;
  accepting_orders: boolean;
  open_now: boolean;
  opens: string | null;
  eta_minutes: number;
  delivery_enabled: boolean;
  pickup_enabled: boolean;
  delivery_fee: number;
  min_order: number;
  payment_methods: string[];
  zones: { id: number; name: string; fee: number; min_order: number }[];
  menu: MCat[];
};
type Line = { key: string; variant_id: number; addon_ids: number[]; qty: number };

export default function MenuPage() {
  const { slug = "" } = useParams();
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState("");
  const [cart, setCart] = useLocalStorage<Line[]>(`cart:${slug}`, []);
  const [picking, setPicking] = useState<{ item: MItem; cat: MCat } | null>(null);
  const [checkout, setCheckout] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const sections = useRef<Record<number, HTMLElement | null>>({});

  const load = () =>
    get<Info>(`/public/r/${slug}`)
      .then((r) => {
        setInfo(r);
        document.title = `${r.name} — اطلب أونلاين`;
      })
      .catch(() => setError("المطعم مش موجود"));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  // index for pricing the cart on the client (display only — the server recomputes)
  const index = useMemo(() => {
    const variants = new Map<number, { item: MItem; cat: MCat; v: Variant }>();
    info?.menu.forEach((cat) => cat.items.forEach((item) => item.variants.forEach((v) => variants.set(v.id, { item, cat, v }))));
    return variants;
  }, [info]);

  const priced = cart
    .map((l) => {
      const found = index.get(l.variant_id);
      if (!found) return null;
      const addons = found.cat.addons.filter((a) => l.addon_ids.includes(a.id));
      const each = found.v.price + addons.reduce((s, a) => s + a.price, 0);
      return { ...l, found, addons, each, total: each * l.qty };
    })
    .filter(Boolean) as (Line & { found: { item: MItem; cat: MCat; v: Variant }; addons: { name: string; price: number }[]; each: number; total: number })[];
  const subtotal = priced.reduce((s, l) => s + l.total, 0);
  const count = priced.reduce((s, l) => s + l.qty, 0);

  useEffect(() => {
    // drop lines whose item disappeared from the menu
    if (info && priced.length !== cart.length) setCart(priced.map(({ key, variant_id, addon_ids, qty }) => ({ key, variant_id, addon_ids, qty })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info]);

  if (error) return <div className="grid min-h-dvh place-items-center text-muted">{error}</div>;
  if (!info)
    return (
      <div className="grid min-h-dvh place-items-center text-muted">
        <Spinner />
      </div>
    );

  const canOrder = info.available && info.accepting_orders && info.open_now;
  const addLine = (variant_id: number, addon_ids: number[], qty: number) => {
    const key = `${variant_id}-${[...addon_ids].sort((a, b) => a - b).join(".")}`;
    const existing = cart.find((l) => l.key === key);
    setCart(existing ? cart.map((l) => (l.key === key ? { ...l, qty: Math.min(50, l.qty + qty) } : l)) : [...cart, { key, variant_id, addon_ids, qty }]);
  };

  return (
    <div className="mx-auto min-h-dvh max-w-3xl pb-28">
      <header className="bg-primary px-4 pb-5 pt-8 text-primary-fg">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">{info.name}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm opacity-90">
              <span className="inline-flex items-center gap-1">
                <Clock className="size-4" /> حوالي {info.eta_minutes} دقيقة
              </span>
              {info.delivery_enabled ? (
                <span className="inline-flex items-center gap-1">
                  <Bike className="size-4" /> توصيل {info.zones.length ? `من ${money(Math.min(...info.zones.map((z) => z.fee)))}` : money(info.delivery_fee)}
                </span>
              ) : null}
            </div>
          </div>
          <Link to={`/r/${slug}/chat`} className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-white/15 px-3 py-1.5 text-sm font-semibold hover:bg-white/25">
            <MessageCircle className="size-4" /> اطلب بالشات
          </Link>
        </div>
        {!canOrder ? (
          <div className="mt-4 rounded-xl bg-white/15 px-3 py-2 text-sm font-semibold">
            {!info.available ? "الخدمة غير متاحة حاليًا" : !info.accepting_orders ? "المطعم مش بيستقبل طلبات دلوقتي" : `مقفولين دلوقتي${info.opens ? `، بنفتح ${info.opens}` : ""}`}
          </div>
        ) : null}
      </header>

      <nav className="sticky top-0 z-20 flex gap-2 overflow-x-auto border-b border-line bg-bg/95 px-4 py-2.5 backdrop-blur">
        {info.menu.map((c) => (
          <button
            key={c.id}
            onClick={() => {
              setActive(c.id);
              sections.current[c.id]?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-semibold ${active === c.id ? "bg-primary text-primary-fg" : "bg-surface text-fg ring-1 ring-line"}`}
          >
            {c.name}
          </button>
        ))}
      </nav>

      <main className="space-y-6 px-4 pt-4">
        {info.menu.map((c) => (
          <section key={c.id} ref={(el) => void (sections.current[c.id] = el)} className="scroll-mt-16">
            <h2 className="mb-2 text-lg font-bold">{c.name}</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {c.items.map((it) => {
                const min = Math.min(...it.variants.map((v) => v.price));
                return (
                  <button
                    key={it.id}
                    disabled={!canOrder}
                    onClick={() => setPicking({ item: it, cat: c })}
                    className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-3 text-right transition hover:border-primary disabled:opacity-70"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold">{it.name}</div>
                      {it.description ? <div className="truncate text-xs text-muted">{it.description}</div> : null}
                      <div className="num mt-1 text-sm text-muted">
                        {it.variants.length > 1 ? it.variants.map((v) => `${v.name} ${v.price}`).join(" · ") + " ج" : money(min)}
                      </div>
                    </div>
                    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary-soft text-primary">
                      <Plus className="size-5" />
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </main>

      {count > 0 ? (
        <div className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-3xl p-3">
          <button onClick={() => setCheckout(true)} className="flex h-14 w-full items-center gap-3 rounded-2xl bg-primary px-5 font-bold text-primary-fg shadow-xl">
            <span className="grid size-8 place-items-center rounded-full bg-white/20 text-sm">{count}</span>
            <span className="flex-1 text-right">عرض السلة</span>
            <span className="num">{money(subtotal)}</span>
          </button>
        </div>
      ) : null}

      {picking ? (
        <ItemSheet
          item={picking.item}
          cat={picking.cat}
          onClose={() => setPicking(null)}
          onAdd={(v, a, q) => {
            addLine(v, a, q);
            setPicking(null);
          }}
        />
      ) : null}

      {checkout ? (
        <Checkout
          info={info}
          slug={slug}
          lines={priced}
          subtotal={subtotal}
          setQty={(key, qty) => setCart(qty <= 0 ? cart.filter((l) => l.key !== key) : cart.map((l) => (l.key === key ? { ...l, qty } : l)))}
          onClose={() => setCheckout(false)}
          onPlaced={() => setCart([])}
          onStale={load}
        />
      ) : null}
    </div>
  );
}

function ItemSheet({ item, cat, onClose, onAdd }: { item: MItem; cat: MCat; onClose: () => void; onAdd: (variant: number, addons: number[], qty: number) => void }) {
  const [variant, setVariant] = useState(item.variants[0].id);
  const [addons, setAddons] = useState<number[]>([]);
  const [qty, setQty] = useState(1);
  const v = item.variants.find((x) => x.id === variant)!;
  const each = v.price + cat.addons.filter((a) => addons.includes(a.id)).reduce((s, a) => s + a.price, 0);
  return (
    <Modal open onClose={onClose} title={item.name}>
      {item.description ? <p className="mb-4 text-sm text-muted">{item.description}</p> : null}
      {item.variants.length > 1 ? (
        <fieldset className="mb-5">
          <legend className="mb-2 text-sm font-bold">الحجم</legend>
          <div className="grid grid-cols-2 gap-2">
            {item.variants.map((x) => (
              <label key={x.id} className={`flex cursor-pointer items-center justify-between rounded-xl border p-3 ${variant === x.id ? "border-primary bg-primary-soft" : "border-line"}`}>
                <span className="flex items-center gap-2">
                  <input type="radio" name="variant" checked={variant === x.id} onChange={() => setVariant(x.id)} className="accent-[var(--primary)]" />
                  {x.name}
                </span>
                <span className="num font-semibold">{money(x.price)}</span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}
      {cat.addons.length ? (
        <fieldset className="mb-5">
          <legend className="mb-2 text-sm font-bold">إضافات (اختياري)</legend>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {cat.addons.map((a) => (
              <label key={a.id} className={`flex cursor-pointer items-center justify-between rounded-xl border px-3 py-2 text-sm ${addons.includes(a.id) ? "border-primary bg-primary-soft" : "border-line"}`}>
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={addons.includes(a.id)}
                    onChange={(e) => setAddons(e.target.checked ? [...addons, a.id] : addons.filter((x) => x !== a.id))}
                    className="accent-[var(--primary)]"
                  />
                  {a.name}
                </span>
                <span className="num text-muted">+{money(a.price)}</span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}
      <div className="flex items-center gap-3">
        <Stepper value={qty} onChange={setQty} min={1} />
        <Button tone="primary" size="lg" className="flex-1" onClick={() => onAdd(variant, addons, qty)}>
          أضف للسلة · <span className="num">{money(each * qty)}</span>
        </Button>
      </div>
    </Modal>
  );
}

function Stepper({ value, onChange, min = 0 }: { value: number; onChange: (v: number) => void; min?: number }) {
  return (
    <div className="flex items-center rounded-xl border border-line">
      <button onClick={() => onChange(Math.min(50, value + 1))} className="grid size-10 place-items-center" aria-label="زوّد">
        <Plus className="size-4" />
      </button>
      <span className="num w-8 text-center font-bold">{value}</span>
      <button onClick={() => onChange(Math.max(min, value - 1))} className="grid size-10 place-items-center" aria-label="قلّل">
        {value <= 1 && min === 0 ? <Trash2 className="size-4 text-danger" /> : <Minus className="size-4" />}
      </button>
    </div>
  );
}

function Checkout({
  info,
  slug,
  lines,
  subtotal,
  setQty,
  onClose,
  onPlaced,
  onStale,
}: {
  info: Info;
  slug: string;
  lines: { key: string; variant_id: number; addon_ids: number[]; qty: number; found: { item: MItem; v: Variant }; addons: { name: string }[]; total: number }[];
  subtotal: number;
  setQty: (key: string, qty: number) => void;
  onClose: () => void;
  onPlaced: () => void;
  onStale: () => void;
}) {
  const nav = useNavigate();
  const [profile, setProfile] = useLocalStorage(`profile`, { name: "", phone: "", address: "" });
  const [ful, setFul] = useState<"delivery" | "pickup">(info.delivery_enabled ? "delivery" : "pickup");
  const [zoneId, setZoneId] = useState<number | "">(info.zones[0]?.id ?? "");
  const [pay, setPay] = useState(info.payment_methods[0]);
  const [notes, setNotes] = useState("");
  const [loc, setLoc] = useState<Coords | null>(null);
  const [locating, setLocating] = useState(false);
  const locate = async () => {
    setLocating(true);
    setErr("");
    try {
      setLoc(await getPosition());
    } catch (e) {
      setErr(geoErrorText(e));
    } finally {
      setLocating(false);
    }
  };
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const zone = info.zones.find((z) => z.id === zoneId);
  const fee = ful === "delivery" ? (info.zones.length ? (zone?.fee ?? 0) : info.delivery_fee) : 0;
  const minOrder = ful === "delivery" ? (zone && zone.min_order > 0 ? zone.min_order : info.min_order) : 0;
  const below = subtotal < minOrder;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const r = await post(`/public/r/${slug}/orders`, {
        customer: { name: profile.name, phone: profile.phone },
        lines: lines.map((l) => ({ variant_id: l.variant_id, addon_ids: l.addon_ids, qty: l.qty })),
        fulfillment: ful,
        zone_id: ful === "delivery" && info.zones.length ? zoneId : null,
        address: ful === "delivery" ? profile.address : null,
        lat: ful === "delivery" && loc ? loc.lat : null,
        lng: ful === "delivery" && loc ? loc.lng : null,
        payment_method: pay,
        notes: notes || null,
      });
      onPlaced();
      nav(`/o/${r.token}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "حصلت مشكلة");
      if (e instanceof ApiError && (e.detail as any)?.code === "items_changed") onStale();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="سلتك">
      <ul className="mb-5 divide-y divide-line">
        {lines.map((l) => (
          <li key={l.key} className="flex items-center gap-3 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="font-semibold">
                {l.found.item.name}
                {l.found.v.name ? <span className="text-muted"> ({l.found.v.name})</span> : null}
              </div>
              {l.addons.length ? <div className="text-xs text-muted">+ {l.addons.map((a) => a.name).join("، ")}</div> : null}
              <div className="num text-sm text-muted">{money(l.total)}</div>
            </div>
            <Stepper value={l.qty} onChange={(q) => setQty(l.key, q)} />
          </li>
        ))}
      </ul>

      <form onSubmit={submit} className="space-y-4">
        {info.delivery_enabled && info.pickup_enabled ? (
          <div className="grid grid-cols-2 gap-2">
            {(["delivery", "pickup"] as const).map((f) => (
              <button
                type="button"
                key={f}
                onClick={() => setFul(f)}
                className={`flex h-12 items-center justify-center gap-2 rounded-xl border font-semibold ${ful === f ? "border-primary bg-primary-soft text-primary" : "border-line"}`}
              >
                {f === "delivery" ? <Bike className="size-4" /> : <ShoppingBag className="size-4" />}
                {f === "delivery" ? "توصيل" : "استلام من المطعم"}
              </button>
            ))}
          </div>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="الاسم">
            <Input required minLength={2} value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} autoComplete="name" />
          </Field>
          <Field label="رقم الموبايل">
            <Input required dir="ltr" inputMode="tel" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} autoComplete="tel" placeholder="01xxxxxxxxx" className="text-right" />
          </Field>
        </div>
        {ful === "delivery" ? (
          <>
            {info.zones.length ? (
              <Field label="المنطقة">
                <select required className={inputCls} value={zoneId} onChange={(e) => setZoneId(Number(e.target.value))}>
                  {info.zones.map((z) => (
                    <option key={z.id} value={z.id}>
                      {z.name} — توصيل {money(z.fee)}
                      {z.min_order ? ` (حد أدنى ${money(z.min_order)})` : ""}
                    </option>
                  ))}
                </select>
              </Field>
            ) : null}
            {loc ? (
              <div className="flex items-center gap-2 rounded-xl bg-ok-soft px-3 py-2 text-sm text-ok">
                <Check className="size-4" />
                <span className="flex-1 font-semibold">تم تحديد موقعك على الخريطة</span>
                <a href={mapsPin(loc.lat, loc.lng)} target="_blank" rel="noreferrer" className="text-xs underline">
                  عرض
                </a>
                <button type="button" onClick={() => setLoc(null)} aria-label="إلغاء الموقع" className="p-0.5">
                  <X className="size-4" />
                </button>
              </div>
            ) : (
              <Button type="button" tone="neutral" className="w-full" loading={locating} onClick={locate}>
                <MapPin className="size-4" /> حدد موقعي على الخريطة (اختياري)
              </Button>
            )}
            <Field label={loc ? "تفاصيل العنوان (العمارة، الدور، الشقة)" : "العنوان بالتفصيل"}>
              <textarea
                required
                minLength={5}
                value={profile.address}
                onChange={(e) => setProfile({ ...profile, address: e.target.value })}
                className={`${inputCls} h-20 py-2`}
                placeholder="الشارع، رقم العمارة، الدور، علامة مميزة"
                autoComplete="street-address"
              />
            </Field>
          </>
        ) : null}
        {info.payment_methods.length > 1 ? (
          <div className="flex gap-2">
            {info.payment_methods.map((m) => (
              <button type="button" key={m} onClick={() => setPay(m)} className={`h-10 flex-1 rounded-xl border text-sm font-semibold ${pay === m ? "border-primary bg-primary-soft text-primary" : "border-line"}`}>
                {m === "cod" ? "كاش عند الاستلام" : "محفظة / إنستاباي"}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">💵 الدفع كاش عند الاستلام</p>
        )}
        <Field label="ملاحظات (اختياري)">
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
        </Field>

        <div className="space-y-1 rounded-xl bg-surface-2 p-3 text-sm">
          <Row label="المجموع" value={money(subtotal)} />
          {ful === "delivery" ? <Row label="التوصيل" value={money(fee)} /> : null}
          <Row label="الإجمالي" value={money(subtotal + fee)} bold />
        </div>
        {below ? (
          <p className="text-sm text-warn">
            الحد الأدنى للتوصيل {money(minOrder)}. <Badge tone="warn">ناقص {money(minOrder - subtotal)}</Badge>
          </p>
        ) : null}
        {err ? <p className="text-sm text-danger">{err}</p> : null}
        <Button tone="primary" size="lg" className="w-full" loading={busy} disabled={below || !lines.length}>
          تأكيد الطلب
        </Button>
      </form>
    </Modal>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className={`flex justify-between ${bold ? "text-base font-bold" : "text-muted"}`}>
      <span>{label}</span>
      <span className="num">{value}</span>
    </div>
  );
}
