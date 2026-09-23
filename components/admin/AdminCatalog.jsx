"use client";
/* ==========================================================================
   369 Mart admin — Products (inventory) · Customers · Riders
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { money } from "@/lib/money";
import { useResource } from "@/lib/useFetch";
import { Avatar, Drawer, Empty, Icon, Search, Select, Tabs } from "./AdminUI";
import { RIDERS, clock, groupIN, isToday } from "./adminData";
import { dateShort, since } from "./format";

/* ============================== products ===============================
   Reads the shop. The tabs, category, storefront and sort all go to the
   server - "lowest stock first" means nothing if it only sorts the page you
   were sent.

   **Read-only, deliberately.** A stock count typed over here would disagree
   with Inventory the moment anything was sold; a real change is an inventory
   adjustment, and price and publishing belong to the product master. So the
   numbers are shown as numbers, not as inputs that do nothing. */
const Thumb = ({ src }) => (
  <span className="ad-thumb">{src ? <img src={src} alt="" loading="lazy" /> : <Icon n="layers" size={18} />}</span>
);
const STOCK = { out: ["Out of stock", "red"], low: ["Low", "orange"] };
const SORT_LABEL = [["low", "Lowest stock"], ["sold", "Best selling"], ["price", "Highest price"], ["name", "Name A–Z"]];

