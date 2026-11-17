import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, SendHorizontal } from "lucide-react";
import { ApiError, get, post } from "../../lib/api";
import { clock, displayPhone } from "../../lib/format";
import { usePoll } from "../../lib/hooks";
import { messageText, type ChatMessage, type ConvSummary } from "../../lib/types";
import { Badge, Button, Modal, Spinner, useToast } from "../../components/ui";

export default function ChatPanel({ convId, onClose }: { convId: number | null; onClose: () => void }) {
  const toast = useToast();
  const [conv, setConv] = useState<ConvSummary | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const lastId = useMemo(() => (msgs.length ? msgs[msgs.length - 1].id : 0), [msgs]);

  useEffect(() => {
    setConv(null);
    setMsgs([]);
  }, [convId]);

  usePoll(
    async () => {
      if (!convId) return;
      const r = await get(`/dash/conversations/${convId}/messages?after=${lastId}`);
      setConv(r.conversation);
      if (r.messages.length) setMsgs((m) => [...m, ...r.messages.filter((x: ChatMessage) => !m.some((y) => y.id === x.id))]);
    },
    3000,
    [convId, lastId],
  );

  useEffect(() => bottom.current?.scrollIntoView({ block: "end" }), [msgs.length]);

  const reply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || !convId) return;
    setBusy(true);
    try {
      const m = await post(`/dash/conversations/${convId}/reply`, { text: text.trim() });
      setMsgs((x) => [...x, m]);
      setText("");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "مبعتتش", "danger");
    } finally {
      setBusy(false);
    }
  };

  const resolve = async () => {
    if (!convId) return;
    await post(`/dash/conversations/${convId}/resolve`);
    toast("البوت رجع يرد على العميل");
    onClose();
  };

  const canReply = conv?.channel === "web_chat";
  return (
    <Modal open={!!convId} onClose={onClose} title={conv?.customer ? `${conv.customer.name ?? "عميل"} · ${displayPhone(conv.customer.phone)}` : "المحادثة"}>
      {!conv ? (
        <div className="grid h-40 place-items-center text-muted">
          <Spinner />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {conv.human_requested_at ? <Badge tone="warn">طالب موظف</Badge> : null}
            {conv.bot_paused_until && new Date(conv.bot_paused_until) > new Date() ? (
              <Badge tone="info">البوت متوقف لحد {clock(conv.bot_paused_until)}</Badge>
            ) : (
              <Badge tone="ok">البوت شغال</Badge>
            )}
            {conv.human_requested_at || conv.state === "HUMAN" ? (
              <Button size="sm" tone="primary" className="ms-auto" onClick={resolve}>
                <Bot className="size-4" /> رجّع البوت
              </Button>
            ) : null}
          </div>
          <div className="wa-wall h-80 space-y-1.5 overflow-y-auto rounded-xl p-3">
            {msgs.map((m) => (
              <div
                key={m.id}
                className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-1.5 text-sm shadow-sm ${
                  m.direction === "in"
                    ? "me-auto bg-white text-[#111b21] dark:bg-[#202c33] dark:text-[#e9edef]"
                    : m.sender === "staff"
                      ? "ms-auto bg-[#cfe9fe] text-[#111b21] dark:bg-[#123a5a] dark:text-[#e9edef]"
                      : "ms-auto bg-[#d9fdd3] text-[#111b21] dark:bg-[#005c4b] dark:text-[#e9edef]"
                }`}
              >
                {m.direction === "out" ? <div className="text-[11px] font-semibold opacity-60">{m.sender === "staff" ? "أنت" : "البوت"}</div> : null}
                {messageText(m.payload)}
                <div className="text-left text-[10px] opacity-50">{clock(m.created_at)}</div>
              </div>
            ))}
            <div ref={bottom} />
          </div>
          {canReply ? (
            <form onSubmit={reply} className="flex gap-2">
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="اكتب رد للعميل…" className="h-10 flex-1 rounded-xl border border-line bg-surface px-3 text-sm" />
              <Button tone="primary" loading={busy} aria-label="إرسال">
                <SendHorizontal className="size-4 -scale-x-100" />
              </Button>
            </form>
          ) : (
            <p className="text-xs text-muted">الرد من هنا متاح لمحادثات الويب. واتساب هيتفعل لما نربطه.</p>
          )}
          <p className="text-xs text-muted">لما ترد، البوت بيسكت 30 دقيقة عشان ميقاطعكش.</p>
        </div>
      )}
    </Modal>
  );
}
