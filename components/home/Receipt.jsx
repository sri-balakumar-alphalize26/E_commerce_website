"use client";
/* ==========================================================================
   369 Mart — Receipt printer (order success)
   A brass printer slot sits on top; the paper feeds out of it in small motor
   steps while the printer chatters (Web Audio, can be muted) and the page
   scrolls with the paper so the printing edge stays in view; the scroll
   stops when the paper ends (or as soon as you scroll yourself). When it's done:
   Re-print receipt (paper rolls back into the slot and prints again) or
   Tear receipt (two tugs, a rip, the paper drops free and settles as a card
   with Download / Track order).
   ========================================================================== */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Icon, money } from "./shared";
import { audioRunning, onAudioState, playPrint, playRewind, playRip, playTug, unlockAudio } from "./sound";

const SOUND_KEY = "369mart.sound";
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/* ---------- barcode from the transaction id ---------- */
function Barcode({ value }) {
  const bars = useMemo(() => {
    const out = [];
    let x = 0;
    const seed = [...String(value)].map((c) => c.charCodeAt(0));
    for (let i = 0; i < 46; i++) {
      const v = seed[i % seed.length] * (i + 3);
      const w = 1 + (v % 3), gap = 1 + ((v >> 2) % 2);
      out.push([x, w]);
      x += w + gap;
    }
    return { out, width: x };
  }, [value]);
  return (
    <svg className="rc-barcode" viewBox={`0 0 ${bars.width} 30`} preserveAspectRatio="none" aria-hidden="true">
      {bars.out.map(([x, w], i) => <rect key={i} x={x} y="0" width={w} height="30" />)}
    </svg>
  );
}

/* zig-zag paper edges; same vertex count torn or not, so clip-path can animate */
function edges(torn) {
  const n = 24, top = [], bottom = [];
  for (let i = 0; i <= n; i++) {
    const x = (i / n) * 100;
    top.push(`${x.toFixed(2)}% ${torn && i % 2 ? 6 : 0}px`);
    bottom.push(`${(100 - x).toFixed(2)}% calc(100% - ${i % 2 ? 7 : 0}px)`);
  }
  return `polygon(${[...top, ...bottom].join(", ")})`;
}

const METHOD_LABEL = { upi: "UPI", card: "Card", netbanking: "Net banking", wallet: "369 Wallet", cod: "Cash on delivery" };

