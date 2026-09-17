"use client";
/* ==========================================================================
   369 Mart — Cart
   Left:  delivery groups (Quick in minutes / Express in days) · minimum-order
          nudge · Recommended rail · You may also like rail
   Right: coupons · free-delivery progress · WhatsApp updates · payment details
          · to-pay bar · cancellation note · delivery instructions
   ========================================================================== */
import { useContext, useEffect, useMemo, useRef, useState } from "react";
import ProductArt from "./art";
import { Icon, OpenContext, Rail, Thumb, inr } from "./shared";

export const CART_RULES = {
  quick: { label: "Quick", eta: "Delivery in 13 mins", minOrder: 99, freeAbove: 499, fee: 30 },
  all: { label: "Express", eta: "Delivery in 2–3 days", minOrder: 0, freeAbove: 999, fee: 49 },
};

export const COUPONS = [
  { code: "QUICK20", title: "20% off on Quick orders", note: "Up to ₹60 · Quick items above ₹199", group: "quick", min: 199, calc: (s) => Math.min(60, Math.round(s.quick * 0.2)) },
  { code: "WELCOME50", title: "Flat ₹50 off", note: "On orders above ₹499", group: null, min: 499, calc: () => 50 },
  { code: "FREEDEL", title: "Free delivery", note: "Waives delivery fees on orders above ₹299", group: null, min: 299, calc: (s) => s.fees },
];

/* One bill for cart and checkout: groups, fees, coupon, totals. */
export function computeBill({ cart, byId, rules = CART_RULES, coupon = null }) {
  const groups = { quick: [], all: [] };
  Object.entries(cart).forEach(([id, qty]) => {
    const p = byId[id];
    if (p && qty > 0) groups[p.delivery ? "all" : "quick"].push({ p, qty });
  });
  const lines = [...groups.quick, ...groups.all];
  const mrp = lines.reduce((s, l) => s + (l.p.mrp || l.p.price) * l.qty, 0);
  const items = lines.reduce((s, l) => s + l.p.price * l.qty, 0);
  const sub = { quick: groups.quick.reduce((s, l) => s + l.p.price * l.qty, 0), all: groups.all.reduce((s, l) => s + l.p.price * l.qty, 0) };
  const feeFor = (g) => (groups[g].length && sub[g] < rules[g].freeAbove ? rules[g].fee : 0);
  const fees = feeFor("quick") + feeFor("all");
  const sums = { items, quick: sub.quick, all: sub.all, fees };
  const active = COUPONS.find((c) => c.code === coupon);
  const couponValid = !!active && (active.group ? sub[active.group] : items) >= active.min;
  const couponOff = couponValid ? Math.min(active.calc(sums), items + fees) : 0;
  const total = Math.max(0, items + fees - couponOff);
  return {
    groups, lines, mrp, items, sub, fees, feeFor, sums, couponValid, couponOff, total,
    saved: mrp - items + couponOff,
    count: lines.reduce((s, l) => s + l.qty, 0),
    blocked: groups.quick.length > 0 && sub.quick < rules.quick.minOrder,
  };
}

/* counts smoothly between values */
export function Amount({ value, prefix = "" }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current, end = value, t0 = performance.now(), dur = 420;
    if (start === end) return;
    let raf;
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      setShown(Math.round(start + (end - start) * e));
      if (k < 1) raf = requestAnimationFrame(tick); else from.current = end;
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); from.current = end; };
  }, [value]);
  return <span className="ct-amt">{prefix}{inr(shown)}</span>;
}

function Stepper({ qty, onChange, name }) {
  return (
    <div className="ct-step" role="group" aria-label={`${name} quantity`}>
      <button onClick={() => onChange(qty - 1)} aria-label={qty === 1 ? "Remove item" : "Remove one"}>
        {qty === 1 ? <Icon n="trash" size={14} /> : "−"}
      </button>
      <span key={qty} className="ct-step-n">{qty}</span>
      <button onClick={() => onChange(qty + 1)} aria-label="Add one" disabled={qty >= 12}>+</button>
    </div>
  );
}

