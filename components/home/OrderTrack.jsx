"use client";
/* ==========================================================================
   369 Mart — After the order   (/track/<id>)
   Hero      status art that changes per step (bag pulse → box closing →
             scooter riding → tick burst / cancelled), ETA that counts down
   Map       Quick: store → home route, rider moves along it, travelled part
             fills, remaining part marches; home pin pulses
   Journey   Express: truck rolls along hub rail with scan events
   Timeline  steps fill one by one with times; active step pulses
   Rider     name, rating, vehicle, call / chat, 4-digit delivery OTP
   Actions   Cancel (reason sheet → refund to source or wallet) · Rate order
             (stars, tags, per item, tip, comment → thank-you burst) · Return /
             replace (pick items → reason → refund or replace + pickup slot →
             return tracker) · Help chat · View receipt · Reorder
   ========================================================================== */
import { useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon, OpenContext, Thumb, money } from "./shared";
import {
  RETURN_STEPS, cancellable, fmtDay, fmtPlaced, fmtTime, liveStatus, returnStatus, returnable, riderFor,
} from "./orderState";
import { api } from "@/lib/api";
import { useAction } from "@/lib/useFetch";
import { addressText } from "@/lib/address";
import { EARN_WHEN, pointsText } from "./points";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const lineName = (o, byId, id) => byId[id]?.name || o.snap?.[id]?.name || "Item";
/* An amount off this order, printed in the money that order was charged
   in - not whatever the shop happens to be quoting today. */
const moneyOf = (o) => (n) => money(n, o?.currency);
/* What this order was charged for the item, not today's catalogue price - a
   price change, or a replacement the shop paid the difference on, must not
   rewrite what the customer sees they paid. */
const linePrice = (o, byId, id) => o.snap?.[id]?.price ?? byId[id]?.price ?? 0;

/* ---------------- bottom sheet / dialog ---------------- */
function Sheet({ title, onClose, children, foot, wide }) {
  const [out, setOut] = useState(false);
  const close = () => { if (reduced()) return onClose(); setOut(true); setTimeout(onClose, 260); };
  useEffect(() => {
    const k = (e) => e.key === "Escape" && close();
    window.addEventListener("keydown", k);
    document.documentElement.classList.add("ls-lock");
    return () => { window.removeEventListener("keydown", k); document.documentElement.classList.remove("ls-lock"); };
  }); // eslint-disable-line
  return createPortal(
    <div className={"ot-sheet-wrap" + (out ? " ot-out" : "")} onClick={close}>
      <section className={"ot-sheet" + (wide ? " ot-wide" : "")} role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <span className="ot-grab" />
        <header><h3>{title}</h3><button className="ot-x" onClick={close} aria-label="Close"><Icon n="x" size={16} /></button></header>
        <div className="ot-sheet-body">{typeof children === "function" ? children(close) : children}</div>
        {foot && <footer>{typeof foot === "function" ? foot(close) : foot}</footer>}
      </section>
    </div>,
    document.querySelector(".hm-page") || document.body
  );
}

/* ---------------- hero art ---------------- */
function StatusArt({ k }) {
  return (
    <span className={"ot-art ot-art-" + k} aria-hidden="true" key={k}>
      {k === "placed" && <><i className="ot-ring" /><i className="ot-ring ot-r2" /><span className="ot-art-ic"><Icon n="bag" size={30} /></span></>}
      {(k === "packed" || k === "shipped") && (
        <span className="ot-box"><i className="ot-flap ot-fl" /><i className="ot-flap ot-fr" /><i className="ot-tape" /><b /></span>
      )}
      {k === "out" && (
        <span className="ot-ride">
          <i className="ot-speed" /><i className="ot-speed ot-s2" /><i className="ot-speed ot-s3" />
          <span className="ot-art-ic"><Icon n="scooter" size={34} /></span>
          <i className="ot-road" />
        </span>
      )}
      {k === "delivered" && (
        <>
          <span className="ot-burst">{Array.from({ length: 10 }, (_, i) => <i key={i} style={{ "--k": i }} />)}</span>
          <svg className="ot-tick" viewBox="0 0 64 64"><circle cx="32" cy="32" r="28" /><path d="M20 33l8 8 16-17" /></svg>
        </>
      )}
      {k === "cancelled" && <svg className="ot-cross" viewBox="0 0 64 64"><circle cx="32" cy="32" r="28" /><path d="M23 23l18 18M41 23 23 41" /></svg>}
    </span>
  );
}