function ReceiptPaper({ order, byId, paperRef, torn }) {
  const b = order.bill;
  const when = new Date(order.at || Date.now());
  const date = when.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
  const time = when.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }).toUpperCase();
  const cod = order.method === "cod";
  const cur = order.currency; /* what this order was charged in, not what the shop quotes today */
  return (
    <div className="rc-paper" ref={paperRef} style={{ clipPath: edges(torn) }}>
      <div className="rc-top">
        <div>
          <span className="rc-brand">369<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 18 18 6M9 6h9v9" /></svg>MART</span>
          <small>{order.mode === "all" ? "EXPRESS ORDER RECEIPT" : "QUICK ORDER RECEIPT"}</small>
        </div>
        <span className="rc-seal" aria-hidden="true"><Icon n={cod ? "cash" : "check"} size={18} /></span>
      </div>
      <div className="rc-amount">{money(order.paid || order.total, cur)}</div>
      <div className="rc-sub">{date} | {cod ? "PAY ON DELIVERY" : "PAID"} · {METHOD_LABEL[order.method] || "ONLINE"}</div>
      <div className="rc-meta">
        <span>ORDER</span><span>{order.id}</span>
        <span>TIME</span><span>{time}</span>
        {order.payNote && <><span>VIA</span><span>{order.payNote}</span></>}
      </div>
      <hr />
      <ul className="rc-items">
        {order.items.map(([id, q]) => {
          const p = byId[id] || order.snap?.[id];
          if (!p) return null;
          return <li key={id}><span>{q}X {p.name}</span><span>{money(p.price * q, cur)}</span></li>;
        })}
      </ul>
      <hr />
      <dl className="rc-bill">
        <div><dt>Item total (MRP)</dt><dd>{money(b.mrp, cur)}</dd></div>
        {b.mrp > b.items && <div><dt>Discount</dt><dd>-{money(b.mrp - b.items, cur)}</dd></div>}
        <div><dt>Delivery</dt><dd>{b.fees ? money(b.fees, cur) : "FREE"}</dd></div>
        {b.couponOff > 0 && <div><dt>Coupon {order.coupon}</dt><dd>-{money(b.couponOff, cur)}</dd></div>}
        {order.walletUsed > 0 && <div><dt>369 Wallet</dt><dd>-{money(order.walletUsed, cur)}</dd></div>}
      </dl>
      <hr className="rc-solid" />
      <div className="rc-total"><span>{cod ? "TO PAY ON DELIVERY" : "TOTAL PAID"}</span><span>{money(order.paid || order.total, cur)}</span></div>
      {order.bill.mrp - order.bill.items + (b.couponOff || 0) > 0 && <p className="rc-saved">YOU SAVED {money(order.bill.mrp - order.bill.items + (b.couponOff || 0), cur)} ON THIS ORDER</p>}
      <div className="rc-deliver">
        <b>DELIVER TO {order.address?.label?.toUpperCase()}</b>
        <span>{order.address?.line}{order.address?.city ? ", " + order.address.city : ""}</span>
        <span>{order.slot}</span>
      </div>
      <p className="rc-thanks">THANK YOU FOR SHOPPING!</p>
      <Barcode value={order.txn} />
      <p className="rc-txn">{order.txn}</p>
    </div>
  );
}

/* motor-step keyframes: feed, pause, feed, pause … */
function feedFrames(dir = 1) {
  const steps = 22, frames = [];
  for (let i = 0; i <= steps; i++) {
    const k = i / steps;
    const y = dir > 0 ? -100 + k * 100 : -k * 100;
    frames.push({ transform: `translateY(${y}%)`, offset: Math.min(1, k) });
    if (i < steps) frames.push({ transform: `translateY(${y}%)`, offset: Math.min(1, k + 0.45 / steps) });
  }
  return frames;
}

const FEED_STEPS = 22;

