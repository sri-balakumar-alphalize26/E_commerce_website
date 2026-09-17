"use client";
/* ==========================================================================
   369 Mart — Receipt printer (order success)
   A brass printer slot sits on top; the paper feeds out of it in small motor
   steps while the printer hums (Web Audio, can be muted). When it's done:
   Re-print receipt (paper rolls back into the slot and prints again) or
   Tear receipt (two tugs, a rip, the paper drops free and settles as a card
   with Download / Track order).
   ========================================================================== */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Icon, inr } from "./shared";

const SOUND_KEY = "369mart.sound";
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/* ---------- printer + tear sounds, synthesised (no audio files) ---------- */
function usePrinterSound(enabled) {
  const ctx = useRef(null);
  const live = useRef([]);
  const get = () => {
    if (typeof window === "undefined") return null;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!ctx.current) ctx.current = new AC();
    if (ctx.current.state === "suspended") ctx.current.resume().catch(() => {});
    return ctx.current;
  };
  const noise = (ac, secs) => {
    const buf = ac.createBuffer(1, Math.ceil(ac.sampleRate * secs), ac.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const src = ac.createBufferSource();
    src.buffer = buf;
    return src;
  };
  const stop = () => { live.current.forEach((n) => { try { n.stop(); } catch (e) {} }); live.current = []; };
  useEffect(() => { if (!enabled) stop(); }, [enabled]);
  useEffect(() => () => { stop(); ctx.current?.close?.().catch(() => {}); }, []);

  return {
    /* thermal print head: band-passed noise chopped by a fast square LFO */
    print(ms) {
      if (!enabled) return;
      const ac = get(); if (!ac) return;
      const t = ac.currentTime, secs = ms / 1000;
      const src = noise(ac, secs + 0.1);
      const bp = ac.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 2600; bp.Q.value = 0.9;
      const amp = ac.createGain(); amp.gain.value = 0;
      const lfo = ac.createOscillator(); lfo.type = "square"; lfo.frequency.value = 26;
      const lfoGain = ac.createGain(); lfoGain.gain.value = 0.05;
      const out = ac.createGain();
      out.gain.setValueAtTime(0, t); out.gain.linearRampToValueAtTime(1, t + 0.05);
      out.gain.setValueAtTime(1, t + secs - 0.12); out.gain.linearRampToValueAtTime(0, t + secs);
      lfo.connect(lfoGain).connect(amp.gain);
      amp.gain.setValueAtTime(0.06, t);
      src.connect(bp).connect(amp).connect(out).connect(ac.destination);
      /* motor whine underneath */
      const motor = ac.createOscillator(); motor.type = "sawtooth"; motor.frequency.value = 118;
      const mg = ac.createGain(); mg.gain.value = 0.012;
      const lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 600;
      motor.connect(lp).connect(mg).connect(out);
      src.start(t); lfo.start(t); motor.start(t);
      src.stop(t + secs + 0.05); lfo.stop(t + secs + 0.05); motor.stop(t + secs + 0.05);
      live.current.push(src, lfo, motor);
    },
    rewind(ms) {
      if (!enabled) return;
      const ac = get(); if (!ac) return;
      const t = ac.currentTime, secs = ms / 1000;
      const o = ac.createOscillator(); o.type = "sawtooth";
      o.frequency.setValueAtTime(90, t); o.frequency.linearRampToValueAtTime(160, t + secs);
      const g = ac.createGain(); g.gain.setValueAtTime(0.018, t); g.gain.linearRampToValueAtTime(0, t + secs);
      const lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 700;
      o.connect(lp).connect(g).connect(ac.destination); o.start(t); o.stop(t + secs);
      live.current.push(o);
    },
    rip() {
      if (!enabled) return;
      const ac = get(); if (!ac) return;
      const t = ac.currentTime;
      const src = noise(ac, 0.4);
      const hp = ac.createBiquadFilter(); hp.type = "highpass";
      hp.frequency.setValueAtTime(900, t); hp.frequency.exponentialRampToValueAtTime(4800, t + 0.28);
      const g = ac.createGain();
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.22, t + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.34);
      src.connect(hp).connect(g).connect(ac.destination); src.start(t); src.stop(t + 0.4);
      live.current.push(src);
    },
    tug() {
      if (!enabled) return;
      const ac = get(); if (!ac) return;
      const t = ac.currentTime;
      const src = noise(ac, 0.12);
      const bp = ac.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 1400;
      const g = ac.createGain(); g.gain.setValueAtTime(0.08, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.1);
      src.connect(bp).connect(g).connect(ac.destination); src.start(t); src.stop(t + 0.12);
      live.current.push(src);
    },
  };
}

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
  return (
    <div className="rc-paper" ref={paperRef} style={{ clipPath: edges(torn) }}>
      <div className="rc-top">
        <div>
          <span className="rc-brand">369<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 18 18 6M9 6h9v9" /></svg>MART</span>
          <small>{order.mode === "all" ? "EXPRESS ORDER RECEIPT" : "QUICK ORDER RECEIPT"}</small>
        </div>
        <span className="rc-seal" aria-hidden="true"><Icon n={cod ? "cash" : "check"} size={18} /></span>
      </div>
      <div className="rc-amount">{inr(order.paid)}.00</div>
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
          return <li key={id}><span>{q}X {p.name}</span><span>{inr(p.price * q)}.00</span></li>;
        })}
      </ul>
      <hr />
      <dl className="rc-bill">
        <div><dt>Item total (MRP)</dt><dd>{inr(b.mrp)}.00</dd></div>
        {b.mrp > b.items && <div><dt>Discount</dt><dd>-{inr(b.mrp - b.items)}.00</dd></div>}
        <div><dt>Delivery</dt><dd>{b.fees ? inr(b.fees) + ".00" : "FREE"}</dd></div>
        {b.couponOff > 0 && <div><dt>Coupon {order.coupon}</dt><dd>-{inr(b.couponOff)}.00</dd></div>}
        {order.walletUsed > 0 && <div><dt>369 Wallet</dt><dd>-{inr(order.walletUsed)}.00</dd></div>}
      </dl>
      <hr className="rc-solid" />
      <div className="rc-total"><span>{cod ? "TO PAY ON DELIVERY" : "TOTAL PAID"}</span><span>{inr(order.paid)}.00</span></div>
      {order.bill.mrp - order.bill.items + (b.couponOff || 0) > 0 && <p className="rc-saved">YOU SAVED {inr(order.bill.mrp - order.bill.items + (b.couponOff || 0))}.00 ON THIS ORDER</p>}
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

