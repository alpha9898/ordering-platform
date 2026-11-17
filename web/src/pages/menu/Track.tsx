import { useState } from "react";
import { Link, useParams } from "react-router";
import { Check, X } from "lucide-react";
import { get } from "../../lib/api";
import { STATUS_LABEL, clock, money, type OrderStatus } from "../../lib/format";
import { usePoll } from "../../lib/hooks";
import type { Order } from "../../lib/types";
import { Card, Spinner } from "../../components/ui";

type Tracked = Order & { restaurant: { slug: string; name: string } };

export default function Track() {
  const { token = "" } = useParams();
  const [o, setO] = useState<Tracked | null>(null);
  const [missing, setMissing] = useState(false);

  usePoll(async () => {
    try {
      const r = await get<Tracked>(`/public/orders/${token}`);
      setO(r);
      document.title = `طلب #${r.order_no} — ${STATUS_LABEL[r.status]}`;
    } catch {
      setMissing(true);
    }
  }, 4000);

  if (missing && !o) return <div className="grid min-h-dvh place-items-center text-muted">الطلب مش موجود</div>;
  if (!o)
    return (
      <div className="grid min-h-dvh place-items-center text-muted">
        <Spinner />
      </div>
    );

  const steps: OrderStatus[] = ["placed", "accepted", "preparing", o.fulfillment === "delivery" ? "out_for_delivery" : "ready_for_pickup", "completed"];
  const reached = new Map(o.events.map((e) => [e.status, e.at]));
  const failed = o.status === "rejected" || o.status === "cancelled";
  const headline: Record<OrderStatus, string> = {
    placed: "مستنيين المطعم يأكد طلبك ⏳",
    accepted: "المطعم قبل طلبك 👨‍🍳",
    preparing: "طلبك بيتجهز دلوقتي 🍳",
    out_for_delivery: "طلبك خرج للتوصيل 🛵",
    ready_for_pickup: "طلبك جاهز للاستلام 🎉",
    completed: "اتسلم، بالهنا والشفا ❤️",
    rejected: "معلش، الطلب اترفض",
    cancelled: "الطلب اتلغى",
  };

  return (
    <div className="mx-auto min-h-dvh max-w-lg space-y-4 px-4 py-8">
      <div className="text-center">
        <Link to={`/r/${o.restaurant.slug}`} className="text-sm font-semibold text-primary">
          {o.restaurant.name}
        </Link>
        <h1 className="mt-2 text-xl font-bold">{headline[o.status]}</h1>
        <p className="num mt-1 text-muted">طلب رقم #{o.order_no}</p>
        {o.status === "accepted" || o.status === "preparing" ? <p className="mt-1 text-sm text-muted">الوقت المتوقع حوالي {o.eta_minutes} دقيقة</p> : null}
      </div>

      <Card className="p-5">
        {failed ? (
          <div className="flex items-center gap-3 text-danger">
            <span className="grid size-9 place-items-center rounded-full bg-danger-soft">
              <X className="size-5" />
            </span>
            <div>
              <div className="font-semibold">{STATUS_LABEL[o.status]}</div>
              {o.reject_reason ? <div className="text-sm">السبب: {o.reject_reason}</div> : null}
            </div>
          </div>
        ) : (
          <ol className="space-y-4">
            {steps.map((s, i) => {
              const done = reached.has(s);
              const current = o.status === s;
              return (
                <li key={s} className="flex items-center gap-3">
                  <span className={`grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold ${done ? "bg-ok text-white" : "bg-surface-2 text-muted"} ${current ? "ring-4 ring-ok-soft" : ""}`}>
                    {done ? <Check className="size-4" /> : i + 1}
                  </span>
                  <span className={`flex-1 ${done ? "font-semibold" : "text-muted"}`}>{STATUS_LABEL[s] === "جديد" ? "اتبعت للمطعم" : STATUS_LABEL[s]}</span>
                  <span className="num text-xs text-muted">{clock(reached.get(s))}</span>
                </li>
              );
            })}
          </ol>
        )}
      </Card>

      <Card className="p-5 text-sm">
        <ul className="mb-3 space-y-1.5">
          {o.items.map((it, i) => (
            <li key={i} className="flex gap-2">
              <span className="num font-bold">{it.qty}×</span>
              <span className="flex-1">
                {it.name}
                {it.variant ? ` (${it.variant})` : ""}
                {it.addons.length ? <span className="block text-xs text-muted">+ {it.addons.map((a) => a.name).join("، ")}</span> : null}
              </span>
              <span className="num text-muted">{money(it.line_total)}</span>
            </li>
          ))}
        </ul>
        <div className="space-y-1 border-t border-line pt-3">
          {o.delivery_fee ? (
            <div className="flex justify-between text-muted">
              <span>التوصيل</span>
              <span className="num">{money(o.delivery_fee)}</span>
            </div>
          ) : null}
          <div className="flex justify-between text-base font-bold">
            <span>الإجمالي</span>
            <span className="num">{money(o.total)}</span>
          </div>
        </div>
      </Card>
      <p className="text-center text-xs text-muted">الصفحة بتتحدث لوحدها</p>
    </div>
  );
}
