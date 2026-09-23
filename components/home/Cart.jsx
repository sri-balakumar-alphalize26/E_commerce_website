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
import { Icon, OpenContext, Rail, Thumb, money } from "./shared";
import { useResource } from "@/lib/useFetch";
import { api } from "@/lib/api";

/* The delivery rules and the coupons are the shop's, not a copy of them kept
   here. Both pages that spend money ask for them, and so do the two that only
   list the codes - `api` caches a GET for a minute, so asking is cheap and
   nobody has to thread them through a tree that does not care. */
export function useRules() {
  const { data } = useResource("/cart/rules");
  return {
    rules: data?.rules || null,
    coupons: useMemo(() => data?.coupons || [], [data]),
  };
}

/* What is in the basket, and which storefront each line ships from. This is
   layout, not money: which lines sit under "Delivery in 13 mins" and which
   under "2-3 days", and how many things there are in total. */
export function computeBill({ cart, byId }) {
  const groups = { quick: [], all: [] };
  Object.entries(cart).forEach(([id, qty]) => {
    const p = byId[id];
    if (p && qty > 0) groups[p.delivery ? "all" : "quick"].push({ p, qty });
  });
  const lines = [...groups.quick, ...groups.all];
  return { groups, lines, count: lines.reduce((s, l) => s + l.qty, 0) };
}

/* The bill itself comes from the shop. What a basket costs is the one number
   the browser must never decide: an app that works out its own total can only
   ever disagree with the till, and the customer reads the disagreement as the
   shop overcharging. `priced` is false until the answer arrives - the page
   shows no amounts and will not start a payment before then.

   `feeFor` stays here because it is a function, which no JSON can carry, but
   it is the shop's rule applied to the shop's subtotal, not a second opinion
   about either. */
export function useBill({ cart, byId, rules, coupon = null, slotFee = 0 }) {
  const shape = useMemo(() => computeBill({ cart, byId }), [cart, byId]);
  const [money, setMoney] = useState(null);
  const [error, setError] = useState(null);
  const tick = useRef(0);
  const key = JSON.stringify([cart, coupon || "", slotFee]);

  useEffect(() => {
    if (!shape.count) { setMoney(null); setError(null); return undefined; }
    const mine = ++tick.current;
    /* A stepper is held down, not tapped once. Wait for the hand to stop. */
    const timer = setTimeout(() => {
      api("/cart/bill", { method: "POST", body: { items: cart, coupon: coupon || "", slotFee } })
        .then((r) => { if (mine === tick.current) { setMoney(r); setError(null); } })
        .catch((e) => { if (mine === tick.current) { setMoney(null); setError(e); } });
    }, 200);
    return () => clearTimeout(timer);
  }, [key, shape.count]); // eslint-disable-line

  const sub = money?.sub || { quick: 0, all: 0 };
  const feeFor = (g) => (shape.groups[g].length && rules?.[g] && sub[g] < rules[g].freeAbove ? rules[g].fee : 0);
  return {
    ...shape,
    mrp: 0, items: 0, fees: 0, couponOff: 0, total: 0, saved: 0,
    couponValid: false, blocked: false, coupons: [], unknown: [],
    ...(money || {}),
    sub, feeFor, priced: !!money, error,
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
  return <span className="ct-amt">{prefix}{money(shown)}</span>;
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
        <small>{p.unit}</small>
      </div>
      <Stepper qty={qty} onChange={change} name={p.name} />
      <div className="ct-line-price">
        <Amount value={p.price * qty} />
        {p.mrp ? <s>{money(p.mrp * qty)}</s> : null}
      </div>
    </li>
  );
}

function DeliveryGroup({ group, lines, setQty, rules, onAddMore }) {
  const subtotal = lines.reduce((s, l) => s + l.p.price * l.qty, 0);
  const count = lines.reduce((s, l) => s + l.qty, 0);
  const short = rules ? Math.max(0, rules.minOrder - subtotal) : 0;
  rules = rules || { label: group === "quick" ? "Quick" : "Express", eta: "", minOrder: 0 };
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
          <p><b>Minimum order value is {money(rules.minOrder)}</b><br />Add items worth <Amount value={short} /> from {rules.label} to place this order</p>
          <button onClick={onAddMore} tabIndex={short ? 0 : -1}>Add items</button>
        </div>
      </div>
    </section>
  );
}

