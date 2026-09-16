"use client";
/* 369mart: this file is VENDORED from the 369mart-store drop and adapted.
   Every local change is marked "369mart: LOCAL EDIT" -- re-apply them when
   dropping in a new version. The short version: this build has no backend,
   so the delivery fees, free-delivery meter, minimum orders, sample coupons
   and pay buttons are removed rather than stubbed. The layout is untouched. */
/* ==========================================================================
   369 Mart — Cart
   Left:  delivery groups (Quick in minutes / Shop all in days) · minimum-order
          nudge · Recommended rail · You may also like rail
   Right: WhatsApp updates · payment details · to-pay note · cancellation
          note · delivery instructions
   ========================================================================== */
import { useEffect, useMemo, useRef, useState } from "react";
import ProductArt from "@/components/home/vendor/art";
import { Icon, Rail, Thumb, inr } from "@/components/home/vendor/shared";

/* 369mart: LOCAL EDIT -- the delivery fees, free-delivery thresholds and
   minimum orders this design shipped are gone, and so are its three sample
   coupons. Nothing here can compute a shipping charge or validate a code,
   and AGENTS.md is explicit that coupons are omitted rather than stubbed.
   Only the group labels survive, because a heading is not a promise. */
export const CART_RULES = {
  quick: { label: "Quick" },
  all: { label: "Express" },
};

/* counts smoothly between values */
function Amount({ value, prefix = "" }) {
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
  const change = (n) => {
    if (n <= 0) { setLeaving(true); setTimeout(() => setQty(p.id, 0), 320); }
    else setQty(p.id, n);
  };
  return (
    <li className={"ct-line" + (leaving ? " ct-leaving" : "")} style={{ "--i": i }}>
      <span className="ct-thumb"><Thumb p={p} /></span>
      <div className="ct-line-info">
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
  return (
    <section className={"ct-card ct-group ct-group-" + group}>
      <header className="ct-group-head">
        <div>
          <strong><Icon n={group === "quick" ? "bolt" : "truck"} size={16} className={group === "quick" ? "hm-fill" : ""} />{rules.label}</strong>
          <small>{count} {count === 1 ? "item" : "items"}</small>
        </div>
        <Amount value={subtotal} />
      </header>
      <ul className="ct-lines">
        {lines.map((l, i) => <LineItem key={l.p.id} p={l.p} qty={l.qty} setQty={setQty} i={i} />)}
      </ul>
    </section>
  );
}

const INSTRUCTIONS = [
  { key: "note", label: "Leave a note", icon: "note" },
  { key: "nocall", label: "Avoid calling", icon: "phoneOff" },
  { key: "nobell", label: "Don't ring the bell", icon: "bellOff" },
  { key: "pet", label: "Pet at home", icon: "paw" },
];

export default function CartPage({ cart, setQty, byId, recommended = [], alsoLike = [], onBack, onCheckout, rules = CART_RULES }) {
  const [whatsapp, setWhatsapp] = useState(true);
  const [instr, setInstr] = useState({});
  const [note, setNote] = useState("");
  const [toast, setToast] = useState("");

  const groups = useMemo(() => {
    const g = { quick: [], all: [] };
    Object.entries(cart).forEach(([id, qty]) => {
      const p = byId[id];
      if (p && qty > 0) g[p.delivery ? "all" : "quick"].push({ p, qty });
    });
    return g;
  }, [cart, byId]);

  const all = [...groups.quick, ...groups.all];
  const mrp = all.reduce((s, l) => s + (l.p.mrp || l.p.price) * l.qty, 0);
  const items = all.reduce((s, l) => s + l.p.price * l.qty, 0);
  const sub = { quick: groups.quick.reduce((s, l) => s + l.p.price * l.qty, 0), all: groups.all.reduce((s, l) => s + l.p.price * l.qty, 0) };
  const total = items;
  const saved = mrp - items;
  const count = all.reduce((s, l) => s + l.qty, 0);

  function flash(msg) { setToast(msg); clearTimeout(flash.t); flash.t = setTimeout(() => setToast(""), 2600); }
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
              <div className="ct-total"><dt>Total</dt><dd><Amount value={total} /></dd></div>
            </dl>
            {saved > 0 && <p className="ct-saved">You saved <Amount value={saved} /></p>}
          </section>

          {/* 369mart: LOCAL EDIT -- the design puts Pay cash / Pay online
              here behind a fake 900ms spinner. Nothing in this phase can
              take a payment, and a button that appears to charge and then
              silently does not is the worst thing on the page. The amount
              stays, because it is real; the action says what is true. */}
          <div className="ct-card ct-pay">
            <div className="ct-topay"><small>To pay</small><Amount value={total} /></div>
            <p className="ct-blocked">Checkout arrives with the store backend. Nothing is charged and no order is created yet.</p>
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

      <div className={"ct-toast" + (toast ? " ct-show" : "")} role="status" aria-live="polite">{toast}</div>
    </div>
  );
}
