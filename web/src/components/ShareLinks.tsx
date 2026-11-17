import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Copy, ExternalLink } from "lucide-react";
import { Button, useToast } from "./ui";

export function ShareLinks({ slug }: { slug: string }) {
  const origin = window.location.origin;
  const links = [
    { label: "ديمو الشات (شكل واتساب)", url: `${origin}/r/${slug}/chat` },
    { label: "صفحة المنيو أونلاين", url: `${origin}/r/${slug}` },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {links.map((l) => (
        <LinkCard key={l.url} {...l} />
      ))}
    </div>
  );
}

function LinkCard({ label, url }: { label: string; url: string }) {
  const toast = useToast();
  const [qr, setQr] = useState("");
  useEffect(() => {
    QRCode.toDataURL(url, { margin: 1, width: 240, color: { dark: "#111111", light: "#ffffff" } }).then(setQr);
  }, [url]);
  return (
    <div className="flex gap-3 rounded-xl border border-line p-3">
      {qr ? <img src={qr} alt={`QR ${label}`} className="size-24 rounded-lg bg-white p-1" /> : <div className="size-24" />}
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="text-sm font-semibold">{label}</div>
        <div className="truncate text-xs text-muted" dir="ltr">
          {url}
        </div>
        <div className="mt-auto flex gap-1">
          <Button
            size="sm"
            onClick={() => {
              navigator.clipboard?.writeText(url);
              toast("اتنسخ");
            }}
          >
            <Copy className="size-3.5" /> نسخ
          </Button>
          <a href={url} target="_blank" rel="noreferrer">
            <Button size="sm" tone="ghost">
              <ExternalLink className="size-3.5" /> فتح
            </Button>
          </a>
        </div>
      </div>
    </div>
  );
}
