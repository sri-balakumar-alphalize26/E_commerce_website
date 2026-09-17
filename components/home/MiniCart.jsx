"use client";
/* ==========================================================================
   369 Mart — floating cart pill + mini cart panel
   Pill   springs in with the first item; thumbnails stack (newest first) and
          each one pops in when its flying product image lands; count and
          total roll. Tap → the pill grows into the panel (clip-path morph from
          the pill's exact box; transform-only, GPU), rows cascade in.
   Panel  Your cart (n) · rows with thumb, name, stepper, price (rows collapse
          out when removed) · free-delivery check (scooter drives across while
          "checking", then progress / unlocked) · subtotal · View cart and
          Checkout. Close / Esc / backdrop → shrinks back into the pill.
   ========================================================================== */
import { useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon, OpenContext, Thumb, inr, useFlying } from "./shared";
import { Amount } from "./Cart";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const inset = (from, box, r) => {
  const c = (v) => Math.max(0, v).toFixed(1) + "px";
  return `inset(${c(from.top - box.top)} ${c(box.right - from.right)} ${c(box.bottom - from.bottom)} ${c(from.left - box.left)} round ${r}px)`;
};

function PillThumb({ p, i }) {
  const flying = useFlying(p.id);
  return <span className={"mc-thumb" + (flying ? " mc-wait" : "")} data-thumb={p.id} style={{ "--i": i }}><Thumb p={p} /></span>;
}

function Row({ p, qty, setQty, i, onOpen }) {
  const [leaving, setLeaving] = useState(false);
  const change = (n) => {
    if (n <= 0) { setLeaving(true); setTimeout(() => setQty(p.id, 0), 300); }
    else setQty(p.id, n);
  };
  return (
    <li className={"mc-row" + (leaving ? " mc-leaving" : "")} data-row={p.id} style={{ "--i": i }}>
      <div>
        <button className="mc-row-img" onClick={() => onOpen(p)} aria-label={`Open ${p.name}`}><Thumb p={p} /></button>
        <div className="mc-row-txt">
          <small>{p.delivery ? "Express" : "Quick"} · {p.unit}</small>
          <b>{p.name}</b>
        </div>
        <div className="mc-step" role="group" aria-label={`${p.name} quantity`}>
          <button onClick={() => change(qty - 1)} aria-label={qty === 1 ? "Remove" : "Remove one"}>{qty === 1 ? <Icon n="trash" size={13} /> : "−"}</button>
          <span key={qty}>{qty}</span>
          <button onClick={() => change(qty + 1)} disabled={qty >= 12} aria-label="Add one">+</button>
        </div>
        <span className="mc-price"><Amount value={p.price * qty} /></span>
      </div>
    </li>
  );
}

function FreeCheck({ total, threshold, open }) {
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    if (!open) return;
    setChecking(true);
    const t = setTimeout(() => setChecking(false), reduced() ? 0 : 650);
    return () => clearTimeout(t);
  }, [open]);
  const left = Math.max(0, threshold - total);
  return (
    <div className={"mc-free" + (checking ? " mc-checking" : left ? "" : " mc-free-ok")}>
      {checking ? (
        <>
          <span className="mc-scoot" aria-hidden="true"><Icon n="scooter" size={18} /></span>
          <span className="mc-free-txt">Checking free delivery eligibility…</span>
        </>
      ) : left ? (
        <>
          <span className="mc-free-ic"><Icon n="scooter" size={16} /></span>
          <span className="mc-free-txt">Add <b><Amount value={left} /></b> more for <b>free delivery</b><i className="mc-bar"><em style={{ width: Math.min(100, (total / threshold) * 100) + "%" }} /></i></span>
        </>
      ) : (
        <>
          <span className="mc-free-ic"><Icon n="check" size={16} /></span>
          <span className="mc-free-txt"><b>Free delivery unlocked</b> on this order</span>
        </>
      )}
    </div>
  );
}

