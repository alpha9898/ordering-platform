import { useState } from "react";
import { Bike, MapPin, MessageCircle, Phone, ShoppingBag } from "lucide-react";
import { ApiError, post } from "../../lib/api";
import { CHANNEL_LABEL, PAYMENT_LABEL, STATUS_LABEL, STATUS_TONE, displayPhone, mapsLink, money, timeAgo, type OrderStatus } from "../../lib/format";
import type { Order } from "../../lib/types";
import { Badge, Button, Modal, inputCls, useToast } from "../../components/ui";

const REJECT_REASONS = ["الصنف خلص", "خارج منطقة التوصيل", "المطعم زحمة جدًا", "العنوان مش واضح"];

type Action = { status: OrderStatus; label: string; tone: "ok" | "primary" | "danger" | "ghost" | "warn" };

function actionsFor(o: Order): Action[] {
  switch (o.status) {
    case "placed":
      return [
        { status: "accepted", label: "قبول", tone: "ok" },
        { status: "rejected", label: "رفض", tone: "danger" },
      ];
    case "accepted":
      return [
        { status: "preparing", label: "ابدأ التحضير", tone: "primary" },
        { status: "cancelled", label: "إلغاء", tone: "ghost" },
      ];
    case "preparing":
      return o.fulfillment === "delivery"
        ? [{ status: "out_for_delivery", label: "خرج للتوصيل 🛵", tone: "primary" }]
        : [{ status: "ready_for_pickup", label: "جاهز للاستلام", tone: "primary" }];
    case "out_for_delivery":
    case "ready_for_pickup":
      return [{ status: "completed", label: "تم التسليم ✓", tone: "ok" }];
    default:
      return [];
  }
}

export default function OrderCard({
  order,
  now,
  onChanged,
  onOpenChat,
  readOnly,
}: {
  order: Order;
  now: number;
  onChanged?: (o: Order) => void;
  onOpenChat?: (convId: number) => void;
  readOnly?: boolean;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const isNew = order.status === "placed";

  const act = async (status: OrderStatus, reject_reason?: string) => {
    if (status === "rejected" && !reject_reason) return setRejecting(true);
    if (status === "cancelled" && !confirm(`إلغاء طلب #${order.order_no}؟`)) return;
    setBusy(status);
    try {
      const o = await post(`/dash/orders/${order.id}/status`, { status, reject_reason });
      onChanged?.(o);
      toast(o.customer_notified ? `#${order.order_no}: ${STATUS_LABEL[status]} · اتبعت رسالة للعميل` : `#${order.order_no}: ${STATUS_LABEL[status]}`);
      setRejecting(false);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    } finally {
      setBusy(null);
    }
  };

  return (
    <article className={`fade-in rounded-2xl border bg-surface p-4 ${isNew ? "pulse-new border-warn" : "border-line"}`}>
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <span className="num text-2xl font-bold">#{order.order_no}</span>
        <Badge tone={STATUS_TONE[order.status]}>{STATUS_LABEL[order.status]}</Badge>
        <Badge tone="muted">{CHANNEL_LABEL[order.channel]}</Badge>
        {order.is_demo ? <Badge tone="muted">ديمو</Badge> : null}
        <span className="ms-auto text-xs text-muted" title={new Date(order.created_at).toLocaleString("ar-EG")}>
          {timeAgo(order.created_at, now)}
        </span>
      </header>

      <div className="mb-3 space-y-1.5 text-sm">
        <div className="flex items-center gap-2">
          <span className="font-semibold">{order.customer?.name ?? "عميل"}</span>
          {order.customer ? (
            <a href={`tel:${displayPhone(order.customer.phone)}`} className="num inline-flex items-center gap-1 text-muted hover:text-fg" dir="ltr">
              <Phone className="size-3.5" />
              {displayPhone(order.customer.phone)}
            </a>
          ) : null}
          {order.conversation_id && onOpenChat ? (
            <button onClick={() => onOpenChat(order.conversation_id!)} className="ms-auto inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">
              <MessageCircle className="size-3.5" /> المحادثة
            </button>
          ) : null}
        </div>
        {order.fulfillment === "delivery" ? (
          <div className="flex items-start gap-2 text-muted">
            <Bike className="mt-0.5 size-4 shrink-0 text-fg" />
            <div>
              <span className="font-semibold text-fg">توصيل</span>
              {order.zone ? <span> · {order.zone}</span> : null}
              {order.address ? (
                <a href={mapsLink(order.address)} target="_blank" rel="noreferrer" className="mt-0.5 flex items-start gap-1 text-fg hover:text-primary">
                  <MapPin className="mt-0.5 size-3.5 shrink-0" />
                  <span>{order.address}</span>
                </a>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <ShoppingBag className="size-4" />
            <span className="font-semibold">استلام من المطعم</span>
          </div>
        )}
      </div>

      <ul className="mb-3 space-y-1.5 rounded-xl bg-surface-2 p-3 text-sm">
        {order.items.map((it, i) => (
          <li key={i}>
            <div className="flex gap-2">
              <span className="num font-bold">{it.qty}×</span>
              <span className="flex-1">
                {it.name}
                {it.variant ? <span className="text-muted"> ({it.variant})</span> : null}
              </span>
              <span className="num text-muted">{money(it.line_total)}</span>
            </div>
            {it.addons.length ? <div className="ms-6 text-xs text-muted">+ {it.addons.map((a) => a.name).join("، ")}</div> : null}
            {it.note ? <div className="ms-6 text-xs text-warn">📝 {it.note}</div> : null}
          </li>
        ))}
      </ul>
      {order.notes ? <p className="mb-3 rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">📝 {order.notes}</p> : null}

      <div className="mb-3 flex items-center justify-between text-sm">
        <span className="text-muted">
          {PAYMENT_LABEL[order.payment_method]}
          {order.delivery_fee ? ` · توصيل ${money(order.delivery_fee)}` : ""}
        </span>
        <span className="num text-lg font-bold">{money(order.total)}</span>
      </div>
      {order.reject_reason ? <p className="mb-2 text-sm text-danger">السبب: {order.reject_reason}</p> : null}

      {!readOnly && actionsFor(order).length ? (
        <div className="flex gap-2">
          {actionsFor(order).map((a) => (
            <Button key={a.status} tone={a.tone} size={isNew ? "lg" : "md"} className={a.tone === "ghost" ? "" : "flex-1"} loading={busy === a.status} disabled={!!busy} onClick={() => act(a.status)}>
              {a.label}
            </Button>
          ))}
        </div>
      ) : null}

      <Modal open={rejecting} onClose={() => setRejecting(false)} title={`رفض طلب #${order.order_no}`}>
        <p className="mb-3 text-sm text-muted">السبب هيتبعت للعميل.</p>
        <div className="mb-3 flex flex-wrap gap-2">
          {REJECT_REASONS.map((r) => (
            <button key={r} onClick={() => setReason(r)} className={`rounded-full border px-3 py-1.5 text-sm ${reason === r ? "border-danger bg-danger-soft text-danger" : "border-line"}`}>
              {r}
            </button>
          ))}
        </div>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="أو اكتب السبب" className={`${inputCls} mb-4 h-20 py-2`} />
        <Button tone="danger" className="w-full" disabled={!reason.trim()} loading={busy === "rejected"} onClick={() => act("rejected", reason.trim())}>
          تأكيد الرفض
        </Button>
      </Modal>
    </article>
  );
}
