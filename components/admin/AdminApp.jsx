"use client";
/* ==========================================================================
   369 Mart — Admin console
   Shell: collapsible sidebar, top bar (search, alerts, profile),
   section routing (/admin/<section>), toast.
   Sections: Dashboard · Home page · Orders · Products · Customers · Offers ·
             Reviews · Settings

   Dashboard and Home page read the shop. The rest still run on adminData.js
   and carry a banner saying so, until Phase B wires each one.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { useResource } from "@/lib/useFetch";
import { Avatar, Confirm, Drawer, Empty, Icon, Pill, Search, Select, Switch, Tabs, useToast } from "./AdminUI";
import { BarChart, DataTable, Legend, LineChart, RankBars, SERIES, Spark } from "./charts";
import {
  COUPONS, CUSTOMERS, FLOW, NEXT_LABEL, ORDERS, REVIEWS, RIDERS, SETTINGS, STOCK, TODAY,
  categorySales, clock, dateLong, hourlyOrders, inr, isToday, revenueSeries, since,
} from "./adminData";
import OrdersSection from "./AdminOrders";
import { CustomersSection, ProductsSection } from "./AdminCatalog";
import { OffersSection, ReviewsSection, SettingsSection } from "./AdminMore";
import HomeSection from "./HomeSection";
import ProductPageSection from "./ProductPageSection";

/* `live` marks a section that reads the shop. Everything else still runs on
   adminData.js and says so across the top of itself, because staff acting on
   an invented number is the one failure this console must not have.

   Riders and hubs are not here at all. There is no rider model and no hub
   model behind them - the storefront's "rider" is a hash of the order id -
   so there is nothing to connect them to later, and a screen that can never
   be made true does not belong in the menu. */
export const SECTIONS = [
  { key: "dashboard", label: "Dashboard", icon: "dash", group: "Overview", live: true },
  { key: "home", label: "Home page", icon: "layers", group: "Store", live: true },
  // Not live yet on purpose: the screen is real and the parts on it are the
  // shop's own, but mart369_product has no admin route, so nothing it shows
  // can be saved. The banner says so rather than the screen pretending.
  { key: "product-page", label: "Product page", icon: "note", group: "Store" },
  { key: "orders", label: "Orders", icon: "box", group: "Sales" },
  { key: "customers", label: "Customers", icon: "users", group: "Sales" },
  { key: "offers", label: "Offers", icon: "ticket", group: "Sales" },
  { key: "reviews", label: "Reviews", icon: "star", group: "Sales" },
  { key: "products", label: "Products", icon: "layers", group: "Catalogue" },
  { key: "settings", label: "Settings", icon: "gear", group: "Store" },
];
const TITLES = Object.fromEntries(SECTIONS.map((s) => [s.key, s.label]));
const LIVE = new Set(SECTIONS.filter((s) => s.live).map((s) => s.key));

/* ================================ dashboard ============================== */
function Stat({ label, value, delta, note, series, color, icon }) {
  const up = delta >= 0;
  return (
    <article className="ad-stat">
      <header><span className="ad-stat-ic" style={{ "--tone": color }}><Icon n={icon} size={18} /></span>{label}</header>
      <b>{value}</b>
      <div className="ad-stat-foot">
        {delta != null && (
          <span className={"ad-delta " + (up ? "ad-up" : "ad-down")}><Icon n={up ? "up" : "down"} size={13} />{Math.abs(delta)}%</span>
        )}
        <small>{note}</small>
      </div>
      {series && <Spark values={series} color={color} />}
    </article>
  );
}

/* Every number below comes from `/admin/dashboard`, which is the same call
   the strips above Odoo's own Orders and Customers lists make. Nothing is
   computed twice and nothing is invented: when a block is missing, the shop
   does not have that module installed, and the card says so.

   The revenue-over-time and orders-per-hour charts the drop shipped are gone.
   There is no aggregate behind either, and a chart is the most convincing way
   there is to show somebody a number that is not true. */
