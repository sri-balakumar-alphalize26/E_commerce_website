"use client";
/* ==========================================================================
   369 Mart — Account
   Sidebar: profile card · My Profile · My List · Delivery Address · Orders ·
   Ratings & reviews · Notifications ·
   Payments & rewards (369 Wallet, Saved payments, Coupons & rewards, Refer & earn) ·
   Help & information (Help, About us, Legal information) · Sign out.
   The extras live in AccountExtras.jsx (+ accountStore.js, acx.css).

   Motion
   - page: sidebar slides in from the left, panel rises, menu items cascade
   - avatar: gradient ring draws once, initial pops
   - menu: one highlight pill glides to the active item (spring); icon bounces
   - section change: panel content slides in from below/above depending on
     menu order, panel height eases to the new content, title rolls
   - each section has its own entrance (cards cascade, rows slide, accordions
     open with height), empty states have animated illustrations
   - sign out: confirm dialog pops, then the page fades out
   ========================================================================== */
import { useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon, OpenContext, QtyControl, Thumb, WishContext, inr } from "./shared";
import { NotifsSec, PaymentsSec, ReferSec, ReviewsSec, RewardsSec, WalletSec, useNotifications } from "./AccountExtras";

const MENU = [
  { key: "profile", label: "My Profile", icon: "user" },
  { key: "list", label: "My List", icon: "heart" },
  { key: "address", label: "Delivery Address", icon: "pin" },
  { key: "orders", label: "Orders", icon: "box" },
  { key: "reviews", label: "Ratings & reviews", icon: "star" },
  { key: "notifications", label: "Notifications", icon: "bell" },
  { group: "Payments & rewards" },
  { key: "wallet", label: "369 Wallet", icon: "wallet" },
  { key: "payments", label: "Saved payments", icon: "card" },
  { key: "rewards", label: "Coupons & rewards", icon: "gift" },
  { key: "refer", label: "Refer & earn", icon: "share" },
  { group: "Help & information" },
  { key: "help", label: "Help", icon: "help" },
  { key: "about", label: "About us", icon: "info" },
  { key: "legal", label: "Legal information", icon: "legal" },
];
const ORDER = MENU.filter((m) => m.key).map((m) => m.key);
const TITLES = Object.fromEntries(MENU.filter((m) => m.key).map((m) => [m.key, m.label]));
export const ACCOUNT_SECTIONS = ORDER;

export const SAMPLE_ORDERS = [
  { id: "369M-24091612", placed: "Today, 11:42 am", mode: "quick", status: "out", eta: "9 mins", items: [["f3", 1], ["d6", 2], ["f2", 1]], total: 796, pay: "UPI" },
  { id: "369E-24091408", placed: "14 Sep 2026", mode: "all", status: "shipped", eta: "Arrives Thu, 18 Sep", items: [["a1", 1], ["b2", 1]], total: 11398, pay: "Card •••• 4821" },
  { id: "369M-24090931", placed: "9 Sep 2026", mode: "quick", status: "delivered", eta: "Delivered 9 Sep, 7:18 pm", items: [["d2", 1], ["d1", 1], ["d7", 1]], total: 1117, pay: "Cash on delivery" },
  { id: "369E-24090205", placed: "2 Sep 2026", mode: "all", status: "cancelled", eta: "Refunded to original payment", items: [["t5", 1]], total: 2499, pay: "UPI" },
];
const STEPS = { quick: ["Placed", "Packed", "Out for delivery", "Delivered"], all: ["Placed", "Shipped", "Out for delivery", "Delivered"] };
const STEP_OF = { placed: 0, packed: 1, shipped: 1, out: 2, delivered: 3 };

/* ---------- panel with height easing + directional content swap ---------- */
function Panel({ k, dir, children }) {
  const inner = useRef(null);
  const [h, setH] = useState(null);
  useLayoutEffect(() => {
    if (!inner.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setH(inner.current.offsetHeight));
    ro.observe(inner.current);
    return () => ro.disconnect();
  }, []);
  return (
    <div className="ac-panel" style={h ? { height: h } : undefined}>
      <div ref={inner}>
        <div key={k} className={"ac-swap " + (dir < 0 ? "ac-from-top" : "ac-from-bottom")}>{children}</div>
      </div>
    </div>
  );
}