function CouponSheet({ open, onClose, coupons, offers, applied, onApply }) {
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
          {coupons.map((c, i) => {
            const priced = offers.find((o) => o.code === c.code) || { off: 0, need: 0 };
            const need = priced.need;
            const save = priced.off;
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
                {need ? <em className="ct-need">Add {money(need)} more to unlock</em>
                  : save > 0 ? <em className="ct-save">You save {money(save)}</em> : <em className="ct-need">Nothing to save on this cart yet</em>}
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

export default function CartPage({ cart, setQty, byId, recommended = [], alsoLike = [], onBack, onCheckout }) {
  const [couponOpen, setCouponOpen] = useState(false);
  const [coupon, setCoupon] = useState(null);
  const [whatsapp, setWhatsapp] = useState(true);
  const [instr, setInstr] = useState({});
  const [note, setNote] = useState("");
  const [toast, setToast] = useState("");
  const [paying, setPaying] = useState("");

  const { rules, coupons } = useRules();
  const bill = useBill({ cart, byId, rules, coupon });
  const { groups, mrp, items, sub, feeFor, couponValid, couponOff, total, saved, blocked, count, priced } = bill;
  /* The shop decides a coupon no longer applies, not the page. */
  useEffect(() => { if (priced && coupon && !couponValid) { setCoupon(null); flash(`${coupon} removed — cart no longer qualifies`); } }, [couponValid, priced]); // eslint-disable-line

  const nextFree = rules && groups.quick.length && sub.quick < rules.quick.freeAbove ? rules.quick.freeAbove - sub.quick : 0;

  function flash(msg) { setToast(msg); clearTimeout(flash.t); flash.t = setTimeout(() => setToast(""), 2600); }
  const applyCoupon = (code) => {
    setCoupon(code); setCouponOpen(false);
    if (code) { const o = bill.coupons.find((x) => x.code === code); flash(`${code} applied${o ? ` · You save ${money(o.off)}` : ""}`); }
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
          <p>Parts and peripherals in minutes, everything else in a couple of days.</p>
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
            <DeliveryGroup key={g} group={g} lines={groups[g]} setQty={setQty} rules={rules?.[g]} onAddMore={onBack} />
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
              {couponValid ? <><b key={coupon}>{coupon} applied</b><small>You save {money(couponOff)}</small></>
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
            {!priced && <p className="ct-pending">{bill.error ? "We couldn't reach the shop for a total. Try again in a moment." : "Working out your total…"}</p>}
            {priced && <dl>
              <div><dt>MRP total</dt><dd><Amount value={mrp} /></dd></div>
              {mrp > items && <div className="ct-green"><dt>Product discount</dt><dd><Amount value={mrp - items} prefix="−" /></dd></div>}
              <div><dt>Subtotal</dt><dd><Amount value={items} /></dd></div>
              {["quick", "all"].map((g) => groups[g].length > 0 && rules?.[g] && (
                <div key={g} className="ct-fee">
                  <dt>Delivery fee ({rules[g].label})<small>{feeFor(g) ? `Free above ${money(rules[g].freeAbove)}` : "Free on this order"}</small></dt>
                  <dd>{feeFor(g) ? money(feeFor(g)) : <><s>{money(rules[g].fee)}</s> <span className="ct-free-tag">FREE</span></>}</dd>
                </div>
              ))}
              {couponOff > 0 && <div className="ct-green ct-coupon-row"><dt>Coupon ({coupon})</dt><dd><Amount value={couponOff} prefix="−" /></dd></div>}
              <div className="ct-total"><dt>Total</dt><dd><Amount value={total} /></dd></div>
            </dl>}
            {saved > 0 && <p className="ct-saved">You saved <Amount value={saved} /></p>}
          </section>

          <div className="ct-card ct-pay">
            <div className="ct-topay"><small>To pay</small>{priced ? <Amount value={total} /> : <span className="ct-amt ct-amt-wait">…</span>}</div>
            <button className="ct-cod" disabled={blocked || !priced || !!paying} onClick={() => pay("cod")}>
              {paying === "cod" ? <span className="ct-spin" /> : <><b>Pay cash</b><small>on delivery</small></>}
            </button>
            <button className="ct-primary" disabled={blocked || !priced || !!paying} onClick={() => pay("online")}>
              {paying === "online" ? <span className="ct-spin" /> : "Pay online"}
            </button>
            {blocked && rules && <p className="ct-blocked">Add {money(rules.quick.minOrder - sub.quick)} more to your Quick items to continue</p>}
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

      <CouponSheet open={couponOpen} onClose={() => setCouponOpen(false)} coupons={coupons} offers={bill.coupons} applied={couponValid ? coupon : null} onApply={applyCoupon} />
      <div className={"ct-toast" + (toast ? " ct-show" : "")} role="status" aria-live="polite">{toast}</div>
    </div>
  );
}
