import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { get } from "../../lib/api";
import { CHANNEL_LABEL, STATUS_LABEL, STATUS_TONE, clock, displayPhone, money } from "../../lib/format";
import { useNow } from "../../lib/hooks";
import type { Order } from "../../lib/types";
import { Badge, Card, Empty, Input, Modal, Spinner } from "../../components/ui";
import OrderCard from "./OrderCard";

function today(): string {
  const d = new Date(Date.now() - 5 * 3600 * 1000); // business day starts 05:00
  return d.toLocaleDateString("en-CA");
}

export default function History({ onOpenChat }: { onOpenChat: (id: number) => void }) {
  const [day, setDay] = useState(today());
  const [q, setQ] = useState("");
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [open, setOpen] = useState<Order | null>(null);
  const now = useNow();

  useEffect(() => {
    setOrders(null);
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    else if (day) params.set("day", day);
    const t = window.setTimeout(() => get(`/dash/orders?${params}`).then((r) => setOrders(r.orders)), q ? 300 : 0);
    return () => window.clearTimeout(t);
  }, [day, q]);

  const total = orders?.filter((o) => o.status === "completed").reduce((s, o) => s + o.total, 0) ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label>
          <span className="mb-1 block text-sm font-semibold">اليوم</span>
          <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} disabled={!!q} className="w-44" />
        </label>
        <label className="relative min-w-60 flex-1">
          <span className="mb-1 block text-sm font-semibold">بحث</span>
          <Search className="pointer-events-none absolute bottom-3 right-3 size-4 text-muted" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="رقم الطلب، الموبايل أو الاسم" className="pr-9" />
        </label>
        {orders ? (
          <div className="text-sm text-muted">
            {orders.length} طلب · المسلَّم: <span className="num font-bold text-fg">{money(total)}</span>
          </div>
        ) : null}
      </div>
      <Card className="overflow-hidden">
        {!orders ? (
          <div className="grid h-40 place-items-center text-muted">
            <Spinner />
          </div>
        ) : !orders.length ? (
          <Empty title="مفيش طلبات" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-right text-xs text-muted">
                <tr>
                  {["#", "الوقت", "العميل", "النوع", "المصدر", "الإجمالي", "الحالة"].map((h) => (
                    <th key={h} className="px-4 py-2.5 font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id} onClick={() => setOpen(o)} className="cursor-pointer border-t border-line hover:bg-surface-2">
                    <td className="num px-4 py-2.5 font-bold">{o.order_no}</td>
                    <td className="num px-4 py-2.5 text-muted">
                      {q ? `${o.business_day} ` : ""}
                      {clock(o.created_at)}
                    </td>
                    <td className="px-4 py-2.5">
                      {o.customer?.name}
                      <div className="num text-xs text-muted" dir="ltr">
                        {displayPhone(o.customer?.phone)}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">{o.fulfillment === "delivery" ? "توصيل" : "استلام"}</td>
                    <td className="px-4 py-2.5 text-muted">{CHANNEL_LABEL[o.channel]}</td>
                    <td className="num px-4 py-2.5 font-semibold">{money(o.total)}</td>
                    <td className="px-4 py-2.5">
                      <Badge tone={STATUS_TONE[o.status]}>{STATUS_LABEL[o.status]}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? `طلب #${open.order_no}` : ""}>
        {open ? (
          <OrderCard
            order={open}
            now={now}
            onOpenChat={(id) => {
              setOpen(null);
              onOpenChat(id);
            }}
            onChanged={(o) => {
              setOpen(o);
              setOrders((list) => list?.map((x) => (x.id === o.id ? o : x)) ?? null);
            }}
          />
        ) : null}
      </Modal>
    </div>
  );
}
