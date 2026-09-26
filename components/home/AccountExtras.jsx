"use client";
/* ==========================================================================
   369 Mart — Account extras
   369 Wallet · Saved payments · Coupons & rewards (scratch cards) ·
   Ratings & reviews · Notifications (+ preferences) · Refer & earn

   Motion
   - wallet: balance counts up, card sheen, add-money sheet with UPI wait →
     coins drop into the wallet; transactions cascade, grouped by month
   - saved payments: cards tilt with the pointer, new card drops in, removed
     card folds away; add-card form shows the live flipping card preview
   - rewards: scratch with finger/mouse on a foil canvas; at 45% it clears
     itself, confetti bursts and the reward lands (cashback → wallet)
   - reviews: tap stars on a pending product → editor sheet; posted review
     slides into "Your reviews"; edit / delete fold
   - notifications: unread dots pop out on read, swipe a row sideways to
     dismiss, preference switches spring
   - refer & earn: gift lid hops, code letters flip in, progress fills with
     milestone dots, invited friend rows pop in
   ========================================================================== */
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon, Thumb, money } from "./shared";
import { Amount, useRules } from "./Cart";
import { BRAND_LABEL, UPI_APPS, upiOk } from "./payment";
import { EARN_WHEN, pointsText } from "./points";
import {
  REFER_GOAL, STAR_WORDS, ago, fmtDate, fmtDateTime, useRemote,
} from "./accountStore";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/* null until mounted, then ticks each 30 s (keeps server and client HTML equal) */
function useNow() {
  const [now, setNow] = useState(null);
  useEffect(() => { setNow(Date.now()); const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t); }, []);
  return now;
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {
    try {
      const t = document.createElement("textarea"); t.value = text; t.style.position = "fixed"; t.style.opacity = "0";
      document.body.appendChild(t); t.select(); const ok = document.execCommand("copy"); t.remove(); return ok;
    } catch (e2) { return false; }
  }
}

/* ---------------- shared bits ---------------- */
export function Sheet({ title, onClose, children, foot, wide, className = "" }) {
  const [out, setOut] = useState(false);
  const close = () => { if (reduced()) return onClose(); setOut(true); setTimeout(onClose, 260); };
  useEffect(() => {
    const k = (e) => e.key === "Escape" && close();
    window.addEventListener("keydown", k);
    document.documentElement.classList.add("ls-lock");
    return () => { window.removeEventListener("keydown", k); document.documentElement.classList.remove("ls-lock"); };
  }); // eslint-disable-line
  return createPortal(
    <div className={"ot-sheet-wrap ax-sheet-wrap" + (out ? " ot-out" : "")} onClick={close}>
      <section className={"ot-sheet " + (wide ? "ot-wide " : "") + className} role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <span className="ot-grab" />
        <header><h3>{title}</h3><button className="ot-x" onClick={close} aria-label="Close"><Icon n="x" size={16} /></button></header>
        <div className="ot-sheet-body">{typeof children === "function" ? children(close) : children}</div>
        {foot && <footer>{typeof foot === "function" ? foot(close) : foot}</footer>}
      </section>
    </div>,
    document.querySelector(".hm-page") || document.body
  );
}

function Tabs({ tabs, value, onChange }) {
  return (
    <div className="ac-tabs" role="tablist" style={{ "--n": tabs.length, "--t": Math.max(0, tabs.findIndex((t) => t[0] === value)) }}>
      <span className="ac-tabs-thumb" aria-hidden="true" />
      {tabs.map(([k, l, n]) => (
        <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)}>{l}{n ? <em className="ax-tabcount">{n}</em> : null}</button>
      ))}
    </div>
  );
}

function Switch({ on, onChange, label, disabled }) {
  return (
    <label className={"ax-switch" + (on ? " ax-on" : "") + (disabled ? " ax-locked" : "")}>
      <input type="checkbox" checked={on} disabled={disabled} onChange={(e) => onChange(e.target.checked)} aria-label={label} />
      <i aria-hidden="true" />
    </label>
  );
}

function Confetti({ n = 22 }) {
  const bits = useMemo(() => Array.from({ length: n }, (_, i) => ({
    a: (i / n) * 360 + Math.random() * 12, d: 70 + Math.random() * 70, c: ["#f7931e", "#0a78ab", "#1f8a3c", "#e23d4b", "#ffc23d"][i % 5], r: Math.random() * 360, s: 0.7 + Math.random() * 0.6,
  })), [n]);
  return (
    <span className="ax-confetti" aria-hidden="true">
      {bits.map((b, i) => <i key={i} style={{ "--a": b.a + "deg", "--d": b.d + "px", "--c": b.c, "--r": b.r + "deg", "--s": b.s }} />)}
    </span>
  );
}

function StarPick({ value, onPick, size = 30, label = true }) {
  const [hover, setHover] = useState(0);
  const shown = hover || value;
  return (
    <div className="ax-starpick" onMouseLeave={() => setHover(0)}>
      <div role="radiogroup" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((k) => (
          <button key={k} type="button" role="radio" aria-checked={value === k} aria-label={`${k} star${k > 1 ? "s" : ""}`}
            className={(k <= shown ? "ax-lit" : "") + (k === value ? " ax-cur" : "")} style={{ "--k": k }}
            onMouseEnter={() => setHover(k)} onFocus={() => setHover(k)} onBlur={() => setHover(0)} onClick={() => onPick(k)}>
            <Icon n="star" size={size} />
          </button>
        ))}
      </div>
      {label && <span className={"ax-starword ax-s" + shown} key={shown}>{STAR_WORDS[shown] || "Tap to rate"}</span>}
    </div>
  );
}

const Chip = ({ stars }) => <span className={"ax-starchip ax-s" + stars}>{stars}<Icon n="star" size={11} /></span>;

/* ==========================================================================
   369 Wallet
   ========================================================================== */
const KIND_META = {
  add: { icon: "plus", label: "Added", sign: "+" },
  spend: { icon: "bag", label: "Spent", sign: "−" },
  refund: { icon: "reorder", label: "Refund", sign: "+" },
  reward: { icon: "gift", label: "Reward", sign: "+" },
};