function LineItem({ p, qty, setQty, i }) {
  const [leaving, setLeaving] = useState(false);
  const open = useContext(OpenContext);
  const change = (n) => {
    if (n <= 0) { setLeaving(true); setTimeout(() => setQty(p.id, 0), 320); }
    else setQty(p.id, n);
  };
  return (
    <li className={"ct-line" + (leaving ? " ct-leaving" : "")} style={{ "--i": i }}>
      <span className="ct-thumb"><Thumb p={p} /></span>
      <div className="ct-line-info" data-open="" onClick={(e) => open?.(p, e.currentTarget.parentElement.querySelector(".ct-thumb")?.getBoundingClientRect())}>
        <b>{p.name}</b>
        <small>{p.unit}{p.veg ? " · Veg" : ""}</small>
      </div>
      <Stepper qty={qty} onChange={change} name={p.name} />
      <div className="ct-line-price">
        <Amount value={p.price * qty} />
        {p.mrp ? <s>{inr(p.mrp * qty)}</s> : null}
      </div>
    </li>
  );
}

function DeliveryGroup({ group, lines, setQty, rules, onAddMore }) {
  const subtotal = lines.reduce((s, l) => s + l.p.price * l.qty, 0);
  const count = lines.reduce((s, l) => s + l.qty, 0);
  const short = Math.max(0, rules.minOrder - subtotal);
  return (
    <section className={"ct-card ct-group ct-group-" + group}>
      <header className="ct-group-head">
        <div>
          <strong><Icon n={group === "quick" ? "bolt" : "truck"} size={16} className={group === "quick" ? "hm-fill" : ""} />{rules.eta}</strong>
          <small>{rules.label} · {count} {count === 1 ? "item" : "items"}</small>
        </div>
        <Amount value={subtotal} />
      </header>
      <ul className="ct-lines">
        {lines.map((l, i) => <LineItem key={l.p.id} p={l.p} qty={l.qty} setQty={setQty} i={i} />)}
      </ul>
      <div className={"ct-minorder" + (short > 0 ? " ct-show" : "")} aria-hidden={short === 0}>
        <div className="ct-minorder-in">
          <span className="ct-minorder-ic"><Icon n="info" size={18} /></span>
          <p><b>Minimum order value is {inr(rules.minOrder)}</b><br />Add items worth <Amount value={short} /> from {rules.label} to place this order</p>
          <button onClick={onAddMore} tabIndex={short ? 0 : -1}>Add items</button>
        </div>
      </div>
    </section>
  );
}

