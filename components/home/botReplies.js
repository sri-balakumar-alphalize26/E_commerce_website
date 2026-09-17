/* ==========================================================================
   369 Mart — support bot brain (demo)
   reply(text, ctx) → { text, actions?, chips?, agent? }
   ctx = { orders, wallet, now }
   Replace with your helpdesk / LLM endpoint: keep the same return shape so the
   chat UI (SupportBot.jsx) does not change.
   ========================================================================== */
import { inr } from "./shared";

export const BOT_NAME = "Mitra";
export const AGENT_NAME = "Anjali";

export const START_CHIPS = ["Track my order", "Refund status", "Cancel an order", "Payment issue", "Delivery charges", "Talk to an agent"];

const ACTIVE = ["placed", "packed", "shipped", "out"];
const STATUS_WORDS = {
  placed: "confirmed and being packed",
  packed: "packed and waiting for a rider",
  shipped: "shipped and on its way to your city",
  out: "out for delivery",
  delivered: "delivered",
  cancelled: "cancelled",
};

export function greeting(ctx) {
  const active = ctx.orders.find((o) => ACTIVE.includes(o.status));
  return {
    text: active
      ? `Hi! I'm ${BOT_NAME}, your 369 Mart assistant. I can see order #${active.id} is ${STATUS_WORDS[active.status]}. What can I help with?`
      : `Hi! I'm ${BOT_NAME}, your 369 Mart assistant. Ask me about orders, refunds, payments or delivery.`,
    chips: START_CHIPS,
  };
}

const has = (t, re) => re.test(t);

export function reply(input, ctx) {
  const t = input.toLowerCase().trim();
  const { orders, wallet } = ctx;
  const active = orders.filter((o) => ACTIVE.includes(o.status));
  const lastDelivered = orders.find((o) => o.status === "delivered");
  const cancelled = orders.filter((o) => o.status === "cancelled");
  const idMatch = t.match(/369[me]-?\d{6,}/i);
  const byId = idMatch && orders.find((o) => o.id.toLowerCase().replace("-", "") === idMatch[0].toLowerCase().replace("-", ""));

  if (has(t, /^(hi|hello|hey|hai|namaste)\b/)) return { text: "Hello! How can I help you today?", chips: START_CHIPS };
  if (has(t, /thank|thanks|ok(ay)?\b|great|done/)) return { text: "Happy to help! Anything else?", chips: ["No, that's all", "Talk to an agent"] };
  if (has(t, /that's all|no,? that/)) return { text: "Have a great day! Tap the bot any time you need us." };

  if (byId) {
    return {
      text: `Order #${byId.id} is ${STATUS_WORDS[byId.status] || byId.status}${byId.status === "out" && byId.eta ? `, arriving in ${byId.eta}` : ""}. Total ${inr(byId.total)}, paid via ${byId.pay}.`,
      actions: [{ label: byId.status === "delivered" || byId.status === "cancelled" ? "Order details" : "Track order", go: ["track", byId.id] }],
    };
  }

  if (has(t, /agent|human|person|call|executive|customer care/)) return { text: "Connecting you to a support agent…", agent: true };

  if (has(t, /refund|money back|returned money/)) {
    const c = cancelled[0];
    return {
      text: c
        ? `Order #${c.id} was cancelled. ${(c.eta || "The refund goes back to your original payment in 3–5 working days").replace(/\.?$/, ".")} Refunds to 369 Wallet are instant — your wallet balance is ${inr(wallet)}.`
        : `No refunds are pending. Refunds to the original payment take 3–5 working days; refunds to 369 Wallet are instant. Your wallet balance is ${inr(wallet)}.`,
      actions: [{ label: "Open 369 Wallet", go: ["account", "wallet"] }],
    };
  }

  if (has(t, /track|where|status|late|arriv|when will/)) {
    if (!active.length) return { text: "You don't have any orders on the way right now.", actions: [{ label: "See all orders", go: ["account", "orders"] }] };
    const o = active[0];
    return {
      text: `Order #${o.id} is ${STATUS_WORDS[o.status]}${o.status === "out" && o.eta ? ` and should reach you in about ${o.eta}` : o.eta ? `. ${o.eta}` : ""}.${active.length > 1 ? ` You have ${active.length} active orders.` : ""}`,
      actions: active.slice(0, 2).map((x) => ({ label: `Track #${x.id.slice(-4)}`, go: ["track", x.id] })),
    };
  }

  if (has(t, /cancel/)) {
    const o = active.find((x) => x.status === "placed") || active[0];
    if (!o) return { text: "There's no active order to cancel." };
    return o.status === "placed"
      ? { text: `Order #${o.id} can still be cancelled. Open it and tap Cancel — you can pick a refund to your wallet (instant) or the original payment.`, actions: [{ label: "Open order to cancel", go: ["track", o.id] }] }
      : { text: `Order #${o.id} is already ${STATUS_WORDS[o.status]}, so it can't be cancelled now. You can return or replace items after delivery.`, actions: [{ label: "Track order", go: ["track", o.id] }] };
  }

  if (has(t, /return|replace|damaged|missing|wrong item|broken|spoil|rotten/)) {
    return lastDelivered
      ? { text: `Sorry about that! For order #${lastDelivered.id}, tap “Return or replace”, choose the items and a pickup slot. Returns are open for 7 days after delivery.`, actions: [{ label: "Return or replace", go: ["track", lastDelivered.id] }] }
      : { text: "Returns open once an order is delivered and stay open for 7 days." };
  }

  if (has(t, /debited, no order/)) return { text: "No worries — that amount is held by your bank and released within 48 hours. If it isn't, share the UPI reference number with an agent.", chips: ["Talk to an agent"] };
  if (has(t, /pay|upi|card|charged|deduct|failed|debited|otp/)) {
    return {
      text: "If money was debited but the order failed, it's reversed automatically to your account within 48 hours. You can manage saved cards and UPI IDs in your account.",
      chips: ["Money debited, no order", "Talk to an agent"],
      actions: [{ label: "Saved payments", go: ["account", "payments"] }],
    };
  }

  if (has(t, /deliver|charge|fee|free|minimum|express|quick|how fast|area|pincode/)) {
    return { text: "Quick: groceries in 10–20 min, ₹30 delivery, free above ₹499, minimum order ₹99. Express: electronics and home items in 2–5 days, ₹49 delivery, free above ₹999." };
  }
  if (has(t, /coupon|offer|discount|promo|code/)) return { text: "Current codes: QUICK20 (20% off Quick, up to ₹60), WELCOME50 (₹50 off above ₹499), FREEDEL (free delivery above ₹299).", actions: [{ label: "See all offers", go: ["offers"] }] };
  if (has(t, /wallet|balance|cashback/)) return { text: `Your 369 Wallet balance is ${inr(wallet)}. It can be used at checkout and never expires.`, actions: [{ label: "Open 369 Wallet", go: ["account", "wallet"] }] };
  if (has(t, /address|location/)) return { text: "You can add or change delivery addresses in your account, or tap the location at the top of the page.", actions: [{ label: "Delivery addresses", go: ["account", "address"] }] };

  return { text: "I'm not sure I got that. Pick a topic below, or I can connect you to an agent.", chips: START_CHIPS };
}

export function agentReply(input, ctx) {
  const active = ctx.orders.find((o) => ACTIVE.includes(o.status));
  return /hi|hello/i.test(input)
    ? "Hi, how can I help?"
    : `Thanks for the details. I've noted this${active ? ` against order #${active.id}` : ""} and will update you here within 30 minutes.`;
}