function Dashboard({ go }) {
  const { data, loading, error, reload } = useResource("/admin/dashboard", { pollMs: 60000 });
  const o = data?.orders;
  const c = data?.customers;

  if (error) {
    return (
      <section className="ad-card">
        <Empty icon="info" title="We could not reach the shop" text={error.message}
          action="Try again" onAction={reload} />
      </section>
    );
  }
  if (!o && !c) {
    return (
      <section className="ad-card">
        <Empty icon="dash" title={loading ? "Loading…" : "No numbers yet"}
          text={loading ? "Asking the shop." : "Install the orders module to see the daily strip here."} />
      </section>
    );
  }

  return (
    <div className="ad-stack">
      {o && (
        <section className="ad-stats">
          <Stat label="Orders today" value={o.today} note={o.today_value} color={SERIES[0]} icon="box"
            series={(o.placed || []).slice(-7).map((d) => d.count)} />
          <Stat label="Waiting to be packed" value={o.packing}
            note={o.late ? `${o.late} running late` : "nothing late"} color={SERIES[1]} icon="clock" />
          <Stat label="Out for delivery" value={o.out} note={`${o.live} live in all`} color={SERIES[3]} icon="truck" />
          <Stat label="Cash to collect" value={o.cash} note={`across ${o.cash_count} orders`} color={SERIES[2]} icon="cash" />
        </section>
      )}

      <div className="ad-grid-2">
        {o && (
          <section className="ad-card">
            <header className="ad-card-head">
              <div><h2>Orders a day</h2><p>The last fortnight</p></div>
              <button className="ad-btn" onClick={() => go("orders")}>Open orders<Icon n="right" size={15} /></button>
            </header>
            <BarChart rows={(o.placed || []).map((d) => ({ label: d.day, full: d.day, value: d.count }))}
              color={SERIES[0]} />
          </section>
        )}

        {c && (
          <section className="ad-card">
            <header className="ad-card-head">
              <div><h2>Customers</h2><p>{c.total} with an account</p></div>
            </header>
            <ul className="ad-rows">
              {[
                ["New this week", c.new_week],
                ["Ordered in the last 30 days", `${c.ordered_30} (${c.ordered_pct}%)`],
                ["Have a mobile number", `${c.with_mobile} (${c.mobile_pct}%)`],
                ["Dormant", c.dormant],
              ].map(([label, value], i) => (
                <li key={label} className="ad-row-set" style={{ "--i": i }}>
                  <span className="ad-row-txt"><b>{label}</b></span>
                  <span className="ad-strong">{value}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {o?.returns > 0 && (
        <section className="ad-card">
          <header className="ad-card-head">
            <div><h2>Returns in progress</h2><p>{o.returns} waiting on a pickup or a refund</p></div>
          </header>
        </section>
      )}
    </div>
  );
}

/* Said once, across the top of every screen that is still the drop's sample
   data. Blunt on purpose: a small grey note is how somebody ends up ringing a
   customer who does not exist. */
function SampleBanner({ label }) {
  return (
    <p className="ad-sample" role="note">
      <Icon n="info" size={15} />
      <span><b>Sample data — not connected yet.</b> Nothing on this screen is
        your shop. {label} is still being wired to Odoo; do not act on what is
        here.</span>
    </p>
  );
}

/* ================================== shell =============================== */
export default function AdminApp({ section: initial = "dashboard", onSection, onExit }) {
  const [section, setSection] = useState(SECTIONS.some((s) => s.key === initial) ? initial : "dashboard");
  const [orders, setOrders] = useState(ORDERS);
  const [stock, setStock] = useState(STOCK);
  const [coupons, setCoupons] = useState(COUPONS);
  const [reviews, setReviews] = useState(REVIEWS);
  const [settings, setSettings] = useState(SETTINGS);
  const [openId, setOpenId] = useState(null);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [alerts, setAlerts] = useState(false);
  const [profile, setProfile] = useState(false);
  const [q, setQ] = useState("");
  const [toast, flash] = useToast();
  /* The drop pinned the clock to a made-up date. Start at null and fill it in
     after mount, so the server and the browser render the same thing and the
     date shown is today's. */
  const [now, setNow] = useState(null);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);

  const go = (k) => { setSection(k); setMobileNav(false); onSection?.(k); window.scrollTo({ top: 0 }); };
  useEffect(() => {
    const c = (e) => { if (!e.target.closest(".ad-pop-wrap")) { setAlerts(false); setProfile(false); } };
    window.addEventListener("click", c);
    return () => window.removeEventListener("click", c);
  }, []);

  /* ---- actions (replace with Odoo calls) ---- */
  const patch = (id, p) => setOrders((l) => l.map((o) => (o.id === id ? { ...o, ...p } : o)));
  const advance = (id) => {
    const o = orders.find((x) => x.id === id);
    const next = FLOW[FLOW.indexOf(o.status) + 1];
    if (!next) return;
    patch(id, { status: next, rider: next === "out" && !o.rider ? { id: RIDERS[0].id, name: RIDERS[0].name } : o.rider });
    flash(`#${id} → ${next === "out" ? "out for delivery" : next}`);
  };
  const cancelOrder = (id, reason) => { patch(id, { status: "cancelled", cancelReason: reason }); flash(`#${id} cancelled`, "bad"); };
  const assign = (id, riderId) => { const r = RIDERS.find((x) => x.id === riderId); patch(id, { rider: { id: r.id, name: r.name } }); flash(`${r.name} assigned to #${id}`); };
  const setQty = (id, qty) => setStock((l) => l.map((s) => (s.id === id ? { ...s, qty: Math.max(0, qty) } : s)));
  const setPrice = (id, price) => setStock((l) => l.map((s) => (s.id === id ? { ...s, price } : s)));
  const toggleProduct = (id) => setStock((l) => l.map((s) => (s.id === id ? { ...s, active: !s.active } : s)));
  const addProduct = (p) => { setStock((l) => [{ ...p, id: "np" + Date.now(), sold7: 0, reorder: 12, active: true }, ...l]); flash(`${p.name} added`); };

  const live = orders.filter((o) => ["new", "packing", "ready", "out"].includes(o.status));
  const lowCount = stock.filter((s) => s.qty <= s.reorder).length;
  const pendingReviews = reviews.filter((r) => r.state === "pending").length;
  const counts = { orders: live.length, reviews: pendingReviews, products: lowCount };
  const notes = useMemo(() => [
    ...live.filter((o) => o.status === "new").slice(0, 3).map((o) => ({ id: "n" + o.id, icon: "box", text: `New order #${o.id} · ${inr(o.total)}`, at: o.at, go: ["orders", o.id] })),
    ...(lowCount ? [{ id: "nlow", icon: "layers", text: `${lowCount} products at or below reorder level`, at: TODAY - 3600000, go: ["products"] }] : []),
    ...(pendingReviews ? [{ id: "nrev", icon: "star", text: `${pendingReviews} reviews waiting for approval`, at: TODAY - 7200000, go: ["reviews"] }] : []),
  ], [live.length, lowCount, pendingReviews]); // eslint-disable-line

  const results = q.trim().length > 1 ? {
    orders: orders.filter((o) => (o.id + o.customer.name + o.customer.area).toLowerCase().includes(q.toLowerCase())).slice(0, 4),
    products: stock.filter((s) => s.name.toLowerCase().includes(q.toLowerCase())).slice(0, 4),
    customers: CUSTOMERS.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())).slice(0, 3),
  } : null;

  let body;
  if (section === "dashboard") body = <Dashboard go={go} />;
  else if (section === "home") body = <HomeSection flash={flash} />;
  else if (section === "product-page") body = <ProductPageSection flash={flash} />;
  else if (section === "orders") body = <OrdersSection orders={orders} openId={openId} setOpenId={setOpenId} advance={advance} cancelOrder={cancelOrder} assign={assign} flash={flash} />;
  else if (section === "products") body = <ProductsSection stock={stock} setQty={setQty} setPrice={setPrice} toggleProduct={toggleProduct} addProduct={addProduct} flash={flash} />;
  else if (section === "customers") body = <CustomersSection orders={orders} flash={flash} />;
  else if (section === "offers") body = <OffersSection coupons={coupons} setCoupons={setCoupons} flash={flash} />;
  else if (section === "reviews") body = <ReviewsSection reviews={reviews} setReviews={setReviews} flash={flash} />;
  else body = <SettingsSection settings={settings} setSettings={setSettings} flash={flash} />;

  const groups = [...new Set(SECTIONS.map((s) => s.group))];
  return (
    <div className={"ad-app" + (collapsed ? " ad-collapsed" : "") + (mobileNav ? " ad-nav-open" : "")}>
      <aside className="ad-side">
        <div className="ad-brand">
          <span className="ad-logo">369<svg viewBox="0 0 24 24"><path d="M6 18 18 6M9 6h9v9" /></svg></span>
          <span className="ad-brand-txt"><b>369 Mart</b><small>Admin console</small></span>
          <button className="ad-collapse" onClick={() => setCollapsed((v) => !v)} aria-label={collapsed ? "Expand menu" : "Collapse menu"}><Icon n={collapsed ? "right" : "left"} size={16} /></button>
        </div>
        <nav className="ad-nav" aria-label="Sections">
          {groups.map((g) => (
            <div key={g} className="ad-nav-group">
              <p>{g}</p>
              {SECTIONS.filter((s) => s.group === g).map((s) => (
                <button key={s.key} className={section === s.key ? "ad-cur" : ""} onClick={() => go(s.key)} title={s.label} aria-current={section === s.key ? "page" : undefined}>
                  <Icon n={s.icon} size={19} />
                  <span>{s.label}</span>
                  {counts[s.key] > 0 && <em className={s.key === "orders" ? "ad-badge ad-badge-live" : "ad-badge"}>{counts[s.key]}</em>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="ad-side-foot">
          <Avatar name="Shan S" tone="ad-a-navy" size={36} />
          <span className="ad-brand-txt"><b>Shan S</b><small>Store manager</small></span>
          <button className="ad-icon-btn" onClick={() => onExit?.()} aria-label="Open storefront" title="Open storefront"><Icon n="store" size={17} /></button>
        </div>
      </aside>

      <div className="ad-main">
        <header className="ad-top">
          <button className="ad-icon-btn ad-only-m" onClick={() => setMobileNav(true)} aria-label="Menu"><Icon n="menu" size={20} /></button>
          <div className="ad-top-title">
            <h1>{TITLES[section]}</h1>
            <small>{now ? `${dateLong(now)} · ${clock(now)}` : ""}</small>
          </div>
          <div className="ad-top-search">
            <Search value={q} onChange={setQ} placeholder="Search orders, products, customers" wide />
            {results && (
              <div className="ad-results">
                {results.orders.map((o) => <button key={o.id} onClick={() => { setQ(""); setOpenId(o.id); go("orders"); }}><Icon n="box" size={15} /><b>#{o.id}</b><small>{o.customer.name} · {inr(o.total)}</small></button>)}
                {results.products.map((p) => <button key={p.id} onClick={() => { setQ(""); go("products"); }}><Icon n="layers" size={15} /><b>{p.name}</b><small>{p.qty} in stock</small></button>)}
                {results.customers.map((c) => <button key={c.id} onClick={() => { setQ(""); go("customers"); }}><Icon n="users" size={15} /><b>{c.name}</b><small>{c.orders} orders</small></button>)}
                {!results.orders.length && !results.products.length && !results.customers.length && <p className="ad-no-res">No matches for “{q}”</p>}
              </div>
            )}
          </div>
          <div className="ad-pop-wrap">
            <button className={"ad-icon-btn" + (notes.length ? " ad-has-dot" : "")} onClick={() => { setAlerts((v) => !v); setProfile(false); }} aria-label="Alerts"><Icon n="bell" size={19} />{notes.length > 0 && <em>{notes.length}</em>}</button>
            {alerts && (
              <div className="ad-pop">
                <header>Alerts<button className="ad-link" onClick={() => setAlerts(false)}>Close</button></header>
                {notes.map((n) => (
                  <button key={n.id} onClick={() => { setAlerts(false); if (n.go[1]) setOpenId(n.go[1]); go(n.go[0]); }}>
                    <span className="ad-pop-ic"><Icon n={n.icon} size={16} /></span>
                    <span><b>{n.text}</b><small>{since(n.at)}</small></span>
                  </button>
                ))}
                {!notes.length && <p className="ad-no-res">Nothing needs attention.</p>}
              </div>
            )}
          </div>
          <div className="ad-pop-wrap">
            <button className="ad-profile" onClick={() => { setProfile((v) => !v); setAlerts(false); }} aria-label="Account">
              <Avatar name="Shan S" tone="ad-a-navy" size={34} /><Icon n="chev" size={15} />
            </button>
            {profile && (
              <div className="ad-pop ad-pop-sm">
                <button onClick={() => { setProfile(false); go("settings"); }}><span className="ad-pop-ic"><Icon n="gear" size={16} /></span><span><b>Store settings</b></span></button>
                <button onClick={() => { setProfile(false); onExit?.(); }}><span className="ad-pop-ic"><Icon n="store" size={16} /></span><span><b>Open storefront</b></span></button>
                <button onClick={() => { setProfile(false); flash("Signed out (demo)"); }}><span className="ad-pop-ic"><Icon n="logout" size={16} /></span><span><b>Sign out</b></span></button>
              </div>
            )}
          </div>
        </header>

        <main className="ad-body" key={section}>
          {!LIVE.has(section) && <SampleBanner label={TITLES[section]} />}
          {body}
        </main>
      </div>

      <div className="ad-nav-back" onClick={() => setMobileNav(false)} />
      {toast}
    </div>
  );
}
