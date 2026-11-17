export type OrderStatus =
  | "placed"
  | "accepted"
  | "preparing"
  | "out_for_delivery"
  | "ready_for_pickup"
  | "completed"
  | "rejected"
  | "cancelled";

export const STATUS_LABEL: Record<OrderStatus, string> = {
  placed: "جديد",
  accepted: "مقبول",
  preparing: "بيتجهز",
  out_for_delivery: "خرج للتوصيل",
  ready_for_pickup: "جاهز للاستلام",
  completed: "اتسلم",
  rejected: "مرفوض",
  cancelled: "ملغي",
};

export const STATUS_TONE: Record<OrderStatus, "warn" | "info" | "primary" | "ok" | "danger" | "muted"> = {
  placed: "warn",
  accepted: "info",
  preparing: "info",
  out_for_delivery: "primary",
  ready_for_pickup: "primary",
  completed: "ok",
  rejected: "danger",
  cancelled: "muted",
};

export const CHANNEL_LABEL: Record<string, string> = {
  web_chat: "شات",
  web_menu: "منيو أونلاين",
  whatsapp: "واتساب",
};

export const PAYMENT_LABEL: Record<string, string> = { cod: "كاش", wallet: "محفظة" };

export function money(v: number | string | null | undefined): string {
  const n = Number(v ?? 0);
  return `${Number.isInteger(n) ? n : n.toFixed(2)} ج`;
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 45) return "دلوقتي";
  const m = Math.round(s / 60);
  if (m < 60) return `من ${m} د`;
  const h = Math.floor(m / 60);
  if (h < 24) return `من ${h} س`;
  return new Date(iso).toLocaleDateString("ar-EG");
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("ar-EG", { hour: "numeric", minute: "2-digit" });
}

export function displayPhone(p: string | null | undefined): string {
  if (!p) return "";
  if (p.startsWith("20") && p.length === 12) return "0" + p.slice(2);
  return p;
}

export function waLink(p: string): string {
  return `https://wa.me/${p}`;
}

export function mapsLink(address: string): string {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
}