function CouponSheet({ open, onClose, sums, applied, onApply }) {
  useEffect(() => {
    if (!open) return;
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  return (
    <div className={"ct-sheet-wrap" + (open ? " ct-open" : "")} aria-hidden={!open}>
      <div className="ct-sheet-back" onClick={onClose} />
      <aside className="ct-sheet" role="dialog" aria-modal="true" aria-label="Coupons">
        <header>
          <h3>Apply coupon</h3>
          <button className="ct-x" onClick={onClose} aria-label="Close"><Icon n="x" size={18} /></button>
        </header>
        <ul className="ct-coupons">
          {COUPONS.map((c, i) => {
            const base = c.group ? sums[c.group] : sums.items;
            const need = Math.max(0, c.min - base);
            const save = c.calc(sums);
            const on = applied === c.code;
            return (
              <li key={c.code} className={"ct-coupon" + (need ? " ct-locked" : "") + (on ? " ct-on" : "")} style={{ "--i": i }}>
                <div className="ct-coupon-top">
                  <span className="ct-code"><Icon n="ticket" size={15} />{c.code}</span>
                  {on ? <button className="ct-link" onClick={() => onApply(null)}>Remove</button>
                    : <button className="ct-link" disabled={!!need || save <= 0} onClick={() => onApply(c.code)}>Apply</button>}
                </div>
                <b>{c.title}</b>
                <small>{c.note}</small>
                {need ? <em className="ct-need">Add {inr(need)} more to unlock</em>
                  : save > 0 ? <em className="ct-save">You save {inr(save)}</em> : <em className="ct-need">Nothing to save on this cart yet</em>}
              </li>
            );
          })}
        </ul>
      </aside>
    </div>
  );
}

const INSTRUCTIONS = [
  { key: "note", label: "Leave a note", icon: "note" },
  { key: "nocall", label: "Avoid calling", icon: "phoneOff" },
  { key: "nobell", label: "Don't ring the bell", icon: "bellOff" },
  { key: "pet", label: "Pet at home", icon: "paw" },
];

export default function CartPage({ cart, setQty, byId, recommended = [], alsoLike = [], onBack, onCheckout, rules = CART_RULES }) {
  const [couponOpen, setCouponOpen] = useState(false);
  const [coupon, setCoupon] = useState(null);
  const [whatsapp, setWhatsapp] = useState(true);
  const [instr, setInstr] = useState({});
  const [note, setNote] = useState("");
  const [toast, setToast] = useState("");
  const [paying, setPaying] = useState("");

  const bill = useMemo(() => computeBill({ cart, byId, rules, coupon }), [cart, byId, rules, coupon]);
  const { groups, mrp, items, sub, fees, feeFor, sums, couponValid, couponOff, total, saved, blocked, count } = bill;
  useEffect(() => { if (coupon && !couponValid) { setCoupon(null); flash(`${coupon} removed — cart no longer qualifies`); } }, [couponValid]); // eslint-disable-line

  const nextFree = groups.quick.length && sub.quick < rules.quick.freeAbove ? rules.quick.freeAbove - sub.quick : 0;

  function flash(msg) { setToast(msg); clearTimeout(flash.t); flash.t = setTimeout(() => setToast(""), 2600); }
  const applyCoupon = (code) => {
    setCoupon(code); setCouponOpen(false);
    if (code) { const c = COUPONS.find((x) => x.code === code); flash(`${code} applied · You save ${inr(c.calc(sums))}`); }
  };
  const pay = (how) => {
    setPaying(how);
    setTimeout(() => { setPaying(""); onCheckout ? onCheckout({ how, total, coupon: couponValid ? coupon : null, instructions: { ...instr, note }, whatsapp }) : flash("Demo: checkout would start here"); }, 350);
  };

  if (!count) {
    return (
      <div className="ct-page">
        <div className="ct-empty">
          <span className="ct-empty-art"><ProductArt art="Basket" /></span>
          <h1>Your cart is empty</h1>
          <p>Fresh groceries in minutes, everything else in a couple of days.</p>
          <button className="ct-primary" onClick={onBack}>Start shopping</button>
        </div>
      </div>
    );
  }

  return (
    <div className="ct-page">
      <div className="ct-titlebar">
        <button className="ct-back" onClick={onBack} aria-label="Back to shopping"><Icon n="left" size={20} /></button>
        <h1>Cart <span>{count} {count === 1 ? "item" : "items"}</span></h1>
      </div>

      <div className="ct-grid">
        <div className="ct-main">
          {["quick", "all"].map((g) => groups[g].length > 0 && (
            <DeliveryGroup key={g} group={g} lines={groups[g]} setQty={setQty} rules={rules[g]} onAddMore={onBack} />
          ))}
          {recommended.length > 0 && (
            <div className="ct-card ct-railcard">
              <Rail section={{ key: "rec", title: "Recommended for you", items: recommended }} cart={cart} setQty={setQty} />
            </div>
          )}
          {alsoLike.length > 0 && (
            <div className="ct-card ct-railcard ct-tint">
              <Rail section={{ key: "like", title: "You may also like", items: alsoLike }} cart={cart} setQty={setQty} />
            </div>
          )}
        </div>

        <aside className="ct-side">
          <button className={"ct-card ct-coupon-btn" + (couponValid ? " ct-applied" : "")} onClick={() => setCouponOpen(true)}>
            <span className="ct-coupon-ic"><Icon n={couponValid ? "check" : "ticket"} size={18} /></span>
            <span className="ct-coupon-txt">
              {couponValid ? <><b key={coupon}>{coupon} applied</b><small>You save {inr(couponOff)}</small></>
                : <><b>Apply a coupon</b><small className="ct-blue">View all coupons</small></>}
            </span>
            <Icon n="right" size={18} />
          </button>

          {nextFree > 0 ? (
            <div className="ct-card ct-free">
              <span className="ct-free-ic"><Icon n="scooter" size={18} /></span>
              <p>Shop for <b><Amount value={nextFree} /></b> more to get <b>free delivery</b> on your Quick order</p>
              <span className="ct-bar"><i style={{ width: Math.min(100, (sub.quick / rules.quick.freeAbove) * 100) + "%" }} /></span>
            </div>
          ) : groups.quick.length > 0 ? (
            <div className="ct-card ct-free ct-free-done"><span className="ct-free-ic"><Icon n="check" size={18} /></span><p><b>Free delivery unlocked</b> on your Quick order</p></div>
          ) : null}

          <label className="ct-card ct-wa">
            <span className="ct-wa-ic"><Icon n="chat" size={18} /></span>
            <span>Get order updates and delivery alerts on WhatsApp</span>
            <input type="checkbox" checked={whatsapp} onChange={(e) => setWhatsapp(e.target.checked)} />
            <span className="ct-box" aria-hidden="true"><Icon n="check" size={13} /></span>
          </label>

          <section className="ct-card ct-bill">
            {saved > 0 && <div className="ct-saving" key={saved}><Icon n="gift" size={15} />You're saving <Amount value={saved} /> on this order</div>}
            <h2>Payment details</h2>
            <dl>
              <div><dt>MRP total</dt><dd><Amount value={mrp} /></dd></div>
              {mrp > items && <div className="ct-green"><dt>Product discount</dt><dd><Amount value={mrp - items} prefix="−" /></dd></div>}
              <div><dt>Subtotal</dt><dd><Amount value={items} /></dd></div>
              {["quick", "all"].map((g) => groups[g].length > 0 && (
                <div key={g} className="ct-fee">
                  <dt>Delivery fee ({rules[g].label})<small>{feeFor(g) ? `Free above ${inr(rules[g].freeAbove)}` : "Free on this order"}</small></dt>
                  <dd>{feeFor(g) ? inr(feeFor(g)) : <><s>{inr(rules[g].fee)}</s> <span className="ct-free-tag">FREE</span></>}</dd>
                </div>
              ))}
              {couponOff > 0 && <div className="ct-green ct-coupon-row"><dt>Coupon ({coupon})</dt><dd><Amount value={couponOff} prefix="−" /></dd></div>}
              <div className="ct-total"><dt>Total</dt><dd><Amount value={total} /></dd></div>
            </dl>
            {saved > 0 && <p className="ct-saved">You saved <Amount value={saved} /></p>}
          </section>

          <div className="ct-card ct-pay">
            <div className="ct-topay"><small>To pay</small><Amount value={total} /></div>
            <button className="ct-cod" disabled={blocked || !!paying} onClick={() => pay("cod")}>
              {paying === "cod" ? <span className="ct-spin" /> : <><b>Pay cash</b><small>on delivery</small></>}
            </button>
            <button className="ct-primary" disabled={blocked || !!paying} onClick={() => pay("online")}>
              {paying === "online" ? <span className="ct-spin" /> : "Pay online"}
            </button>
            {blocked && <p className="ct-blocked">Add {inr(rules.quick.minOrder - sub.quick)} more to your Quick items to continue</p>}
          </div>

          <div className="ct-card ct-policy">
            <Icon n="shield" size={18} />
            <p>Orders can be cancelled for a refund until they are packed for delivery. <a href="/cancellation-policy">Cancellation policy</a></p>
          </div>

          <section className="ct-card ct-instr">
            <h2>Delivery instructions</h2>
            <div className="ct-instr-grid">
              {INSTRUCTIONS.map((x) => (
                <button key={x.key} className={"ct-instr-tile" + (instr[x.key] ? " ct-on" : "")} aria-pressed={!!instr[x.key]}
                  onClick={() => setInstr((s) => ({ ...s, [x.key]: !s[x.key] }))}>
                  <span className="ct-tick" aria-hidden="true"><Icon n="check" size={11} /></span>
                  <Icon n={x.icon} size={20} />
                  <span>{x.label}</span>
                </button>
              ))}
            </div>
            <div className={"ct-note" + (instr.note ? " ct-show" : "")}>
              <div>
                <textarea id="ct-note" rows={2} maxLength={140} placeholder="e.g. Leave the bag with the security desk"
                  value={note} onChange={(e) => setNote(e.target.value)} tabIndex={instr.note ? 0 : -1} />
                <small>{note.length}/140</small>
              </div>
            </div>
          </section>
        </aside>
      </div>

      <div className="ct-mobile-pay">
        <div className="ct-topay"><small>To pay</small><Amount value={total} /></div>
        <button className="ct-primary" disabled={blocked || !!paying} onClick={() => pay("online")}>{paying ? <span className="ct-spin" /> : "Pay online"}</button>
      </div>

      <CouponSheet open={couponOpen} onClose={() => setCouponOpen(false)} sums={sums} applied={couponValid ? coupon : null} onApply={applyCoupon} />
      <div className={"ct-toast" + (toast ? " ct-show" : "")} role="status" aria-live="polite">{toast}</div>
    </div>
  );
}