export function ProductsSection({ initialQ = "" }) {
  const [tab, setTab] = useState("all");
  const [term, setTerm] = useState(initialQ);
  const [q, setQ] = useState(initialQ);
  const [categ, setCateg] = useState("");
  const [mode, setMode] = useState("");
  const [sort, setSort] = useState("low");
  const [limit, setLimit] = useState(50);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);
  useEffect(() => setLimit(50), [tab, q, categ, mode, sort]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("tab", tab);
    if (q) p.set("q", q);
    if (categ) p.set("categ", categ);
    if (mode) p.set("mode", mode);
    p.set("sort", sort);
    p.set("limit", String(limit));
    return "/admin/products?" + p.toString();
  }, [tab, q, categ, mode, sort, limit]);

  const { data, loading, error, reload } = useResource(path, { keepLast: true });
  const rows = data?.rows || [];
  const tiles = data?.tiles || {};
  const counts = data?.counts || {};
  const currency = data?.currency;
  const categName = (data?.categories || []).find((c) => String(c.id) === categ)?.name;
  const why = [q && `"${q}"`, categName && `in ${categName}`, mode && (mode === "all" ? "on Express" : "on Quick")].filter(Boolean).join(", ");
  const TAB_EMPTY = { low: "Nothing is running low.", out: "Nothing is out of stock.", off: "Every product is live in the app." };

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Products</small><b>{tiles.count ?? 0}</b></span>
        <span><small>Stock value</small><b>{money(tiles.value ?? 0, currency)}</b></span>
        <span className="ad-warn"><small>Low stock</small><b>{tiles.low ?? 0}</b></span>
        <span className="ad-bad"><small>Out of stock</small><b>{tiles.out ?? 0}</b></span>
      </section>

      <p className="ad-hint ad-readonly">
        <Icon n="info" size={14} />
        <span>
          Nothing here can be changed. Stock moves through an inventory adjustment, and
          price and publishing are set on the product in Odoo — so this list always
          agrees with what the app is selling.
          {data && tiles.stock === false && " Inventory is not installed, so stock is not tracked."}
        </span>
      </p>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["all", "All", counts.all ?? 0], ["low", "Low", counts.low ?? 0], ["out", "Out of stock", counts.out ?? 0], ["off", "Hidden", counts.off ?? 0]]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Name or code" />
            <Select value={categ} onChange={setCateg} label="Category" options={[["", "All categories"], ...(data?.categories || []).map((c) => [String(c.id), c.name])]} />
            <Select value={mode} onChange={setMode} label="Storefront" options={[["", "Both storefronts"], ["quick", "Quick"], ["all", "Express"]]} />
            <Select value={sort} onChange={setSort} label="Sort" options={SORT_LABEL} />
          </div>
        </div>
        {why && data && <p className="ad-hint"><Icon n="info" size={14} />Showing {rows.length} of {data.total} that match — the tiles count the whole shop.</p>}

        <div className="ad-table-wrap">
          {error && !rows.length && <Empty icon="info" title="We could not reach the shop" text={error.message} action="Try again" onAction={reload} />}
          {loading && !rows.length && !error && <Empty icon="layers" title="Loading…" text="Fetching products." />}
          {!!rows.length && (
            <table className="ad-table">
              <thead><tr><th>Product</th><th>Category</th><th>Delivery</th><th className="ad-num">Price</th><th className="ad-num">Sold / 7d</th><th className="ad-num">In stock</th><th>Live</th><th /></tr></thead>
              <tbody>
                {rows.map((s, i) => (
                  <tr key={s.id} style={{ "--i": i % 12 }} className={s.state === "out" ? "ad-row-bad" : s.state === "low" ? "ad-row-warn" : ""}
                    onClick={(e) => { if (!e.target.closest("button")) setOpen(s); }}>
                    <td><span className="ad-cell-person"><Thumb src={s.image} /><span><b>{s.name}</b><small>{[s.unit, s.code].filter(Boolean).join(" · ")}</small></span></span></td>
                    <td><small>{s.cat || "—"}</small></td>
                    <td><span className={"ad-tag " + (s.delivery ? "ad-tag-e" : "ad-tag-q")}>{s.delivery ? "Express" : "Quick"}</span></td>
                    <td className="ad-num">{money(s.price, currency)}</td>
                    <td className="ad-num">{s.sold7}</td>
                    <td className="ad-num ad-strong">{s.qty ?? "—"}</td>
                    <td>{s.active ? <span className="ad-pill ad-t-green"><i />Live</span> : <span className="ad-pill ad-t-grey"><i />Hidden</span>}</td>
                    <td className="ad-row-act"><button className="ad-icon-btn" onClick={() => setOpen(s)} aria-label={`Details for ${s.name}`}><Icon n="right" size={16} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!error && !loading && !rows.length && (
            <Empty icon="layers" title="No products match"
              text={why ? `Nothing${tab !== "all" ? ` in "${tab}"` : ""} matches ${why}. Clear a filter to see more.` : TAB_EMPTY[tab] || "There are no products for sale yet."} />
          )}
          {data && rows.length > 0 && rows.length < data.total && (
            <div className="ad-more"><button className="ad-btn" onClick={() => setLimit((n) => n + 50)}>Show more ({data.total - rows.length} left)</button></div>
          )}
        </div>
      </section>

      {open && (
        <Drawer title={open.name} sub={[open.unit, open.cat].filter(Boolean).join(" · ")} onClose={() => setOpen(null)}
          foot={(close) => <button className="ad-btn ad-primary" onClick={close}>Close</button>}>
          <div className="ad-prod-hero"><Thumb src={open.image} /><div><b>{money(open.price, currency)}</b>{open.mrp > open.price && <s>{money(open.mrp, currency)}</s>}<small>{open.sold7} sold in the last 7 days</small></div></div>
          <div className="ad-kv">
            <span><small>In stock</small>{open.qty ?? "—"}{STOCK[open.state] ? ` · ${STOCK[open.state][0]}` : ""}</span>
            <span><small>Warn at</small>{open.reorder || "Off"}</span>
            <span><small>Delivery</small>{open.delivery ? `Express${open.deliveryText ? ` · ${open.deliveryText}` : ""}` : "Quick"}</span>
            <span><small>Status</small>{open.active ? "Live in app" : "Hidden"}</span>
          </div>
          <p className="ad-hint"><Icon n="info" size={14} />"Warn at" is the stock level where the app starts saying "Only N left". Change it, the price or the stock on the product in Odoo.</p>
        </Drawer>
      )}
    </div>
  );
}

/* ============================== customers ==============================
   Reads the shop. Every filter is sent to the server - filtering the page you
   were handed is not filtering the shop. The tiles and tab counts are the whole
   shop; "showing N of M" is the filter. Read-only: nothing here changes an
   account. */
const STATUS = { active: ["Active", "green"], new: ["New", "blue"], dormant: ["Dormant", "grey"], archived: ["Archived", "grey"] };
const JOINED_LABEL = { month: "joined this month", "3m": "joined in the last 3 months", year: "joined this year" };

export function CustomersSection({ initialQ = "" }) {
  const [term, setTerm] = useState(initialQ);
  const [q, setQ] = useState(initialQ);
  const [tab, setTab] = useState("all");
  const [area, setArea] = useState("");
  const [joined, setJoined] = useState("");
  const [wallet, setWallet] = useState("");
  const [limit, setLimit] = useState(50);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);
  useEffect(() => setLimit(50), [tab, q, area, joined, wallet]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("tab", tab);
    if (q) p.set("q", q);
    if (area) p.set("area", area);
    if (joined) p.set("joined", joined);
    if (wallet) p.set("wallet", "1");
    p.set("limit", String(limit));
    return "/admin/customers?" + p.toString();
  }, [tab, q, area, joined, wallet, limit]);

  const { data, loading, error, reload } = useResource(path, { keepLast: true });
  const rows = data?.rows || [];
  const counts = data?.counts || {};
  const currency = data?.currency;
  const why = [q && `"${q}"`, area && `in ${area}`, joined && JOINED_LABEL[joined], wallet && "with a wallet balance"].filter(Boolean).join(", ");

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Customers</small><b>{counts.all ?? 0}</b></span>
        <span><small>Active</small><b>{counts.active ?? 0}</b></span>
        <span><small>New this week</small><b>{counts.new ?? 0}</b></span>
        <span className="ad-warn"><small>Dormant</small><b>{counts.dormant ?? 0}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["all", "All", counts.all ?? 0], ["active", "Active", counts.active ?? 0], ["new", "New", counts.new ?? 0], ["dormant", "Dormant", counts.dormant ?? 0]]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Name, email, phone or area" />
            <Select value={area} onChange={setArea} label="Area" options={[["", "All areas"], ...(data?.areas || []).map((a) => [a, a])]} />
            <Select value={joined} onChange={setJoined} label="Joined" options={[["", "Any time"], ["month", "This month"], ["3m", "Last 3 months"], ["year", "This year"]]} />
            <Select value={wallet} onChange={setWallet} label="Wallet" options={[["", "Any wallet"], ["1", "Has a balance"]]} />
          </div>
        </div>
        {why && data && <p className="ad-hint"><Icon n="info" size={14} />Showing {rows.length} of {data.total} that match — the tiles count the whole shop.</p>}
        <div className="ad-table-wrap">
          {error && !rows.length && <Empty icon="info" title="We could not reach the shop" text={error.message} action="Try again" onAction={reload} />}
          {loading && !rows.length && !error && <Empty icon="users" title="Loading…" text="Fetching customers." />}
          {!!rows.length && (
            <table className="ad-table">
              <thead><tr><th>Customer</th><th>Contact</th><th>Area</th><th className="ad-num">Orders</th><th className="ad-num">Spent</th><th className="ad-num">Wallet</th><th>Last order</th><th>Status</th><th /></tr></thead>
              <tbody>
                {rows.map((c, i) => {
                  const [label, tone] = STATUS[c.status] || STATUS.active;
                  return (
                    <tr key={c.id} style={{ "--i": i % 12 }} onClick={(e) => { if (!e.target.closest("button")) setOpen(c); }}>
                      <td><span className="ad-cell-person"><Avatar name={c.name} size={32} tone="ad-a-blue" /><span><b>{c.name}</b><small>{c.joined ? `Joined ${dateShort(c.joined)}` : ""}</small></span></span></td>
                      <td><small>{c.email}<br />{c.phone}</small></td>
                      <td><small>{c.area || "—"}</small></td>
                      <td className="ad-num">{c.orders}</td>
                      <td className="ad-num ad-strong">{money(c.spent, currency)}</td>
                      <td className="ad-num">{money(c.wallet, currency)}</td>
                      <td><small>{c.last ? since(c.last) : "Never"}</small></td>
                      <td><span className={"ad-pill ad-t-" + tone}><i />{label}</span></td>
                      <td className="ad-row-act"><button className="ad-icon-btn" onClick={() => setOpen(c)} aria-label={`Open ${c.name}`}><Icon n="right" size={16} /></button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {!error && !loading && !rows.length && (
            <Empty icon="users" title="No customers match"
              text={why ? `Nobody${tab !== "all" ? ` ${tab}` : ""} matches ${why}. Clear a filter to see more.` : tab !== "all" ? `No ${tab} customers right now.` : "Nobody has signed up yet."} />
          )}
          {data && rows.length > 0 && rows.length < data.total && (
            <div className="ad-more"><button className="ad-btn" onClick={() => setLimit((n) => n + 50)}>Show more ({data.total - rows.length} left)</button></div>
          )}
        </div>
      </section>

      {open && <CustomerDrawer row={open} currency={currency} onClose={() => setOpen(null)} />}
    </div>
  );
}

/* One customer. Their orders are joined by account on the server - the
   sample joined them by name, and two customers can share one. */
function CustomerDrawer({ row, currency, onClose }) {
  const { data, error } = useResource(`/admin/customers/${row.id}`);
  const c = data?.customer || row;
  const recent = data?.customer?.recent;
  const [label] = STATUS[c.status] || STATUS.active;
  return (
    <Drawer title={c.name} sub={[c.area, label].filter(Boolean).join(" · ")} onClose={onClose}
      foot={(close) => <button className="ad-btn ad-primary" onClick={close}>Close</button>}>
      <div className="ad-person ad-person-lg"><Avatar name={c.name} size={52} tone="ad-a-blue" /><span><b>{c.name}</b><small>{c.email}<br />{c.phone}</small></span></div>
      <div className="ad-mini-stats ad-inline-stats">
        <span><small>Orders</small><b>{c.orders}</b></span>
        <span><small>Spent</small><b>{money(c.spent, currency)}</b></span>
        <span><small>Wallet</small><b>{money(c.wallet, currency)}</b></span>
        <span><small>Last order</small><b>{c.last ? since(c.last) : "Never"}</b></span>
      </div>
      <section className="ad-dsec">
        <h4>Recent orders</h4>
        <ul className="ad-items">
          {(recent || []).map((o) => (
            <li key={o.ref}><span className="ad-qty-chip">{o.items}</span><span><b>#{o.ref}</b><small>{o.at ? dateShort(o.at) : ""}{o.method ? ` · ${o.method}` : ""}</small></span><b>{money(o.total, currency)}</b></li>
          ))}
          {recent && !recent.length && <li className="ad-dim">No orders yet.</li>}
          {!recent && !error && <li className="ad-dim">Loading…</li>}
          {error && <li className="ad-dim">{error.message}</li>}
        </ul>
      </section>
    </Drawer>
  );
}

/* ================================ riders =============================== */
export function RidersSection({ orders, assign, flash }) {
  const live = orders.filter((o) => o.status === "out");
  const ready = orders.filter((o) => o.status === "ready");
  const load = (id) => live.filter((o) => o.rider?.id === id);
  const doneToday = (id) => orders.filter((o) => o.rider?.id === id && o.status === "delivered" && isToday(o.at)).length;

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Riders on shift</small><b>{RIDERS.length}</b></span>
        <span><small>On delivery</small><b>{live.length}</b></span>
        <span className="ad-warn"><small>Waiting for a rider</small><b>{ready.length}</b></span>
        <span><small>Delivered today</small><b>{orders.filter((o) => o.status === "delivered" && isToday(o.at)).length}</b></span>
      </section>

      <div className="ad-riders">
        {RIDERS.map((r, i) => {
          const busy = load(r.id);
          return (
            <article key={r.id} className={"ad-card ad-rider" + (busy.length ? " ad-busy" : "")} style={{ "--i": i }}>
              <header>
                <Avatar name={r.name} size={46} tone={busy.length ? "ad-a-orange" : "ad-a-green"} />
                <span><b>{r.name}</b><small>{r.vehicle}</small></span>
                <span className={"ad-pill " + (busy.length ? "ad-t-orange" : "ad-t-green")}><i />{busy.length ? "On delivery" : "Idle"}</span>
              </header>
              <div className="ad-kv">
                <span><small>Shift</small>{r.shift}</span>
                <span><small>Rating</small>{r.rating} ★</span>
                <span><small>Delivered today</small>{doneToday(r.id)}</span>
                <span><small>Lifetime trips</small>{groupIN(r.trips)}</span>
              </div>
              {busy.length > 0 ? (
                <ul className="ad-items ad-rider-jobs">
                  {busy.map((o) => <li key={o.id}><span className="ad-qty-chip">{o.items.length}</span><span><b>#{o.id}</b><small>{o.customer.area} · {clock(o.at)}</small></span><b>{o.eta} min</b></li>)}
                </ul>
              ) : ready.length ? (
                <div className="ad-rider-assign">
                  <p>{ready.length} order{ready.length > 1 ? "s" : ""} packed and waiting.</p>
                  <button className="ad-btn ad-primary ad-sm" onClick={() => { assign(ready[0].id, r.id); flash(`#${ready[0].id} assigned to ${r.name}`); }}>Assign #{ready[0].id}</button>
                </div>
              ) : <p className="ad-dim ad-rider-idle">Nothing waiting — free for the next order.</p>}
              <footer>
                <button className="ad-btn ad-sm" onClick={() => flash(`Calling ${r.name}`)}><Icon n="phone" size={15} />Call</button>
                <button className="ad-btn ad-sm" onClick={() => flash(`Message sent to ${r.name}`)}><Icon n="chat" size={15} />Message</button>
              </footer>
            </article>
          );
        })}
      </div>
    </div>
  );
}
