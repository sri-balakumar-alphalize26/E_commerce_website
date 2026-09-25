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
  categorySales, hourlyOrders, isToday, revenueSeries,
} from "./adminData";
import { clock, dateLong, since } from "./format";
import { money } from "@/lib/money";
import OrdersSection from "./AdminOrders";
import ReturnsSection from "./AdminReturns";
import { CustomersSection, ProductsSection } from "./AdminCatalog";
import { OffersSection, ReviewsSection, SettingsSection } from "./AdminMore";
import { ReferralsSection } from "./AdminReferrals";
import { SearchesSection } from "./AdminSearches";
import { CategoriesSection } from "./AdminCategories";
import { PaymentsSection } from "./AdminPayments";
import { WalletsSection } from "./AdminWallets";
import { RewardsSection } from "./AdminRewards";
import { AddressesSection } from "./AdminAddresses";
import { NotificationsSection } from "./AdminNotifications";
import { BotAnswersSection } from "./AdminBotAnswers";
import { DeliverySection } from "./AdminDelivery";
import { SupportSection } from "./AdminSupport";
import { StaffSection } from "./AdminStaff";
import HomeSection from "./HomeSection";
import { signOut, useAdminMe } from "./AdminGate";
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
  { key: "product-page", label: "Product pages", icon: "note", group: "Store", live: true },
  { key: "orders", label: "Orders", icon: "box", group: "Sales", live: true },
  { key: "returns", label: "Returns", icon: "truck", group: "Sales", live: true },
  { key: "customers", label: "Customers", icon: "users", group: "Sales", live: true },
  { key: "offers", label: "Offers", icon: "ticket", group: "Sales", live: true },
  { key: "reviews", label: "Reviews", icon: "star", group: "Sales", live: true },
  { key: "referrals", label: "Referrals", icon: "users", group: "Sales", live: true },
  { key: "rewards", label: "Rewards", icon: "gift", group: "Sales", live: true },
  { key: "addresses", label: "Addresses", icon: "pin", group: "Sales", live: true },
  { key: "notifications", label: "Notifications", icon: "bell", group: "Store", live: true },
  { key: "bot-answers", label: "Bot answers", icon: "chat", group: "Store", live: true },
  { key: "delivery", label: "Delivery", icon: "scooter", group: "Store", live: true },
  { key: "support", label: "Support", icon: "chat", group: "Sales", live: true },
  { key: "payments", label: "Payments", icon: "card", group: "Money", live: true },
  { key: "wallets", label: "Wallets", icon: "wallet", group: "Money", live: true },
  { key: "catalog", label: "Catalog", icon: "store", group: "Catalogue", live: true },
  { key: "searches", label: "Searches", icon: "search", group: "Catalogue", live: true },
  { key: "products", label: "Products", icon: "layers", group: "Catalogue", live: true },
  { key: "settings", label: "Settings", icon: "gear", group: "Store", live: true },
  /* Owner only: hidden from everyone else's sidebar, and the section itself
     refuses them (the server does too). */
  { key: "staff", label: "Staff & roles", icon: "users", group: "Store", live: true, owner: true },
];
const TITLES = Object.fromEntries(SECTIONS.map((s) => [s.key, s.label]));
const LIVE = new Set(SECTIONS.filter((s) => s.live).map((s) => s.key));

/* ================================ dashboard ============================== */
/* `i` is the card's place in the strip. `.ad-stat` has staggered its entrance
   off `var(--i)` since the drop, but nothing ever passed one, so all four
   cards landed together on delay 0 and the sweep the CSS describes never
   happened. */
