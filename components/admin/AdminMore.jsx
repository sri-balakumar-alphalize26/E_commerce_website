"use client";
/* ==========================================================================
   369 Mart admin — Offers · Reviews · Settings
   ========================================================================== */
import { useState } from "react";
import { Avatar, Confirm, Drawer, Empty, Icon, Search, Select, Switch, Tabs } from "./AdminUI";
import { groupIN, inr, since } from "./adminData";

/* ================================ offers ================================ */
function NewCoupon({ onClose, onAdd }) {
  const [f, setF] = useState({ code: "", title: "", note: "", cap: "500", ends: "30 Sep 2026" });
  const set = (k) => (e) => setF({ ...f, [k]: k === "code" ? e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") : e.target.value });
  const ok = f.code.length >= 4 && f.title.trim().length > 3;
  return (
    <Drawer title="New coupon" sub="Customers can apply it in the cart and at checkout" onClose={onClose}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={!ok} onClick={() => { onAdd({ ...f, cap: +f.cap || 100, used: 0, active: true }); close(); }}>Create coupon</button>
        </>
      )}>
      <div className="ad-form">
        <label className="ad-field"><span>Code</span><input value={f.code} onChange={set("code")} placeholder="ONAM25" /></label>
        <label className="ad-field"><span>Usage limit</span><input inputMode="numeric" value={f.cap} onChange={set("cap")} /></label>
        <label className="ad-field ad-span2"><span>Title customers see</span><input value={f.title} onChange={set("title")} placeholder="25% off staples" /></label>
        <label className="ad-field ad-span2"><span>Conditions</span><input value={f.note} onChange={set("note")} placeholder="Atta, rice and oils · max ₹150" /></label>
        <label className="ad-field"><span>Valid until</span><input value={f.ends} onChange={set("ends")} /></label>
        <p className="ad-hint ad-span2"><Icon n="info" size={14} />Discount rules (percentage, cap, minimum order, categories) come from your loyalty setup once connected.</p>
      </div>
    </Drawer>
  );
}

export function OffersSection({ coupons, setCoupons, flash }) {
  const [adding, setAdding] = useState(false);
  const toggle = (code) => {
    setCoupons((l) => l.map((c) => (c.code === code ? { ...c, active: !c.active } : c)));
    const c = coupons.find((x) => x.code === code);
    flash(`${code} ${c.active ? "paused" : "activated"}`);
  };
  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Coupons</small><b>{coupons.length}</b></span>
        <span><small>Active</small><b>{coupons.filter((c) => c.active).length}</b></span>
        <span><small>Redemptions</small><b>{groupIN(coupons.reduce((s, c) => s + c.used, 0))}</b></span>
        <span className="ad-warn"><small>Nearly used up</small><b>{coupons.filter((c) => c.used / c.cap > 0.9 && c.active).length}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <div><h2 className="ad-sec-h">Coupons</h2></div>
          <div className="ad-toolbar-right"><button className="ad-btn ad-primary" onClick={() => setAdding(true)}><Icon n="plus" size={16} />New coupon</button></div>
        </div>
        <div className="ad-coupons">
          {coupons.map((c, i) => {
            const pct = Math.min(100, Math.round((c.used / c.cap) * 100));
            return (
              <article key={c.code} className={"ad-coupon" + (c.active ? "" : " ad-off")} style={{ "--i": i }}>
                <span className="ad-coupon-stub"><Icon n="pct" size={18} /><b>{c.code}</b></span>
                <div className="ad-coupon-body">
                  <b>{c.title}</b><small>{c.note}</small>
                  <div className="ad-progress" style={{ "--p": pct + "%" }} role="img" aria-label={`${c.used} of ${c.cap} used`}><i /></div>
                  <small className="ad-coupon-use">{groupIN(c.used)} of {groupIN(c.cap)} used · {c.ends}</small>
                </div>
                <div className="ad-coupon-act">
                  <Switch on={c.active} onChange={() => toggle(c.code)} label={`${c.code} active`} />
                  <button className="ad-link" onClick={() => { navigator.clipboard?.writeText(c.code); flash(`${c.code} copied`); }}>Copy</button>
                </div>
              </article>
            );
          })}
        </div>
      </section>
      {adding && <NewCoupon onClose={() => setAdding(false)} onAdd={(c) => { setCoupons((l) => [c, ...l]); flash(`${c.code} created`); }} />}
    </div>
  );
}

