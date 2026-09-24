"use client";
/* ==========================================================================
   369 Mart admin — Products (inventory) · Customers · Riders
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { money } from "@/lib/money";
import { useResource } from "@/lib/useFetch";
import { Avatar, Drawer, Empty, Icon, Search, Select, Tabs } from "./AdminUI";
import ProductEditor, { PhotoViewer } from "./ProductEditor";
import { RIDERS, clock, groupIN, isToday } from "./adminData";
import { dateShort, since } from "./format";

/* ============================== products ===============================
   The shop's products, and the same editor as Odoo's Products desk.

   The list reads the shop: the tabs, category and sort all go to
   the server - "lowest stock first" means nothing if it only sorts the page
   you were sent. The tiles count the whole shop, never the filter.

   **What can be changed here is what the desk can change.** New product and
   Edit write through `mart369_desk_save`, whose allowlist is the product's
   own details, wording and photographs. Stock is still never typed over: a
   stock change is an inventory adjustment, and a number typed here would
   disagree with Inventory the moment anything was sold. */
const Thumb = ({ src }) => (
  <span className="ad-thumb">{src ? <img src={src} alt="" loading="lazy" /> : <Icon n="layers" size={18} />}</span>
);
const STOCK = { out: ["Out of stock", "red"], low: ["Low", "orange"] };
const SORT_LABEL = [["low", "Lowest stock"], ["sold", "Best selling"], ["price", "Highest price"], ["name", "Name A–Z"]];
const VIEW_KEY = "369mart.admin.products.view";
const SOURCE = { product: "this product", category: "its category", odoo: "the product record", default: "the shop" };