function Empty({ icon, title, text, action, onAction, tone = "" }) {
  return (
    <div className={"ac-empty " + tone}>
      <span className="ac-empty-art">
        <Icon n={icon} size={30} />
        {icon === "heart" && <><i className="ac-float f1" /><i className="ac-float f2" /><i className="ac-float f3" /></>}
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {action && <button className="ac-primary" onClick={onAction}>{action}</button>}
    </div>
  );
}

/* ---------- sections ---------- */
function ProfileSec({ user, onSave }) {
  const [form, setForm] = useState(user);
  const [edit, setEdit] = useState(false);
  const [saved, setSaved] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const save = (e) => {
    e.preventDefault();
    onSave(form); setEdit(false); setSaved(true);
    setTimeout(() => setSaved(false), 2200);
  };
  return (
    <form className="ac-card ac-profile" onSubmit={save}>
      <div className="ac-card-head">
        <div><h3>Personal details</h3><p>Used for deliveries and invoices.</p></div>
        {saved ? <span className="ac-saved-tag"><Icon n="check" size={14} />Saved</span>
          : !edit && <button type="button" className="ac-ghost" onClick={() => setEdit(true)}><Icon n="edit" size={15} />Edit</button>}
      </div>
      <div className="ac-fields">
        {[["name", "Full name", "user", "text"], ["email", "Email", "mail", "email"], ["phone", "Mobile number", "phone", "tel"]].map(([k, label, icon, type], i) => (
          <label key={k} className={"ac-field" + (edit ? " ac-editing" : "")} style={{ "--i": i }}>
            <span className="ac-field-label"><Icon n={icon} size={15} />{label}</span>
            <input type={type} value={form[k] || ""} onChange={set(k)} readOnly={!edit} placeholder={edit ? `Add ${label.toLowerCase()}` : "Not added"} />
          </label>
        ))}
      </div>
      <div className={"ac-actions" + (edit ? " ac-show" : "")}>
        <div>
          <button type="button" className="ac-ghost" onClick={() => { setForm(user); setEdit(false); }} tabIndex={edit ? 0 : -1}>Cancel</button>
          <button type="submit" className="ac-primary" tabIndex={edit ? 0 : -1}>Save changes</button>
        </div>
      </div>
    </form>
  );
}