export function WalletSec({ onNav }) {
  const { data, loading } = useRemote("/wallet");
  const log = useMemo(() => data?.ledger || [], [data]);
  const balance = data?.balance ?? 0;
  const [tab, setTab] = useState("all");
  const sum = (kinds) => log.filter((t) => kinds.includes(t.kind)).reduce((s, t) => s + t.amount, 0);
  const list = log.filter((t) => tab === "all" || (tab === "refund" ? t.kind === "refund" || t.kind === "reward" : t.kind === tab));
  const groups = [];
  list.forEach((t) => {
    const m = new Date(t.at).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
    const g = groups[groups.length - 1];
    if (g && g.m === m) g.items.push(t); else groups.push({ m, items: [t] });
  });
  let row = 0;
  return (
    <div className="ac-stack">
      <section className="ax-wallet">
        <span className="ax-wallet-sheen" aria-hidden="true" />
        <span className="ax-wallet-deco" aria-hidden="true"><i /><i /><i /></span>
        <div className="ax-wallet-top">
          <span className="ax-wallet-ic"><Icon n="wallet" size={22} /></span>
          <span><small>369 Wallet balance</small><b className="ax-wallet-amt">{loading ? <i className="ax-wait">…</i> : <Amount value={balance} />}</b></span>
        </div>
        <div className="ax-wallet-stats">
          <span style={{ "--i": 0 }}><small>Added</small><b>{money(sum(["add"]))}</b></span>
          <span style={{ "--i": 1 }}><small>Refunds & rewards</small><b>{money(sum(["refund", "reward"]))}</b></span>
          <span style={{ "--i": 2 }}><small>Spent</small><b>{money(sum(["spend"]))}</b></span>
        </div>
        <p className="ax-wallet-note"><Icon n="bolt" size={13} className="hm-fill" />Refunds to wallet are instant. Use your balance at checkout.</p>
        {/* Adding money is a payment, and payments are the last thing to move
            across. Until then this screen says what the wallet holds rather
            than offering a top-up that no one is charged for. */}
      </section>

      <Tabs value={tab} onChange={setTab} tabs={[["all", "All"], ["add", "Added"], ["spend", "Spent"], ["refund", "Refunds"]]} />
      <div className="ac-card ax-txns" key={tab}>
        {!list.length && !loading && (
          <div className="ac-empty"><span className="ac-empty-art"><Icon n="wallet" size={30} /></span><h3>Nothing here yet</h3><p>Wallet activity will show up in this tab.</p></div>
        )}
        {groups.map((g) => (
          <div key={g.m} className="ax-txn-group">
            <p className="ax-month">{g.m}</p>
            {g.items.map((t) => {
              const m = KIND_META[t.kind] || KIND_META.add;
              const order = (t.sub || "").match(/#(369[ME]-\d+)/);
              const i = row++;
              return (
                <button key={t.id} className={"ax-txn ax-k-" + t.kind} style={{ "--i": i }} disabled={!order} onClick={() => order && onNav?.("track", order[1])}>
                  <span className="ax-txn-ic"><Icon n={m.icon} size={17} /></span>
                  <span className="ax-txn-txt"><b>{t.title}</b><small>{t.sub ? t.sub + " · " : ""}{fmtDateTime(t.at)}</small></span>
                  <span className="ax-txn-amt">{m.sign}{money(t.amount)}</span>
                  {order && <Icon n="right" size={15} className="ax-go" />}
                </button>
              );
            })}
          </div>
        ))}
      </div>

    </div>
  );
}

/* ==========================================================================
   Loyalty points — one card per customer, earned on app orders and on orders
   the shop makes in Odoo, and spent at checkout. All of it is one list.
   ========================================================================== */
const POINT_META = {
  earned: { icon: "coin", sign: "+" },
  redeemed: { icon: "bag", sign: "−" },
  returned: { icon: "reorder", sign: "−" },
  redeem_returned: { icon: "reorder", sign: "+" },
};

export function PointsSec({ onNav }) {
  const { data, loading } = useRemote("/loyalty");
  const log = useMemo(() => data?.history || [], [data]);
  const card = data?.card;
  const rule = data?.rule;
  const [tab, setTab] = useState("all");
  const sum = (kinds) => log.filter((t) => kinds.includes(t.kind)).reduce((s, t) => s + t.points, 0);
  const list = log.filter((t) => tab === "all" || (tab === "earned" ? t.credit : !t.credit));
  const groups = [];
  list.forEach((t) => {
    const m = new Date(t.at).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
    const g = groups[groups.length - 1];
    if (g && g.m === m) g.items.push(t); else groups.push({ m, items: [t] });
  });
  let row = 0;

  if (!loading && data && !data.enabled) {
    return (
      <div className="ac-card"><div className="ac-empty"><span className="ac-empty-art"><Icon n="coin" size={30} /></span>
        <h3>Loyalty points are resting</h3><p>They aren't available right now. Anything you've earned is kept.</p></div></div>
    );
  }
  return (
    <div className="ac-stack">
      <section className="ax-wallet ax-points">
        <span className="ax-wallet-sheen" aria-hidden="true" />
        <span className="ax-wallet-deco" aria-hidden="true"><i /><i /><i /></span>
        <div className="ax-wallet-top">
          <span className="ax-wallet-ic"><Icon n="coin" size={22} /></span>
          <span>
            <small>Loyalty points</small>
            <b className="ax-wallet-amt">{loading ? <i className="ax-wait">…</i> : pointsText(card?.points || 0)}</b>
            {card?.number && <span className="ax-points-num">{card.number}</span>}
          </span>
        </div>
        <div className="ax-wallet-stats">
          <span style={{ "--i": 0 }}><small>Worth</small><b>{money(card?.value || 0)}</b></span>
          <span style={{ "--i": 1 }}><small>Earned</small><b>{pointsText(sum(["earned", "redeem_returned"]))}</b></span>
          <span style={{ "--i": 2 }}><small>Used</small><b>{pointsText(sum(["redeemed", "returned"]))}</b></span>
        </div>
        <p className="ax-wallet-note"><Icon n="bolt" size={13} className="hm-fill" />
          {card ? (data.redeem ? "Use your points at checkout." : "Keep earning - using points at checkout is coming back soon.") : "Your card starts with your first order, on the mobile number in your profile."}
        </p>
      </section>

      {rule && (
        <div className="ac-card ax-points-how">
          <span style={{ "--i": 0 }}><Icon n="bag" size={18} /><span><b>Earn {pointsText(rule.earn)} points</b>for every <bdi>{money(rule.spend)}</bdi> you spend, {EARN_WHEN[data.earnOn] || EARN_WHEN.delivered}</span></span>
          <span style={{ "--i": 1 }}><Icon n="coin" size={18} /><span><b>{pointsText(rule.perRupee)} points = <bdi>{money(1)}</bdi></b>off your order at checkout{data.redeem ? "" : " (paused for now)"}</span></span>
          <span style={{ "--i": 2 }}><Icon n="check" size={18} /><span><b>Use from {pointsText(rule.minRedeem)} points</b>{rule.maxPercent < 100 ? `up to ${pointsText(rule.maxPercent)}% of an order, ` : ""}once a day</span></span>
        </div>
      )}

      <Tabs value={tab} onChange={setTab} tabs={[["all", "All"], ["earned", "Earned"], ["used", "Used"]]} />
      <div className="ac-card ax-txns" key={tab}>
        {!list.length && !loading && (
          <div className="ac-empty"><span className="ac-empty-art"><Icon n="coin" size={30} /></span><h3>Nothing here yet</h3><p>Points you earn and use will show up in this tab.</p></div>
        )}
        {groups.map((g) => (
          <div key={g.m} className="ax-txn-group">
            <p className="ax-month">{g.m}</p>
            {g.items.map((t) => {
              const m = POINT_META[t.kind] || POINT_META.earned;
              const i = row++;
              return (
                <button key={t.id} className={"ax-txn ax-k-" + t.kind} style={{ "--i": i }} disabled={!t.orderRef} onClick={() => t.orderRef && onNav?.("track", t.orderRef)}>
                  <span className="ax-txn-ic"><Icon n={m.icon} size={17} /></span>
                  <span className="ax-txn-txt"><b>{t.title}</b><small>{t.sub ? t.sub + " · " : ""}{fmtDateTime(t.at)}</small></span>
                  <span className="ax-txn-amt">{m.sign}{pointsText(t.points)}</span>
                  {t.orderRef && <Icon n="right" size={15} className="ax-go" />}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ==========================================================================
   Saved payments
   ========================================================================== */
const upiApp = (vpa) => {
  const h = (vpa.split("@")[1] || "").toLowerCase();
  return UPI_APPS.find((a) => a.handle === "@" + h) || (h.startsWith("ok") ? UPI_APPS[0] : UPI_APPS[3]);
};

function TiltCard({ c, fresh }) {
  const ref = useRef(null);
  const move = (e) => {
    if (e.pointerType !== "mouse" || reduced()) return;
    const r = ref.current.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
    ref.current.style.setProperty("--rx", (-y * 12).toFixed(2) + "deg");
    ref.current.style.setProperty("--ry", (x * 16).toFixed(2) + "deg");
    ref.current.style.setProperty("--gx", ((x + 0.5) * 100).toFixed(1) + "%");
  };
  const leave = () => { ref.current?.style.setProperty("--rx", "0deg"); ref.current?.style.setProperty("--ry", "0deg"); };
  return (
    <div ref={ref} className={"ax-cc ax-cc-" + c.brand + (fresh ? " ax-fresh" : "")} onPointerMove={move} onPointerLeave={leave} aria-hidden="true">
      <div className="ax-cc-face">
        <span className="ax-cc-bank">{c.bank}</span>
        <span className="ax-cc-brand">{BRAND_LABEL[c.brand] || "CARD"}</span>
        <span className="co-cc-chip" />
        <span className="ax-cc-num">•••• •••• •••• {c.last4}</span>
        <span className="ax-cc-row"><span>{c.name}</span><span>{c.exp}</span></span>
      </div>
    </div>
  );
}

export function PaymentsSec({ flash }) {
  /* A card and a UPI ID are things the shop holds for this customer, as
     tokens - so they are read from it, and every change is asked of it. The
     two invented ones that used to sit here (a Visa ending 4821, demo@okaxis)
     were shown to everyone as their own saved methods. */
  const { data, loading, send, busy } = useRemote("/payment/methods");
  const pay = useMemo(() => ({ cards: data?.cards || [], upis: data?.upis || [] }), [data]);
  const [fresh, setFresh] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [leaving, setLeaving] = useState(null);
  const [vpa, setVpa] = useState({ open: false, value: "", busy: false, error: "" });

  const removeOne = async (kind, id) => {
    setConfirm(null); setLeaving(id);
    const gone = await send(`/payment/methods/${id}`, { method: "DELETE" });
    setLeaving(null);
    flash?.(gone ? (kind === "cards" ? "Card removed" : "UPI ID removed") : "We couldn't remove that just now");
  };
  const makeDefault = async (kind, id) => {
    const done = await send(`/payment/methods/${id}`, { method: "PATCH", body: { default: true } });
    if (!done) flash?.("We couldn't change that just now");
  };

  const addVpa = async () => {
    const v = vpa.value.trim().toLowerCase();
    setVpa((x) => ({ ...x, busy: true, error: "" }));
    const saved = await send("/payment/methods/upi", { method: "POST", body: { vpa: v } });
    if (!saved) {
      /* The shop checks the handle and whether it is already saved; its
         sentence is the one the field shows. */
      return setVpa((x) => ({ ...x, busy: false, error: "That UPI ID was not accepted. Check it and try again." }));
    }
    const added = (saved.upis || []).find((u) => u.vpa === v);
    if (added) setFresh(added.id);
    setVpa({ open: false, value: "", busy: false, error: "" });
    flash?.(`Verified · ${added?.name || v}`);
  };

  return (
    <div className="ac-stack">
      <section className="ac-card ax-block">
        <div className="ac-card-head">
          <div><h3>Saved cards</h3><p>Pay faster at checkout. Only CVV is asked.</p></div>
          <span className="ax-count">{loading ? "…" : pay.cards.length}</span>
        </div>
        <div className="ax-cards">
          {pay.cards.map((c, i) => (
            <div key={c.id} className={"ax-cardslot" + (leaving === c.id ? " ax-leaving" : "")} style={{ "--i": i }}>
              <TiltCard c={c} fresh={fresh === c.id} />
              <div className="ax-cardbar">
                {c.default ? <span className="ax-default"><Icon n="check" size={12} />Default</span>
                  : <button className="ac-link" onClick={() => makeDefault("cards", c.id)}>Set as default</button>}
                {confirm === c.id ? (
                  <span className="ax-confirm"><button className="ac-link ac-danger" onClick={() => removeOne("cards", c.id)}>Remove</button><button className="ac-link" onClick={() => setConfirm(null)}>Keep</button></span>
                ) : <button className="ac-link ac-danger" onClick={() => setConfirm(c.id)} aria-label={`Remove card ending ${c.last4}`}>Remove</button>}
              </div>
            </div>
          ))}
        </div>
        <p className="ax-fine"><Icon n="lock" size={14} />A card is saved when you pay with it, on the payment form itself - the number is tokenised there and never reaches 369 Mart.</p>
      </section>

      <section className="ac-card ax-block" style={{ "--i": 1 }}>
        <div className="ac-card-head">
          <div><h3>UPI IDs</h3><p>Verified IDs show up first at checkout.</p></div>
          <span className="ax-count">{pay.upis.length}</span>
        </div>
        <div className="ax-upis">
          {pay.upis.map((u, i) => {
            const a = UPI_APPS.find((x) => x.key === u.app) || UPI_APPS[3];
            return (
              <div key={u.id} className={"ax-upi" + (leaving === u.id ? " ax-leaving" : "") + (fresh === u.id ? " ax-fresh" : "")} style={{ "--i": i }}>
                <span className="co-app-logo ax-upi-logo" style={{ "--tone": a.tone }}>{a.short}</span>
                <span className="ax-upi-txt"><b>{u.vpa}</b><small><Icon n="check" size={12} />{u.name}{u.default && <em>Default</em>}</small></span>
                <span className="ax-upi-act">
                  {!u.default && <button className="ac-link" onClick={() => makeDefault("upis", u.id)}>Set default</button>}
                  {confirm === u.id
                    ? <><button className="ac-link ac-danger" onClick={() => removeOne("upis", u.id)}>Remove</button><button className="ac-link" onClick={() => setConfirm(null)}>Keep</button></>
                    : <button className="ax-iconbtn" onClick={() => setConfirm(u.id)} aria-label={`Remove ${u.vpa}`}><Icon n="trash" size={16} /></button>}
                </span>
              </div>
            );
          })}
          {!pay.upis.length && <p className="ac-muted ax-none">No UPI IDs saved yet.</p>}
        </div>
        {vpa.open ? (
          <div className="ax-addvpa">
            <div className={"co-vpa" + (vpa.error ? " co-err" : "")}>
              <label className="co-field">
                <input value={vpa.value} placeholder=" " autoFocus autoCapitalize="none" autoComplete="off"
                  onChange={(e) => setVpa((s) => ({ ...s, value: e.target.value.trim(), error: "" }))}
                  onKeyDown={(e) => { if (e.key === "Enter" && upiOk(vpa.value)) addVpa(); if (e.key === "Escape") setVpa({ open: false, value: "", busy: false, error: "" }); }} />
                <span>UPI ID (e.g. name@okaxis)</span>
              </label>
              <button className="co-verify" disabled={!upiOk(vpa.value) || vpa.busy} onClick={addVpa}>{vpa.busy ? <i className="co-spin" /> : "Verify & save"}</button>
            </div>
            {vpa.error && <p className="co-error" key={vpa.error}>{vpa.error}</p>}
          </div>
        ) : (
          <button className="ax-addline" onClick={() => setVpa((s) => ({ ...s, open: true }))}><Icon n="plus" size={16} />Add UPI ID</button>
        )}
      </section>

      <div className="ax-secure" style={{ "--i": 2 }}>
        <span><Icon n="shield" size={20} /></span>
        <p><b>Your payment details are safe</b>Cards are stored as tokens with your bank's network. 369 Mart never sees or keeps your full card number or CVV.</p>
      </div>
    </div>
  );
}

/* ==========================================================================
   Coupons & rewards
   ========================================================================== */
function rewardText(r) {
  if (r.type === "cash") return { big: money(r.amount), small: "Cashback added to wallet" };
  if (r.type === "coupon") return { big: r.title, small: `Coupon ${r.code} unlocked` };
  return { big: "Better luck next time", small: "Keep ordering to win more" };
}

function ScratchSheet({ card, onClose, onReveal }) {
  const canvas = useRef(null);
  const [done, setDone] = useState(card.scratched);
  const [started, setStarted] = useState(false);
  const state = useRef({ down: false, last: null, moves: 0 });
  const t = rewardText(card.reward);

  useEffect(() => {
    const cv = canvas.current;
    if (!cv || done) return;
    const dpr = window.devicePixelRatio || 1, w = cv.offsetWidth, h = cv.offsetHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext("2d");
    ctx.scale(dpr, dpr);
    const g = ctx.createLinearGradient(0, 0, w, h);
    g.addColorStop(0, "#0b4a6e"); g.addColorStop(0.5, "#0a78ab"); g.addColorStop(1, "#f7931e");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    ctx.globalAlpha = 0.14; ctx.fillStyle = "#fff";
    for (let y = -10; y < h + 20; y += 22) for (let x = (y / 22) % 2 ? 0 : 11; x < w + 20; x += 22) { ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill(); }
    ctx.globalAlpha = 1; ctx.fillStyle = "#fff"; ctx.textAlign = "center";
    ctx.font = "800 22px Inter, system-ui, sans-serif"; ctx.fillText("369", w / 2, h / 2 - 6);
    ctx.font = "700 13px Inter, system-ui, sans-serif"; ctx.fillText("SCRATCH HERE", w / 2, h / 2 + 18);
  }, [done]);

  const reveal = () => {
    if (done) return;
    setDone(true);
    onReveal(card);
  };
  const point = (e) => { const r = canvas.current.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const scratch = (p) => {
    const ctx = canvas.current.getContext("2d");
    ctx.globalCompositeOperation = "destination-out";
    ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.lineWidth = 38;
    const l = state.current.last || p;
    ctx.beginPath(); ctx.moveTo(l.x, l.y); ctx.lineTo(p.x + 0.1, p.y); ctx.stroke();
    state.current.last = p;
    if (++state.current.moves % 8 === 0) {
      const cv = canvas.current, data = ctx.getImageData(0, 0, cv.width, cv.height).data;
      let clear = 0, total = 0;
      for (let i = 3; i < data.length; i += 4 * 24) { total++; if (data[i] < 20) clear++; }
      if (clear / total > 0.45) reveal();
    }
  };
  return (
    <Sheet title="Scratch card" onClose={onClose} className="ax-scratchsheet"
      foot={(close) => done ? <button className="ot-primary ax-wide" onClick={close}>{card.reward.type === "cash" ? "Great" : "Close"}</button>
        : <button className="ac-ghost ax-wide" onClick={reveal}>Reveal without scratching</button>}>
      <p className="ax-scratch-from">From {card.from}</p>
      <div className={"ax-scratchbox" + (done ? " ax-done" : "") + (card.reward.type === "none" ? " ax-none" : "")}>
        <div className="ax-prize">
          <span className="ax-prize-ic"><Icon n={card.reward.type === "cash" ? "wallet" : card.reward.type === "coupon" ? "ticket" : "gift"} size={30} /></span>
          <b>{t.big}</b><small>{t.small}</small>
        </div>
        {done && card.reward.type !== "none" && <Confetti />}
        {!card.scratched && (
          <canvas ref={canvas} className={"ax-foil" + (started ? " ax-started" : "")} aria-label="Scratch area"
            onPointerDown={(e) => { e.currentTarget.setPointerCapture?.(e.pointerId); state.current.down = true; state.current.last = point(e); setStarted(true); scratch(point(e)); }}
            onPointerMove={(e) => state.current.down && !done && scratch(point(e))}
            onPointerUp={() => { state.current.down = false; state.current.last = null; }}
            onPointerCancel={() => { state.current.down = false; state.current.last = null; }} />
        )}
        {!started && !done && <span className="ax-hand" aria-hidden="true"><Icon n="pen" size={22} /></span>}
      </div>
      <p className="ax-fine ax-center">{done ? (card.reward.type === "cash" ? "Cashback is in your 369 Wallet and never expires." : card.reward.type === "coupon" ? "Find it under Your coupons below." : "Every delivered order earns a scratch card.") : "Drag your finger or mouse across the card."}</p>
    </Sheet>
  );
}

export function RewardsSec({ onNav, flash }) {
  /* A scratch card is minted by the shop when an order is delivered, and
     scratching one is the shop crediting a wallet. Revealing it here only
     ever changed a copy in this browser - and handed out the cashback. */
  const { data, loading, send } = useRemote("/rewards");
  const rw = useMemo(() => ({ scratch: data?.scratch || [], won: data?.won || [] }), [data]);
  const [open, setOpen] = useState(null);
  const [copied, setCopied] = useState(null);
  const won = rw.scratch.filter((s) => s.scratched && s.reward.type === "cash").reduce((s, c) => s + c.reward.amount, 0);
  const fresh = rw.scratch.filter((s) => !s.scratched).length;

  const onReveal = async (card) => {
    const done = await send(`/rewards/${card.id}/scratch`, { method: "POST" });
    if (!done) flash?.("We couldn't open that card just now");
  };
  const copy = async (code) => { if (await copyText(code)) { setCopied(code); flash?.(`${code} copied`); setTimeout(() => setCopied((c) => (c === code ? null : c)), 1800); } };
  const { coupons: live } = useRules();
  const coupons = [...live].sort((a, b) => rw.won.includes(b.code) - rw.won.includes(a.code));

  return (
    <div className="ac-stack">
      <div className="ax-rewardstats">
        <span style={{ "--i": 0 }}><Icon n="wallet" size={20} /><b><Amount value={won} /></b><small>Cashback won</small></span>
        <span style={{ "--i": 1 }}><Icon n="gift" size={20} /><b>{loading ? "…" : fresh}</b><small>Cards to scratch</small></span>
        <span style={{ "--i": 2 }}><Icon n="ticket" size={20} /><b>{coupons.length}</b><small>Coupons available</small></span>
      </div>

      <section className="ac-card ax-block">
        <div className="ac-card-head"><div><h3>Scratch cards</h3><p>One for every order delivered.</p></div></div>
        <div className="ax-scratchgrid">
          {rw.scratch.map((s, i) => {
            const t = rewardText(s.reward);
            return (
              <button key={s.id} className={"ax-scard" + (s.scratched ? " ax-open" : "") + (s.reward.type === "none" ? " ax-none" : "")} style={{ "--i": i }} onClick={() => setOpen(s.id)}>
                {s.scratched ? (
                  <span className="ax-scard-in"><span className="ax-prize-ic"><Icon n={s.reward.type === "cash" ? "wallet" : s.reward.type === "coupon" ? "ticket" : "gift"} size={20} /></span><b>{t.big}</b><small>{s.from}</small></span>
                ) : (
                  <span className="ax-scard-foil"><span className="ax-sparkle" aria-hidden="true"><i /><i /><i /></span><Icon n="gift" size={28} /><b>Scratch to win</b><small>{s.from}</small></span>
                )}
              </button>
            );
          })}
        </div>
      </section>

      <section className="ac-card ax-block" style={{ "--i": 1 }}>
        <div className="ac-card-head"><div><h3>Your coupons</h3><p>Apply in the cart or at checkout.</p></div><button className="ac-ghost" onClick={() => onNav?.("offers")}>All offers</button></div>
        <div className="ax-coupons">
          {coupons.map((c, i) => (
            <div key={c.code} className={"ax-coupon" + (rw.won.includes(c.code) ? " ax-won" : "")} style={{ "--i": i }}>
              <span className="ax-coupon-stub"><Icon n="pct" size={20} /><b>{c.code}</b></span>
              <span className="ax-coupon-txt">
                <b>{c.title}{rw.won.includes(c.code) && <em>Won</em>}</b>
                <small>{c.note}</small>
              </span>
              <button className={"ax-copy" + (copied === c.code ? " ax-copied" : "")} onClick={() => copy(c.code)} aria-label={`Copy ${c.code}`}>
                <span>{copied === c.code ? <><Icon n="check" size={14} />Copied</> : "Copy"}</span>
              </button>
            </div>
          ))}
        </div>
      </section>

      {open && <ScratchSheet card={rw.scratch.find((s) => s.id === open)} onClose={() => setOpen(null)} onReveal={onReveal} />}
    </div>
  );
}

/* ==========================================================================
   Ratings & reviews
   ========================================================================== */
const TAGS_UP = ["Fresh", "Well packed", "Good value", "As described", "Fast delivery"];
const TAGS_DOWN = ["Not fresh", "Damaged", "Wrong item", "Poor quality", "Late delivery"];

function ReviewEditor({ p, initial, onClose, onSave }) {
  const [r, setR] = useState({ stars: 0, title: "", text: "", tags: [], photos: 0, ...initial });
  const [posting, setPosting] = useState(false);
  const tags = r.stars && r.stars <= 3 ? TAGS_DOWN : TAGS_UP;
  const toggle = (t) => setR((x) => ({ ...x, tags: x.tags.includes(t) ? x.tags.filter((y) => y !== t) : [...x.tags, t] }));
  return (
    <Sheet title={initial?.at ? "Edit your review" : "Rate this product"} onClose={onClose} className="ax-review"
      foot={(close) => (
        <button className="ot-primary ax-wide" disabled={!r.stars || posting} onClick={async () => { setPosting(true); await wait(reduced() ? 100 : 700); onSave({ ...r, tags: r.tags.filter((t) => tags.includes(t)), at: initial?.at || Date.now(), edited: !!initial?.at, helpful: initial?.helpful || 0 }); close(); }}>
          {posting ? <><i className="co-spin co-spin-w" />Posting…</> : initial?.at ? "Update review" : "Post review"}
        </button>
      )}>
      <div className="ax-rev-prod"><span className="ac-thumb"><Thumb p={p} /></span><span><b>{p.name}</b><small>{p.unit}</small></span></div>
      <StarPick value={r.stars} onPick={(k) => setR((x) => ({ ...x, stars: k }))} size={36} />
      <div className={"ac-collapse" + (r.stars ? " ac-show" : "")}>
        <div inert={!r.stars}>
          <p className="ax-label">{r.stars && r.stars <= 3 ? "What went wrong?" : "What did you like?"}</p>
          <div className="ax-tags" key={r.stars <= 3 ? "d" : "u"}>
            {tags.map((t, k) => <button key={t} type="button" className={r.tags.includes(t) ? "ax-on" : ""} style={{ "--k": k }} onClick={() => toggle(t)}>{r.tags.includes(t) && <Icon n="check" size={13} />}{t}</button>)}
          </div>
          <label className="co-field ax-mt"><input value={r.title} maxLength={60} placeholder=" " onChange={(e) => setR({ ...r, title: e.target.value })} /><span>Headline (optional)</span></label>
          <label className="ax-textarea">
            <textarea value={r.text} maxLength={500} rows={4} placeholder="Tell others about build quality, performance, size or value" onChange={(e) => setR({ ...r, text: e.target.value })} />
            <small className={r.text.length > 450 ? "ax-warn" : ""}>{r.text.length}/500</small>
          </label>
          <div className="ax-photos">
            {Array.from({ length: r.photos }, (_, i) => (
              <span key={i} className="ax-photo" style={{ "--h": 190 + i * 40 }}><Thumb p={p} /><button type="button" onClick={() => setR((x) => ({ ...x, photos: x.photos - 1 }))} aria-label="Remove photo"><Icon n="x" size={12} /></button></span>
            ))}
            {r.photos < 3 && <button type="button" className="ax-photo-add" onClick={() => setR((x) => ({ ...x, photos: x.photos + 1 }))}><Icon n="plus" size={18} /><small>Photo</small></button>}
          </div>
        </div>
      </div>
    </Sheet>
  );
}

export function ReviewsSec({ orders, byId, onOpen, flash }) {
  /* One review per product, as the shop keeps them - the page reads
     `reviews[p.id]`, which is why there can only ever be one. */
  const { data, send } = useRemote("/reviews");
  const reviews = useMemo(() => data?.reviews || {}, [data]);
  const [edit, setEdit] = useState(null);
  const [leaving, setLeaving] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [posted, setPosted] = useState(null);
  const pending = [];
  const seen = new Set();
  orders.filter((o) => o.status === "delivered").forEach((o) => o.items.forEach(([id]) => {
    if (seen.has(id) || reviews[id] || !byId[id]) return;
    seen.add(id); pending.push({ id, order: o });
  }));
  const mine = Object.entries(reviews).filter(([id]) => byId[id]).sort((a, b) => b[1].at - a[1].at);

  const save = async (id, r) => {
    const sent = await send(`/reviews/${id}`, { method: "POST", body: { stars: r.stars, title: r.title, text: r.text, tags: r.tags } });
    if (!sent) return flash?.("We couldn't post that just now");
    setPosted(id);
    flash?.(r.edited ? "Review updated" : "Thanks! Your review is live");
  };
  const del = async (id) => {
    setConfirm(null); setLeaving(id);
    const gone = await send(`/reviews/${id}`, { method: "DELETE" });
    setLeaving(null);
    flash?.(gone ? "Review deleted" : "We couldn't delete that just now");
  };

  return (
    <div className="ac-stack">
      <section className="ac-card ax-block">
        <div className="ac-card-head"><div><h3>Waiting for your review</h3><p>From your delivered orders. It takes 10 seconds.</p></div><span className="ax-count">{pending.length}</span></div>
        {pending.length ? (
          <div className="ax-pending">
            {pending.map(({ id, order }, i) => (
              <article key={id} className="ax-pend" style={{ "--i": i }}>
                <button className="ax-pend-img" onClick={(e) => onOpen?.(byId[id], e.currentTarget.getBoundingClientRect())} aria-label={`Open ${byId[id].name}`}><Thumb p={byId[id]} /></button>
                <b>{byId[id].name}</b>
                <small>Order #{order.id}</small>
                <StarPick value={0} size={22} label={false} onPick={(k) => setEdit({ id, initial: { stars: k } })} />
              </article>
            ))}
          </div>
        ) : (
          <div className="ac-empty ax-empty-sm"><span className="ac-empty-art"><Icon n="star" size={28} /></span><h3>All caught up</h3><p>You've reviewed everything you ordered.</p></div>
        )}
      </section>

      <section className="ac-card ax-block" style={{ "--i": 1 }}>
        <div className="ac-card-head"><div><h3>Your reviews</h3><p>Shown on the product page with a Verified purchase tag.</p></div><span className="ax-count">{mine.length}</span></div>
        {!mine.length && <p className="ac-muted ax-none">Reviews you write will appear here.</p>}
        <div className="ax-myrevs">
          {mine.map(([id, r], i) => (
            <article key={id + (r.edited ? r.at : "")} className={"ax-myrev" + (leaving === id ? " ax-leaving" : "") + (posted === id ? " ax-posted" : "")} style={{ "--i": i }}>
              <span className="ac-thumb ax-myrev-img"><Thumb p={byId[id]} /></span>
              <div className="ax-myrev-body">
                <div className="ax-myrev-top"><Chip stars={r.stars} /><b>{r.title || STAR_WORDS[r.stars]}</b></div>
                <small className="ax-myrev-name">{byId[id].name} · {fmtDate(r.at)}{r.edited ? " · Edited" : ""}</small>
                {r.text && <p>{r.text}</p>}
                {!!r.tags?.length && <div className="ax-tagline">{r.tags.map((t) => <span key={t}>{t}</span>)}</div>}
                <div className="ax-myrev-foot">
                  <span className="ac-muted"><Icon n="trend" size={13} /> {r.helpful || 0} found this helpful</span>
                  <span>
                    <button className="ac-link" onClick={() => setEdit({ id, initial: r })}>Edit</button>
                    {confirm === id
                      ? <><button className="ac-link ac-danger" onClick={() => del(id)}>Delete</button><button className="ac-link" onClick={() => setConfirm(null)}>Keep</button></>
                      : <button className="ac-link ac-danger" onClick={() => setConfirm(id)}>Delete</button>}
                  </span>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      {edit && <ReviewEditor p={byId[edit.id]} initial={edit.initial} onClose={() => setEdit(null)} onSave={(r) => save(edit.id, r)} />}
    </div>
  );
}

/* ==========================================================================
   Notifications
   ========================================================================== */
const NOTE_IC = { order: "box", offer: "pct", wallet: "wallet" };
/* The feed is the shop's. It used to be four invented announcements plus one
   row per order made up here from the order's status - so a "your order is on
   the way" that the warehouse had never sent, and a read mark no other device
   would ever see. `orders` is kept as an argument because the feed is worth
   re-reading when they change. */
export function useNotifications(orders) {
  const { data, send, reload } = useRemote("/notifications");
  const all = useMemo(() => data?.notifications || [], [data]);
  const read = useMemo(() => all.filter((n) => n.read).map((n) => n.id), [all]);
  const unread = all.filter((n) => !n.read).length;
  const count = orders?.length ?? 0;
  useEffect(() => { reload(); }, [count]); // eslint-disable-line
  return { all, st: { read, dismissed: [] }, send, prefs: data?.prefs || null, unread };
}

function NoteRow({ n, unread, now, i, onOpen, onDismiss }) {
  const ref = useRef(null);
  const drag = useRef(null);
  const [gone, setGone] = useState(false);
  const dismiss = (dir = -1) => { setGone(dir); setTimeout(onDismiss, reduced() ? 0 : 360); };
  const down = (e) => { if (e.button > 0 || e.target.closest(".ax-note-x")) return; drag.current = { x: e.clientX, y: e.clientY, dx: 0, lock: null }; };
  const move = (e) => {
    const d = drag.current; if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (d.lock === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) { d.lock = Math.abs(dx) > Math.abs(dy) ? "x" : "y"; if (d.lock === "x") ref.current.setPointerCapture?.(e.pointerId); }
    if (d.lock !== "x") return;
    d.dx = dx;
    ref.current.style.transition = "none";
    ref.current.style.transform = `translateX(${dx}px)`;
    ref.current.style.opacity = String(1 - Math.min(0.6, Math.abs(dx) / 300));
  };
  const up = () => {
    const d = drag.current; drag.current = null; if (!d) return;
    ref.current.style.transition = ""; ref.current.style.opacity = "";
    if (d.lock === "x" && Math.abs(d.dx) > 90) { ref.current.style.transform = ""; dismiss(d.dx > 0 ? 1 : -1); return; }
    ref.current.style.transform = "";
    if (d.lock === null) onOpen();
  };
  return (
    <div className={"ax-note-wrap" + (gone ? " ax-gone" : "")} style={{ "--i": i, "--dir": gone || -1 }}>
      <span className="ax-note-under" aria-hidden="true"><Icon n="trash" size={18} /></span>
      <div ref={ref} className={"ax-note ax-t-" + n.type + (unread ? " ax-unread" : "")} role="button" tabIndex={0}
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { drag.current = null; if (ref.current) { ref.current.style.transform = ""; ref.current.style.opacity = ""; } }}
        onKeyDown={(e) => { if (e.key === "Enter") onOpen(); if (e.key === "Delete" || e.key === "Backspace") dismiss(); }}>
        <span className="ax-note-ic"><Icon n={NOTE_IC[n.type]} size={18} /></span>
        <span className="ax-note-txt"><b>{n.title}</b><small>{n.text}</small><em>{now ? ago(n.at, now) : fmtDate(n.at)}</em></span>
        <i className="ax-dot" aria-label={unread ? "Unread" : undefined} />
        <button className="ax-note-x" onClick={(e) => { e.stopPropagation(); dismiss(); }} aria-label="Dismiss notification"><Icon n="x" size={14} /></button>
      </div>
    </div>
  );
}

const PREFS = [
  ["orders", "Order updates", "Packed, out for delivery, delivered", "box", true],
  ["offers", "Offers & deals", "Sales, price drops on My List", "pct"],
  ["wallet", "Wallet & rewards", "Refunds, cashback, scratch cards", "wallet"],
  ["whatsapp", "WhatsApp", "Order updates and invoices on WhatsApp", "chat"],
  ["email", "Email", "Invoices and monthly summaries", "mail"],
  ["sms", "SMS", "Delivery OTP and critical alerts", "phone"],
];

export function NotifsSec({ orders, onNav, goSection }) {
  const { all, st, send, prefs, unread } = useNotifications(orders);
  const [tab, setTab] = useState("all");
  const [saved, setSaved] = useState(0);
  const now = useNow();
  const list = all.filter((n) => tab === "all" || n.type === tab);
  const count = (t) => all.filter((n) => n.type === t && !st.read.includes(n.id)).length;
  const today = now ? new Date(now).toDateString() : null;
  const sections = [
    ["Today", list.filter((n) => today && new Date(n.at).toDateString() === today)],
    [today ? "Earlier" : "Recent", list.filter((n) => !today || new Date(n.at).toDateString() !== today)],
  ].filter(([, l]) => l.length);

  const open = (n) => {
    if (!st.read.includes(n.id)) send("/notifications/read", { method: "POST", body: { ids: [n.id] } });
    const [v, p] = n.go || [];
    setTimeout(() => { if (v === "account") goSection?.(p); else if (v) onNav?.(v, p); }, 220);
  };
  let row = 0;
  return (
    <div className="ac-stack">
      <div className="ax-notehead">
        <Tabs value={tab} onChange={setTab} tabs={[["all", "All", unread], ["order", "Orders", count("order")], ["offer", "Offers", count("offer")], ["wallet", "Wallet", count("wallet")]]} />
        <button className="ac-link ax-markall" disabled={!unread} onClick={() => send("/notifications/read", { method: "POST", body: { all: true } })}><Icon n="check" size={14} />Mark all as read</button>
      </div>
      <div className="ac-card ax-notes" key={tab}>
        {!list.length && <div className="ac-empty"><span className="ac-empty-art"><Icon n="bell" size={30} /></span><h3>You're all caught up</h3><p>New updates will show up here.</p></div>}
        {sections.map(([label, l]) => (
          <div key={label}>
            <p className="ax-month">{label}</p>
            {l.map((n) => (
              <NoteRow key={n.id} n={n} i={row++} now={now} unread={!st.read.includes(n.id)} onOpen={() => open(n)}
                onDismiss={() => send("/notifications/dismiss", { method: "POST", body: { ids: [n.id] } })} />
            ))}
          </div>
        ))}
        {!!list.length && <p className="ax-fine ax-center ax-swipehint">Swipe a notification sideways to clear it.</p>}
      </div>

      <section className="ac-card ax-block" style={{ "--i": 1 }}>
        <div className="ac-card-head"><div><h3>Notification preferences</h3><p>Choose what we send and where.</p></div>{saved > 0 && <span className="ac-saved-tag" key={saved}><Icon n="check" size={14} />Saved</span>}</div>
        <div className="ax-prefs">
          {PREFS.map(([k, t, d, ic, locked], i) => (
            <div key={k} className="ax-pref" style={{ "--i": i }}>
              <span className="ax-pref-ic"><Icon n={ic} size={17} /></span>
              <span className="ax-pref-txt"><b>{t}</b><small>{locked ? "Always on so you don't miss a delivery" : d}</small></span>
              <Switch on={locked ? true : !!prefs?.[k]} disabled={locked || !prefs} label={t} onChange={(v) => { send("/notifications/prefs", { method: "PATCH", body: { [k]: v } }); setSaved((x) => x + 1); }} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

/* ==========================================================================
   Refer & earn
   ========================================================================== */
const REF_STATUS = {
  ordered: { label: "Ordered", note: (reward) => `${money(reward)} earned`, tone: "green" },
  joined: { label: "Joined", note: () => "First order pending", tone: "blue" },
  invited: { label: "Invited", note: () => "Hasn't joined yet", tone: "grey" },
};

export function ReferSec({ user, flash }) {
  /* The code is the shop's - it has to be, or nobody could redeem it - and so
     is who has joined and who has ordered. A customer can only ever say "I
     invited someone"; the rest are claims only the shop can make. */
  const { data, send } = useRemote("/referrals");
  const refs = useMemo(() => data?.referrals || [], [data]);
  const [copied, setCopied] = useState(false);
  const [reminded, setReminded] = useState({});
  const [invite, setInvite] = useState("");
  const [freshId, setFreshId] = useState(null);
  const code = data?.code || "";
  const link = data?.link || "";
  /* The shop's setting. It was a 100 written in here, so moving the setting
     moved the totals and left the promise beside them saying something else. */
  const reward = data?.reward ?? 0;
  const message = `Shop computer parts at 369 Mart with my code ${code} - fast delivery: ${link}`;
  const ordered = refs.filter((r) => r.status === "ordered").length;
  const joined = refs.filter((r) => r.status !== "invited").length;
  const earned = data?.earned ?? 0;
  const pending = data?.pending ?? 0;

  const copy = async () => { if (await copyText(code)) { setCopied(true); flash?.("Code copied"); setTimeout(() => setCopied(false), 1800); } };
  const share = async () => {
    if (navigator.share) { try { await navigator.share({ title: "369 Mart", text: message, url: link }); return; } catch (e) { return; } }
    if (await copyText(message)) flash?.("Invite message copied");
  };
  const add = async (e) => {
    e.preventDefault();
    const name = invite.trim();
    if (name.length < 2) return;
    const saved = await send("/referrals", { method: "POST", body: { name } });
    if (!saved) return flash?.("We couldn't record that invite just now");
    setFreshId(saved.referral?.id || null); setInvite("");
    flash?.(`Invite sent to ${name}`);
  };

  return (
    <div className="ac-stack">
      <section className="ax-refer">
        <div className="ax-refer-copy">
          <small>Refer & earn</small>
          <h3>Invite friends, earn {money(reward)} each</h3>
          <p>Share your code. When a friend signs up with it and places their first order, {money(reward)} goes into your 369 Wallet.</p>
        </div>
        <span className="ax-giftbox" aria-hidden="true">
          <i className="ax-gift-lid" /><i className="ax-gift-body" /><i className="ax-gift-ribbon" />
          <b className="ax-gift-coin c1">★</b><b className="ax-gift-coin c2">★</b><b className="ax-gift-coin c3">★</b>
        </span>
        <div className="ax-code">
          <span className="ax-code-box" aria-label={`Your code ${code}`}>
            {code.split("").map((ch, i) => <i key={i} style={{ "--i": i }}>{ch}</i>)}
          </span>
          <button className={"ax-copy ax-copy-lg" + (copied ? " ax-copied" : "")} onClick={copy}><span>{copied ? <><Icon n="check" size={15} />Copied</> : "Copy code"}</span></button>
        </div>
        <div className="ax-share">
          <a className="ax-share-wa" href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer"><Icon n="chat" size={17} />WhatsApp</a>
          <button onClick={async () => { if (await copyText(link)) flash?.("Link copied"); }}><Icon n="note" size={17} />Copy link</button>
          <button onClick={share}><Icon n="share" size={17} />More</button>
        </div>
      </section>

      <section className="ac-card ax-block" style={{ "--i": 1 }}>
        <div className="ax-refstats">
          <span><small>Earned</small><b><Amount value={earned} /></b></span>
          <span><small>Pending</small><b>{money(pending)}</b></span>
          <span><small>Friends joined</small><b>{joined}</b></span>
        </div>
        {/* The bar counts friends. It used to promise a bonus at five that
            nothing in the shop pays - a progress bar towards nothing. */}
        <div className="ax-goal" style={{ "--p": Math.min(1, joined / REFER_GOAL) }}>
          <div className="ax-goal-bar"><i />{Array.from({ length: REFER_GOAL }, (_, k) => <b key={k} className={k < joined ? "ax-hit" : ""} style={{ "--k": k, left: `${((k + 1) / REFER_GOAL) * 100}%` }}>{k + 1}</b>)}</div>
          <p>{joined ? <>{joined} friend{joined > 1 ? "s have" : " has"} joined with your code. {money(reward)} for each first order.</> : <>Nobody has used your code yet. {money(reward)} lands in your wallet for each friend's first order.</>}</p>
        </div>
      </section>

      <section className="ac-card ax-block" style={{ "--i": 2 }}>
        <div className="ac-card-head"><div><h3>How it works</h3></div></div>
        <ol className="ax-steps">
          {[["share", "Share your code", "Send it on WhatsApp or anywhere"], ["user", "Friend orders", "They sign up with your code and place a first order"], ["wallet", "You earn", `${money(reward)} lands in your wallet`]].map(([ic, t, d], k) => (
            <li key={t} style={{ "--k": k }}><span><Icon n={ic} size={19} /></span><b>{t}</b><small>{d}</small></li>
          ))}
        </ol>
      </section>

      <section className="ac-card ax-block" style={{ "--i": 3 }}>
        <div className="ac-card-head"><div><h3>Your invites</h3><p>Remind friends who haven't ordered yet.</p></div><span className="ax-count">{refs.length}</span></div>
        <form className="ax-invite" onSubmit={add}>
          <label className="co-field"><input value={invite} maxLength={40} placeholder=" " onChange={(e) => setInvite(e.target.value)} /><span>Friend's name or email</span></label>
          <button className="ac-primary" disabled={invite.trim().length < 2}>Invite</button>
        </form>
        <ul className="ax-friends">
          {refs.map((r, i) => {
            const s = REF_STATUS[r.status];
            return (
              <li key={r.id} className={freshId === r.id ? "ax-fresh" : ""} style={{ "--i": i }}>
                <span className={"ax-av ax-" + s.tone}>{r.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()}</span>
                <span className="ax-friend-txt"><b>{r.name}</b><small>{s.note(reward)}</small></span>
                <span className={"ax-pill ax-" + s.tone}>{s.label}</span>
                {r.status !== "ordered" && (
                  reminded[r.id] ? <span className="ax-reminded"><Icon n="check" size={13} />Reminded</span>
                    : <button className="ac-link" onClick={() => { setReminded((m) => ({ ...m, [r.id]: true })); flash?.(`Reminder sent to ${r.name}`); }}>Remind</button>
                )}
              </li>
            );
          })}
        </ul>
        <p className="ax-fine">Rewards are credited within 24 hours of your friend's first delivery. Up to 20 referrals a month.</p>
      </section>
    </div>
  );
}
