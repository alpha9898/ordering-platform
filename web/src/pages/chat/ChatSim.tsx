import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { ArrowRight, BadgeCheck, CheckCheck, List as ListIcon, RotateCcw, SendHorizontal, Store, X } from "lucide-react";
import { ApiError, get, post } from "../../lib/api";
import { clock } from "../../lib/format";
import { useLocalStorage, usePoll } from "../../lib/hooks";
import { Button, Spinner } from "../../components/ui";

type Btn = { id: string; title: string };
type Row = { id: string; title: string; description?: string | null };
type Payload =
  | { type: "text"; body?: string; text?: string }
  | { type: "buttons"; body: string; buttons: Btn[]; header?: string | null; footer?: string | null }
  | { type: "list"; body: string; button: string; sections: { title: string; rows: Row[] }[] }
  | { type: "button_reply" | "list_reply"; id: string; title: string };
type Msg = { id: number; direction: "in" | "out"; sender: string; payload: Payload; created_at: string | null; pending?: boolean };
type Session = { session_id: string; name: string; phone: string };

export default function ChatSim() {
  const { slug = "" } = useParams();
  const [info, setInfo] = useState<{ name: string; available: boolean } | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [session, setSession] = useLocalStorage<Session | null>(`chat:${slug}`, null);

  useEffect(() => {
    get(`/public/r/${slug}`)
      .then((r) => setInfo({ name: r.name, available: r.available }))
      .catch(() => setNotFound(true));
  }, [slug]);

  useEffect(() => {
    if (info) document.title = `${info.name} — واتساب`;
  }, [info]);

  if (notFound) return <div className="grid min-h-screen place-items-center text-muted">المطعم مش موجود</div>;

  return (
    <div className="min-h-dvh bg-bg sm:flex sm:items-center sm:justify-center sm:gap-10 sm:p-6">
      <div className="relative flex h-dvh w-full flex-col overflow-hidden bg-[#efeae2] sm:h-[800px] sm:max-h-[calc(100dvh-3rem)] sm:w-[400px] sm:rounded-[2.5rem] sm:border-[10px] sm:border-neutral-900 sm:shadow-2xl dark:bg-[#0b141a]">
        {!info ? (
          <div className="grid flex-1 place-items-center text-muted">
            <Spinner />
          </div>
        ) : session ? (
          <Conversation key={session.session_id} slug={slug} name={info.name} session={session} onSession={setSession} />
        ) : (
          <ProfileGate slug={slug} name={info.name} onStart={setSession} />
        )}
      </div>
      <aside className="hidden max-w-sm sm:block">
        <p className="mb-2 text-sm font-semibold text-primary">ديمو حي</p>
        <h1 className="mb-3 text-2xl font-bold leading-snug">جرّب تطلب من {info?.name ?? "المطعم"} كأنك على واتساب</h1>
        <p className="mb-6 leading-relaxed text-muted">
          ده نفس البوت اللي هيرد على عملاءك على واتساب: نفس القوايم والزراير. الطلب بيوصل فورًا لداشبورد المطعم، ولما المطعم يقبل
          أو يبعت الأوردر، الرسالة بتظهر هنا.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link to={`/r/${slug}`}>
            <Button>
              <Store className="size-4" /> صفحة المنيو
            </Button>
          </Link>
          {session ? (
            <Button tone="ghost" onClick={() => setSession(null)}>
              <RotateCcw className="size-4" /> محادثة جديدة
            </Button>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function Header({ name, onReset }: { name: string; onReset?: () => void }) {
  return (
    <header className="flex items-center gap-3 bg-[#008069] px-3 pb-2.5 pt-3 text-white dark:bg-[#1f2c34]">
      <ArrowRight className="size-5 opacity-90" aria-hidden />
      <div className="grid size-10 place-items-center rounded-full bg-white/20 text-lg font-bold">{name.slice(0, 1)}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1 font-semibold">
          <span className="truncate">{name}</span>
          <BadgeCheck className="size-4 shrink-0 fill-[#25d366] text-[#008069]" aria-label="حساب تجاري" />
        </div>
        <div className="text-xs opacity-80">حساب تجاري · بيرد فورًا</div>
      </div>
      {onReset ? (
        <button onClick={onReset} className="rounded-full p-2 hover:bg-white/10 sm:hidden" aria-label="محادثة جديدة">
          <RotateCcw className="size-5" />
        </button>
      ) : null}
    </header>
  );
}

function ProfileGate({ slug, name, onStart }: { slug: string; name: string; onStart: (s: Session) => void }) {
  const [form, setForm] = useState({ name: "", phone: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const r = await post(`/chat/${slug}/start`, form);
      onStart({ session_id: r.session_id, name: form.name, phone: form.phone });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "حصلت مشكلة");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Header name={name} />
      <div className="wa-wall flex flex-1 items-center justify-center p-5">
        <form onSubmit={submit} className="w-full rounded-2xl bg-surface p-5 shadow-lg">
          <h2 className="mb-1 text-lg font-bold">جرّب كأنك عميل 👋</h2>
          <p className="mb-4 text-sm text-muted">على واتساب البوت بيعرف اسمك ورقمك لوحده. هنا اكتبهم مرة واحدة.</p>
          <label className="mb-3 block">
            <span className="mb-1 block text-sm font-semibold">الاسم</span>
            <input
              required
              minLength={2}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="h-11 w-full rounded-xl border border-line bg-surface px-3"
              placeholder="مثلًا: أحمد"
            />
          </label>
          <label className="mb-4 block">
            <span className="mb-1 block text-sm font-semibold">رقم الموبايل</span>
            <input
              required
              inputMode="tel"
              dir="ltr"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              className="h-11 w-full rounded-xl border border-line bg-surface px-3 text-right"
              placeholder="01xxxxxxxxx"
            />
          </label>
          {err ? <p className="mb-3 text-sm text-danger">{err}</p> : null}
          <button disabled={busy} className="h-11 w-full rounded-full bg-[#008069] font-semibold text-white disabled:opacity-60">
            {busy ? "..." : "ابدأ المحادثة"}
          </button>
        </form>
      </div>
    </>
  );
}

function Conversation({ slug, name, session, onSession }: { slug: string; name: string; session: Session; onSession: (s: Session | null) => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [sheet, setSheet] = useState<Extract<Payload, { type: "list" }> | null>(null);
  const [typing, setTyping] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const lastId = useMemo(() => msgs.reduce((m, x) => (!x.pending && x.id > m ? x.id : m), 0), [msgs]);

  const merge = (incoming: Msg[]) =>
    setMsgs((cur) => {
      const byId = new Map(cur.filter((m) => !m.pending).map((m) => [m.id, m]));
      incoming.forEach((m) => byId.set(m.id, m));
      return [...byId.values()].sort((a, b) => a.id - b.id);
    });

  useEffect(() => {
    // resume an existing session
    post(`/chat/${slug}/start`, { session_id: session.session_id, name: session.name, phone: session.phone })
      .then((r) => {
        if (r.session_id !== session.session_id) {
          onSession({ ...session, session_id: r.session_id });
          return;
        }
        merge(r.messages);
      })
      .catch(() => onSession(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  usePoll(
    async () => {
      const r = await get(`/chat/${slug}/messages?session_id=${session.session_id}&after=${lastId}`);
      if (r.messages.length) merge(r.messages);
    },
    2000,
    [lastId],
  );

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs.length, typing]);

  const send = async (kind: "text" | "button" | "list", title: string, id?: string) => {
    const temp: Msg = {
      id: Number.MAX_SAFE_INTEGER - msgs.length,
      direction: "in",
      sender: "customer",
      payload: kind === "text" ? { type: "text", text: title } : { type: kind === "button" ? "button_reply" : "list_reply", id: id!, title },
      created_at: new Date().toISOString(),
      pending: true,
    };
    setMsgs((m) => [...m, temp]);
    setTyping(true);
    try {
      const r = await post(`/chat/${slug}/send`, { session_id: session.session_id, kind, text: title, id });
      merge(r.messages);
    } catch (e) {
      setMsgs((m) => m.filter((x) => x !== temp));
      alert(e instanceof ApiError ? e.message : "الرسالة موصلتش");
    } finally {
      setTyping(false);
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    setText("");
    send("text", t);
  };

  return (
    <>
      <Header name={name} onReset={() => onSession(null)} />
      <div className="wa-wall relative flex-1 overflow-y-auto px-3 py-3">
        <div className="mx-auto mb-3 w-fit rounded-lg bg-[#fff5c4] px-3 py-1.5 text-center text-[11px] leading-relaxed text-[#54656f] shadow-sm dark:bg-[#182229] dark:text-[#ffd279]">
          🔒 ديمو: نفس تجربة واتساب، والطلبات بتوصل لداشبورد المطعم الحقيقية
        </div>
        {msgs.length === 0 ? (
          <div className="mt-10 flex flex-col items-center gap-3">
            <p className="text-sm text-[#54656f] dark:text-[#8696a0]">ابعت أي رسالة عشان تبدأ</p>
            <button onClick={() => send("text", "أهلًا")} className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-[#008069] shadow dark:bg-[#202c33] dark:text-[#00a884]">
              👋 أهلًا
            </button>
          </div>
        ) : null}
        <div className="flex flex-col gap-1.5">
          {msgs.map((m) => (
            <Bubble key={m.id} m={m} onReply={send} onOpenList={setSheet} />
          ))}
          {typing ? (
            <div className="w-fit rounded-lg rounded-tr-none bg-white px-3 py-2 shadow-sm dark:bg-[#202c33]">
              <span className="inline-flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="size-1.5 animate-bounce rounded-full bg-[#8696a0]" style={{ animationDelay: `${i * 120}ms` }} />
                ))}
              </span>
            </div>
          ) : null}
        </div>
        <div ref={bottom} />
      </div>
      <form onSubmit={submit} className="flex items-center gap-2 bg-[#f0f2f5] px-2 py-2 dark:bg-[#1f2c34]">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="اكتب رسالة"
          aria-label="اكتب رسالة"
          className="h-11 flex-1 rounded-full bg-white px-4 text-[15px] text-[#111b21] outline-none placeholder:text-[#8696a0] dark:bg-[#2a3942] dark:text-[#e9edef]"
        />
        <button aria-label="إرسال" className="grid size-11 shrink-0 place-items-center rounded-full bg-[#00a884] text-white">
          <SendHorizontal className="size-5 -scale-x-100" />
        </button>
      </form>
      {sheet ? (
        <ListSheet
          list={sheet}
          onClose={() => setSheet(null)}
          onPick={(row) => {
            setSheet(null);
            send("list", row.title, row.id);
          }}
        />
      ) : null}
    </>
  );
}

function Bubble({ m, onReply, onOpenList }: { m: Msg; onReply: (k: "button", title: string, id: string) => void; onOpenList: (l: any) => void }) {
  const mine = m.direction === "in";
  const p = m.payload;
  const base = "relative max-w-[85%] rounded-lg px-2.5 pb-1.5 pt-1.5 text-[14.5px] leading-relaxed shadow-sm";
  const time = (
    <span className="float-left mr-2 mt-1.5 inline-flex items-center gap-0.5 text-[10.5px] text-[#667781] dark:text-[#8696a0]">
      {clock(m.created_at)}
      {mine ? <CheckCheck className={`size-3.5 ${m.pending ? "text-[#8696a0]" : "text-[#53bdeb]"}`} /> : null}
    </span>
  );
  if (mine) {
    const label = p.type === "text" ? p.text : "title" in p ? p.title : "";
    return (
      <div className={`${base} fade-in self-end rounded-tl-none bg-[#d9fdd3] text-[#111b21] dark:bg-[#005c4b] dark:text-[#e9edef]`}>
        <span className="whitespace-pre-wrap break-words">{label}</span>
        {time}
      </div>
    );
  }
  const body = "body" in p ? p.body : "";
  return (
    <div className="fade-in flex max-w-[85%] flex-col self-start">
      <div className={`${base} max-w-none rounded-tr-none bg-white text-[#111b21] dark:bg-[#202c33] dark:text-[#e9edef] ${p.type !== "text" ? "rounded-b-none" : ""}`}>
        {m.sender === "staff" ? <div className="mb-0.5 text-xs font-semibold text-[#008069] dark:text-[#00a884]">فريق المطعم</div> : null}
        <span className="whitespace-pre-wrap break-words">{body}</span>
        {time}
      </div>
      {p.type === "buttons" ? (
        <div className="flex flex-col gap-px overflow-hidden rounded-b-lg">
          {p.buttons.map((b) => (
            <button
              key={b.id}
              onClick={() => onReply("button", b.title, b.id)}
              className="bg-white py-2.5 text-center text-[14.5px] font-medium text-[#00a5f4] hover:bg-[#f5f6f6] dark:bg-[#202c33] dark:text-[#53bdeb] dark:hover:bg-[#26343d]"
            >
              {b.title}
            </button>
          ))}
        </div>
      ) : null}
      {p.type === "list" ? (
        <button
          onClick={() => onOpenList(p)}
          className="flex items-center justify-center gap-2 rounded-b-lg border-t border-[#e9edef] bg-white py-2.5 text-[14.5px] font-medium text-[#00a5f4] hover:bg-[#f5f6f6] dark:border-[#2a3942] dark:bg-[#202c33] dark:text-[#53bdeb]"
        >
          <ListIcon className="size-4" /> {p.button}
        </button>
      ) : null}
    </div>
  );
}

function ListSheet({ list, onClose, onPick }: { list: Extract<Payload, { type: "list" }>; onClose: () => void; onPick: (r: Row) => void }) {
  const [sel, setSel] = useState<Row | null>(null);
  return (
    <div className="absolute inset-0 z-20 flex flex-col justify-end bg-black/40" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet-in flex max-h-[80%] flex-col rounded-t-2xl bg-white dark:bg-[#111b21]" role="dialog" aria-label={list.button}>
        <div className="flex items-center gap-3 border-b border-[#e9edef] px-4 py-3 dark:border-[#2a3942]">
          <button onClick={onClose} aria-label="إغلاق" className="text-[#54656f] dark:text-[#aebac1]">
            <X className="size-5" />
          </button>
          <div className="flex-1 text-center font-semibold text-[#111b21] dark:text-[#e9edef]">{list.button}</div>
          <span className="w-5" />
        </div>
        <div className="flex-1 overflow-y-auto">
          {list.sections.map((s) => (
            <div key={s.title}>
              <div className="px-5 pb-1 pt-4 text-[13px] font-semibold text-[#008069] dark:text-[#00a884]">{s.title}</div>
              {s.rows.map((r) => (
                <label key={r.id} className="flex cursor-pointer items-center gap-3 px-5 py-2.5 hover:bg-[#f5f6f6] dark:hover:bg-[#202c33]">
                  <div className="min-w-0 flex-1">
                    <div className="text-[15px] text-[#111b21] dark:text-[#e9edef]">{r.title}</div>
                    {r.description ? <div className="text-[13px] text-[#667781] dark:text-[#8696a0]">{r.description}</div> : null}
                  </div>
                  <input type="radio" name="row" className="size-5 accent-[#008069]" checked={sel?.id === r.id} onChange={() => setSel(r)} />
                </label>
              ))}
            </div>
          ))}
        </div>
        <div className="border-t border-[#e9edef] p-3 dark:border-[#2a3942]">
          <button
            disabled={!sel}
            onClick={() => sel && onPick(sel)}
            className="h-11 w-full rounded-full bg-[#008069] font-semibold text-white disabled:opacity-40"
          >
            إرسال
          </button>
        </div>
      </div>
    </div>
  );
}
