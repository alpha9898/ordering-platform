import { useState } from "react";
import { MessageCircle } from "lucide-react";
import { get } from "../../lib/api";
import { displayPhone, timeAgo } from "../../lib/format";
import { useNow, usePoll } from "../../lib/hooks";
import { messageText, type ConvSummary } from "../../lib/types";
import { Badge, Card, Empty, Spinner } from "../../components/ui";

export default function Chats({ onOpen }: { onOpen: (id: number) => void }) {
  const [convs, setConvs] = useState<ConvSummary[] | null>(null);
  const now = useNow();
  usePoll(async () => setConvs((await get("/dash/conversations")).conversations), 5000);

  if (!convs)
    return (
      <div className="grid h-40 place-items-center text-muted">
        <Spinner />
      </div>
    );
  const sorted = [...convs].sort((a, b) => Number(!!b.human_requested_at) - Number(!!a.human_requested_at));
  return (
    <Card className="divide-y divide-line">
      {!sorted.length ? (
        <Empty icon={<MessageCircle className="size-8" />} title="مفيش محادثات لسه" />
      ) : (
        sorted.map((c) => (
          <button key={c.id} onClick={() => onOpen(c.id)} className="flex w-full items-center gap-3 px-4 py-3 text-right hover:bg-surface-2">
            <div className="grid size-10 shrink-0 place-items-center rounded-full bg-primary-soft font-bold text-primary">{(c.customer?.name ?? "؟").slice(0, 1)}</div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-semibold">{c.customer?.name ?? "عميل"}</span>
                <span className="num text-xs text-muted" dir="ltr">
                  {displayPhone(c.customer?.phone)}
                </span>
                {c.human_requested_at ? <Badge tone="danger">طالب موظف</Badge> : null}
              </div>
              <p className="truncate text-sm text-muted">{messageText(c.last_message?.payload).split("\n")[0]}</p>
            </div>
            <span className="shrink-0 text-xs text-muted">{timeAgo(c.last_message_at, now)}</span>
          </button>
        ))
      )}
    </Card>
  );
}
