import { useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes, useNavigate } from "react-router";
import { BellRing, ChefHat, ClipboardList, ExternalLink, LogOut, MessageCircle, Settings2, Shield, UtensilsCrossed, Volume2, VolumeX } from "lucide-react";
import { ApiError, get, patch, post } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { audioReady, beep, unlockAudio, useNow, usePoll } from "../../lib/hooks";
import type { Board as BoardT, Order } from "../../lib/types";
import { Badge, Button, Empty, Switch, useToast } from "../../components/ui";
import OrderCard from "./OrderCard";
import ChatPanel from "./ChatPanel";
import History from "./History";
import MenuEditor from "./MenuEditor";
import SettingsPage from "./Settings";
import Chats from "./Chats";

export default function Dashboard() {
  const { me, setMe, logout } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const [board, setBoard] = useState<BoardT | null>(null);
  const [chatId, setChatId] = useState<number | null>(null);
  const [sound, setSound] = useState(audioReady());
  const seen = useRef<Set<number> | null>(null);
  const now = useNow(20000);
  const r = me?.restaurant;

  usePoll(async () => {
    try {
      const b = await get<BoardT>("/dash/board");
      const placed = b.orders.filter((o) => o.status === "placed");
      if (seen.current) {
        const fresh = placed.filter((o) => !seen.current!.has(o.id));
        if (fresh.length) {
          beep();
          toast(`🔔 طلب جديد #${fresh.map((o) => o.order_no).join("، #")}`, "info");
        }
      }
      seen.current = new Set(b.orders.map((o) => o.id));
      setBoard(b);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && me?.is_super) nav("/admin");
    }
  }, 3000);

  // keep beeping every 15s while a new order is waiting
  const waiting = board?.orders.filter((o) => o.status === "placed").length ?? 0;
  useEffect(() => {
    if (!waiting) return;
    const t = window.setInterval(beep, 15000);
    return () => window.clearInterval(t);
  }, [waiting]);

  useEffect(() => {
    document.title = waiting ? `(${waiting}) طلب جديد — ${r?.name ?? ""}` : `${r?.name ?? "الداشبورد"} — الطلبات`;
  }, [waiting, r?.name]);

  if (!me || !r) return null;

  const upsert = (o: Order) => setBoard((b) => (b ? { ...b, orders: b.orders.map((x) => (x.id === o.id ? { ...x, ...o } : x)) } : b));

  const toggleAccepting = async (v: boolean) => {
    setBoard((b) => (b ? { ...b, accepting_orders: v } : b));
    try {
      await patch("/dash/settings", { accepting_orders: v });
      toast(v ? "المطعم بيستقبل طلبات" : "وقفنا استقبال الطلبات");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    }
  };

  const saveEta = async (eta: number) => {
    if (!eta || eta === board?.eta_minutes) return;
    try {
      await patch("/dash/settings", { eta_minutes: eta });
      toast(`الوقت المتوقع: ${eta} دقيقة`);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "حصلت مشكلة", "danger");
    }
  };

  const exitToAdmin = async () => {
    setMe(await post("/admin/exit"));
    nav("/admin");
  };

  const tabs = [
    { to: "/dashboard", label: "الطلبات", icon: ChefHat, end: true },
    { to: "/dashboard/history", label: "السجل", icon: ClipboardList },
    { to: "/dashboard/menu", label: "المنيو", icon: UtensilsCrossed },
    { to: "/dashboard/chats", label: "المحادثات", icon: MessageCircle },
    ...(me.can_manage ? [{ to: "/dashboard/settings", label: "الإعدادات", icon: Settings2 }] : []),
  ];

  return (
    <div className="min-h-dvh">
      {me.is_super ? (
        <div className="flex items-center gap-2 bg-fg px-4 py-1.5 text-xs text-bg">
          <Shield className="size-3.5" /> انت داخل كـ super admin على {r.name}
          <button onClick={exitToAdmin} className="ms-auto font-semibold underline">
            رجوع للوحة الإدارة
          </button>
        </div>
      ) : null}
      <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <img src="/favicon.svg" alt="" className="size-8" />
            <div>
              <div className="font-bold leading-tight">{r.name}</div>
              <div className="text-xs text-muted">{me.user.display_name ?? me.user.username}</div>
            </div>
          </div>
          <label className="flex items-center gap-2 rounded-xl border border-line px-3 py-1.5">
            <Switch checked={!!board?.accepting_orders} onChange={toggleAccepting} label="استقبال الطلبات" disabled={!board} />
            <span className={`text-sm font-semibold ${board?.accepting_orders ? "text-ok" : "text-danger"}`}>{board?.accepting_orders ? "مفتوح" : "مقفول"}</span>
            {board && board.accepting_orders && !board.open_now ? <Badge tone="warn">خارج المواعيد</Badge> : null}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted">الوقت المتوقع</span>
            <input
              key={board?.eta_minutes}
              type="number"
              min={1}
              max={300}
              defaultValue={board?.eta_minutes}
              onBlur={(e) => saveEta(Number(e.target.value))}
              onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
              className="num h-9 w-16 rounded-lg border border-line bg-surface px-2 text-center"
            />
            <span className="text-muted">دقيقة</span>
          </label>
          <div className="ms-auto flex items-center gap-1">
            <Button
              size="sm"
              tone={sound ? "ghost" : "warn"}
              onClick={() => {
                if (unlockAudio()) {
                  setSound(true);
                  beep();
                }
              }}
              title="المتصفح بيمنع الصوت لحد ما تضغط"
            >
              {sound ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}
              {sound ? "الصوت شغال" : "تفعيل الصوت"}
            </Button>
            <a href={`/r/${r.slug}/chat`} target="_blank" rel="noreferrer">
              <Button size="sm" tone="ghost">
                <ExternalLink className="size-4" /> ديمو الشات
              </Button>
            </a>
            <Button
              size="sm"
              tone="ghost"
              aria-label="خروج"
              onClick={async () => {
                await logout();
                nav("/login");
              }}
            >
              <LogOut className="size-4" />
            </Button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-[1600px] gap-1 overflow-x-auto px-3">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-semibold ${isActive ? "border-primary text-primary" : "border-transparent text-muted hover:text-fg"}`
              }
            >
              <t.icon className="size-4" />
              {t.label}
              {t.label === "الطلبات" && waiting ? <Badge tone="warn">{waiting}</Badge> : null}
              {t.label === "المحادثات" && board?.human.length ? <Badge tone="danger">{board.human.length}</Badge> : null}
            </NavLink>
          ))}
        </nav>
      </header>

      {board?.human.length ? (
        <div className="sticky top-[105px] z-20 mx-auto max-w-[1600px] px-4 pt-3">
          {board.human.map((c) => (
            <div key={c.id} className="mb-2 flex items-center gap-3 rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-danger">
              <BellRing className="size-5 shrink-0" />
              <span className="flex-1 text-sm font-semibold">{c.customer?.name ?? "عميل"} طالب يكلم موظف</span>
              <Button size="sm" tone="danger" onClick={() => setChatId(c.id)}>
                افتح المحادثة
              </Button>
            </div>
          ))}
        </div>
      ) : null}

      <main className="mx-auto max-w-[1600px] p-4">
        <Routes>
          <Route index element={<BoardView board={board} now={now} onChanged={upsert} onOpenChat={setChatId} />} />
          <Route path="history" element={<History onOpenChat={setChatId} />} />
          <Route path="menu" element={<MenuEditor />} />
          <Route path="chats" element={<Chats onOpen={setChatId} />} />
          {me.can_manage ? <Route path="settings" element={<SettingsPage />} /> : null}
        </Routes>
      </main>
      <ChatPanel convId={chatId} onClose={() => setChatId(null)} />
    </div>
  );
}

function BoardView({ board, now, onChanged, onOpenChat }: { board: BoardT | null; now: number; onChanged: (o: Order) => void; onOpenChat: (id: number) => void }) {
  if (!board) return <div className="py-20 text-center text-muted">جاري التحميل…</div>;
  const cols = [
    { title: "جديد", tone: "warn" as const, statuses: ["placed"] },
    { title: "في المطبخ", tone: "info" as const, statuses: ["accepted", "preparing"] },
    { title: "في الطريق / جاهز", tone: "primary" as const, statuses: ["out_for_delivery", "ready_for_pickup"] },
  ];
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {cols.map((c) => {
        const orders = board.orders.filter((o) => c.statuses.includes(o.status));
        return (
          <section key={c.title} className="min-w-0">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-bold">
              {c.title} <Badge tone={c.tone}>{orders.length}</Badge>
            </h2>
            <div className="space-y-3">
              {orders.length ? (
                orders.map((o) => <OrderCard key={o.id} order={o} now={now} onChanged={onChanged} onOpenChat={onOpenChat} />)
              ) : (
                <div className="rounded-2xl border border-dashed border-line">
                  <Empty title="مفيش طلبات هنا" />
                </div>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