/* =============================== reviews ================================ */
export function ReviewsSection({ reviews, setReviews, flash }) {
  const [tab, setTab] = useState("pending");
  const [q, setQ] = useState("");
  const [drop, setDrop] = useState(null);
  const rows = reviews.filter((r) => (tab === "all" || r.state === tab) && (!q.trim() || (r.product + r.title + r.text + r.by).toLowerCase().includes(q.toLowerCase())));
  const set = (id, state) => setReviews((l) => l.map((r) => (r.id === id ? { ...r, state } : r)));
  const count = (k) => reviews.filter((r) => r.state === k).length;
  const avg = (reviews.reduce((s, r) => s + r.stars, 0) / (reviews.length || 1)).toFixed(1);

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Average rating</small><b>{avg} ★</b></span>
        <span className="ad-warn"><small>Waiting</small><b>{count("pending")}</b></span>
        <span><small>Published</small><b>{count("published")}</b></span>
        <span className="ad-bad"><small>Hidden</small><b>{count("hidden")}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["pending", "Waiting", count("pending")], ["published", "Published", count("published")], ["hidden", "Hidden", count("hidden")], ["all", "All"]]} />
          <div className="ad-toolbar-right"><Search value={q} onChange={setQ} placeholder="Product, customer or text" /></div>
        </div>
        <ul className="ad-reviews">
          {rows.map((r, i) => (
            <li key={r.id} style={{ "--i": i }}>
              <Avatar name={r.by} size={38} tone={r.stars >= 4 ? "ad-a-green" : r.stars >= 3 ? "ad-a-orange" : "ad-a-red"} />
              <div className="ad-review-body">
                <div className="ad-review-top">
                  <span className={"ad-stars ad-s" + r.stars}>{r.stars}★</span>
                  <b>{r.title}</b>
                  <small>{r.by} · {r.product} · {since(r.at)}</small>
                </div>
                <p>{r.text}</p>
              </div>
              <div className="ad-review-act">
                {r.state !== "published" && <button className="ad-btn ad-sm ad-primary" onClick={() => { set(r.id, "published"); flash("Review published"); }}>Publish</button>}
                {r.state !== "hidden" && <button className="ad-btn ad-sm" onClick={() => setDrop(r)}>Hide</button>}
                <button className="ad-btn ad-sm" onClick={() => flash(`Reply sent to ${r.by}`)}>Reply</button>
              </div>
            </li>
          ))}
        </ul>
        {!rows.length && <Empty icon="star" title="Nothing here" text="No reviews in this tab." />}
      </section>

      {drop && (
        <Confirm danger title="Hide this review?" confirmLabel="Hide review"
          text={`“${drop.title}” by ${drop.by} will no longer show on the product page.`}
          onCancel={() => setDrop(null)} onConfirm={() => { set(drop.id, "hidden"); setDrop(null); flash("Review hidden"); }} />
      )}
    </div>
  );
}

/* =============================== settings =============================== */
function Field({ label, value, onChange, suffix, wide, type = "text" }) {
  return (
    <label className={"ad-field" + (wide ? " ad-span2" : "")}>
      <span>{label}</span>
      <span className="ad-field-in">
        <input type={type} value={value} onChange={(e) => onChange(e.target.value)} />
        {suffix && <em>{suffix}</em>}
      </span>
    </label>
  );
}