export default function ReceiptPrinter({ order, byId, onTrack, onShop }) {
  const [phase, setPhase] = useState("printing"); // printing | printed | rewinding | tearing | torn
  const [sound, setSound] = useState(true);
  const [pulled, setPulled] = useState(false);
  const paper = useRef(null);
  const printer = useRef(null);
  const anim = useRef(null);
  const sfx = usePrinterSound(sound);

  useEffect(() => { try { if (localStorage.getItem(SOUND_KEY) === "off") setSound(false); } catch (e) {} }, []);
  const toggleSound = () => setSound((s) => { try { localStorage.setItem(SOUND_KEY, s ? "off" : "on"); } catch (e) {} return !s; });

  const print = () => {
    const el = paper.current;
    if (!el) return;
    setPhase("printing");
    if (reduced() || !el.animate) { setPhase("printed"); return; }
    const ms = Math.max(1800, Math.min(4200, el.offsetHeight * 5.2));
    anim.current?.cancel();
    anim.current = el.animate(feedFrames(1), { duration: ms, easing: "linear", fill: "both" });
    printer.current?.animate([{ transform: "translateY(0)" }, { transform: "translateY(-0.6px)" }, { transform: "translateY(0.6px)" }], { duration: 90, iterations: Math.ceil(ms / 90) });
    sfx.print(ms);
    anim.current.onfinish = () => setPhase("printed");
  };

  useLayoutEffect(() => { const t = setTimeout(print, 650); return () => clearTimeout(t); }, []); // eslint-disable-line

  const reprint = () => {
    const el = paper.current;
    if (!el || phase !== "printed") return;
    if (reduced() || !el.animate) return print();
    setPhase("rewinding");
    anim.current?.cancel();
    sfx.rewind(520);
    anim.current = el.animate([{ transform: "translateY(0)" }, { transform: "translateY(-100%)" }], { duration: 520, easing: "cubic-bezier(.5,0,.75,0)", fill: "both" });
    anim.current.onfinish = () => setTimeout(print, 160);
  };

  const tear = async () => {
    const el = paper.current;
    if (!el || phase !== "printed") return;
    setPhase("tearing");
    if (reduced() || !el.animate) { setPulled(true); setPhase("torn"); return; }
    anim.current?.cancel();
    const tug = (y, r) => el.animate([{ transform: "translateY(0) rotate(0)" }, { transform: `translateY(${y}px) rotate(${r}deg)` }, { transform: "translateY(0) rotate(0)" }], { duration: 170, easing: "ease-out" }).finished;
    sfx.tug(); await tug(5, 0.6);
    sfx.tug(); await tug(8, -0.8);
    sfx.rip();
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

  return (
    <div className={"rc rc-" + phase}>
      <div className="rc-chip"><span className="rc-chip-ic"><Icon n="check" size={14} /></span>{cod ? `Order placed · pay ${inr(order.paid)} on delivery` : `${inr(order.paid)} paid · ${order.payNote || METHOD_LABEL[order.method]}`}</div>

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

      <button className={"rc-sound" + (sound ? "" : " rc-muted")} onClick={toggleSound} aria-pressed={!sound} aria-label={sound ? "Mute printer sound" : "Unmute printer sound"}>
        <Icon n={sound ? "volume" : "mute"} size={18} />
      </button>
    </div>
  );
}