function Stat({ label, value, delta, note, series, color, icon, i = 0 }) {
  const up = delta >= 0;
  return (
    <article className="ad-stat" style={{ "--i": i }}>
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
/* What delivery is doing, on the landing page.

   The Delivery screen is where these are changed; this is where somebody
   notices they need changing. So it carries the three numbers that are wrong
   in a way nobody would otherwise see - a storefront switched off, no slot
   left open in one of them, nowhere being delivered to - and says so plainly
   rather than printing a green tick over them.

   Its own read, not the dashboard's. `/admin/dashboard` is orders and
   customers; widening it to carry pricing would make the whole strip fail
   when one of them does, and this panel is the one that may legitimately
   answer nothing - a shop that has not installed the pricing module still
   has a dashboard. Silent when it cannot read, for the same reason. */
function DeliveryPanel({ go }) {
  const { data } = useResource("/admin/delivery", { pollMs: 60000, keepLast: true });
  if (!data?.rules) return null;

  const rules = data.rules || [];
  const currency = data.currency;
  const slots = (data.slots || []).filter((s) => s.active);
  const areas = (data.areas || []).filter((a) => a.active);
  const quickAreas = areas.filter((a) => a.quick).length;
  const dark = rules.filter((r) => !r.active);
  const modes = data.modes || [];
  /* A storefront with no slot left open cannot be checked out of, and the
     only place that shows is the slot step, one screen from the money. */
  const shut = modes.filter((m) => !slots.some((s) => s.mode === m.key));

  return (
    <section className="ad-card" style={{ "--i": 6 }}>
      <header className="ad-card-head">
        <div>
          <h2>Delivery</h2>
          <p>{areas.length ? `${areas.length} area${areas.length === 1 ? "" : "s"} covered` : "Nowhere covered"}</p>
        </div>
        <button className="ad-btn" onClick={() => go("delivery")}>
          Open delivery<Icon n="right" size={15} />
        </button>
      </header>

      <ul className="ad-rows">
        {rules.map((r, i) => (
          <li key={r.id} className="ad-row-set" style={{ "--i": i }}>
            <span className="ad-row-txt">
              <b>{r.modeLabel}</b>
              <small>
                {r.active
                  ? (r.freeAbove > 0
                    ? `Free above ${money(r.freeAbove, currency)} · ${r.eta}`
                    : `Never free · ${r.eta}`)
                  : "Switched off — this storefront is not delivering"}
              </small>
            </span>
            <span className="ad-strong">{r.fee ? money(r.fee, currency) : "Free"}</span>
          </li>
        ))}
        <li className="ad-row-set" style={{ "--i": rules.length }}>
          <span className="ad-row-txt">
            <b>Slots open</b>
            <small>{shut.length
              ? `Nothing open for ${shut.map((m) => m.label).join(" or ")}`
              : "Across both storefronts"}</small>
          </span>
          <span className="ad-strong">{slots.length}</span>
        </li>
        <li className="ad-row-set" style={{ "--i": rules.length + 1 }}>
          <span className="ad-row-txt">
            <b>Quick delivery reaches</b>
            <small>{quickAreas ? `of ${areas.length} areas` : "no area at all"}</small>
          </span>
          <span className="ad-strong">{quickAreas}</span>
        </li>
      </ul>

      {(dark.length || shut.length || !areas.length) ? (
        <p className="ad-hint ad-hint-pad" role="status">
          <Icon n="info" size={15} />
          <span>
            {!areas.length
              ? "No service area is on, so every pincode is told we do not deliver there yet."
              : dark.length
                ? `${dark.map((r) => r.modeLabel).join(" and ")} is switched off — nothing from it can be bought.`
                : `Nothing is open for ${shut.map((m) => m.label).join(" or ")}, so that storefront has no slot to offer at checkout.`}
            {" "}
            <button className="ad-link" onClick={() => go("delivery")}>Put it right</button>
          </span>
        </p>
      ) : null}
    </section>
  );
}

function Dashboard({ go }) {
  const { data, loading, error, reload } = useResource("/admin/dashboard", { pollMs: 60000, keepLast: true });
  const o = data?.orders;
  const c = data?.customers;

  /* Only when there is nothing to fall back on. A failed poll on a strip that
     already has this morning's numbers keeps them and says so below, rather
     than blanking the screen and then re-animating the lot on the next tick. */
  if (error && !o && !c) {
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
      {error && (o || c) && (
        <p className="ad-hint" role="status">
          <Icon n="info" size={15} />
          <span>Could not reach the shop just now, so these are the last
            numbers we read. <button className="ad-link" onClick={reload}>Try again</button></span>
        </p>
      )}
      {o && (
        <section className="ad-stats">
          <Stat i={0} label="Orders today" value={o.today} note={o.today_value} color={SERIES[0]} icon="box"
            series={(o.placed || []).slice(-7).map((d) => d.count)} />
          <Stat i={1} label="Waiting to be packed" value={o.packing}
            note={o.late ? `${o.late} running late` : "nothing late"} color={SERIES[1]} icon="clock" />
          <Stat i={2} label="Out for delivery" value={o.out} note={`${o.live} live in all`} color={SERIES[3]} icon="truck" />
          <Stat i={3} label="Cash to collect" value={o.cash} note={`across ${o.cash_count} orders`} color={SERIES[2]} icon="cash" />
        </section>
      )}

      <div className="ad-grid-2">
        {o && (
          /* 4 and 5 carry on from the four stat cards above, so the strip and
             the two panels under it read as one sweep rather than two. */
          <section className="ad-card" style={{ "--i": 4 }}>
            <header className="ad-card-head">
              <div><h2>Orders a day</h2><p>The last fortnight</p></div>
              <button className="ad-btn" onClick={() => go("orders")}>Open orders<Icon n="right" size={15} /></button>
            </header>
            <BarChart rows={(o.placed || []).map((d) => ({ label: d.day, full: d.day, value: d.count }))}
              color={SERIES[0]} />
          </section>
        )}

        {c && (
          <section className="ad-card" style={{ "--i": 5 }}>
            <header className="ad-card-head">
              <div><h2>Customers</h2><p>{c.total} with an account</p></div>
            </header>
            <ul className="ad-rows">
              {[
                ["New customers", c.new_week],
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

      <DeliveryPanel go={go} />

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
  const [openId, setOpenId] = useState(null);
  /* What the topbar handed to Orders to search for. Orders owns its own box;
     this only seeds it. Products and Customers the same. */
  const [orderQ, setOrderQ] = useState("");
  const [seedQ, setSeedQ] = useState({ products: "", customers: "" });
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [alerts, setAlerts] = useState(false);
  const [profile, setProfile] = useState(false);
  const [q, setQ] = useState("");
  const [toast, flash] = useToast();
  /* Who is signed in, from the gate (AdminGate.jsx). The gate only renders the
     console for staff, so this is never empty in practice; the fallback is
     for a console mounted outside it. */
  const me = useAdminMe();
  const who = { name: me?.name || "Staff", email: me?.email || "" };
  const isOwner = me?.role === "owner";
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

  /* The sidebar badge is a real number now, so the shell asks for it rather
     than counting a list it no longer holds. Slower than the section's own
     poll on purpose: this one is only a badge. */
  const orderCounts = useResource("/admin/orders/counts", { pollMs: 60000 });
  /* Same again, and its own route for the same reason Orders has one: a badge
     wants three numbers, not every review in the shop once a minute. */
  const reviewCounts = useResource("/admin/reviews/counts", { pollMs: 60000 });
  const supportCounts = useResource("/admin/support/counts", { pollMs: 60000 });
  /* Settings › Alerts decides whether these two speak at all. Late orders
     always do: a promise already broken is not something to switch off. */
  const alertSettings = useResource("/admin/settings", { pollMs: 60000, keepLast: true });
  const alertsOn = alertSettings.data?.settings?.alerts || { newOrder: true, lowStock: true };
  const waiting = alertsOn.newOrder ? orderCounts.data?.counts?.needs || 0 : 0;
  const lateCount = orderCounts.data?.counts?.late || 0;
  /* Low stock is worked out over the whole shop on the server; one row is
     asked for only because the tiles come with any page. Every five minutes:
     stock does not move by the second, and this is only a badge. */
  const productCounts = useResource("/admin/products?limit=1", { pollMs: 300000, enabled: alertsOn.lowStock !== false });
  const lowCount = alertsOn.lowStock ? productCounts.data?.tiles?.low || 0 : 0;
  const pendingReviews = reviewCounts.data?.counts?.pending || 0;
  /* Tickets nobody has replied to - not every open one. A ticket already
     answered and waiting on the customer is not somebody sitting unheard. */
  const unanswered = supportCounts.data?.counts?.needs || 0;
  const lateTickets = supportCounts.data?.late || 0;
  const counts = { orders: waiting, reviews: pendingReviews, products: lowCount, support: unanswered };
  /* One line per thing to do, not one per order. The shell has no order list
     to name rows out of, and "2 late" is the part a manager acts on anyway. */
  const notes = useMemo(() => [
    ...(lateCount ? [{ id: "nlate", icon: "clock", text: `${lateCount} order${lateCount === 1 ? "" : "s"} past the time they were promised`, at: null, go: ["orders"] }] : []),
    ...(waiting ? [{ id: "nord", icon: "box", text: `${waiting} order${waiting === 1 ? "" : "s"} still on their way`, at: null, go: ["orders"] }] : []),
    ...(lowCount ? [{ id: "nlow", icon: "layers", text: `${lowCount} product${lowCount === 1 ? "" : "s"} running low`, at: null, go: ["products"] }] : []),
    ...(pendingReviews ? [{ id: "nrev", icon: "star", text: `${pendingReviews} review${pendingReviews === 1 ? "" : "s"} nobody has looked at yet`, at: null, go: ["reviews"] }] : []),
    ...(lateTickets ? [{ id: "nsup", icon: "chat", text: `${lateTickets} customer${lateTickets === 1 ? "" : "s"} waiting over half an hour for a reply`, at: null, go: ["support"] }] : []),
  ], [waiting, lateCount, lowCount, pendingReviews, lateTickets]); // eslint-disable-line

  /* Orders, products and customers are all searched in the shop, not here -
     so this hands the term over rather than pretending to have matched
     anything. */
  const results = q.trim().length > 1;
  const seed = (k) => { setSeedQ((s) => ({ ...s, [k]: q.trim() })); setQ(""); go(k); };

  let body;
  if (section === "dashboard") body = <Dashboard go={go} />;
  else if (section === "home") body = <HomeSection flash={flash} />;
  else if (section === "product-page") body = <ProductPageSection flash={flash} />;
  else if (section === "orders") body = <OrdersSection openId={openId} setOpenId={setOpenId} query={orderQ} flash={flash} />;
  else if (section === "returns") body = <ReturnsSection flash={flash} />;
  else if (section === "products") body = <ProductsSection key={"p" + seedQ.products} initialQ={seedQ.products} flash={flash} go={go} />;
  else if (section === "customers") body = <CustomersSection key={"c" + seedQ.customers} initialQ={seedQ.customers}
    onOpenTicket={(ref) => { setOpenId(ref); go("support"); }} />;
  else if (section === "offers") body = <OffersSection flash={flash} />;
  else if (section === "reviews") body = <ReviewsSection flash={flash} />;
  else if (section === "referrals") body = <ReferralsSection flash={flash} />;
  else if (section === "searches") body = <SearchesSection flash={flash} />;
  else if (section === "catalog") body = <CategoriesSection flash={flash} />;
  else if (section === "payments") body = <PaymentsSection />;
  else if (section === "wallets") body = <WalletsSection />;
  else if (section === "rewards") body = <RewardsSection flash={flash} />;
  else if (section === "addresses") body = <AddressesSection flash={flash} />;
  else if (section === "notifications") body = <NotificationsSection flash={flash} />;
  else if (section === "bot-answers") body = <BotAnswersSection flash={flash} />;
  else if (section === "delivery") body = <DeliverySection flash={flash} />;
  else if (section === "support") body = <SupportSection openRef={openId} setOpenRef={setOpenId} flash={flash} />;
  else if (section === "staff") body = isOwner
    ? <StaffSection flash={flash} />
    : <Empty icon="users" title="Only the Owner can manage staff" text="Ask the shop's Owner to change your role." />;
  else body = <SettingsSection flash={flash} />;

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
              {SECTIONS.filter((s) => s.group === g && (!s.owner || isOwner)).map((s) => (
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
          <Avatar name={who.name} tone="ad-a-navy" size={36} />
          <span className="ad-brand-txt"><b>{who.name}</b><small>{who.email || "Staff"}</small></span>
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
                <button onClick={() => { setOrderQ(q); setQ(""); go("orders"); }}><Icon n="box" size={15} /><b>Search orders for “{q}”</b><small>Order number, customer or phone</small></button>
                <button onClick={() => seed("products")}><Icon n="layers" size={15} /><b>Search products for “{q}”</b><small>Name or code</small></button>
                <button onClick={() => seed("customers")}><Icon n="users" size={15} /><b>Search customers for “{q}”</b><small>Name, email, phone or area</small></button>
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
                    <span><b>{n.text}</b><small>{n.at ? since(n.at) : "now"}</small></span>
                  </button>
                ))}
                {!notes.length && <p className="ad-no-res">Nothing needs attention.</p>}
              </div>
            )}
          </div>
          <div className="ad-pop-wrap">
            <button className="ad-profile" onClick={() => { setProfile((v) => !v); setAlerts(false); }} aria-label="Account">
              <Avatar name={who.name} tone="ad-a-navy" size={34} /><Icon n="chev" size={15} />
            </button>
            {profile && (
              <div className="ad-pop ad-pop-sm">
                <button onClick={() => { setProfile(false); go("settings"); }}><span className="ad-pop-ic"><Icon n="gear" size={16} /></span><span><b>Store settings</b></span></button>
                <button onClick={() => { setProfile(false); onExit?.(); }}><span className="ad-pop-ic"><Icon n="store" size={16} /></span><span><b>Open storefront</b></span></button>
                <button onClick={() => { setProfile(false); signOut(); }}><span className="ad-pop-ic"><Icon n="logout" size={16} /></span><span><b>Sign out</b></span></button>
              </div>
            )}
          </div>
        </header>

        {/* `data-sec` lets a section tune its own entrance from the stylesheet
            without every section file having to grow a class prop. The two
            drag-and-drop editors use it to opt out of a translating entrance -
            see the note by `.ad-body[data-sec]` in admin.css. */}
        <main className="ad-body" key={section} data-sec={section}>
          {!LIVE.has(section) && <SampleBanner label={TITLES[section]} />}
          {body}
        </main>
      </div>

      <div className="ad-nav-back" onClick={() => setMobileNav(false)} />
      {toast}
    </div>
  );
}