export default function ReceiptPrinter({ order, byId, onTrack, onShop }) {
  const [phase, setPhase] = useState("printing"); // printing | printed | rewinding | tearing | torn
  const [sound, setSound] = useState(true);
  const [needTap, setNeedTap] = useState(false);
  const [pulled, setPulled] = useState(false);
  const paper = useRef(null);
  const printer = useRef(null);
  const anim = useRef(null);
  const stopSound = useRef(() => {});
  const run = useRef(null); /* { t0, ms } of the current print */
  const soundOn = useRef(true);
  soundOn.current = sound;
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  useEffect(() => { try { if (localStorage.getItem(SOUND_KEY) === "off") setSound(false); } catch (e) {} }, []);
  useEffect(() => () => { stopSound.current(); cancelAnimationFrame(follow.current.raf); }, []); // eslint-disable-line

  /* play the print sound from wherever the paper is now */
  const soundFromNow = () => {
    const r = run.current;
    if (!r || !soundOn.current) return;
    const done = (performance.now() - r.t0) / r.ms;
    if (done >= 0.97) return;
    if (!audioRunning()) { setNeedTap(true); return; }
    setNeedTap(false);
    stopSound.current();
    const from = Math.min(FEED_STEPS - 1, Math.floor(done * FEED_STEPS));
    stopSound.current = playPrint({ ms: r.ms, steps: FEED_STEPS, from });
  };
  /* sound unlocked later (e.g. first tap on this page) → join in mid-print */
  useEffect(() => onAudioState((st) => { if (st === "running") { setNeedTap(false); if (phaseRef.current === "printing") soundFromNow(); } }), []); // eslint-disable-line

  const toggleSound = () => {
    const next = !sound;
    setSound(next);
    soundOn.current = next;
    try { localStorage.setItem(SOUND_KEY, next ? "on" : "off"); } catch (e) {}
    if (!next) { stopSound.current(); setNeedTap(false); return; }
    unlockAudio().then(() => { if (phaseRef.current === "printing") soundFromNow(); });
  };

  /* ---- auto-scroll: keep the paper's bottom edge in view while it feeds ---- */
  const follow = useRef({ raf: 0, user: false });
  const stopFollow = () => { cancelAnimationFrame(follow.current.raf); window.removeEventListener("wheel", userScroll); window.removeEventListener("touchmove", userScroll); window.removeEventListener("keydown", userKey); };
  function userScroll() { follow.current.user = true; }
  function userKey(e) { if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(e.key)) follow.current.user = true; }
  const startFollow = () => {
    stopFollow();
    follow.current.user = false;
    window.addEventListener("wheel", userScroll, { passive: true });
    window.addEventListener("touchmove", userScroll, { passive: true });
    window.addEventListener("keydown", userKey);
    const tick = () => {
      const el = paper.current;
      if (!el || !anim.current || anim.current.playState !== "running") return stopFollow();
      if (!follow.current.user) {
        const bottom = el.getBoundingClientRect().bottom;
        const keep = Math.min(230, window.innerHeight * 0.32); /* room for the title and buttons under the paper */
        const over = bottom - (window.innerHeight - keep);
        if (over > 1) window.scrollTo(0, window.scrollY + over * 0.22);
      }
      follow.current.raf = requestAnimationFrame(tick);
    };
    follow.current.raf = requestAnimationFrame(tick);
  };

  const print = () => {
    const el = paper.current;
    if (!el) return;
    setPhase("printing");
    if (reduced() || !el.animate) { setPhase("printed"); return; }
    const ms = Math.max(1800, Math.min(4200, el.offsetHeight * 5.2));
    anim.current?.cancel();
    anim.current = el.animate(feedFrames(1), { duration: ms, easing: "linear", fill: "both" });
    printer.current?.animate([{ transform: "translateY(0)" }, { transform: "translateY(-0.6px)" }, { transform: "translateY(0.6px)" }], { duration: 90, iterations: Math.ceil(ms / 90) });
    run.current = { t0: performance.now(), ms };
    stopSound.current();
    if (soundOn.current) {
      if (audioRunning()) stopSound.current = playPrint({ ms, steps: FEED_STEPS });
      else setNeedTap(true);
    }
    startFollow();
    anim.current.onfinish = () => { stopFollow(); run.current = null; setNeedTap(false); setPhase("printed"); };
  };

  useLayoutEffect(() => { const t = setTimeout(print, 650); return () => { clearTimeout(t); stopFollow(); }; }, []); // eslint-disable-line

  const reprint = () => {
    const el = paper.current;
    if (!el || phase !== "printed") return;
    if (reduced() || !el.animate) return print();
    setPhase("rewinding");
    anim.current?.cancel();
    if (sound) { unlockAudio(); stopSound.current = playRewind({ ms: 520 }); }
    window.scrollTo({ top: 0, behavior: "smooth" }); /* watch it print again from the top */
    anim.current = el.animate([{ transform: "translateY(0)" }, { transform: "translateY(-100%)" }], { duration: 520, easing: "cubic-bezier(.5,0,.75,0)", fill: "both" });
    anim.current.onfinish = () => setTimeout(print, 160);
  };

  const tear = async () => {
    const el = paper.current;
    if (!el || phase !== "printed") return;
    setPhase("tearing");
    if (reduced() || !el.animate) { setPulled(true); setPhase("torn"); return; }
    anim.current?.cancel();
    if (sound) unlockAudio();
    const tug = (y, r) => el.animate([{ transform: "translateY(0) rotate(0)" }, { transform: `translateY(${y}px) rotate(${r}deg)` }, { transform: "translateY(0) rotate(0)" }], { duration: 170, easing: "ease-out" }).finished;
    if (sound) playTug({}); await tug(5, 0.6);
    if (sound) playTug({}); await tug(8, -0.8);
    if (sound) playRip({});
    setPulled(true); /* top edge becomes jagged */
    const drop = el.animate(
      [{ transform: "translateY(0) rotate(0)" }, { transform: "translateY(26px) rotate(-3.5deg)", offset: 0.45 }, { transform: "translateY(16px) rotate(1.2deg)", offset: 0.75 }, { transform: "translateY(20px) rotate(-1.2deg)" }],
      { duration: 700, easing: "cubic-bezier(.3,.7,.3,1)", fill: "forwards" }
    );
    await drop.finished;
    setPhase("torn");
    drop.cancel();
  };

  const busy = phase === "printing" || phase === "rewinding" || phase === "tearing";
  const cod = order.method === "cod";
  const cur = order.currency; /* what this order was charged in, not what the shop quotes today */

  return (
    <div className={"rc rc-" + phase}>
      <div className="rc-chip"><span className="rc-chip-ic"><Icon n="check" size={14} /></span>{cod ? `Order placed · pay ${money(order.paid || order.total, cur)} on delivery` : `${money(order.paid || order.total, cur)} paid · ${order.payNote || METHOD_LABEL[order.method]}`}</div>

      <div className="rc-stage">
        <div className="rc-printer" ref={printer} aria-hidden="true">
          <i className="rc-screw rc-l" /><i className="rc-screw rc-r" />
          <span className="rc-led" />
          <i className="rc-lip" />
        </div>
        <div className="rc-feed">
          <ReceiptPaper order={order} byId={byId} paperRef={paper} torn={pulled} />
        </div>
      </div>

      <div className="rc-copy">
        <h1 key={phase === "torn" ? "t" : "p"}>{phase === "torn" ? "Receipt saved to your orders" : cod ? "Order placed" : "Payment successful"}</h1>
        <p>{phase === "torn" ? `Order ${order.id} · ${order.slot}` : phase === "printed" ? "You're all set — keep a copy or tear it off." : "You're all set — now let the receipt roll!"}</p>
      </div>

      <div className="rc-actions">
        {phase === "torn" ? (
          <>
            <button className="rc-btn" onClick={() => window.print()}><Icon n="note" size={16} />Download receipt</button>
            <button className="rc-btn rc-gold" onClick={onTrack}><Icon n="box" size={16} />Track order</button>
            <button className="rc-link" onClick={onShop}>Continue shopping</button>
          </>
        ) : busy && phase !== "tearing" ? (
          <button className="rc-btn rc-wait" disabled><Icon n="printer" size={16} className="rc-print-ic" />{phase === "rewinding" ? "Rewinding…" : "Printing…"}</button>
        ) : (
          <>
            <button className="rc-btn" onClick={reprint} disabled={busy}><Icon n="printer" size={16} />Re-print receipt</button>
            <button className="rc-btn rc-gold" onClick={tear} disabled={busy}><Icon n="scissors" size={16} />Tear receipt</button>
          </>
        )}
      </div>

      {needTap && sound && <button className="rc-sound-hint" onClick={() => unlockAudio().then(soundFromNow)}><Icon n="volume" size={14} />Tap for printer sound</button>}
      <button className={"rc-sound" + (sound ? "" : " rc-muted") + (needTap && sound ? " rc-need" : "")} onClick={needTap && sound ? () => unlockAudio().then(soundFromNow) : toggleSound} aria-pressed={!sound} aria-label={sound ? "Mute printer sound" : "Unmute printer sound"}>
        <Icon n={sound ? "volume" : "mute"} size={18} />
      </button>
    </div>
  );
}