function ListSec({ byId, cart, setQty, onBrowse }) {
  const wish = useContext(WishContext);
  const [leaving, setLeaving] = useState({});
  const open = useContext(OpenContext);
  const ids = wish ? [...wish.ids] : [];
  if (!ids.length) {
    return (
      <div className="ac-card">
        <Empty icon="heart" title="Your list is empty" text="Tap the heart on any product to save it here." action="Browse products" onAction={onBrowse} />
      </div>
    );
  }
  const remove = (id) => { setLeaving((l) => ({ ...l, [id]: true })); setTimeout(() => { wish.toggle(id); setLeaving((l) => { const n = { ...l }; delete n[id]; return n; }); }, 320); };
  return (
    <div className="ac-grid">
      {ids.filter((id) => byId[id]).map((id, i) => {
        const p = byId[id];
        return (
          <article key={id} className={"ac-wish" + (leaving[id] ? " ac-leaving" : "")} style={{ "--i": i }}>
            <div className="ac-wish-img" onClick={(e) => { if (!e.target.closest("button")) open?.(p, e.currentTarget.getBoundingClientRect()); }} style={{ cursor: "pointer" }}><Thumb p={p} />
              <button className="ac-wish-heart" onClick={() => remove(id)} aria-label={`Remove ${p.name} from My List`}><Icon n="heartFill" size={18} /></button>
            </div>
            <b>{p.name}</b>
            <small>{p.unit}</small>
            <div className="ac-wish-foot">
              <span className="ac-price">{inr(p.price)}{p.mrp ? <s>{inr(p.mrp)}</s> : null}</span>
              {p.stock === 0 ? <span className="ac-muted">Sold out</span> : <QtyControl qty={cart[p.id] || 0} id={p.id} name={p.name} onChange={(n) => setQty(p.id, n)} />}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function AddressSec({ addresses, onAddAddress, onRemoveAddress, selected, onSelect, busy, error }) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ label: "Home", line: "", city: "" });
  const add = async (e) => {
    e.preventDefault();
    if (!draft.line.trim() || !draft.city.trim()) return;
    /* The shop mints the id, works out the icon and splits the pincode off the
       city. A locally invented id could never be ordered against. */
    const saved = await onAddAddress(draft);
    if (!saved) return; /* the error is shown under the form */
    setAdding(false); setDraft({ label: "Home", line: "", city: "" });
  };
  return (
    <div className="ac-stack">
      <button className={"ac-card ac-add" + (adding ? " ac-open" : "")} onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
        <span className="ac-add-ic"><Icon n="plus" size={18} /></span>Add a new address
      </button>
      <div className={"ac-collapse" + (adding ? " ac-show" : "")}>
        <div>
        <form className="ac-card ac-addr-form" onSubmit={add}>
          <div className="ac-chips">
            {["Home", "Work", "Other"].map((l) => (
              <button type="button" key={l} className={draft.label === l ? "ac-on" : ""} onClick={() => setDraft({ ...draft, label: l })} tabIndex={adding ? 0 : -1}>{l}</button>
            ))}
          </div>
          <input placeholder="House / flat, street, area" value={draft.line} onChange={(e) => setDraft({ ...draft, line: e.target.value })} tabIndex={adding ? 0 : -1} />
          <input placeholder="City and pincode" value={draft.city} onChange={(e) => setDraft({ ...draft, city: e.target.value })} tabIndex={adding ? 0 : -1} />
          {error && <p className="co-error" key={error}>{error}</p>}
          <button className="ac-primary" type="submit" tabIndex={adding ? 0 : -1} disabled={busy}>{busy ? "Saving…" : "Save address"}</button>
        </form>
        </div>
      </div>
      {addresses.map((a, i) => {
        const on = selected?.id === a.id;
        return (
          <div key={a.id} className={"ac-card ac-addr" + (on ? " ac-on" : "")} style={{ "--i": i }}>
            <span className="ac-addr-ic"><Icon n={a.icon || "pin"} size={18} /></span>
            <div className="ac-addr-txt">
              <b>{a.label}{on && <em>Default</em>}</b>
              <small>{a.line}{a.city ? `, ${a.city}` : ""}</small>
            </div>
            <div className="ac-addr-act">
              {!on && <button className="ac-link" onClick={() => onSelect(a)}>Set as default</button>}
              <button className="ac-link ac-danger" onClick={() => onRemoveAddress(a)}>Remove</button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function OrdersSec({ orders, byId, onReorder, onTrack }) {
  const [tab, setTab] = useState("all");
  const [open, setOpen] = useState(orders[0]?.id);
  const tabs = [["all", "All"], ["active", "Active"], ["delivered", "Delivered"], ["cancelled", "Cancelled"]];
  const list = orders.filter((o) => tab === "all" || (tab === "active" ? ["placed", "packed", "shipped", "out"].includes(o.status) : o.status === tab));
  return (
    <div className="ac-stack">
      <div className="ac-tabs" role="tablist" style={{ "--n": tabs.length, "--t": tabs.findIndex((t) => t[0] === tab) }}>
        <span className="ac-tabs-thumb" aria-hidden="true" />
        {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      <div key={tab} className="ac-stack">
        {!list.length && <div className="ac-card"><Empty icon="box" title="No orders here" text="Orders you place will show up in this tab." /></div>}
        {list.map((o, i) => {
          const steps = STEPS[o.mode];
          const at = STEP_OF[o.status] ?? -1;
          const isOpen = open === o.id;
          const cancelled = o.status === "cancelled";
          return (
            <article key={o.id} className={"ac-card ac-order" + (isOpen ? " ac-open" : "")} style={{ "--i": i }}>
              <button className="ac-order-head" onClick={() => setOpen(isOpen ? null : o.id)} aria-expanded={isOpen}>
                <span className="ac-thumbs">
                  {o.items.slice(0, 3).map(([id]) => byId[id] && <span key={id} className="ac-thumb"><Thumb p={byId[id]} /></span>)}
                  {o.items.length > 3 && <span className="ac-thumb ac-more">+{o.items.length - 3}</span>}
                </span>
                <span className="ac-order-txt">
                  <b>{o.mode === "quick" ? <Icon n="bolt" size={13} className="hm-fill ac-q" /> : <Icon n="truck" size={14} className="ac-e" />}
                    Order #{o.id}</b>
                  <small>{o.placed} · {inr(o.total)}</small>
                </span>
                <span className={"ac-status ac-s-" + o.status}>{cancelled ? "Cancelled" : o.status === "delivered" ? "Delivered" : o.status === "out" ? `Arriving in ${o.eta}` : steps[at]}</span>
                <Icon n="chev" size={18} className="ac-chev" />
              </button>
              {!cancelled && (
                <div className="ac-track" style={{ "--p": at / (steps.length - 1) }}>
                  <div className="ac-track-line"><i /></div>
                  {steps.map((s, k) => (
                    <span key={s} className={"ac-step" + (k <= at ? " ac-done" : "") + (k === at && o.status !== "delivered" ? " ac-now" : "")} style={{ "--k": k }}>
                      <i>{k <= at ? <Icon n="check" size={11} /> : null}</i>{s}
                    </span>
                  ))}
                </div>
              )}
              <div className={"ac-collapse" + (isOpen ? " ac-show" : "")}>
                <div>
                <div className="ac-order-body">
                  <ul>
                    {o.items.map(([id, q]) => byId[id] && (
                      <li key={id}><span className="ac-thumb"><Thumb p={byId[id]} /></span><span>{byId[id].name}<small> × {q}</small></span><b>{inr(byId[id].price * q)}</b></li>
                    ))}
                  </ul>
                  <div className="ac-order-meta">
                    <span><small>Status</small>{o.eta}</span>
                    <span><small>Paid with</small>{o.pay}</span>
                    <span><small>Total</small><b>{inr(o.total)}</b></span>
                  </div>
                  <div className="ac-order-act">
                    {onTrack && <button className="ac-ghost" onClick={() => onTrack(o)} tabIndex={isOpen ? 0 : -1}><Icon n={cancelled || o.status === "delivered" ? "note" : "pin"} size={15} />{cancelled || o.status === "delivered" ? "Order details" : "Track order"}</button>}
                    {o.status === "delivered" && <button className="ac-ghost" onClick={() => onTrack?.(o)} tabIndex={isOpen ? 0 : -1}><Icon n="star" size={15} />{o.rating ? "Rated " + o.rating.stars + "★" : "Rate order"}</button>}
                    <button className="ac-primary" onClick={(e) => onReorder(o, e.currentTarget)} tabIndex={isOpen ? 0 : -1}>Reorder</button>
                  </div>
                </div>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

const FAQ = [
  ["How fast is Quick delivery?", "Quick orders are packed at a store near you and usually arrive in 10–20 minutes. The live timer on your order shows the exact estimate."],
  ["What is Express?", "Express covers electronics, home and office products shipped from our warehouse. Delivery takes 2–5 days depending on your pincode."],
  ["How do I cancel an order?", "Open Orders, choose the order and tap Cancel. Quick orders can be cancelled until they are packed; Express orders until they are shipped."],
  ["When will I get my refund?", "Refunds go back to the original payment method within 3–5 working days, or instantly for cash-on-delivery orders refunded to your wallet."],
  ["An item was missing or damaged", "Open the order within 48 hours of delivery, tap Get help and choose the item. We'll arrange a replacement or refund."],
];
function Accordion({ items }) {
  const [open, setOpen] = useState(0);
  return (
    <div className="ac-card ac-acc">
      {items.map(([q, a], i) => (
        <div key={q} className={"ac-acc-item" + (open === i ? " ac-open" : "")} style={{ "--i": i }}>
          <button onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i}>{q}<Icon n="chev" size={18} className="ac-chev" /></button>
          <div className={"ac-collapse" + (open === i ? " ac-show" : "")}><div><p>{a}</p></div></div>
        </div>
      ))}
    </div>
  );
}
function HelpSec() {
  const [q, setQ] = useState("");
  const hits = FAQ.filter(([t, a]) => (t + a).toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="ac-stack">
      <div className="ac-card ac-help-search"><Icon n="search" size={18} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search help topics" aria-label="Search help topics" /></div>
      <div className="ac-help-quick">
        {[["box", "Track an order"], ["cash", "Refund status"], ["chat", "Chat with us"], ["phone", "Call support"]].map(([ic, l], i) => (
          <button key={l} className="ac-card ac-tile" style={{ "--i": i }}><span><Icon n={ic} size={20} /></span>{l}</button>
        ))}
      </div>
      {hits.length ? <Accordion key={q} items={hits} /> : <div className="ac-card"><Empty icon="help" title="No matching topics" text="Try a different word, or chat with us." /></div>}
    </div>
  );
}
function AboutSec() {
  return (
    <div className="ac-stack">
      <div className="ac-card ac-about">
        <div className="ac-about-hero"><span className="ac-about-logo">369<svg viewBox="0 0 24 24"><path d="M6 18 18 6M9 6h9v9" /></svg>Mart</span><p>Computer parts and gear. In minutes, or in days.</p></div>
        <div className="ac-about-stats">
          {[["10–20", "min Quick delivery"], ["2–5", "day Express delivery"], ["7 days", "support"]].map(([n, l], i) => (
            <span key={l} style={{ "--i": i }}><b>{n}</b>{l}</span>
          ))}
        </div>
        <p className="ac-about-copy">369 Mart brings daily essentials from neighbourhood stores to your door in minutes, and ships electronics, home and office products from our warehouse through Express.</p>
      </div>
    </div>
  );
}
const LEGAL = [
  ["Terms of use", "The terms that apply when you browse, order and pay on 369 Mart."],
  ["Privacy policy", "What we collect, why, how long we keep it and how to ask us to delete it."],
  ["Cancellation & refund policy", "When orders can be cancelled and how refunds are processed."],
  ["Shipping policy", "Delivery areas, timelines and charges for Quick and Express."],
  ["Grievance officer", "How to raise a complaint and our response timelines."],
];
function LegalSec() {
  return (
    <div className="ac-card ac-legal">
      {LEGAL.map(([t, d], i) => (
        <a key={t} href="#" onClick={(e) => e.preventDefault()} style={{ "--i": i }}>
          <span className="ac-legal-ic"><Icon n="legal" size={17} /></span>
          <span><b>{t}</b><small>{d}</small></span>
          <Icon n="right" size={16} className="ac-go" />
        </a>
      ))}
    </div>
  );
}

/* ---------- page ---------- */
export default function AccountPage({
  user: initialUser = { name: "Demo", email: "abc", phone: "" },
  section: initialSection = "list",
  byId, cart, setQty, addresses, onAddAddress, onRemoveAddress, selectedAddress, onSelectAddress, addrBusy, addrError,
  orders = SAMPLE_ORDERS, onBrowse, onReorder, onTrack, onSignOut,
  wallet = 0, onWallet, onNav, onSection,
}) {
  const [user, setUser] = useState(initialUser);
  useEffect(() => { if (initialUser) setUser(initialUser); }, [initialUser?.name, initialUser?.email]); // eslint-disable-line
  const [section, setSection] = useState(ORDER.includes(initialSection) ? initialSection : "list");
  const [toast, setToast] = useState(null);
  const toastT = useRef(null);
  const flash = (m) => { setToast(m); clearTimeout(toastT.current); toastT.current = setTimeout(() => setToast(null), 2200); };
  const { unread } = useNotifications(orders);
  const openProduct = useContext(OpenContext);
  const [dir, setDir] = useState(1);
  const [ind, setInd] = useState(null);
  const [confirm, setConfirm] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const nav = useRef(null);

  useLayoutEffect(() => {
    const place = () => {
      const el = nav.current?.querySelector(`[data-k="${section}"]`);
      if (el) setInd({ y: el.offsetTop, x: el.offsetLeft, h: el.offsetHeight, w: el.offsetWidth });
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [section]);

  useEffect(() => {
    if (!confirm) return;
    const k = (e) => e.key === "Escape" && setConfirm(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [confirm]);

  const go = (k) => {
    if (k === section) return;
    setDir(ORDER.indexOf(k) > ORDER.indexOf(section) ? 1 : -1);
    setSection(k);
    onSection?.(k);
    const el = nav.current?.querySelector(`[data-k="${k}"]`);
    el?.scrollIntoView?.({ block: "nearest", inline: "center", behavior: "smooth" });
  };
  const initial = (user.name || "?").trim()[0]?.toUpperCase();

  let body;
  if (section === "profile") body = <ProfileSec user={user} onSave={setUser} />;
  else if (section === "list") body = <ListSec byId={byId} cart={cart} setQty={setQty} onBrowse={onBrowse} />;
  else if (section === "address") body = <AddressSec addresses={addresses} onAddAddress={onAddAddress} onRemoveAddress={onRemoveAddress} selected={selectedAddress} onSelect={onSelectAddress} busy={addrBusy} error={addrError} />;
  else if (section === "orders") body = <OrdersSec orders={orders} byId={byId} onReorder={onReorder} onTrack={onTrack} />;
  else if (section === "reviews") body = <ReviewsSec orders={orders} byId={byId} onOpen={openProduct} flash={flash} />;
  else if (section === "notifications") body = <NotifsSec orders={orders} onNav={onNav} goSection={go} />;
  else if (section === "wallet") body = <WalletSec balance={wallet} onWallet={onWallet} onNav={onNav} flash={flash} />;
  else if (section === "payments") body = <PaymentsSec flash={flash} />;
  else if (section === "rewards") body = <RewardsSec onWallet={onWallet} onNav={onNav} flash={flash} />;
  else if (section === "refer") body = <ReferSec user={user} flash={flash} />;
  else if (section === "help") body = <HelpSec />;
  else if (section === "about") body = <AboutSec />;
  else body = <LegalSec />;

  return (
    <div className={"ac-page" + (leaving ? " ac-signing-out" : "")}>
      <aside className="ac-side">
        <div className="ac-me">
          <span className="ac-avatar"><i>{initial}</i></span>
          <span className="ac-me-txt"><b key={user.name}>{user.name}</b><small>{user.email || user.phone}</small></span>
        </div>
        <nav className="ac-nav" ref={nav} aria-label="Account">
          {ind && <span className="ac-ind" style={{ transform: `translate(${ind.x}px, ${ind.y}px)`, height: ind.h, width: ind.w }} aria-hidden="true" />}
          {MENU.map((m, i) => m.group ? (
            <p key={m.group} className="ac-group" style={{ "--i": i }}>{m.group}</p>
          ) : (
            <button key={m.key} data-k={m.key} className={section === m.key ? "ac-cur" : ""} aria-current={section === m.key ? "page" : undefined}
              style={{ "--i": i }} onClick={() => go(m.key)}>
              <span className="ac-nav-ic" key={section === m.key ? "on" : "off"}><Icon n={section === m.key && m.icon === "heart" ? "heartFill" : m.icon} size={19} /></span>
              {m.label}
              {m.key === "orders" && orders.some((o) => o.status === "out") && <em className="ac-live">Live</em>}
              {m.key === "notifications" && unread > 0 && <em className="ax-badge" key={unread}>{unread}</em>}
              {m.key === "wallet" && <em className="ax-navamt">{inr(wallet)}</em>}
            </button>
          ))}
          <hr />
          <button className="ac-signout" style={{ "--i": MENU.length }} onClick={() => setConfirm(true)}>
            <span className="ac-nav-ic"><Icon n="logout" size={19} /></span>Sign out
          </button>
        </nav>
      </aside>

      <main className="ac-main">
        <h1 className="ac-title"><span key={section}>{TITLES[section]}</span></h1>
        <Panel k={section} dir={dir}>{body}</Panel>
      </main>

      <div className={"ot-toast ax-toast" + (toast ? " ot-show" : "")} role="status" aria-live="polite">{toast}</div>

      {confirm && (
        <div className="ac-modal-wrap" role="presentation" onClick={() => setConfirm(false)}>
          <div className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="ac-so" onClick={(e) => e.stopPropagation()}>
            <span className="ac-modal-ic"><Icon n="logout" size={24} /></span>
            <h3 id="ac-so">Sign out of 369 Mart?</h3>
            <p>Your cart stays saved on this device.</p>
            <div>
              <button className="ac-ghost" onClick={() => setConfirm(false)} autoFocus>Stay signed in</button>
              <button className="ac-primary ac-danger-btn" onClick={() => { setConfirm(false); setLeaving(true); setTimeout(() => onSignOut?.(), 480); }}>Sign out</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
