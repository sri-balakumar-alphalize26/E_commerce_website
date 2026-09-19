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
import { Icon, Thumb, inr } from "./shared";
import { Amount, useRules } from "./Cart";
import { CardPreview } from "./Checkout";
import { BRAND_LABEL, UPI_APPS, cardBrand, demoGateway, expiryOk, formatCard, formatExpiry, luhn, upiOk } from "./payment";
import {
  KEYS, REFER_BONUS, REFER_GOAL, REFER_REWARD, SEED_NOTIFS, SEED_NOTIF_STATE, SEED_PAYMENTS, SEED_PREFS, SEED_REFERRALS,
  SEED_REVIEWS, SEED_REWARDS, SEED_WALLET_LOG, STAR_WORDS, WALLET_LIMIT, ago, fmtDate, fmtDateTime, orderNotifs, useStored,
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

function AddMoneySheet({ balance, onClose, onDone }) {
  const room = Math.max(0, WALLET_LIMIT - balance);
  const [amt, setAmt] = useState(String(Math.min(500, room)));
  const [app, setApp] = useState("gpay");
  const [phase, setPhase] = useState("form");
  const n = parseInt(amt || "0", 10);
  const err = !n ? "" : n < 10 ? "Add at least ₹10" : n > room ? `You can add up to ${inr(room)} more (wallet limit ${inr(WALLET_LIMIT)})` : "";
  const a = UPI_APPS.find((x) => x.key === app);
  const pay = async () => {
    setPhase("paying");
    await wait(reduced() ? 300 : 2000);
    setPhase("done");
    onDone(n, a.name);
  };
  return (
    <Sheet title={phase === "done" ? "Money added" : "Add money to 369 Wallet"} onClose={onClose} className="ax-addmoney"
      foot={(close) => phase === "form" ? (
        <button className="ot-primary ax-wide" disabled={!n || !!err} onClick={pay}>Add {n ? inr(n) : "money"} with {a.name}</button>
      ) : phase === "done" ? <button className="ot-primary ax-wide" onClick={close}>Done</button> : null}>
      {phase === "form" && (
        <div className="ax-am">
          <p className="ax-am-bal">Current balance <b>{inr(balance)}</b></p>
          <label className={"ax-am-input" + (err ? " ax-err" : "")}>
            <span>₹</span>
            <input inputMode="numeric" value={amt} autoFocus aria-label="Amount" onChange={(e) => setAmt(e.target.value.replace(/\D/g, "").slice(0, 5))} />
          </label>
          {err && <p className="co-error" key={err}>{err}</p>}
          <div className="ax-am-chips">
            {[100, 200, 500, 1000].map((v, k) => (
              <button key={v} style={{ "--k": k }} onClick={() => setAmt(String(Math.min(room, (n || 0) + v)))}>+{inr(v)}</button>
            ))}
          </div>
          <p className="ax-label">Pay using UPI</p>
          <div className="co-apps ax-apps">
            {UPI_APPS.map((x, k) => (
              <button key={x.key} className={"co-app" + (app === x.key ? " co-on" : "")} style={{ "--k": k, "--tone": x.tone }} onClick={() => setApp(x.key)}>
                <span className="co-app-logo">{x.short}</span><small>{x.name}</small>
              </button>
            ))}
          </div>
          <p className="ax-fine"><Icon n="shield" size={14} />Wallet money can't be withdrawn to a bank. It never expires.</p>
        </div>
      )}
      {phase === "paying" && (
        <div className="ax-am-wait">
          <span className="ax-am-app" style={{ "--tone": a.tone }}>{a.short}<i /><i /></span>
          <b>Waiting for {a.name}</b>
          <small>Approve the request for {inr(n)} in your UPI app</small>
        </div>
      )}
      {phase === "done" && (
        <div className="ax-am-done">
          <span className="ax-coins" aria-hidden="true">{[0, 1, 2, 3, 4].map((i) => <i key={i} style={{ "--i": i }}>₹</i>)}</span>
          <span className="ax-am-wallet"><Icon n="wallet" size={38} /></span>
          <b>{inr(n)} added</b>
          <small>New balance {inr(balance)}</small>
        </div>
      )}
    </Sheet>
  );
}

export function WalletSec({ balance, onWallet, onNav, flash }) {
  const [log] = useStored(KEYS.walletLog, SEED_WALLET_LOG);
  const [tab, setTab] = useState("all");
  const [adding, setAdding] = useState(false);
  const [glow, setGlow] = useState(0);
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
        <span className="ax-wallet-sheen" key={"s" + glow} aria-hidden="true" />
        <span className="ax-wallet-deco" aria-hidden="true"><i /><i /><i /></span>
        <div className="ax-wallet-top">
          <span className="ax-wallet-ic"><Icon n="wallet" size={22} /></span>
          <span><small>369 Wallet balance</small><b className="ax-wallet-amt"><Amount value={balance} /></b></span>
          <button className="ax-wallet-add" onClick={() => setAdding(true)}><Icon n="plus" size={16} />Add money</button>
        </div>
        <div className="ax-wallet-stats">
          <span style={{ "--i": 0 }}><small>Added</small><b>{inr(sum(["add"]))}</b></span>
          <span style={{ "--i": 1 }}><small>Refunds & rewards</small><b>{inr(sum(["refund", "reward"]))}</b></span>
          <span style={{ "--i": 2 }}><small>Spent</small><b>{inr(sum(["spend"]))}</b></span>
        </div>
        <p className="ax-wallet-note"><Icon n="bolt" size={13} className="hm-fill" />Refunds to wallet are instant. Use your balance at checkout.</p>
      </section>

      <Tabs value={tab} onChange={setTab} tabs={[["all", "All"], ["add", "Added"], ["spend", "Spent"], ["refund", "Refunds"]]} />
      <div className="ac-card ax-txns" key={tab}>
        {!list.length && (
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
                  <span className="ax-txn-amt">{m.sign}{inr(t.amount)}</span>
                  {order && <Icon n="right" size={15} className="ax-go" />}
                </button>
              );
            })}
          </div>
        ))}
      </div>

      {adding && (
        <AddMoneySheet balance={balance} onClose={() => setAdding(false)}
          onDone={(n, via) => { onWallet(n, { kind: "add", title: "Money added", sub: `Via ${via}` }); setGlow((g) => g + 1); flash?.(`${inr(n)} added to your wallet`); }} />
      )}
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
  const [pay, setPay] = useStored(KEYS.payments, SEED_PAYMENTS);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ num: "", name: "", exp: "", cvv: "" });
  const [cvvFocus, setCvvFocus] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fresh, setFresh] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [leaving, setLeaving] = useState(null);
  const [vpa, setVpa] = useState({ open: false, value: "", busy: false, error: "" });

  const brand = cardBrand(form.num);
  const digits = form.num.replace(/\D/g, "");
  const numOk = luhn(form.num) && digits.length >= 15;
  const ok = numOk && form.name.trim().length > 1 && expiryOk(form.exp) && form.cvv.length >= 3;
  const set = (k) => (e) => {
    const v = e.target.value;
    setForm((f) => ({ ...f, [k]: k === "num" ? formatCard(v) : k === "exp" ? formatExpiry(v) : k === "cvv" ? v.replace(/\D/g, "").slice(0, 4) : v }));
  };

  const saveCard = async (e) => {
    e.preventDefault();
    if (!ok || saving) return;
    setSaving(true);
    await wait(reduced() ? 200 : 1300);
    const id = "c" + Date.now();
    setPay((p) => ({ ...p, cards: [...p.cards.map((c) => c), { id, brand: brand || "visa", last4: digits.slice(-4), name: form.name.trim(), exp: form.exp, bank: "Saved card", default: !p.cards.length }] }));
    setFresh(id); setSaving(false); setAdding(false); setForm({ num: "", name: "", exp: "", cvv: "" });
    flash?.("Card saved securely");
  };
  const removeOne = (kind, id) => {
    setConfirm(null); setLeaving(id);
    setTimeout(() => {
      setPay((p) => {
        const rest = p[kind].filter((x) => x.id !== id);
        if (rest.length && !rest.some((x) => x.default)) rest[0] = { ...rest[0], default: true };
        return { ...p, [kind]: rest };
      });
      setLeaving(null);
      flash?.(kind === "cards" ? "Card removed" : "UPI ID removed");
    }, reduced() ? 0 : 380);
  };
  const makeDefault = (kind, id) => setPay((p) => ({ ...p, [kind]: p[kind].map((x) => ({ ...x, default: x.id === id })) }));

  const addVpa = async () => {
    const v = vpa.value.trim().toLowerCase();
    if (pay.upis.some((u) => u.vpa === v)) return setVpa((s) => ({ ...s, error: "This UPI ID is already saved" }));
    setVpa((s) => ({ ...s, busy: true, error: "" }));
    const r = await demoGateway.verifyUpi(v);
    if (!r.ok) return setVpa((s) => ({ ...s, busy: false, error: r.error }));
    const id = "u" + Date.now();
    setPay((p) => ({ ...p, upis: [...p.upis, { id, vpa: v, name: r.name, app: upiApp(v).key, default: !p.upis.length }] }));
    setFresh(id); setVpa({ open: false, value: "", busy: false, error: "" });
    flash?.(`Verified · ${r.name}`);
  };

  return (
    <div className="ac-stack">
      <section className="ac-card ax-block">
        <div className="ac-card-head">
          <div><h3>Saved cards</h3><p>Pay faster at checkout. Only CVV is asked.</p></div>
          <span className="ax-count">{pay.cards.length}</span>
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
          <button className={"ax-cardslot ax-addcard" + (adding ? " ac-open" : "")} onClick={() => setAdding((v) => !v)} aria-expanded={adding} style={{ "--i": pay.cards.length }}>
            <span className="ac-add-ic"><Icon n="plus" size={18} /></span><b>Add a new card</b><small>Visa, Mastercard, RuPay, Amex</small>
          </button>
        </div>
        <div className={"ac-collapse" + (adding ? " ac-show" : "")}>
          <div><form className="ax-cardform" onSubmit={saveCard} inert={!adding}>
            <CardPreview num={form.num} name={form.name} exp={form.exp} flipped={cvvFocus} brand={brand} />
            <div className="co-form-grid ax-fields">
              <label className={"co-field ax-span2" + (digits.length >= 15 && !luhn(form.num) ? " co-err" : "")}>
                <input value={form.num} onChange={set("num")} placeholder=" " inputMode="numeric" autoComplete="cc-number" />
                <span>Card number</span>
                {brand && <b className={"co-brandtag co-inline co-b-" + brand} key={brand}>{BRAND_LABEL[brand]}</b>}
                {digits.length >= 15 && !luhn(form.num) && <em>Check the card number</em>}
              </label>
              <label className="co-field ax-span2"><input value={form.name} onChange={set("name")} placeholder=" " autoComplete="cc-name" /><span>Name on card</span></label>
              <label className={"co-field" + (form.exp.length === 5 && !expiryOk(form.exp) ? " co-err" : "")}>
                <input value={form.exp} onChange={set("exp")} placeholder=" " inputMode="numeric" autoComplete="cc-exp" /><span>Expiry (MM/YY)</span>
                {form.exp.length === 5 && !expiryOk(form.exp) && <em>Card expired or invalid</em>}
              </label>
              <label className="co-field"><input value={form.cvv} onChange={set("cvv")} onFocus={() => setCvvFocus(true)} onBlur={() => setCvvFocus(false)} placeholder=" " inputMode="numeric" type="password" autoComplete="cc-csc" /><span>CVV</span></label>
              <p className="ax-fine ax-span2"><Icon n="lock" size={14} />Your card is tokenised as per RBI rules. CVV is never stored.</p>
              <div className="ax-span2 ax-formact">
                <button type="button" className="ac-ghost" onClick={() => setAdding(false)}>Cancel</button>
                <button className="ac-primary" disabled={!ok || saving}>{saving ? <><i className="co-spin co-spin-w" />Securing card…</> : "Save card"}</button>
              </div>
            </div>
          </form></div>
        </div>
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
  if (r.type === "cash") return { big: inr(r.amount), small: "Cashback added to wallet" };
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
      <p className="ax-fine ax-center">{done ? (card.reward.type === "cash" ? "Cashback is in your 369 Wallet and never expires." : card.reward.type === "coupon" ? "Find it under Your coupons below." : "Every order above ₹199 earns a scratch card.") : "Drag your finger or mouse across the card."}</p>
    </Sheet>
  );
}

