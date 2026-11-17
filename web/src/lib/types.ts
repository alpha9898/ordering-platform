import type { OrderStatus } from "./format";

export type OrderLine = {
  name: string;
  variant: string | null;
  unit_price: number;
  qty: number;
  line_total: number;
  note: string | null;
  addons: { name: string; price: number }[];
};

export type Order = {
  id: number;
  order_no: number;
  business_day: string;
  status: OrderStatus;
  channel: "web_chat" | "web_menu" | "whatsapp";
  fulfillment: "delivery" | "pickup";
  zone: string | null;
  subtotal: number;
  delivery_fee: number;
  total: number;
  payment_method: "cod" | "wallet";
  payment_status: string;
  reject_reason: string | null;
  eta_minutes: number | null;
  created_at: string;
  updated_at: string;
  items: OrderLine[];
  events: { status: OrderStatus; at: string }[];
  customer?: { name: string | null; phone: string } | null;
  address?: string | null;
  notes?: string | null;
  is_demo?: boolean;
  conversation_id?: number | null;
  public_token?: string;
};

export type ConvSummary = {
  id: number;
  channel: string;
  state: string;
  customer: { name: string | null; phone: string } | null;
  human_requested_at: string | null;
  bot_paused_until: string | null;
  last_message: ChatMessage | null;
  last_message_at: string | null;
};

export type ChatMessage = {
  id: number;
  direction: "in" | "out";
  sender: "customer" | "bot" | "staff";
  payload: any;
  created_at: string | null;
};

export type Board = {
  orders: Order[];
  human: ConvSummary[];
  accepting_orders: boolean;
  eta_minutes: number;
  open_now: boolean;
};

export function messageText(p: any): string {
  if (!p) return "";
  if (p.type === "text") return p.body ?? p.text ?? "";
  if (p.type === "button_reply" || p.type === "list_reply") return p.title;
  if (p.type === "buttons") return `${p.body}\n[${p.buttons.map((b: any) => b.title).join(" | ")}]`;
  if (p.type === "list") return `${p.body}\n[☰ ${p.button}]`;
  return "";
}