export default function MiniCart({ lines, count, total, freeAt = 499, setQty, onViewCart, onCheckout, hidden = false }) {
  const [phase, setPhase] = useState("closed"); // closed | open | closing
  const pill = useRef(null);
  const panel = useRef(null);
  const back = useRef(null);
  const fromRect = useRef(null);
  const anim = useRef([]);
  const openProduct = useContext(OpenContext);

  const show = count > 0 && !hidden;
  useEffect(() => { if (!show && phase !== "closed") { anim.current.forEach((a) => a.cancel()); setPhase("closed"); } }, [show]); // eslint-disable-line

  const open = () => {
    if (!pill.current || phase !== "closed") return;
    fromRect.current = pill.current.getBoundingClientRect();
    setPhase("open");
  };

  /* Morph = one GPU layer (.mc-bg) scaled from the pill's box to the panel's box.
     Only transform + opacity animate, so the page behind is never repainted. */
  const morph = (el, from, box) => {
    const sx = Math.max(0.05, from.width / box.width), sy = Math.max(0.05, from.height / box.height);
    const r = from.height / 2;
    return {
      t: `translate(${(from.left - box.left).toFixed(1)}px, ${(from.top - box.top).toFixed(1)}px) scale(${sx.toFixed(4)}, ${sy.toFixed(4)})`,
      radius: `${(r / sx).toFixed(1)}px / ${(r / sy).toFixed(1)}px`,
    };
  };

  useLayoutEffect(() => {
    if (phase !== "open" || !panel.current) return;
    const el = panel.current;
    const bg = el.querySelector(".mc-bg");
    el.querySelector(".mc-x")?.focus({ preventScroll: true });
    if (reduced() || !el.animate || !fromRect.current) { el.setAttribute("data-in", ""); return; }
    const box = el.getBoundingClientRect();
    const m = morph(el, fromRect.current, box);
    anim.current.forEach((a) => a.cancel());
    const ease = "cubic-bezier(.16,1,.3,1)";
    anim.current = [
      bg.animate([{ transform: m.t, borderRadius: m.radius }, { transform: "none", borderRadius: "22px" }], { duration: 340, easing: ease }),
      back.current.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: "ease-out" }),
    ];
    void el.offsetWidth; /* commit the hidden state so the content fade actually runs */
    el.setAttribute("data-in", ""); /* content fades in on its own short delay (CSS) */
  }, [phase]);

  const close = (after) => {
    if (phase !== "open") return; /* ignores repeat taps while it is closing */
    const el = panel.current;
    /* Don't cancel the finished animations here: cancelling drops their "forwards" fill, so the
       panel and backdrop flashed back to fully open for a frame before unmounting (looked like it
       re-opened and closed again). The pill is swapped in instantly where the panel shrank to. */
    const done = () => {
      const pl = pill.current;
      if (pl) { pl.style.transition = "none"; requestAnimationFrame(() => requestAnimationFrame(() => { pl.style.transition = ""; })); }
      anim.current = [];
      setPhase("closed");
      after?.();
    };
    if (reduced() || !el?.animate) { anim.current.forEach((a) => a.cancel()); return done(); }
    el.removeAttribute("data-in");
    setPhase("closing");
    const box = el.getBoundingClientRect();
    const to = pill.current?.getBoundingClientRect() || fromRect.current;
    const m = morph(el, to, box);
    anim.current.forEach((a) => a.cancel());
    const bg = el.querySelector(".mc-bg");
    const a = bg.animate([{ transform: "none", borderRadius: "22px" }, { transform: m.t, borderRadius: m.radius }], { duration: 260, delay: 60, easing: "cubic-bezier(.5,0,.2,1)", fill: "forwards" });
    const b = back.current.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 240, delay: 60, fill: "forwards" });
    anim.current = [a, b];
    a.onfinish = done;
  };

  useEffect(() => {
    if (phase !== "open") return;
    const k = (e) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }); // eslint-disable-line

  const thumbs = lines.slice(-3).reverse();
  const isOpen = phase !== "closed";

  return (
    <div className="mc">
      <button ref={pill} className={"mc-pill" + (show ? " mc-show" : "") + (isOpen ? " mc-under" : "")} onClick={open}
        tabIndex={show ? 0 : -1} aria-hidden={!show} aria-haspopup="dialog" aria-expanded={isOpen}>
        <span className="mc-thumbs">
          {thumbs.map((l, i) => <PillThumb key={l.p.id} p={l.p} i={i} />)}
        </span>
        <span className="mc-pill-txt">
          <b>View cart</b>
          <small><span key={count} className="mc-roll">{count} {count === 1 ? "item" : "items"}</span> · <Amount value={total} /></small>
        </span>
        <span className="mc-go"><Icon n="right" size={16} /></span>
      </button>

      {isOpen && (
        <>
          <div className="mc-back" ref={back} onClick={() => close()} />
          <section ref={panel} className="mc-panel" role="dialog" aria-modal="true" aria-label="Your cart">
            <i className="mc-bg" aria-hidden="true" />
            <header className="mc-head">
              <span className="mc-head-ic"><Icon n="bag" size={17} /></span>
              <b>Your cart</b>
              <em key={count}>{count}</em>
              <button className="mc-x" onClick={() => close()} aria-label="Close cart"><Icon n="x" size={16} /></button>
            </header>
            <ul className="mc-rows">
              {[...lines].reverse().map((l, i) => (
                <Row key={l.p.id} p={l.p} qty={l.qty} setQty={setQty} i={i} onOpen={(p) => close(() => openProduct?.(p, null))} />
              ))}
            </ul>
            <FreeCheck total={total} threshold={freeAt} open={phase === "open"} />
            <div className="mc-sub"><span>Subtotal</span><b><Amount value={total} /></b></div>
            <div className="mc-actions">
              <button className="mc-view" onClick={() => close(onViewCart)}>View cart</button>
              <button className="mc-checkout" onClick={() => close(onCheckout)}>
                <span>Proceed to checkout</span><span className="mc-checkout-amt"><Amount value={total} /><Icon n="right" size={15} /></span>
              </button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
