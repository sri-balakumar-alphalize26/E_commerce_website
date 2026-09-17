/* ==========================================================================
   369 Mart — payment helpers and the demo payment gateway.
   Replace `demoGateway` with your real flow (Razorpay / PayU / Cashfree order
   created by Odoo, then verify the signature server-side before marking paid).
   ========================================================================== */

export const WALLET_BALANCE = 250;
export const COD_LIMIT = 5000;

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

export const SAVED_CARDS = [
  { id: "c4821", brand: "visa", last4: "4821", name: "Demo User", exp: "08/29", bank: "HDFC Bank" },
];

/* ---------- cards ---------- */
export function cardBrand(num) {
  const n = num.replace(/\D/g, "");
  if (/^3[47]/.test(n)) return "amex";
  if (/^(60|65|81|82|508)/.test(n)) return "rupay";
  if (/^(5[1-5]|2[2-7])/.test(n)) return "mastercard";
  if (/^4/.test(n)) return "visa";
  return "";
}
export const BRAND_LABEL = { visa: "VISA", mastercard: "Mastercard", rupay: "RuPay", amex: "AMEX" };

export function formatCard(num) {
  const n = num.replace(/\D/g, "").slice(0, cardBrand(num) === "amex" ? 15 : 16);
  return cardBrand(n) === "amex" ? n.replace(/^(\d{0,4})(\d{0,6})(\d{0,5}).*/, (m, a, b, c) => [a, b, c].filter(Boolean).join(" ")) : n.replace(/(\d{4})(?=\d)/g, "$1 ");
}
export function luhn(num) {
  const n = num.replace(/\D/g, "");
  if (n.length < 13) return false;
  let sum = 0, alt = false;
  for (let i = n.length - 1; i >= 0; i--) {
    let d = +n[i];
    if (alt) { d *= 2; if (d > 9) d -= 9; }
    sum += d; alt = !alt;
  }
  return sum % 10 === 0;
}
export function formatExpiry(v) {
  const n = v.replace(/\D/g, "").slice(0, 4);
  return n.length > 2 ? n.slice(0, 2) + "/" + n.slice(2) : n;
}
export function expiryOk(v) {
  const m = v.match(/^(\d{2})\/(\d{2})$/);
  if (!m) return false;
  const mm = +m[1], yy = 2000 + +m[2];
  if (mm < 1 || mm > 12) return false;
  const now = new Date();
  return yy > now.getFullYear() || (yy === now.getFullYear() && mm >= now.getMonth() + 1);
}

/* ---------- UPI ---------- */
export const upiOk = (v) => /^[a-z0-9._-]{2,}@[a-z]{2,}$/i.test(v.trim());

/* ---------- ids ---------- */
export function newOrderId(mode) {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${mode === "all" ? "369E" : "369M"}-${String(d.getFullYear()).slice(2)}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${Math.floor(Math.random() * 90 + 10)}`;
}
export const newTxnId = () => "TXN" + Date.now().toString().slice(-10);

/* ---------- demo gateway ----------
   Resolves like a real gateway would after the customer approves.
   Demo rules so every screen can be seen:
     UPI ID containing "fail"  → declined
     card ending 0002          → declined after OTP
     OTP                       → any 6 digits except 000000
*/
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
export const demoGateway = {
  async verifyUpi(vpa) {
    await wait(900);
    if (!upiOk(vpa)) return { ok: false, error: "Enter a valid UPI ID, like name@okaxis" };
    const user = vpa.split("@")[0].replace(/[._-]+/g, " ").replace(/\d+/g, "").trim() || "UPI user";
    return { ok: true, name: user.replace(/\b\w/g, (c) => c.toUpperCase()) };
  },
  async collectUpi({ vpa }) {
    await wait(3200);
    return /fail/i.test(vpa || "") ? { ok: false, error: "The payment request was declined in your UPI app." } : { ok: true, txn: newTxnId() };
  },
  async verifyOtp({ otp, card }) {
    await wait(1100);
    if (otp === "000000") return { ok: false, retry: true, error: "Incorrect OTP. Please try again." };
    if ((card || "").replace(/\D/g, "").endsWith("0002")) return { ok: false, error: "Your bank declined this transaction." };
    return { ok: true, txn: newTxnId() };
  },
  async netbanking() { await wait(2600); return { ok: true, txn: newTxnId() }; },
  async wallet() { await wait(1200); return { ok: true, txn: newTxnId() }; },
  async cod() { await wait(1200); return { ok: true, txn: "COD" + Date.now().toString().slice(-8) }; },
};