export function ProductsSection({ initialQ = "", flash, go }) {
  const [tab, setTab] = useState("all");
  const [term, setTerm] = useState(initialQ);
  const [q, setQ] = useState(initialQ);
  const [categ, setCateg] = useState("");
  const [sort, setSort] = useState("low");
  const [limit, setLimit] = useState(50);
  const [view, setViewState] = useState("list");
  /* One of: null (the list), {detail: id, row}, {edit: id|null, back}. */
  const [screen, setScreen] = useState(null);

  useEffect(() => {
    try { const v = localStorage.getItem(VIEW_KEY); if (v === "cards" || v === "list") setViewState(v); } catch (e) { /* private window */ }
  }, []);
  const setView = (v) => { setViewState(v); try { localStorage.setItem(VIEW_KEY, v); } catch (e) { /* ignore */ } };

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);
  useEffect(() => setLimit(50), [tab, q, categ, sort]);
  useEffect(() => { window.scrollTo({ top: 0 }); }, [screen]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("tab", tab);
    if (q) p.set("q", q);
    if (categ) p.set("categ", categ);
    p.set("sort", sort);
    p.set("limit", String(limit));
    return "/admin/products?" + p.toString();
  }, [tab, q, categ, sort, limit]);

  /* Paused while the editor or a product is open, and re-read on the way
     back, so a save shows in the list at once. */
  const [nonce, setNonce] = useState(0);
  const { data, loading, error, reload } = useResource(path, { keepLast: true, enabled: !screen, deps: [nonce] });
  const rows = data?.rows || [];
  const tiles = data?.tiles || {};
  const counts = data?.counts || {};
  const currency = data?.currency;
  const categories = data?.categories || [];
  const categName = categories.find((c) => String(c.id) === categ)?.name;
  const why = [q && `"${q}"`, categName && `in ${categName}`].filter(Boolean).join(", ");
  const TAB_EMPTY = { low: "Nothing is running low.", out: "Nothing is out of stock.", off: "Every product is live in the app." };
  const anyFilter = !!(q || categ || tab !== "all");
  const clearAll = () => { setTerm(""); setQ(""); setCateg(""); setTab("all"); };
  const toList = () => { setScreen(null); setNonce((n) => n + 1); };

  if (screen && "edit" in screen) {
    return (
      <ProductEditor key={String(screen.edit)} productId={screen.edit} currency={currency} flash={flash}
        onClose={() => (screen.back ? setScreen(screen.back) : toList())}
        onSaved={(id) => setScreen({ detail: id, row: null })} />
    );
  }
  if (screen && "detail" in screen) {
    return (
      <ProductDetail key={screen.detail} id={screen.detail} row={screen.row} currency={currency} onBack={toList} go={go}
        onEdit={() => setScreen({ edit: screen.detail, back: screen })} />
    );
  }

  const openRow = (s) => setScreen({ detail: s.id, row: s });
  const stockTile = (key, label, cls, value) => (
    <button type="button" className={"pdk-tile " + cls + (tab === key ? " pdk-on" : "")} aria-pressed={tab === key}
      title={tab === key ? "Show every product" : `Show only ${label.toLowerCase()}`}
      onClick={() => setTab(tab === key ? "all" : key)}><small>{label}</small><b>{value}</b></button>
  );

  return (
    <div className="ad-stack">
      <div className="pdk-listhead">
        <div>
          <h2>Products</h2>
          <p>Every product in the shop. Open one to see what its page shows, or change its details and photographs.</p>
        </div>
        <button className="ad-btn ad-primary" onClick={() => setScreen({ edit: null })}><Icon n="plus" size={16} />New product</button>
      </div>

      <section className="ad-mini-stats pdk-tiles">
        <span><small>Products</small><b>{tiles.count ?? 0}</b></span>
        <span><small>Stock value</small><b>{money(tiles.value ?? 0, currency)}</b></span>
        {stockTile("low", "Low stock", "ad-warn", tiles.low ?? 0)}
        {stockTile("out", "Out of stock", "ad-bad", tiles.out ?? 0)}
      </section>
      {data && tiles.stock === false && <p className="ad-hint"><Icon n="info" size={14} />Inventory is not installed, so stock is not tracked.</p>}

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["all", "All", counts.all ?? 0], ["low", "Low", counts.low ?? 0], ["out", "Out of stock", counts.out ?? 0], ["off", "Hidden", counts.off ?? 0]]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Name or code" />
            <Select value={sort} onChange={setSort} label="Sort" options={SORT_LABEL} />
            <div className="pdk-views" role="group" aria-label="View">
              <button type="button" className={view === "cards" ? "pdk-on" : ""} aria-pressed={view === "cards"} title="Cards" aria-label="Cards" onClick={() => setView("cards")}><Icon n="dash" size={16} /></button>
              <button type="button" className={view === "list" ? "pdk-on" : ""} aria-pressed={view === "list"} title="List" aria-label="List" onClick={() => setView("list")}><Icon n="menu" size={16} /></button>
            </div>
          </div>
        </div>
        {categories.length > 0 && (
          <div className="pdk-chips" role="group" aria-label="Category">
            <button type="button" className={"pdk-chip" + (!categ ? " pdk-on" : "")} aria-pressed={!categ} onClick={() => setCateg("")}>All categories</button>
            {categories.map((c) => (
              <button key={c.id} type="button" className={"pdk-chip" + (categ === String(c.id) ? " pdk-on" : "")} aria-pressed={categ === String(c.id)}
                onClick={() => setCateg(categ === String(c.id) ? "" : String(c.id))}>{c.name}</button>
            ))}
          </div>
        )}
        {why && data && !loading && (
          <p className="ad-hint pdk-why"><Icon n="info" size={14} />
            <span>Showing {rows.length} of {data.total} that match {why}. The tiles count the whole shop.</span>
            <button type="button" className="pdk-clear" onClick={clearAll}><Icon n="x" size={13} />Clear all filters<b>{[q, categ, tab !== "all"].filter(Boolean).length}</b></button>
          </p>
        )}

        <div className="ad-table-wrap">
          {error && !rows.length && <Empty icon="info" title="We could not reach the shop" text={error.message} action="Try again" onAction={reload} />}
          {loading && !rows.length && !error && <Empty icon="layers" title="Loading…" text="Fetching products." />}
          {!!rows.length && view === "list" && (
            <table className="ad-table pdk-table">
              <thead><tr><th>Product</th><th>Category</th><th className="ad-num">Price</th><th className="ad-num">Sold / 7d</th><th className="ad-num">In stock</th><th>Live</th><th /></tr></thead>
              <tbody>
                {rows.map((s, i) => (
                  <tr key={s.id} style={{ "--i": i % 12 }} className={s.state === "out" ? "ad-row-bad" : s.state === "low" ? "ad-row-warn" : ""}
                    onClick={(e) => { if (!e.target.closest("button")) openRow(s); }}>
                    <td><span className="ad-cell-person"><Thumb src={s.image} /><span><b>{s.name}</b><small>{[s.unit, s.code].filter(Boolean).join(" · ")}</small></span></span></td>
                    <td><small>{s.cat || "—"}</small></td>
                    <td className="ad-num">{money(s.price, currency)}</td>
                    <td className="ad-num">{s.sold7}</td>
                    <td className="ad-num ad-strong">{s.qty ?? "—"}</td>
                    <td>{s.active ? <span className="ad-pill ad-t-green"><i />Live</span> : <span className="ad-pill ad-t-grey"><i />Hidden</span>}</td>
                    <td className="ad-row-act pdk-row-act">
                      <button className="ad-icon-btn" onClick={() => setScreen({ edit: s.id })} aria-label={`Edit ${s.name}`} title="Edit"><Icon n="edit" size={15} /></button>
                      <button className="ad-icon-btn" onClick={() => openRow(s)} aria-label={`Details for ${s.name}`}><Icon n="right" size={16} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!!rows.length && view === "cards" && (
            <div className="pdk-cards">
              {rows.map((s, i) => (
                <button key={s.id} type="button" className={"pdk-card" + (s.state ? " pd-" + s.state : "")} style={{ "--i": i % 12 }} onClick={() => openRow(s)}>
                  <span className="pdk-card-img">
                    {s.image ? <img src={s.image} alt="" loading="lazy" /> : <Icon n="layers" size={26} />}
                    {!s.active && <em className="pdk-card-flag">Hidden</em>}
                  </span>
                  <span className="pdk-card-body">
                    <b>{s.name}</b>
                    <small>{[s.unit, s.cat].filter(Boolean).join(" · ") || " "}</small>
                    <span className="pdk-card-foot">
                      <strong>{money(s.price, currency)}</strong>
                      {s.qty != null && <span className={"ad-pill ad-t-" + (STOCK[s.state]?.[1] || "grey")}><i />{s.state === "out" ? "Out" : `${s.qty} left`}</span>}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
          {!error && !loading && !rows.length && (
            <Empty icon="layers" title="No products match"
              text={why ? `Nothing${tab !== "all" ? ` in "${tab}"` : ""} matches ${why}. Clear a filter to see more.` : TAB_EMPTY[tab] || "There are no products for sale yet."}
              action={anyFilter ? "Clear filters" : "New product"} onAction={anyFilter ? clearAll : () => setScreen({ edit: null })} />
          )}
          {data && rows.length > 0 && rows.length < data.total && (
            <div className="ad-more"><button className="ad-btn" onClick={() => setLimit((n) => n + 50)}>Show more ({data.total - rows.length} left)</button></div>
          )}
        </div>
      </section>
    </div>
  );
}

/* One product: its photographs, Odoo's own figures, and what its page shows
   - each line with the layer it came from, so an inherited value does not
   read like one set on this product. */
function ProductDetail({ id, row, currency: listCurrency, onBack, onEdit, go }) {
  const { data, error, loading, reload } = useResource(`/admin/products/${id}`);
  const [viewing, setViewing] = useState(null);
  useEffect(() => { reload(); }, []); // eslint-disable-line -- always fresh on open
  const p = data?.product;
  const stats = data?.stats || {};
  const cur = stats.currency || listCurrency;
  const name = p?.name || row?.name || "Product";
  const photos = p ? [p.photo && { kind: "main", url: p.photo }, ...(p.photos || []).map((ph) => ({ kind: "saved", url: ph.url }))].filter(Boolean) : [];
  const num = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString());
  const statTiles = Object.keys(stats).length ? [
    ["On hand", num(stats.onHand)],
    ["Forecast", num(stats.forecast)],
    [`Sold, ${stats.soldDays || 30} days`, num(stats.sold)],
    ["Price", money(stats.price || 0, cur)],
    ["Cost", stats.cost ? money(stats.cost, cur) : "—"],
    ["Margin", stats.margin == null ? "—" : `${stats.margin} %`, stats.margin != null && stats.margin < 0],
  ] : [];
  const valueOf = (f) => {
    if (f.kind === "bool") return f.value === "1" ? "Yes" : f.value === "0" ? "No" : "Not set";
    if ((f.key === "price" || f.key === "mrp") && f.value && !isNaN(Number(f.value))) return Number(f.value) ? money(Number(f.value), cur) : "Nothing set";
    return f.value === "" || f.value == null ? "Nothing set" : String(f.value);
  };
  const shown = (data?.sections || []).reduce((n, s) => n + (s.show ? s.shown : 0), 0);

  return (
    <div className="ad-stack pdk-detail">
      <header className="pdk-bar">
        <button className="ad-btn ad-sm" onClick={onBack}><Icon n="left" size={15} />All products</button>
        <div className="pdk-bar-title">
          <h2>{name}</h2>
          <small>{p ? [`${shown} parts on its page`, p.categories?.join(", ")].filter(Boolean).join(" · ") : loading ? "Loading…" : ""}</small>
        </div>
        <div className="pdk-bar-act">
          {go && <button className="ad-btn" onClick={() => go("product-page")}><Icon n="note" size={15} />Edit page</button>}
          <button className="ad-btn ad-primary" onClick={onEdit}><Icon n="edit" size={15} />Edit details</button>
        </div>
      </header>

      {error && <section className="ad-card"><Empty icon="info" title="We could not open the product" text={error.message} action="Try again" onAction={reload} /></section>}

      {(p || row) && (
        <section className="ad-card pdk-hero">
          <div className="pdk-hero-photos">
            <button type="button" className="pdk-hero-main" onClick={() => photos.length && setViewing(0)} aria-label="View photographs" disabled={!photos.length}>
              {photos[0] ? <img src={photos[0].url} alt="" /> : row?.image ? <img src={row.image} alt="" /> : <Icon n="layers" size={34} />}
              {photos.length > 1 && <em>{photos.length} photos</em>}
            </button>
            {photos.length > 1 && (
              <div className="pdk-hero-strip">
                {photos.slice(1, 5).map((ph, i) => (
                  <button key={ph.url} type="button" onClick={() => setViewing(i + 1)} aria-label={`Photograph ${i + 2}`}>
                    <img src={ph.url} alt="" />
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="pdk-hero-facts">
            <div className="pdk-hero-price">
              <b>{money(p?.price ?? row?.price ?? 0, cur)}</b>
              {(p?.mrp || row?.mrp) > (p?.price ?? row?.price) && <s>{money(p?.mrp || row?.mrp, cur)}</s>}
              {(p ? p.published : row?.active) ? <span className="ad-pill ad-t-green"><i />Live</span> : <span className="ad-pill ad-t-grey"><i />Hidden</span>}
            </div>
            <div className="ad-kv">
              <span><small>Article ID</small>{p?.code || row?.code || "—"}</span>
              <span><small>Unit</small>{p?.unit || row?.unit || "—"}</span>
              <span><small>Categories</small>{p?.categories?.length ? p.categories.join(", ") : row?.cat || "None"}</span>
              <span><small>In stock</small>{row?.qty ?? stats.onHand ?? "—"}{STOCK[row?.state] ? ` · ${STOCK[row.state][0]}` : ""}</span>
            </div>
            {p?.differs > 0 && <p className="ad-hint"><Icon n="info" size={14} />{p.differs} line{p.differs > 1 ? "s" : ""} on its page differ from the shop's defaults.</p>}
          </div>
        </section>
      )}

      {statTiles.length > 0 && (
        <section className="ad-mini-stats pdk-stats">
          {statTiles.map(([label, value, bad]) => <span key={label} className={bad ? "ad-bad" : ""}><small>{label}</small><b>{value}</b></span>)}
        </section>
      )}

      {data && !(data.sections || []).length && <section className="ad-card"><Empty icon="layers" title="No sections yet" text="The product page has nothing on it to show." /></section>}
      {(data?.sections || []).map((s, i) => (
        <section key={s.id} className={"ad-card pdk-page-sec" + (s.show ? "" : " pdk-off")} style={{ "--i": i }}>
          <header className="pdk-sec-head">
            <h3>{s.name}</h3>
            <span className={"ad-pill " + (s.show ? "ad-t-grey" : "ad-t-amber")}><i />{s.show ? `${s.shown} of ${s.total} shown` : "Switched off"}</span>
          </header>
          <ul className="pdk-rows">
            {s.fields.map((f) => (
              <li key={f.id} className={s.show && f.visible ? "" : "pdk-off"}>
                <span className="pdk-row-name">{f.name}{!(s.show && f.visible) && <small>hidden</small>}</span>
                <span className={"pdk-row-value" + (f.value === "" || f.value == null ? " ad-dim" : "")}>{valueOf(f)}</span>
                <span className="pdk-row-from">from {SOURCE[f.source] || f.source}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {loading && !data && !error && <section className="ad-card"><Empty icon="layers" title="Loading…" text="Reading the page." /></section>}

      {viewing !== null && photos[viewing] && <PhotoViewer list={photos} index={viewing} onIndex={setViewing} onClose={() => setViewing(null)} />}
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