/* ---------------- quick map ---------------- */
const ROUTE = "M78 236 C 140 236 150 170 214 164 S 300 176 318 120 S 420 70 470 96 S 520 84 540 64";
function LiveMap({ s, rider, address }) {
  const path = useRef(null);
  const [len, setLen] = useState(0);
  const [pos, setPos] = useState({ x: 78, y: 236 });
  const shown = useRef(0);
  const raf = useRef(0);
  const target = s.idx < 2 ? 0 : s.idx === 2 ? s.progress : 1;
  useLayoutEffect(() => { if (path.current) setLen(path.current.getTotalLength()); }, []);
  useEffect(() => {
    if (!len) return;
    const from = shown.current, t0 = performance.now(), dur = reduced() ? 0 : 900;
    const step = (now) => {
      const k = dur ? Math.min(1, (now - t0) / dur) : 1;
      const v = from + (target - from) * (1 - Math.pow(1 - k, 3));
      shown.current = v;
      const pt = path.current.getPointAtLength(len * v);
      setPos({ x: pt.x, y: pt.y });
      if (k < 1) raf.current = requestAnimationFrame(step);
    };
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [target, len]);
  const km = (2.4 * (1 - target)).toFixed(1);
  const bubble = s.idx < 2 ? "Packing your order" : s.idx === 2 ? `${rider.name.split(" ")[0]} is ${km} km away` : "Delivered";
  return (
    <div className={"ot-map ot-map-" + s.key}>
      <svg viewBox="0 0 600 300" preserveAspectRatio="xMidYMid slice" role="img" aria-label={`Rider route. ${bubble}`}>
        <rect width="600" height="300" className="ot-land" />
        <path d="M-10 60 C 120 40 180 100 300 70 S 520 10 620 30 V -10 H -10z" className="ot-water" />
        <ellipse cx="460" cy="220" rx="90" ry="46" className="ot-park" />
        <ellipse cx="150" cy="96" rx="60" ry="28" className="ot-park" />
        {[["M0 200 H600", 14], ["M0 130 C 200 150 400 120 600 150", 12], ["M120 0 V300", 12], ["M380 0 C 360 120 420 200 400 300", 12], ["M250 300 C 260 200 230 120 280 0", 10], ["M520 300 V120 H600", 10]].map(([d, w], i) => (
          <path key={i} d={d} className="ot-road-bg" strokeWidth={w} />
        ))}
        {[[40, 150, 60, 36], [180, 215, 50, 30], [300, 222, 64, 40], [430, 150, 56, 32], [210, 88, 44, 28], [520, 176, 42, 30], [60, 255, 40, 24]].map(([x, y, w, h], i) => (
          <rect key={i} x={x} y={y} width={w} height={h} rx="6" className="ot-block" />
        ))}
        <path ref={path} d={ROUTE} className="ot-route-rest" />
        {len > 0 && <path d={ROUTE} className="ot-route-done" style={{ strokeDasharray: len, strokeDashoffset: len * (1 - shown.current) }} />}
        <g transform="translate(78 236)" className="ot-pin-store">
          <circle r="16" /><text y="4" textAnchor="middle">369</text>
        </g>
        <g transform="translate(540 64)" className="ot-pin-home">
          <circle r="26" className="ot-pulse" /><circle r="15" />
          <path d="M-6 1 0 -5 6 1 V6 H-6z" />
        </g>
        <g transform={`translate(${pos.x} ${pos.y})`} className="ot-rider">
          <circle r="19" className="ot-rider-halo" />
          <circle r="14" className="ot-rider-dot" />
          <g transform="translate(-9 -9) scale(.75)"><path d="M8.5 17h6.5l2-6h-4l-2 4M15 5h3l1 6" /><circle cx="6" cy="17" r="2.5" /><circle cx="18" cy="17" r="2.5" /></g>
        </g>
      </svg>
      <span className="ot-bubble" key={bubble} style={{ left: `${(pos.x / 600) * 100}%`, top: `${(pos.y / 300) * 100}%` }}>{bubble}</span>
      <span className="ot-map-addr"><Icon n="home" size={13} />{address?.label || "Home"}</span>
    </div>
  );
}

/* ---------------- express journey ---------------- */
function Journey({ s, o }) {
  const hubs = ["Seller", "Bengaluru hub", "Kochi hub", "You"];
  const pct = s.idx <= 0 ? s.progress * 0.33 * 0.5 : s.idx === 1 ? 0.33 + s.progress * 0.33 : s.idx === 2 ? 0.66 + s.progress * 0.3 : 1;
  const events = [
    [0, "Order confirmed by seller", "Kochi"],
    [1, "Shipped · in transit to Kochi hub", "Bengaluru hub"],
    [2, "Out for delivery", "Kochi hub"],
    [3, "Delivered", o.address?.town || o.address?.city || "Kochi"],
  ].filter(([i]) => i <= s.idx).reverse();
  return (
    <div className="ot-journey">
      <div className="ot-rail" style={{ "--p": pct }}>
        <i className="ot-rail-line"><b /></i>
        {hubs.map((h, i) => <span key={h} className={"ot-hub" + (pct >= i / 3 - 0.001 ? " ot-on" : "")} style={{ left: `${(i / 3) * 100}%` }}><i />{h}</span>)}
        <span className="ot-truck" style={{ left: `${pct * 100}%` }}><Icon n="truck" size={20} /></span>
      </div>
      <ul className="ot-events">
        {events.map(([i, t, where], k) => (
          <li key={i} style={{ "--k": k }} className={k === 0 ? "ot-latest" : ""}>
            <i /><div><b>{t}</b><small>{where} · {s.times[i] ? `${fmtDay(s.times[i])}, ${fmtTime(s.times[i])}` : fmtDay(o.at, i)}</small></div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ---------------- timeline ---------------- */
function Timeline({ s, o }) {
  if (s.key === "cancelled") {
    return (
      <ol className="ot-steps ot-cancelled">
        <li className="ot-done"><i><Icon n="check" size={12} /></i><div><b>Order placed</b><small>{fmtPlaced(o.at)}</small></div></li>
        <li className="ot-done ot-red"><i><Icon n="x" size={12} /></i><div><b>Cancelled</b><small>{o.cancel?.reason || "Cancelled"}{o.cancel?.at ? ` · ${fmtTime(o.cancel.at)}` : ""}</small></div></li>
      </ol>
    );
  }
  return (
    <ol className="ot-steps" style={{ "--p": Math.min(1, (s.idx + (s.idx < 3 ? s.progress * 0.9 : 0)) / 3) }}>
      <span className="ot-steps-line" aria-hidden="true"><b /></span>
      {s.steps.map((st, i) => (
        <li key={st.key} className={(i < s.idx || s.idx === 3 ? "ot-done" : "") + (i === s.idx && s.idx < 3 ? " ot-now" : "")}>
          <i key={i <= s.idx ? "d" : "p"}>{i < s.idx || s.idx === 3 ? <Icon n="check" size={12} /> : i === s.idx ? <b /> : null}</i>
          <div>
            <b>{st.label}</b>
            <small>{i <= s.idx ? (s.times[i] ? fmtTime(s.times[i]) + " · " : "") + st.sub : i === 3 ? (o.eta || `Expected ${fmtDay(o.at, 3)}`) : "Pending"}</small>
          </div>
        </li>
      ))}
    </ol>
  );
}

/* ---------------- cancel ---------------- */
const CANCEL_REASONS = ["Ordered by mistake", "Want to change items or quantity", "Delivery is taking too long", "Found a better price elsewhere", "Want to change the address or slot", "Other"];
function CancelSheet({ o, onClose, onConfirm }) {
  const m = moneyOf(o);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const cod = o.method === "cod";
  const paid = cod ? 0 : o.paid ?? o.total;
  const [to, setTo] = useState("source");
  return (
    <Sheet title="Cancel order" onClose={onClose}
      foot={(close) => (
        <>
          <button className="ot-ghost" onClick={close}>Keep order</button>
          <button className="ot-danger" disabled={!reason || (reason === "Other" && note.trim().length < 3)} onClick={() => { onConfirm({ reason: reason === "Other" ? note.trim() : reason, refundTo: cod ? null : to, amount: paid }); close(); }}>Cancel order</button>
        </>
      )}>
      <p className="ot-lead">Why are you cancelling? This helps us improve.</p>
      <div className="ot-radios">
        {CANCEL_REASONS.map((r, i) => (
          <label key={r} className={"ot-radio" + (reason === r ? " ot-on" : "")} style={{ "--i": i }}>
            <input type="radio" name="cr" checked={reason === r} onChange={() => setReason(r)} /><span className="ot-dot"><i /></span>{r}
          </label>
        ))}
      </div>
      {reason === "Other" && <textarea className="ot-note" rows={2} placeholder="Tell us a little more" value={note} onChange={(e) => setNote(e.target.value)} autoFocus />}
      {!cod && paid > 0 && (
        <div className="ot-refund-pick">
          <b>Refund {m(paid)} to</b>
          <div className="ot-chips">
            <button className={to === "source" ? "ot-on" : ""} onClick={() => setTo("source")}><Icon n="card" size={15} />{o.pay || "Original payment"}<small>3–5 working days</small></button>
            <button className={to === "wallet" ? "ot-on" : ""} onClick={() => setTo("wallet")}><Icon n="wallet" size={15} />369 Wallet<small>Instant</small></button>
          </div>
        </div>
      )}
    </Sheet>
  );
}

/* ---------------- rate ---------------- */
const MOODS = ["", "Terrible", "Bad", "Okay", "Good", "Loved it!"];
const GOOD = ["On-time delivery", "Polite rider", "Fresh items", "Well packed", "Great prices"];
const BAD = ["Late delivery", "Damaged items", "Missing items", "Poor packaging", "Rude rider"];
function RateCard({ o, byId, rider, onSubmit }) {
  const m = moneyOf(o);
  const [stars, setStars] = useState(0);
  const [hover, setHover] = useState(0);
  const [tags, setTags] = useState([]);
  const [items, setItems] = useState({});
  const [tip, setTip] = useState(0);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(!!o.rating);
  const v = hover || stars;
  const pool = stars >= 4 ? GOOD : BAD;
  if (sent) {
    const r = o.rating || { stars };
    return (
      <section className="ot-card ot-rated">
        <span className="ot-hearts" aria-hidden="true">{Array.from({ length: 8 }, (_, i) => <i key={i} style={{ "--k": i }}><Icon n="star" size={14} /></i>)}</span>
        <div className="ot-rated-stars">{[1, 2, 3, 4, 5].map((n) => <Icon key={n} n="star" size={18} className={n <= r.stars ? "ot-lit" : ""} />)}</div>
        <b>Thanks for rating your order!</b>
        <small>{r.tip ? `${m(r.tip)} tip sent to ${rider.name.split(" ")[0]} · ` : ""}Your feedback helps {rider.name.split(" ")[0]} and the store.</small>
      </section>
    );
  }
  return (
    <section className="ot-card ot-rate">
      <h3>How was your order?</h3>
      <div className="ot-stars" onMouseLeave={() => setHover(0)} role="radiogroup" aria-label="Rate your order">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} role="radio" aria-checked={stars === n} aria-label={`${n} star${n > 1 ? "s" : ""}`} className={n <= v ? "ot-lit" : ""} style={{ "--n": n }}
            onMouseEnter={() => setHover(n)} onClick={() => { setStars(n); setTags([]); }}>
            <Icon n="star" size={34} />
          </button>
        ))}
      </div>
      <p className="ot-mood" key={v}>{MOODS[v] || "Tap a star to rate"}</p>
      <div className={"ot-grow" + (stars ? " ot-show" : "")}>
        <div inert={!stars}>
          <div className="ot-tags">
            <span>{stars >= 4 ? "What went well?" : "What went wrong?"}</span>
            {pool.map((t, i) => <button key={t} style={{ "--i": i }} className={tags.includes(t) ? "ot-on" : ""} onClick={() => setTags((x) => (x.includes(t) ? x.filter((y) => y !== t) : [...x, t]))}>{t}</button>)}
          </div>
          <div className="ot-rate-items">
            <span>Rate items</span>
            {o.items.slice(0, 6).map(([id]) => (
              <div key={id} className="ot-rate-item">
                <span className="ot-mini">{byId[id] ? <Thumb p={byId[id]} /> : <Icon n="box" size={16} />}</span>
                <b>{lineName(o, byId, id)}</b>
                <span className="ot-thumbs-ud">
                  <button className={items[id] === 1 ? "ot-on ot-up" : ""} onClick={() => setItems((x) => ({ ...x, [id]: x[id] === 1 ? 0 : 1 }))} aria-label="Liked"><Icon n="heart" size={15} /></button>
                  <button className={items[id] === -1 ? "ot-on ot-down" : ""} onClick={() => setItems((x) => ({ ...x, [id]: x[id] === -1 ? 0 : -1 }))} aria-label="Not good"><Icon n="x" size={15} /></button>
                </span>
              </div>
            ))}
          </div>
          {o.mode !== "all" && (
            <div className="ot-tip">
              <span><b>Tip {rider.name.split(" ")[0]}</b><small>100% of the tip goes to your rider</small></span>
              <div className="ot-chips">{[10, 20, 30, 50].map((t) => <button key={t} className={tip === t ? "ot-on" : ""} onClick={() => setTip(tip === t ? 0 : t)}>{money(t)}</button>)}</div>
            </div>
          )}
          <textarea className="ot-note" rows={2} maxLength={300} placeholder="Add a comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
          <button className="ot-primary ot-block" onClick={() => { onSubmit({ stars, tags, items, tip, comment: comment.trim(), at: Date.now() }); setSent(true); }}>Submit feedback</button>
        </div>
      </div>
    </section>
  );
}

/* ---------------- return / replace ---------------- */
const RETURN_REASONS = ["Item damaged or leaking", "Wrong item delivered", "Item missing from the order", "Quality not as expected", "Expired or near expiry"];
function ReturnSheet({ o, byId, onClose, onSubmit }) {
  const m = moneyOf(o);
  const [step, setStep] = useState(0);
  const [pick, setPick] = useState({});
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState("refund");
  const [slot, setSlot] = useState("today");
  const chosen = Object.entries(pick).filter(([, q]) => q > 0);
  /* A return is settled against the order total, not line by line - that is
     what the shop records and pays back. Quoting the picked lines here would
     promise a different refund from the one that actually arrives. */
  const amount = o.total;
  const canNext = step === 0 ? chosen.length > 0 : step === 1 ? !!reason : true;
  const titles = ["Select items", "What's wrong?", "Refund or replace"];
  return (
    <Sheet title={`Return or replace · ${titles[step]}`} onClose={onClose} wide
      foot={(close) => (
        <>
          <span className="ot-stepdots">{[0, 1, 2].map((i) => <i key={i} className={i <= step ? "ot-on" : ""} />)}</span>
          {step > 0 && <button className="ot-ghost" onClick={() => setStep(step - 1)}>Back</button>}
          <button className="ot-primary" disabled={!canNext} onClick={() => {
            if (step < 2) return setStep(step + 1);
            onSubmit({ items: chosen.map(([id, q]) => [id, q]), reason, resolution: mode, slot, amount });
            close();
          }}>{step < 2 ? "Continue" : mode === "refund" ? `Request refund of ${m(amount)}` : "Request replacement"}</button>
        </>
      )}>
      <div className="ot-flow" key={step}>
        {step === 0 && (
          <ul className="ot-pick">
            {o.items.map(([id, q], i) => {
              const n = pick[id] || 0;
              return (
                <li key={id} className={n ? "ot-on" : ""} style={{ "--i": i }}>
                  <button className="ot-pick-check" onClick={() => setPick((x) => ({ ...x, [id]: n ? 0 : 1 }))} aria-pressed={!!n} aria-label={`Select ${lineName(o, byId, id)}`}><Icon n="check" size={12} /></button>
                  <span className="ot-mini">{byId[id] ? <Thumb p={byId[id]} /> : <Icon n="box" size={16} />}</span>
                  <span className="ot-pick-txt"><b>{lineName(o, byId, id)}</b><small>{m(linePrice(o, byId, id))} · bought {q}</small></span>
                  {n > 0 && q > 1 && (
                    <span className="ot-qty">
                      <button onClick={() => setPick((x) => ({ ...x, [id]: Math.max(0, n - 1) }))} aria-label="Less">−</button><b key={n}>{n}</b>
                      <button disabled={n >= q} onClick={() => setPick((x) => ({ ...x, [id]: Math.min(q, n + 1) }))} aria-label="More">+</button>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {step === 1 && (
          <div className="ot-radios">
            {RETURN_REASONS.map((r, i) => (
              <label key={r} className={"ot-radio" + (reason === r ? " ot-on" : "")} style={{ "--i": i }}>
                <input type="radio" name="rr" checked={reason === r} onChange={() => setReason(r)} /><span className="ot-dot"><i /></span>{r}
              </label>
            ))}
          </div>
        )}
        {step === 2 && (
          <>
            <div className="ot-choice">
              <button className={mode === "refund" ? "ot-on" : ""} onClick={() => setMode("refund")}><Icon n="wallet" size={20} /><b>Refund {m(amount)}</b><small>To {o.method === "cod" ? "369 Wallet" : o.pay || "original payment"}</small></button>
              <button className={mode === "replace" ? "ot-on" : ""} onClick={() => setMode("replace")}><Icon n="reorder" size={20} /><b>Replace items</b><small>Same items, delivered with pickup</small></button>
            </div>
            <span className="ot-sub">Pickup slot</span>
            <div className="ot-chips ot-slots">
              {[["today", "Today", "6 – 8 PM"], ["tm", "Tomorrow", "9 – 11 AM"], ["te", "Tomorrow", "5 – 7 PM"]].map(([k, a, b]) => (
                <button key={k} className={slot === k ? "ot-on" : ""} onClick={() => setSlot(k)}><b>{a}</b><small>{b}</small></button>
              ))}
            </div>
            <p className="ot-fine"><Icon n="info" size={14} />Keep the items and their packaging ready. The rider checks them at pickup.</p>
          </>
        )}
      </div>
    </Sheet>
  );
}

function ReturnTracker({ ret, cur }) {
  const m = (n) => money(n, cur);
  const r = returnStatus(ret);
  const replace = ret.kind === "replace";
  const steps = RETURN_STEPS.map((x, i) => (i === 3 ? { ...x, label: replace ? "Replacement delivered" : "Refund issued" } : x));
  return (
    <section className="ot-card ot-return">
      <header><h3><Icon n="reorder" size={17} />{replace ? "Replacement" : "Return"} {r.refused ? "refused" : "in progress"}</h3></header>
      {!r.refused && (
        <div className="ot-hsteps" style={{ "--p": r.idx / 3 }}>
          <i className="ot-hline"><b /></i>
          {steps.map((st, i) => <span key={st.key} className={(i <= r.idx ? "ot-on" : "") + (i === r.idx && i < 3 ? " ot-now" : "")}><i>{i <= r.idx ? <Icon n="check" size={11} /> : null}</i>{st.label}</span>)}
        </div>
      )}
      <p className="ot-return-meta">
        {ret.reason}{ret.detail ? ` · ${ret.detail}` : ""}
        {!replace && ret.amount ? <> · <b>{m(ret.amount)}</b> {r.idx === 3 ? "refunded" : "refund"}</> : null}
      </p>
    </section>
  );
}

/* ---------------- help chat ---------------- */
function HelpSheet({ o, s, rider, onClose, onCancel }) {
  const m = moneyOf(o);
  const [msgs, setMsgs] = useState([{ me: false, t: `Hi! I'm Mitra from 369 Mart. How can I help with order #${o.id}?` }]);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const list = useRef(null);
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" }); }, [msgs, typing]);
  const answer = (q) => {
    const low = q.toLowerCase();
    if (/where|status|late|when/.test(low)) return s.key === "out" ? `${rider.name} is on the way. ${o.eta || "It should reach you shortly."}${o.otp ? ` Share OTP ${o.otp} at the door.` : ""}` : s.key === "delivered" ? "This order was delivered. If something's wrong you can return or replace items from this page." : s.key === "cancelled" ? "This order was cancelled. Your refund status is shown on the order page." : `Your order is ${{ placed: "confirmed and being prepared", packed: "packed and waiting for a rider", shipped: "shipped and on its way to your city" }[s.key] || "on the way"}. ${o.eta || "We'll notify you when it moves on."}`;
    if (/missing|damaged|wrong/.test(low)) return "Sorry about that! Tap “Return or replace” on the order page, choose the items and we'll arrange a pickup and a refund or replacement.";
    if (/payment|refund|charged|money/.test(low)) return o.method === "cod" ? "This is a cash on delivery order, so nothing has been charged yet." : `Payment of ${m(o.paid || o.total)} was received via ${o.pay}. Refunds reach the source in 3–5 working days, or instantly to 369 Wallet.`;
    if (/cancel/.test(low)) return cancellable(o, s) ? "You can still cancel — I've opened the cancellation for you." : "This order can't be cancelled any more because it's already been packed. You can return items after delivery.";
    if (/agent|human|call/.test(low)) return "Connecting you to a support agent… Typical wait is under 2 minutes. You can keep browsing; we'll notify you.";
    return "Got it. A support agent will look into this and reply here shortly.";
  };
  const send = (q) => {
    if (!q.trim()) return;
    setMsgs((m) => [...m, { me: true, t: q.trim() }]); setText(""); setTyping(true);
    setTimeout(() => {
      setTyping(false);
      setMsgs((m) => [...m, { me: false, t: answer(q) }]);
      if (/cancel/i.test(q) && cancellable(o, s)) setTimeout(onCancel, 700);
    }, reduced() ? 50 : 1000);
  };
  return (
    <Sheet title="Help with this order" onClose={onClose}>
      <div className="ot-chat" ref={list}>
        {msgs.map((m, i) => <p key={i} className={m.me ? "ot-me" : ""}>{m.t}</p>)}
        {typing && <p className="ot-typing" aria-label="Typing"><i /><i /><i /></p>}
      </div>
      <div className="ot-quick">
        {["Where is my order?", "Item missing or damaged", "Payment or refund", cancellable(o, s) ? "Cancel my order" : null, "Talk to an agent"].filter(Boolean).map((q) => <button key={q} onClick={() => send(q)}>{q}</button>)}
      </div>
      <form className="ot-send" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a message" aria-label="Message" />
        <button type="submit" disabled={!text.trim()} aria-label="Send"><Icon n="right" size={18} /></button>
      </form>
    </Sheet>
  );
}

/* ---------------- page ---------------- */
export default function OrderTrack({ order: o, byId, onChanged, onBack, onReceipt, onReorder, onRefundWallet, onShop }) {
  const m = moneyOf(o);
  const s = useMemo(() => liveStatus(o), [o]);
  const ret = (o.returns || [])[0] || null;
  const act = useAction();
  /* Every write here is the shop's to make. The page asks, then re-reads the
     order rather than patching its own copy - the reply is the record. */
  const ask = (path, body) => act.run(async () => {
    const r = await api(`/orders/${encodeURIComponent(o.id)}${path}`, { method: "POST", body });
    api.invalidate("/orders");
    await onChanged?.();
    return r;
  });
  const rider = riderFor(o);
  const open = useContext(OpenContext);
  const [sheet, setSheet] = useState(null); // cancel | return | help
  const [toast, setToast] = useState("");
  const [otpShown, setOtpShown] = useState(false);
  const [subPick, setSubPick] = useState({}); // replacement offer id -> the option picked
  const rateRef = useRef(null);
  const flash = (m) => { setToast(m); clearTimeout(flash.t); flash.t = setTimeout(() => setToast(""), 2600); };

  /* The shop moved the order on while this page was open - say so. */
  const lastKey = useRef(s.key);
  useEffect(() => {
    if (lastKey.current === s.key) return;
    lastKey.current = s.key;
    if (s.key === "delivered") flash("Your order has been delivered");
    if (s.key === "out") flash(`${rider.name} picked up your order`);
  }, [s.key]); // eslint-disable-line

  const cancelled = s.key === "cancelled";
  const title = cancelled ? (o.cancel?.returned ? "Returned to store" : "Order cancelled") : s.key === "delivered" ? "Order delivered" : s.key === "out" ? (s.mode === "quick" ? "On the way" : "Out for delivery") : s.key === "placed" ? "Order confirmed" : s.mode === "quick" ? "Packing your order" : "Shipped";
  const sub = cancelled ? (o.cancel?.refundTo === "wallet" ? `${m(o.cancel.amount)} added to your 369 Wallet` : o.cancel?.refundTo ? `Refund of ${m(o.cancel.amount)} to ${o.pay} in 3–5 working days` : "No payment was taken for this order")
    : s.key === "delivered" ? `Delivered ${s.times[3] ? "at " + fmtTime(s.times[3]) : ""} · ${o.address?.label || "Home"}`
    : o.eta || (s.key === "out" ? "Arriving today" : `Expected ${fmtDay(o.at, 3)}`);
  const itemsTotal = o.items.reduce((sum, [id, q]) => sum + linePrice(o, byId, id) * q, 0);

  return (
    <div className={"ot-page ot-st-" + s.key}>
      <div className="ot-titlebar">
        <button className="ot-back" onClick={onBack} aria-label="Back to orders"><Icon n="left" size={20} /></button>
        <div><h1>Order #{o.id}</h1><small>{fmtPlaced(o.at)} · {o.items.reduce((n, [, q]) => n + q, 0)} items · {m(o.total)}</small></div>
        <button className="ot-helpbtn" onClick={() => setSheet("help")}><Icon n="chat" size={16} />Help</button>
      </div>

      <div className="ot-grid">
        <div className="ot-main">
          <section className="ot-card ot-hero">
            <StatusArt k={s.key} />
            <div className="ot-hero-txt">
              <span className={"ot-mode ot-mode-" + s.mode}><Icon n={s.mode === "quick" ? "bolt" : "truck"} size={12} className={s.mode === "quick" ? "hm-fill" : ""} />{s.mode === "quick" ? "Quick" : "Express"}</span>
              <h2 key={title}>{title}</h2>
              <p key={sub}>{sub}</p>
            </div>
          </section>

          {!cancelled && s.key === "delivered" && <div ref={rateRef}><RateCard o={o} byId={byId} rider={rider} onSubmit={async (r) => {
            const sent = await ask("/rate", { stars: r.stars, tags: r.tags, comment: r.comment, tip: r.tip });
            flash(sent ? (r.tip ? `Thanks! ${m(r.tip)} tip sent` : "Thanks for your feedback") : act.error?.message || "We couldn't send that just now");
          }} /></div>}
          {ret && <ReturnTracker ret={ret} cur={o.currency} />}
          {/* An item ran out and the shop offers something else: the customer
              decides. No answer by the deadline is a refund. */}
          {(o.substitutes || []).filter((x) => x.state === "offered").map((x) => {
            const options = x.options?.length ? x.options : [{ id: 0, name: x.offered, image: x.offeredImage, youPay: x.youPay, shopPays: x.shopPays, difference: x.difference }];
            const chosen = options.find((p) => p.id === subPick[x.id]) || options[0];
            return (
              <section key={x.id} className="ot-card ot-sub">
                <h3 className="ot-h3">{options.length > 1 ? `Choose a replacement (${options.length} options)` : "Choose a replacement"}</h3>
                <p className="ot-sub-was"><s>{x.qty} × {x.was}</s> is out of stock.</p>
                <div className="ot-sub-opts" role="radiogroup" aria-label="Replacements">
                  {options.map((p) => (
                    <button key={p.id} type="button" role="radio" aria-checked={chosen.id === p.id}
                      className={"ot-sub-new" + (chosen.id === p.id ? " ot-on" : "")} onClick={() => setSubPick((s) => ({ ...s, [x.id]: p.id }))}>
                      {p.image ? <img src={p.image} alt="" /> : <span className="ot-mini"><Icon n="box" size={16} /></span>}
                      <span><b>{x.qty} × {p.name}</b>
                        <small>{p.shopPays > 0 ? `You pay ${m(p.youPay * x.qty)} — no extra, we cover ${m(p.shopPays)}`
                          : p.difference > 0 ? `You pay ${m(p.youPay * x.qty)} — ${m(p.difference)} ${o.method === "cod" ? "less at the door" : "back to your 369 Wallet"}`
                          : `You pay ${m(p.youPay * x.qty)} — same as before`}</small></span>
                    </button>
                  ))}
                </div>
                <p className="ot-fine"><Icon n="clock" size={14} />Answer within {Math.max(0, Math.round((x.deadline - Date.now()) / 60000))} min, or we'll refund the item.</p>
                <div className="ot-sub-act">
                  <button className="ot-primary" disabled={act.busy}
                    onClick={async () => flash((await ask(`/substitute/${x.id}`, { accept: true, product_id: chosen.id || undefined })) ? "Replacement added" : act.error?.message || "We couldn't save that")}>
                    {options.length > 1 ? "Accept this one" : "Accept replacement"}</button>
                  <button className="ot-ghost" disabled={act.busy}
                    onClick={async () => flash((await ask(`/substitute/${x.id}`, { accept: false })) ? "Refund on its way" : act.error?.message || "We couldn't save that")}>No, refund me</button>
                </div>
              </section>
            );
          })}

          {/* The rider could not deliver it and it is going out again. */}
          {!cancelled && s.key === "out" && o.attempts > 0 && (
            <section className="ot-card ot-failed">
              <Icon n="info" size={18} />
              <span><b>We couldn't deliver it{o.failedReason ? ` — ${o.failedReason.toLowerCase()}` : ""}</b>
                <small>We'll try again. Your delivery code has changed — use the new one below.</small></span>
            </section>
          )}

          {!cancelled && (
            <section className="ot-card ot-tracker">
              {s.mode === "quick" ? <LiveMap s={s} rider={rider} address={o.address} /> : <Journey s={s} o={o} />}
              {s.mode === "quick" && s.idx >= 2 && s.idx < 3 && (
                <div className="ot-rider-card">
                  <span className="ot-avatar">{rider.name.split(" ").map((w) => w[0]).join("")}</span>
                  <span className="ot-rider-txt"><b>{rider.name}</b><small><Icon n="star" size={11} className="ot-star" />{rider.rating} · {rider.trips} deliveries · {rider.vehicle}</small></span>
                  <button className="ot-round" onClick={() => flash(`Calling ${rider.name.split(" ")[0]} on a masked number…`)} aria-label="Call rider"><Icon n="phone" size={17} /></button>
                  <button className="ot-round" onClick={() => setSheet("help")} aria-label="Chat"><Icon n="chat" size={17} /></button>
                </div>
              )}
              {/* Only when the shop has actually sent one. A spent code comes
                  back empty, and a row of dots hiding nothing would have the
                  customer reading out a number that opens no door. */}
              {s.idx === 2 && !!o.otp && (
                <div className="ot-otp">
                  <span><b>Delivery OTP</b><small>Share only when the rider is at your door</small></span>
                  <button className={"ot-otp-code" + (otpShown ? " ot-shown" : "")} onClick={() => setOtpShown((v) => !v)} aria-label={otpShown ? "Hide OTP" : "Show OTP"}>
                    {String(o.otp).split("").map((d, i) => <i key={i} style={{ "--i": i }}>{otpShown ? d : "•"}</i>)}
                  </button>
                </div>
              )}
            </section>
          )}

          <section className="ot-card">
            <h3 className="ot-h3">Order status</h3>
            <Timeline s={s} o={o} />
          </section>
        </div>

        <aside className="ot-side">
          <section className="ot-card ot-actions">
            {cancellable(o, s) && <button className="ot-act ot-act-red" onClick={() => setSheet("cancel")}><Icon n="x" size={17} />Cancel order<small>Before it's packed</small></button>}
            {returnable(o, s) && <button className="ot-act" onClick={() => setSheet("return")}><Icon n="reorder" size={17} />Return or replace<small>Within 7 days</small></button>}
            {s.key === "delivered" && !o.rating && <button className="ot-act" onClick={() => rateRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })}><Icon n="star" size={17} />Rate order<small>Takes 10 seconds</small></button>}
            {o.bill && <button className="ot-act" onClick={onReceipt}><Icon n="printer" size={17} />View receipt<small>Print or download</small></button>}
            <button className="ot-act" onClick={() => setSheet("help")}><Icon n="chat" size={17} />Need help?<small>Chat with us</small></button>
            <button className="ot-act ot-act-blue" onClick={(e) => onReorder(o, e.currentTarget)}><Icon n="cart" size={17} />Reorder<small>Add all to cart</small></button>
          </section>

          <section className="ot-card">
            <h3 className="ot-h3">Items</h3>
            <ul className="ot-items">
              {o.items.map(([id, q], i) => (
                <li key={id} style={{ "--i": i }}>
                  <button className="ot-mini" onClick={() => byId[id] && open?.(byId[id], null)} aria-label={`Open ${lineName(o, byId, id)}`}>{byId[id] ? <Thumb p={byId[id]} /> : <Icon n="box" size={16} />}</button>
                  <span><b>{lineName(o, byId, id)}</b><small>{q} × {m(linePrice(o, byId, id))}</small></span>
                  <em>{m(linePrice(o, byId, id) * q)}</em>
                </li>
              ))}
              {/* Taken out by the store because it ran out. */}
              {(o.removed || []).map((g, i) => (
                <li key={"gone" + i} className="ot-removed" style={{ "--i": o.items.length + i }}>
                  <span className="ot-mini" aria-hidden="true"><Icon n="box" size={16} /></span>
                  <span><b><s>{g.name}</s></b><small>Removed — {g.reason || "Out of stock"}{g.refund ? ` · ${m(g.refund)} refunded to your 369 Wallet` : ""}</small></span>
                </li>
              ))}
            </ul>
            <dl className="ot-bill">
              <div><dt>Items</dt><dd>{m(o.bill?.items ?? itemsTotal)}</dd></div>
              {o.bill?.mrp > o.bill?.items && <div className="ot-green"><dt>You saved</dt><dd>−{m(o.bill.mrp - o.bill.items + (o.bill.couponOff || 0))}</dd></div>}
              {o.bill && <div><dt>Delivery</dt><dd>{o.bill.fees ? m(o.bill.fees) : "FREE"}</dd></div>}
              {o.bill?.pointsOff > 0 && <div className="ot-green"><dt>Loyalty points ({pointsText(o.points?.spent)})</dt><dd>−{m(o.bill.pointsOff)}</dd></div>}
              {o.walletUsed > 0 && <div className="ot-green"><dt>369 Wallet</dt><dd>−{m(o.walletUsed)}</dd></div>}
              <div className="ot-total"><dt>{o.method === "cod" && s.key !== "delivered" && !cancelled ? "To pay on delivery" : "Paid"}</dt><dd>{m(o.paid || o.total)}</dd></div>
            </dl>
            {/* What this order earns on the loyalty card, or already has. */}
            {o.points?.earned > 0 ? (
              <p className="ot-points"><Icon n="coin" size={15} />You earned {pointsText(o.points.earned)} loyalty points on this order</p>
            ) : o.points?.willEarn > 0 && !cancelled ? (
              <p className="ot-points"><Icon n="coin" size={15} />You'll earn {pointsText(o.points.willEarn)} loyalty points {EARN_WHEN[o.points.earnOn] || EARN_WHEN.delivered}</p>
            ) : null}
            {cancelled && o.points?.returned > 0 && <p className="ot-points"><Icon n="coin" size={15} />{pointsText(o.points.returned)} points are back on your loyalty card</p>}
          </section>

          <section className="ot-card ot-info">
            <div><Icon n="pin" size={16} /><span><small>Delivering to</small><b>{o.address?.label || "Home"}</b>{o.address?.line ? addressText(o.address) : "Flat 4B, Palm Grove Apartments, MG Road, Kochi"}</span></div>
            <div><Icon n={o.method === "cod" ? "cash" : "card"} size={16} /><span><small>Payment</small><b>{o.pay}</b>{o.txn ? `Txn ${o.txn}` : ""}</span></div>
            {o.slot && <div><Icon n="clock" size={16} /><span><small>Slot</small><b>{o.slot}</b></span></div>}
          </section>
          <button className="ot-link ot-shop" onClick={onShop}>Continue shopping</button>
        </aside>
      </div>

      {sheet === "cancel" && (
        <CancelSheet o={o} onClose={() => setSheet(null)} onConfirm={async (c) => {
          const done = await ask("/cancel", { reason: c.reason });
          if (!done) { flash(act.error?.message || "We couldn't cancel that just now"); return; }
          if (c.refundTo === "wallet" && c.amount) onRefundWallet?.(c.amount);
          flash(c.refundTo === "wallet" ? `Order cancelled · ${m(c.amount)} added to wallet` : "Order cancelled");
        }} />
      )}
      {sheet === "return" && (
        <ReturnSheet o={o} byId={byId} onClose={() => setSheet(null)} onSubmit={async (r) => {
          const going = (r.items || []).map(([id, q]) => `${q} × ${lineName(o, byId, id)}`).join(", ");
          const sent = await ask("/return", {
            kind: r.resolution, reason: r.reason,
            detail: [going && `Sending back: ${going}`, r.slot && `Pickup: ${r.slot}`].filter(Boolean).join(" · "),
          });
          flash(sent ? (r.resolution === "refund" ? "Return requested · pickup scheduled" : "Replacement requested") : act.error?.message || "We couldn't send that just now");
        }} />
      )}
      {sheet === "help" && <HelpSheet o={o} s={s} rider={rider} onClose={() => setSheet(null)} onCancel={() => setSheet("cancel")} />}

      <div className={"ot-toast" + (toast ? " ot-show" : "")} role="status" aria-live="polite">{toast}</div>
    </div>
  );
}