export function SettingsSection({ settings, setSettings, flash }) {
  const [s, setS] = useState(settings);
  const [tab, setTab] = useState("store");
  const dirty = JSON.stringify(s) !== JSON.stringify(settings);
  const set = (group, key) => (v) => setS({ ...s, [group]: { ...s[group], [key]: v } });
  const save = () => { setSettings(s); flash("Settings saved"); };

  return (
    <div className="ad-stack">
      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["store", "Store"], ["delivery", "Delivery"], ["payments", "Payments"], ["alerts", "Alerts"]]} />
          <div className="ad-toolbar-right">
            {dirty && <span className="ad-dim">Unsaved changes</span>}
            <button className="ad-btn" disabled={!dirty} onClick={() => setS(settings)}>Reset</button>
            <button className="ad-btn ad-primary" disabled={!dirty} onClick={save}>Save changes</button>
          </div>
        </div>

        {tab === "store" && (
          <div className="ad-form ad-form-pad">
            <Field label="Store name" value={s.store.name} onChange={set("store", "name")} wide />
            <Field label="Phone" value={s.store.phone} onChange={set("store", "phone")} />
            <Field label="Email" value={s.store.email} onChange={set("store", "email")} />
            <Field label="Address" value={s.store.address} onChange={set("store", "address")} wide />
            <Field label="GSTIN" value={s.store.gstin} onChange={set("store", "gstin")} />
            <div className="ad-field-row">
              <Field label="Opens" type="time" value={s.store.open} onChange={set("store", "open")} />
              <Field label="Closes" type="time" value={s.store.close} onChange={set("store", "close")} />
            </div>
          </div>
        )}

        {tab === "delivery" && (
          <div className="ad-two">
            {[["quick", "Quick", "Groceries in 10–20 minutes"], ["express", "Express", "Electronics and home in 2–5 days"]].map(([k, title, sub]) => (
              <div key={k} className="ad-panel">
                <h3>{title}<small>{sub}</small></h3>
                <div className="ad-form">
                  <Field label="Minimum order" value={s[k].min} onChange={(v) => set(k, "min")(+v.replace(/\D/g, "") || 0)} suffix="₹" />
                  <Field label="Delivery fee" value={s[k].fee} onChange={(v) => set(k, "fee")(+v.replace(/\D/g, "") || 0)} suffix="₹" />
                  <Field label="Free above" value={s[k].freeAbove} onChange={(v) => set(k, "freeAbove")(+v.replace(/\D/g, "") || 0)} suffix="₹" />
                  <Field label={k === "quick" ? "Delivery radius" : "Slots per day"} value={k === "quick" ? s[k].radius : s[k].slots} onChange={(v) => set(k, k === "quick" ? "radius" : "slots")(+v.replace(/\D/g, "") || 0)} suffix={k === "quick" ? "km" : "slots"} />
                  <Field label="Promised time" value={s[k].eta} onChange={set(k, "eta")} wide />
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "payments" && (
          <div className="ad-rows">
            {[["upi", "UPI", "Google Pay, PhonePe, Paytm, any UPI ID"], ["card", "Cards", "Visa, Mastercard, RuPay, Amex"], ["netbanking", "Net banking", "All major Indian banks"], ["cod", "Cash on delivery", `Allowed up to ${inr(s.pay.codLimit)}`], ["wallet", "369 Wallet", "Balance, refunds and cashback"]].map(([k, t, d]) => (
              <div key={k} className="ad-row-set">
                <span className="ad-row-ic"><Icon n={k === "upi" ? "upi" : k === "card" ? "card" : k === "netbanking" ? "bank" : k === "cod" ? "cash" : "wallet"} size={18} /></span>
                <span className="ad-row-txt"><b>{t}</b><small>{d}</small></span>
                <Switch on={s.pay[k]} onChange={set("pay", k)} label={t} />
              </div>
            ))}
            <div className="ad-row-set">
              <span className="ad-row-ic"><Icon n="shield" size={18} /></span>
              <span className="ad-row-txt"><b>Cash on delivery limit</b><small>Orders above this must be paid online</small></span>
              <span className="ad-field-in ad-narrow"><input value={s.pay.codLimit} onChange={(e) => set("pay", "codLimit")(+e.target.value.replace(/\D/g, "") || 0)} aria-label="COD limit" /><em>₹</em></span>
            </div>
          </div>
        )}

        {tab === "alerts" && (
          <div className="ad-rows">
            {[["newOrder", "New order", "Beep and badge when an order comes in"], ["lowStock", "Low stock", "When a product reaches its reorder level"], ["cancelled", "Cancellations", "When a customer cancels an order"], ["dailySummary", "Daily summary", "Sales and stock email at closing time"]].map(([k, t, d]) => (
              <div key={k} className="ad-row-set">
                <span className="ad-row-ic"><Icon n="bell" size={18} /></span>
                <span className="ad-row-txt"><b>{t}</b><small>{d}</small></span>
                <Switch on={s.alerts[k]} onChange={set("alerts", k)} label={t} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
