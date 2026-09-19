/* ==========================================================================
   369 Mart — the names and shapes a payment screen needs to draw itself:
   UPI apps, banks, card brands, and the reference the app puts on an order.

   What a payment *does* belongs to the shop, through /369mart/payment/*.
   There used to be a `demoGateway` here that resolved the way a real one
   would - a UPI ID containing "fail" was declined, any OTP but 000000
   passed, cash always succeeded - and the app believed it. A wallet balance
   and a cash-on-delivery ceiling sat beside it as constants; both are the
   shop's configuration now, and it says which methods it can take at all.
   ========================================================================== */

export const UPI_APPS = [
  { key: "gpay", name: "Google Pay", short: "G Pay", tone: "#1a73e8", handle: "@okaxis" },
  { key: "phonepe", name: "PhonePe", short: "Pe", tone: "#5f259f", handle: "@ybl" },
  { key: "paytm", name: "Paytm", short: "Paytm", tone: "#00baf2", handle: "@paytm" },
  { key: "bhim", name: "BHIM", short: "BHIM", tone: "#f47b20", handle: "@upi" },
];

export const BANKS = [
  { key: "sbi", name: "State Bank of India", short: "SBI", tone: "#1b5fa8" },
  { key: "hdfc", name: "HDFC Bank", short: "HDFC", tone: "#0e3a7a" },
  { key: "icici", name: "ICICI Bank", short: "ICICI", tone: "#b3202a" },
  { key: "axis", name: "Axis Bank", short: "AXIS", tone: "#8a1538" },
  { key: "fed", name: "Federal Bank", short: "FED", tone: "#d9a400" },
  { key: "sib", name: "South Indian Bank", short: "SIB", tone: "#c3282e" },
  { key: "kotak", name: "Kotak Mahindra Bank", short: "KOTAK", tone: "#e1261c" },
  { key: "canara", name: "Canara Bank", short: "CAN", tone: "#0b7bc1" },
];

/* ---------- cards ---------- */
export const BRAND_LABEL = { visa: "VISA", mastercard: "Mastercard", rupay: "RuPay", amex: "AMEX" };

/* ---------- UPI ---------- */
export const upiOk = (v) => /^[a-z0-9._-]{2,}@[a-z]{2,}$/i.test(v.trim());

/* ---------- the order's reference ----------
   The app's, not the shop's, and deliberately: it is what makes a double tap
   safe. Placing again with the same reference settles the same draft instead
   of making a second order. */
export function newOrderId(mode) {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${mode === "all" ? "369E" : "369M"}-${String(d.getFullYear()).slice(2)}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${Math.floor(Math.random() * 90 + 10)}`;
}