export function RewardsSec({ onWallet, onNav, flash }) {
  const [rw, setRw] = useStored(KEYS.rewards, SEED_REWARDS);
  const [open, setOpen] = useState(null);
  const [copied, setCopied] = useState(null);
  const won = rw.scratch.filter((s) => s.scratched && s.reward.type === "cash").reduce((s, c) => s + c.reward.amount, 0);
  const fresh = rw.scratch.filter((s) => !s.scratched).length;

  const onReveal = (card) => {
    setRw((r) => ({
      ...r,
      scratch: r.scratch.map((s) => (s.id === card.id ? { ...s, scratched: true } : s)),
      won: card.reward.type === "coupon" && !r.won.includes(card.reward.code) ? [card.reward.code, ...r.won] : r.won,
    }));
    if (card.reward.type === "cash") onWallet(card.reward.amount, { kind: "reward", title: "Scratch card reward", sub: `From ${card.from.replace(/^Order /, "order ")}` });
  };
  const copy = async (code) => { if (await copyText(code)) { setCopied(code); flash?.(`${code} copied`); setTimeout(() => setCopied((c) => (c === code ? null : c)), 1800); } };
  const { coupons: live } = useRules();
  const coupons = [...live].sort((a, b) => rw.won.includes(b.code) - rw.won.includes(a.code));

  return (
    <div className="ac-stack">
      <div className="ax-rewardstats">
        <span style={{ "--i": 0 }}><Icon n="wallet" size={20} /><b><Amount value={won} /></b><small>Cashback won</small></span>
        <span style={{ "--i": 1 }}><Icon n="gift" size={20} /><b>{fresh}</b><small>Cards to scratch</small></span>
        <span style={{ "--i": 2 }}><Icon n="ticket" size={20} /><b>{coupons.length}</b><small>Coupons available</small></span>
      </div>

      <section className="ac-card ax-block">
        <div className="ac-card-head"><div><h3>Scratch cards</h3><p>Earned on orders above ₹199 and on referrals.</p></div></div>
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
            <textarea value={r.text} maxLength={500} rows={4} placeholder="Tell others about quality, freshness, size or taste" onChange={(e) => setR({ ...r, text: e.target.value })} />
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
  const [reviews, setReviews] = useStored(KEYS.reviews, SEED_REVIEWS);
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

  const save = (id, r) => {
    setReviews((all) => ({ ...all, [id]: r }));
    setPosted(id);
    flash?.(r.edited ? "Review updated" : "Thanks! Your review is live");
  };
  const del = (id) => {
    setConfirm(null); setLeaving(id);
    setTimeout(() => { setReviews((all) => { const n = { ...all }; delete n[id]; return n; }); setLeaving(null); flash?.("Review deleted"); }, reduced() ? 0 : 360);
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
export function useNotifications(orders) {
  const [st, setSt] = useStored(KEYS.notifs, SEED_NOTIF_STATE);
  const all = useMemo(() => [...orderNotifs(orders), ...SEED_NOTIFS].filter((n) => !st.dismissed.includes(n.id)).sort((a, b) => b.at - a.at), [orders, st]);
  const unread = all.filter((n) => !st.read.includes(n.id)).length;
  return { all, st, setSt, unread };
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
  const { all, st, setSt, unread } = useNotifications(orders);
  const [prefs, setPrefs] = useStored(KEYS.notifPrefs, SEED_PREFS);
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
    if (!st.read.includes(n.id)) setSt((s) => ({ ...s, read: [...s.read, n.id] }));
    const [v, p] = n.go || [];
    setTimeout(() => { if (v === "account") goSection?.(p); else if (v) onNav?.(v, p); }, 220);
  };
  let row = 0;
  return (
    <div className="ac-stack">
      <div className="ax-notehead">
        <Tabs value={tab} onChange={setTab} tabs={[["all", "All", unread], ["order", "Orders", count("order")], ["offer", "Offers", count("offer")], ["wallet", "Wallet", count("wallet")]]} />
        <button className="ac-link ax-markall" disabled={!unread} onClick={() => setSt((s) => ({ ...s, read: [...new Set([...s.read, ...all.map((n) => n.id)])] }))}><Icon n="check" size={14} />Mark all as read</button>
      </div>
      <div className="ac-card ax-notes" key={tab}>
        {!list.length && <div className="ac-empty"><span className="ac-empty-art"><Icon n="bell" size={30} /></span><h3>You're all caught up</h3><p>New updates will show up here.</p></div>}
        {sections.map(([label, l]) => (
          <div key={label}>
            <p className="ax-month">{label}</p>
            {l.map((n) => (
              <NoteRow key={n.id} n={n} i={row++} now={now} unread={!st.read.includes(n.id)} onOpen={() => open(n)}
                onDismiss={() => setSt((s) => ({ ...s, dismissed: [...s.dismissed, n.id] }))} />
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
              <Switch on={locked ? true : !!prefs[k]} disabled={locked} label={t} onChange={(v) => { setPrefs((p) => ({ ...p, [k]: v })); setSaved((s) => s + 1); }} />
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
  ordered: { label: "Ordered", note: `${inr(REFER_REWARD)} earned`, tone: "green" },
  joined: { label: "Joined", note: "First order pending", tone: "blue" },
  invited: { label: "Invited", note: "Hasn't joined yet", tone: "grey" },
};

export function ReferSec({ user, flash }) {
  const [refs, setRefs] = useStored(KEYS.referrals, SEED_REFERRALS);
  const [copied, setCopied] = useState(false);
  const [reminded, setReminded] = useState({});
  const [invite, setInvite] = useState("");
  const [freshId, setFreshId] = useState(null);
  const code = ((user?.name || "friend").replace(/[^a-z]/gi, "").toUpperCase().slice(0, 6) || "FRIEND") + "369";
  const link = `https://369mart.in/r/${code}`;
  const message = `Get ${inr(REFER_REWARD)} off your first 369 Mart order with my code ${code}. Computer parts, fast: ${link}`;
  const ordered = refs.filter((r) => r.status === "ordered").length;
  const joined = refs.filter((r) => r.status !== "invited").length;
  const earned = ordered * REFER_REWARD;
  const pending = refs.filter((r) => r.status === "joined").length * REFER_REWARD;

  const copy = async () => { if (await copyText(code)) { setCopied(true); flash?.("Code copied"); setTimeout(() => setCopied(false), 1800); } };
  const share = async () => {
    if (navigator.share) { try { await navigator.share({ title: "369 Mart", text: message, url: link }); return; } catch (e) { return; } }
    if (await copyText(message)) flash?.("Invite message copied");
  };
  const add = (e) => {
    e.preventDefault();
    const name = invite.trim();
    if (name.length < 2) return;
    const id = "r" + Date.now();
    setRefs((l) => [{ id, name, status: "invited", at: Date.now() }, ...l]);
    setFreshId(id); setInvite("");
    flash?.(`Invite sent to ${name}`);
  };

  return (
    <div className="ac-stack">
      <section className="ax-refer">
        <div className="ax-refer-copy">
          <small>Refer & earn</small>
          <h3>Invite friends, earn {inr(REFER_REWARD)} each</h3>
          <p>Your friend gets {inr(REFER_REWARD)} off their first order above ₹299. You get {inr(REFER_REWARD)} in your wallet when it's delivered.</p>
        </div>
        <span className="ax-giftbox" aria-hidden="true">
          <i className="ax-gift-lid" /><i className="ax-gift-body" /><i className="ax-gift-ribbon" />
          <b className="ax-gift-coin c1">₹</b><b className="ax-gift-coin c2">₹</b><b className="ax-gift-coin c3">₹</b>
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
          <span><small>Pending</small><b>{inr(pending)}</b></span>
          <span><small>Friends joined</small><b>{joined}</b></span>
        </div>
        <div className="ax-goal" style={{ "--p": Math.min(1, joined / REFER_GOAL) }}>
          <div className="ax-goal-bar"><i />{Array.from({ length: REFER_GOAL }, (_, k) => <b key={k} className={k < joined ? "ax-hit" : ""} style={{ "--k": k, left: `${((k + 1) / REFER_GOAL) * 100}%` }}>{k + 1 === REFER_GOAL ? <Icon n="gift" size={12} /> : k + 1}</b>)}</div>
          <p>{joined >= REFER_GOAL ? `Bonus unlocked! ${inr(REFER_BONUS)} is on its way.` : <>Invite <b>{REFER_GOAL - joined} more</b> friend{REFER_GOAL - joined > 1 ? "s" : ""} to unlock a <b>{inr(REFER_BONUS)}</b> bonus</>}</p>
        </div>
      </section>

      <section className="ac-card ax-block" style={{ "--i": 2 }}>
        <div className="ac-card-head"><div><h3>How it works</h3></div></div>
        <ol className="ax-steps">
          {[["share", "Share your code", "Send it on WhatsApp or anywhere"], ["user", "Friend orders", `They get ${inr(REFER_REWARD)} off above ₹299`], ["wallet", "You earn", `${inr(REFER_REWARD)} lands in your wallet`]].map(([ic, t, d], k) => (
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
                <span className="ax-friend-txt"><b>{r.name}</b><small>{s.note}</small></span>
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
