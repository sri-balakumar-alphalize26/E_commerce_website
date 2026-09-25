"use client";
/* ==========================================================================
   369 Mart admin — Products (inventory) · Customers · Riders
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import { useResource } from "@/lib/useFetch";
import { Avatar, Drawer, Empty, Icon, Search, Select, SortMenu, Switch, Tabs } from "./AdminUI";
import ProductEditor, { PhotoViewer } from "./ProductEditor";
import AddressForm from "../home/AddressForm";
import { RIDERS, clock, groupIN, isToday } from "./adminData";
import { dateShort, dateYear, since } from "./format";

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
/* The badges, as [label, tone] pairs. A New customer's first badge says how
   long it has left (Settings > Customers); the second says whether they have
   ordered yet. Every Active / Dormant badge says when they last placed an
   order - placed, so a cash-on-delivery order counts before it is confirmed. */
const badgesOf = (c) => {
  const ordered = c?.lastPlaced ? `ordered ${since(c.lastPlaced)}` : "";
  if (c?.status === "new") {
    const left = c.newDaysLeft;
    return [
      [!left ? "New" : left === 1 ? "New · last day" : `New · ${left} days left`, "blue"],
      ordered ? [`Active · ${ordered}`, "green"] : ["Not ordered yet", "amber"],
    ];
  }
  if (c?.status === "active") return [[`Active · ${ordered || "no orders yet"}`, "green"]];
  if (c?.status === "dormant") return [[`Dormant · ${ordered || "no orders"}`, "grey"]];
  return [STATUS[c?.status] || STATUS.active];
};
const JOINED_LABEL = { month: "joined this month", "3m": "joined in the last 3 months", year: "joined this year" };
/* The server's orders (SORTS in customer_admin.py). The first is the default. */
/* A tag's colour, from Odoo's colour index on the tag (0-11) - the same
   mapping the Odoo desk uses. */
const TAG_TONES = ["grey", "red", "orange", "amber", "blue", "violet", "green", "blue", "red", "violet", "green", "orange"];
const tagTone = (t) => TAG_TONES[(t?.color || 0) % TAG_TONES.length];
const CUSTOMER_SORTS = [
  ["new", "Newest first"], ["old", "Oldest first"],
  ["name", "Name A → Z"], ["name_desc", "Name Z → A"], ["seen", "Recently active"],
];

export function CustomersSection({ initialQ = "", onOpenTicket }) {
  const [term, setTerm] = useState(initialQ);
  const [q, setQ] = useState(initialQ);
  const [tab, setTab] = useState("all");
  const [area, setArea] = useState("");
  const [joined, setJoined] = useState("");
  const [wallet, setWallet] = useState("");
  const [sort, setSort] = useState("new");
  const [tag, setTag] = useState("");
  const [limit, setLimit] = useState(50);
  const [open, setOpen] = useState(null);
  /* The full profile, by customer id. In the address bar as ?customer=<id>, so
     a profile can be reloaded or sent to a colleague. */
  const [profile, setProfileState] = useState(() => {
    if (typeof window === "undefined") return null;
    const id = Number(new URLSearchParams(window.location.search).get("customer"));
    return id || null;
  });
  const setProfile = (id) => {
    setProfileState(id);
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("customer", String(id)); else url.searchParams.delete("customer");
    history.replaceState(null, "", url.pathname + url.search);
    window.scrollTo({ top: 0 });
  };

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);
  useEffect(() => setLimit(50), [tab, q, area, joined, wallet, sort, tag]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("tab", tab);
    if (q) p.set("q", q);
    if (area) p.set("area", area);
    if (joined) p.set("joined", joined);
    if (wallet) p.set("wallet", "1");
    if (sort !== "new") p.set("sort", sort);
    if (tag) p.set("tag", tag);
    p.set("limit", String(limit));
    return "/admin/customers?" + p.toString();
  }, [tab, q, area, joined, wallet, sort, tag, limit]);

  const { data, loading, error, reload } = useResource(path, { pollMs: 120000, keepLast: true, enabled: !profile });
  const rows = data?.rows || [];
  const counts = data?.counts || {};
  const currency = data?.currency;
  const allTags = data?.tags || [];
  const tagName = allTags.find((t) => String(t.id) === tag)?.name;
  if (profile) return <CustomerProfile userId={profile} onBack={() => { setProfile(null); reload(); }} onOpenTicket={onOpenTicket} />;
  const why = [q && `"${q}"`, area && `in ${area}`, joined && JOINED_LABEL[joined], wallet && "with a wallet balance", tagName && `tagged ${tagName}`].filter(Boolean).join(", ");

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Customers</small><b>{counts.all ?? 0}</b></span>
        <span><small>Active</small><b>{counts.active ?? 0}</b></span>
        <span><small>New customers</small><b>{counts.new ?? 0}</b></span>
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
            {!!allTags.length && <Select value={tag} onChange={setTag} label="Tag" options={[["", "All tags"], ...allTags.map((t) => [String(t.id), t.name])]} />}
            <SortMenu value={sort} onChange={setSort} options={CUSTOMER_SORTS} label="Sort customers" />
          </div>
        </div>
        {why && data && <p className="ad-hint"><Icon n="info" size={14} />Showing {rows.length} of {data.total} that match — the tiles count the whole shop.</p>}
        {!why && data && !!rows.length && <p className="ad-hint">{data.total} customer{data.total === 1 ? "" : "s"}</p>}
        <div className="ad-table-wrap">
          {error && !rows.length && <Empty icon="info" title="We could not reach the shop" text={error.message} action="Try again" onAction={reload} />}
          {loading && !rows.length && !error && <Empty icon="users" title="Loading…" text="Fetching customers." />}
          {!!rows.length && (
            <table className="ad-table">
              <thead><tr><th>Customer</th><th>Contact</th><th>Area</th><th className="ad-num">Addresses</th><th className="ad-num">Orders</th><th className="ad-num">Spent</th><th className="ad-num">Wallet</th><th>Last order</th><th>Status</th><th /></tr></thead>
              <tbody>
                {rows.map((c, i) => {
                  return (
                    <tr key={c.id} style={{ "--i": i % 12 }} className={open?.id === c.id ? "ad-row-open" : ""} onClick={(e) => { if (!e.target.closest("button")) setOpen(c); }}>
                      <td><span className="ad-cell-person"><Avatar name={c.name} size={32} tone="ad-a-blue" /><span><b>{c.name}</b><small>{c.joined ? `Joined ${dateYear(c.joined)}` : ""}</small>{!!c.tags?.length && <span className="ad-cust-rowtags">{c.tags.map((t) => <span key={t.id} className={"ad-pill ad-t-" + tagTone(t)}>{t.name}</span>)}</span>}</span></span></td>
                      <td><small>{c.email}<br />{c.phone}</small></td>
                      <td><small>{c.area || "—"}</small></td>
                      <td className="ad-num">{c.addressCount || "—"}</td>
                      <td className="ad-num">{c.orders}</td>
                      <td className="ad-num ad-strong">{money(c.spent, currency)}</td>
                      <td className="ad-num">{money(c.wallet, currency)}</td>
                      <td><small>{c.lastPlaced || c.last ? since(c.lastPlaced || c.last) : "Never"}</small></td>
                      <td><span className="ad-pills">{badgesOf(c).map(([label, tone]) => <span key={label} className={"ad-pill ad-t-" + tone}><i />{label}</span>)}</span></td>
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

      {open && <CustomerDrawer row={open} currency={currency} onClose={() => setOpen(null)} onChanged={reload}
        onProfile={(id) => { setOpen(null); setProfile(id); }} />}
    </div>
  );
}

/* An address as the lines a parcel label reads, top to bottom - the same
   lines the Odoo desk prints (customer_desk.js addressLines). */
const addressLines = (a) => {
  const near = a.landmark && !/^(near|opp|opposite|behind|beside|next to)\b/i.test(a.landmark)
    ? "near " + a.landmark : a.landmark;
  const place = a.town
    ? `${a.town}${a.state ? ", " + a.state : ""}${a.pin ? " " + a.pin : ""}`
    : [a.city, a.state].filter(Boolean).join(", ");
  return [a.line, [a.area, near].filter(Boolean).join(", "), place].filter(Boolean);
};

/* One customer, the same panel as the Odoo desk's: who they are, four
   figures, every address they keep (default first), and their recent orders.
   The addresses and each order's "to Home" come with the detail - mart369_address
   adds them to it. */
/* Staff-only labels on a customer, saved the moment they change. The picker
   offers every tag not already on them, and "Create" for a new name. */
function CustomerTags({ userId, tags, onSaved }) {
  const { data } = useResource("/admin/customer-tags");
  const [picking, setPicking] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const all = data?.tags || [];
  const on = new Set(tags.map((t) => t.id));
  const q = text.trim().toLowerCase();
  const choices = all.filter((t) => !on.has(t.id) && t.name.toLowerCase().includes(q));
  const isNew = !!q && !all.some((t) => t.name.toLowerCase() === q);

  const save = async (names) => {
    setBusy(true); setError("");
    try {
      const r = await api(`/admin/customers/${userId}/tags`, { method: "PATCH", body: { tags: names } });
      api.invalidate("/admin/customer-tags");
      setPicking(false); setText("");
      onSaved(r.tags || []);
    } catch (e) {
      setError(e.message || "That could not be saved.");
    } finally {
      setBusy(false);
    }
  };
  const add = (name) => name.trim() && save([...tags.map((t) => t.name), name.trim()]);
  const remove = (tag) => save(tags.filter((t) => t.id !== tag.id).map((t) => t.name));

  return (
    <section className="ad-cust-sec">
      <h4>Tags</h4>
      {error && <p className="ad-form-error" role="alert">{error}</p>}
      <div className="ad-cust-tags">
        {tags.map((t) => (
          <span key={t.id} className={"ad-pill ad-t-" + tagTone(t) + " ad-cust-tag"}>
            {t.name}
            <button type="button" aria-label={`Remove ${t.name}`} disabled={busy} onClick={() => remove(t)}>×</button>
          </span>
        ))}
        {!picking && <button type="button" className="ad-cust-tag-add" onClick={() => setPicking(true)}>+ Add tag</button>}
      </div>
      {picking && (
        <div className="ad-cust-tagpick">
          <input autoFocus value={text} placeholder="Type a tag…" onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); add(isNew || !choices[0] ? text : choices[0].name); }
              if (e.key === "Escape") setPicking(false);
            }} />
          <ul>
            {choices.map((t) => <li key={t.id}><button type="button" disabled={busy} onClick={() => add(t.name)}>{t.name}</button></li>)}
            {isNew && <li><button type="button" className="ad-cust-tag-new" disabled={busy} onClick={() => add(text)}>+ Create “{text.trim()}”</button></li>}
            {!choices.length && !isNew && <li className="ad-dim">Type a name to make a new tag.</li>}
          </ul>
        </div>
      )}
    </section>
  );
}

/* Only staff read these - never the customer. Each one is signed with who
   wrote it and when; you can remove your own. */
function CustomerNotes({ userId, notes, onSaved }) {
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(null); // {id, text} of the note being changed
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (path, opts, clear) => {
    setBusy(true); setError("");
    try {
      const r = await api(path, opts);
      if (clear) setText("");
      setEditing(null);
      onSaved(r.notes || []);
    } catch (e) {
      setError(e.message || "That did not work.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="ad-cust-sec">
      <h4>Staff notes</h4>
      {error && <p className="ad-form-error" role="alert">{error}</p>}
      <div className="ad-cust-note-new">
        <textarea rows={2} maxLength={1000} value={text} placeholder="Write a note for the team…"
          onChange={(e) => setText(e.target.value)} />
        <button className="ad-btn ad-primary" disabled={busy || !text.trim()}
          onClick={() => run(`/admin/customers/${userId}/notes`, { method: "POST", body: { text: text.trim() } }, true)}>Add</button>
      </div>
      {!notes.length && <p className="ad-dim">No notes yet.</p>}
      {!!notes.length && (
        <ul className="ad-cust-notes">
          {notes.map((n) => (
            <li key={n.id}>
              {editing?.id === n.id ? (
                <>
                  <textarea className="ad-cust-note-edit" rows={2} maxLength={1000} autoFocus value={editing.text}
                    onChange={(e) => setEditing({ id: n.id, text: e.target.value })} />
                  <span className="ad-cust-note-edit-act">
                    <button className="ad-btn ad-sm" onClick={() => setEditing(null)}>Cancel</button>
                    <button className="ad-btn ad-sm ad-primary" disabled={busy || !editing.text.trim()}
                      onClick={() => run(`/admin/customers/${userId}/notes/${n.id}`, { method: "PATCH", body: { text: editing.text.trim() } })}>Save</button>
                  </span>
                </>
              ) : <p>{n.text}</p>}
              <small>
                {n.author} · {n.at ? since(n.at) : ""}
                {n.mine && editing?.id !== n.id && (
                  <button type="button" className="ad-cust-note-pen" aria-label="Edit note" disabled={busy}
                    onClick={() => setEditing({ id: n.id, text: n.text })}>
                    <Icon n="pen" size={13} />
                  </button>
                )}
                {n.mine && (
                  <button type="button" aria-label="Delete note" disabled={busy}
                    onClick={() => run(`/admin/customers/${userId}/notes/${n.id}`, { method: "DELETE" })}>
                    <Icon n="trash" size={13} />
                  </button>
                )}
              </small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function CustomerDrawer({ row, currency, onClose, onChanged, onProfile }) {
  const { data, error, reload } = useResource(`/admin/customers/${row.id}`);
  const [giving, setGiving] = useState(false);
  /* Edits land here first, so the drawer shows them without a refetch. */
  const [tagsNow, setTagsNow] = useState(null);
  const [notesNow, setNotesNow] = useState(null);
  const c = data?.customer || row;
  const detail = data?.customer;
  const recent = detail?.recent;
  const addresses = detail?.addresses;
  const tags = tagsNow || detail?.tags || row.tags || [];
  const notes = notesNow || detail?.notes || [];
  const tel = c.phone ? "tel:" + c.phone.replace(/[^\d+]/g, "") : "";
  const wa = detail?.waPhone ? "https://wa.me/" + detail.waPhone : "";
  const changed = () => { api.invalidate(`/admin/customers/${row.id}`); onChanged?.(); };
  return (
    <Drawer title={c.name} onClose={onClose}
      lead={<Avatar name={c.name} size={52} tone="ad-a-blue" />}
      sub={<>
        <span>{c.email}{c.phone ? ` · ${c.phone}` : ""}</span>
        <span>{c.area || "No area"} · {badgesOf(c).map(([label]) => label).join(" · ")}</span>
      </>}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Close</button>
          {onProfile && <button className="ad-btn ad-primary" onClick={() => onProfile(row.id)}>Open full profile</button>}
        </>
      )}>
      {/* Reach them without copying the number. */}
      <div className="ad-cust-reach">
        {tel ? <a className="ad-btn" href={tel}><Icon n="phone" size={15} />Call</a>
          : <span className="ad-btn ad-cust-off"><Icon n="phone" size={15} />Call</span>}
        {wa ? <a className="ad-btn" href={wa} target="_blank" rel="noopener noreferrer"><Icon n="chat" size={15} />WhatsApp</a>
          : <span className="ad-btn ad-cust-off"><Icon n="chat" size={15} />WhatsApp</span>}
      </div>

      {(riskLine(detail?.risk) || detail?.risk?.codOff) && (
        <p className="ad-risk-line">
          <Icon n="info" size={14} />
          <span>{riskLine(detail.risk)}</span>
          {detail.risk.codOff && <span className="ad-pill ad-t-red">COD off</span>}
        </p>
      )}

      {detail && <CustomerTags userId={row.id} tags={tags} onSaved={(t) => { setTagsNow(t); changed(); }} />}

      <div className="ad-cust-figs">
        <span><small>Orders</small><b>{c.orders ?? 0}</b></span>
        <span><small>Spent</small><b>{money(c.spent, currency)}</b></span>
        <span><small>Wallet</small><b>{money(c.wallet, currency)}</b></span>
        <span><small>Last order</small><b>{c.lastPlaced || c.last ? since(c.lastPlaced || c.last) : "Never"}</b></span>
      </div>
      {detail && !giving && <button type="button" className="ad-cust-tag-add ad-cust-give" onClick={() => setGiving(true)}>+ Goodwill credit</button>}
      {detail && giving && <GoodwillForm userId={row.id} onCancel={() => setGiving(false)}
        onDone={() => { setGiving(false); changed(); reload(); }} />}

      {addresses && (
        <section className="ad-cust-sec">
          <h4>Addresses ({addresses.length})</h4>
          {!addresses.length && <p className="ad-dim">No saved addresses yet.</p>}
          {!!addresses.length && (
            <ul className="ad-cust-addrs">
              {addresses.map((a) => (
                <li key={a.id} className={a.default ? "ad-cust-addr-on" : ""}>
                  <span className="ad-cust-addr-head">
                    <b>{a.label || "Address"}</b>
                    {a.default && <span className="ad-pill ad-t-green">Ships here</span>}
                    {!!a.gaps?.length && <span className="ad-pill ad-t-orange">Missing {a.gaps.join(", ")}</span>}
                  </span>
                  <small>{a.name}{a.phone ? ` · ${a.phone}` : ""}</small>
                  {addressLines(a).map((line, i) => <small key={i}>{line}</small>)}
                </li>
              ))}
            </ul>
          )}
          {!!detail.removedAddresses && (
            <p className="ad-dim">+ {detail.removedAddresses} removed by the customer</p>
          )}
          <AddAddress userId={row.id} customer={c} country={homeCountry(addresses)} onAdded={() => { changed(); reload(); }} />
        </section>
      )}

      {detail && <CustomerNotes userId={row.id} notes={notes} onSaved={(n) => { setNotesNow(n); changed(); }} />}

      <section className="ad-cust-sec">
        <h4>Recent orders</h4>
        {!detail && !error && <p className="ad-dim">Loading…</p>}
        {error && <p className="ad-dim">{error.message}</p>}
        {recent && !recent.length && <p className="ad-dim">No orders yet.</p>}
        {!!recent?.length && (
          <ul className="ad-items">
            {recent.map((o) => (
              <li key={o.ref}><span className="ad-qty-chip">{o.items}</span><span><b>#{o.ref}</b><small>{o.at ? dateShort(o.at) : ""}{o.method ? ` · ${o.method}` : ""}{o.addressLabel ? ` · to ${o.addressLabel}` : ""}</small></span><b>{money(o.total, currency)}</b></li>
            ))}
          </ul>
        )}
      </section>
    </Drawer>
  );
}

/* =========================== add an address ============================ */
const homeCountry = (list) => ((list || []).find((a) => a.default) || (list || [])[0])?.country_code || "";
/* An address taken over the phone: the shop's own form (so the same fields,
   the same pincode lookup and the same country rules), saved through the
   staff route. Opens in place under the address list. */
function AddAddress({ userId, customer, country, onAdded }) {
  const [open, setOpen] = useState(false);
  /* Start in the customer's country, not the staff member's: the form
     otherwise opens wherever the signed-in account lives. */
  const { data: meta } = useResource("/addresses/form" + (country ? `?country=${encodeURIComponent(country)}` : ""), { enabled: open });
  if (!open) return <button type="button" className="ad-cust-tag-add ad-cust-addr-add" onClick={() => setOpen(true)}>+ Add address</button>;
  const save = async (body) => {
    try {
      const r = await api(`/admin/customers/${userId}/addresses`, { method: "POST", body });
      if (r?.ok === false) return { error: { field: r.field, message: r.error } };
      setOpen(false);
      onAdded?.(r.address);
      return r;
    } catch (e) {
      return { error: { field: e.field, message: e.message || "Could not save that address. Try again." } };
    }
  };
  return (
    <div className="ad-cust-addform">
      {!meta && <p className="ad-dim">Loading the form…</p>}
      {meta && <AddressForm meta={meta} me={{ name: customer?.name, phone: customer?.phone }}
        onSave={save} onCancel={() => setOpen(false)} saveLabel="Add address" />}
    </div>
  );
}

/* ============================== customer risk =========================== */
/* The few numbers support reads before picking up the phone. A number over
   0 is worth a look (amber); three or more refusals or cancellations by the
   customer is a pattern (red). */
const riskTone = (n, loud = false) => (!n ? "" : loud && n >= 3 ? " ad-risk-bad" : " ad-risk-warn");
const riskLine = (r) => [
  r?.cancelledByCustomer && `${r.cancelledByCustomer} cancelled by them`,
  r?.refused && `${r.refused} refused at the door`,
  r?.returned && `${r.returned} returned`,
  r?.returnRequests && `${r.returnRequests} return request${r.returnRequests === 1 ? "" : "s"}`,
].filter(Boolean).join(" · ");

function RiskStrip({ userId, risk, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const setCod = async (off) => {
    setBusy(true); setError("");
    try {
      const r = await api(`/admin/customers/${userId}/cod`, { method: "PATCH", body: { off } });
      onChanged(r.risk);
    } catch (e) { setError(e.message || "That could not be saved."); } finally { setBusy(false); }
  };
  const r = risk || {};
  return (
    <section className="ad-card ad-risk">
      <div className="ad-risk-tiles">
        <span className={"ad-risk-tile" + riskTone(r.cancelledByCustomer, true)}><small>Cancelled by them</small><b>{r.cancelledByCustomer ?? 0}</b></span>
        <span className={"ad-risk-tile" + riskTone(r.cancelledByShop)}><small>Cancelled by shop</small><b>{r.cancelledByShop ?? 0}</b></span>
        <span className={"ad-risk-tile" + riskTone(r.refused, true)}><small>Refused at door</small><b>{r.refused ?? 0}</b></span>
        <span className={"ad-risk-tile" + riskTone(r.returned)}><small>Returned</small><b>{r.returned ?? 0}</b></span>
        <span className={"ad-risk-tile" + riskTone(r.returnRequests)}><small>Return requests</small><b>{r.returnRequests ?? 0}</b></span>
        <div className={"ad-risk-tile ad-risk-cod" + (r.codOff ? " ad-risk-bad" : "")}>
          <small>Cash on delivery</small>
          <span><b>{r.codOff ? "Off" : "On"}</b>
            <Switch on={!r.codOff} onChange={(on) => !busy && setCod(!on)} label="Cash on delivery for this customer" /></span>
        </div>
      </div>
      {error && <p className="ad-form-error" role="alert">{error}</p>}
      {r.codOff && <p className="ad-hint"><Icon n="info" size={14} />Cash on delivery isn't offered to this customer at checkout — they pay online.</p>}
    </section>
  );
}

/* Money into the wallet with a reason, as a reward - the customer sees
   "Goodwill credit · <reason>" in their wallet history. */
function GoodwillForm({ userId, onDone, onCancel }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async () => {
    setBusy(true); setError("");
    try {
      await api(`/admin/customers/${userId}/goodwill`, { method: "POST", body: { amount: Number(amount), reason } });
      onDone();
    } catch (e) { setError(e.message || "That could not be added."); } finally { setBusy(false); }
  };
  return (
    <section className="ad-card ad-goodwill">
      <h4>Goodwill credit</h4>
      {error && <p className="ad-form-error" role="alert">{error}</p>}
      <div className="ad-goodwill-row">
        <input inputMode="decimal" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} />
        <input placeholder="Reason, e.g. late delivery" maxLength={120} value={reason} onChange={(e) => setReason(e.target.value)} />
        <button className="ad-btn" onClick={onCancel}>Cancel</button>
        <button className="ad-btn ad-primary" disabled={busy || !(Number(amount) > 0) || !reason.trim()} onClick={save}>Add to wallet</button>
      </div>
      <p className="ad-hint"><Icon n="info" size={14} />The customer sees this in their wallet as “Goodwill credit”, with your reason and name.</p>
    </section>
  );
}

const RETURN_TONE = { requested: "amber", pickup: "blue", picked: "violet", done: "green", refused: "grey" };
const TICKET_TONE = { new: "red", open: "amber", waiting: "blue", done: "green", cancelled: "grey" };

/* ============================ customer profile ========================== */
/* Everything about one customer on one page: who they are, how to reach them,
   the team's tags and notes, every address, every order and every wallet
   movement. The drawer is the glance; this is the whole story. */
const ORDER_STATE = {
  placed: ["Placed", "blue"], confirmed: ["Confirmed", "blue"], packed: ["Packed", "violet"],
  ready: ["Ready", "violet"], out: ["Out for delivery", "amber"], delivered: ["Delivered", "green"],
  failed: ["Delivery failed", "red"], cancelled: ["Cancelled", "grey"], returned: ["Returned", "grey"],
};
const CREDIT = ["add", "refund", "reward"];
const PAID_BY = { cod: "Cash on delivery", upi: "UPI", card: "Card", netbanking: "Net banking", wallet: "Wallet" };

function CustomerProfile({ userId, onBack, onOpenTicket }) {
  const { data, error, reload } = useResource(`/admin/customers/${userId}/profile`);
  const [riskNow, setRiskNow] = useState(null);
  const [giving, setGiving] = useState(false);
  const c = data?.customer;
  const currency = c?.currency;
  const [tagsNow, setTagsNow] = useState(null);
  const [notesNow, setNotesNow] = useState(null);
  const changed = () => { api.invalidate(`/admin/customers/${userId}/profile`); api.invalidate(`/admin/customers/${userId}`); };

  const back = <button className="ad-btn" onClick={onBack}><Icon n="left" size={15} />All customers</button>;
  if (error && !c) return <div className="ad-stack">{back}<Empty icon="info" title="We could not open this customer" text={error.message} action="Try again" onAction={reload} /></div>;
  if (!c) return <div className="ad-stack">{back}<Empty icon="users" title="Loading…" text="Fetching the customer." /></div>;

  const tags = tagsNow || c.tags || [];
  const notes = notesNow || c.notes || [];
  const tel = c.phone ? "tel:" + c.phone.replace(/[^\d+]/g, "") : "";
  const wa = c.waPhone ? "https://wa.me/" + c.waPhone : "";
  const orders = c.orders || [];
  const moves = c.walletMoves || [];

  return (
    <div className="ad-stack ad-prof">
      <div>{back}</div>
      <section className="ad-card ad-prof-head">
        <Avatar name={c.name} size={64} tone="ad-a-blue" />
        <div className="ad-prof-who">
          <h2>{c.name}</h2>
          <small>{c.email}{c.phone ? ` · ${c.phone}` : ""}</small>
          <small>{c.area || "No area"} · Joined {c.joined ? dateYear(c.joined) : "—"}</small>
          <span className="ad-pills">{badgesOf(c).map(([label, tone]) => <span key={label} className={"ad-pill ad-t-" + tone}><i />{label}</span>)}</span>
        </div>
        <div className="ad-cust-reach">
          {tel ? <a className="ad-btn" href={tel}><Icon n="phone" size={15} />Call</a>
            : <span className="ad-btn ad-cust-off"><Icon n="phone" size={15} />Call</span>}
          {wa ? <a className="ad-btn" href={wa} target="_blank" rel="noopener noreferrer"><Icon n="chat" size={15} />WhatsApp</a>
            : <span className="ad-btn ad-cust-off"><Icon n="chat" size={15} />WhatsApp</span>}
        </div>
      </section>

      <RiskStrip userId={userId} risk={riskNow || c.risk} onChanged={(r) => { setRiskNow(r); changed(); }} />

      <section className="ad-mini-stats">
        <span><small>Orders</small><b>{c.orderCount ?? 0}</b></span>
        <span><small>Spent</small><b>{money(c.spent, currency)}</b></span>
        <span className="ad-prof-wallet"><small>Wallet</small><b>{money(c.wallet, currency)}</b>
          {!giving && <button type="button" className="ad-cust-tag-add" onClick={() => setGiving(true)}>+ Goodwill credit</button>}</span>
        <span><small>Last order</small><b>{c.lastPlaced || c.last ? since(c.lastPlaced || c.last) : "Never"}</b></span>
      </section>

      {giving && <GoodwillForm userId={userId} onCancel={() => setGiving(false)}
        onDone={() => { setGiving(false); changed(); reload(); }} />}

      <div className="ad-prof-grid">
        <div className="ad-prof-side">
          <div className="ad-card ad-prof-card">
            <CustomerTags userId={userId} tags={tags} onSaved={(t) => { setTagsNow(t); changed(); }} />
          </div>
          <div className="ad-card ad-prof-card">
            <CustomerNotes userId={userId} notes={notes} onSaved={(n) => { setNotesNow(n); changed(); }} />
          </div>
          <div className="ad-card ad-prof-card">
            <section className="ad-cust-sec">
              <h4>Addresses ({(c.addresses || []).length})</h4>
              {!(c.addresses || []).length && <p className="ad-dim">No saved addresses yet.</p>}
              <ul className="ad-cust-addrs">
                {(c.addresses || []).map((a) => (
                  <li key={a.id} className={a.default ? "ad-cust-addr-on" : ""}>
                    <span className="ad-cust-addr-head">
                      <b>{a.label || "Address"}</b>
                      {a.default && <span className="ad-pill ad-t-green">Ships here</span>}
                      {!!a.gaps?.length && <span className="ad-pill ad-t-orange">Missing {a.gaps.join(", ")}</span>}
                    </span>
                    <small>{a.name}{a.phone ? ` · ${a.phone}` : ""}</small>
                    {addressLines(a).map((line, i) => <small key={i}>{line}</small>)}
                  </li>
                ))}
              </ul>
              {!!c.removedAddresses && <p className="ad-dim">+ {c.removedAddresses} removed by the customer</p>}
              <AddAddress userId={userId} customer={c} country={homeCountry(c.addresses)} onAdded={() => { changed(); reload(); }} />
            </section>
          </div>
        </div>

        <div className="ad-prof-main">
          <div className="ad-card">
            <div className="ad-prof-cardhead"><h4>Orders ({c.orderTotal ?? orders.length})</h4></div>
            {!orders.length && <Empty icon="box" title="No orders yet" text="Orders appear here once they place one." />}
            {!!orders.length && (
              <div className="ad-table-wrap">
                <table className="ad-table">
                  <thead><tr><th>Order</th><th>Placed</th><th>Type</th><th className="ad-num">Items</th><th className="ad-num">Total</th><th>Paid by</th><th>Status</th></tr></thead>
                  <tbody>
                    {orders.map((o) => {
                      const [label, tone] = ORDER_STATE[o.state] || [o.state, "grey"];
                      return (
                        <tr key={o.ref}>
                          <td className="ad-nowrap"><b>#{o.ref}</b></td>
                          <td><small>{o.at ? `${dateYear(o.at)} · ${since(o.at)}` : "—"}</small></td>
                          <td><small>{o.mode === "all" ? "Express" : "Quick"}</small></td>
                          <td className="ad-num">{o.itemCount}</td>
                          <td className="ad-num ad-strong">{money(o.total, currency)}</td>
                          <td><small>{PAID_BY[o.method] || o.method || "—"}</small></td>
                          <td><span className={"ad-pill ad-t-" + tone}><i />{label}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="ad-card">
            <div className="ad-prof-cardhead"><h4>Support tickets ({(c.tickets || []).length}){c.openTickets ? ` · ${c.openTickets} open` : ""}</h4></div>
            {!(c.tickets || []).length && <Empty icon="chat" title="No tickets" text="Complaints and questions this customer raised appear here." />}
            {!!(c.tickets || []).length && (
              <ul className="ad-prof-list">
                {c.tickets.map((t) => (
                  <li key={t.id}>
                    <button type="button" onClick={() => onOpenTicket?.(t.ref)} disabled={!onOpenTicket}>
                      <span><b>{t.ref} · {t.subject}</b><small>{[t.order && `Order #${t.order}`, t.openedAt ? `${dateYear(t.openedAt)} · ${since(t.openedAt)}` : ""].filter(Boolean).join(" · ")}</small></span>
                      <span className={"ad-pill ad-t-" + (TICKET_TONE[t.state] || "grey")}><i />{t.stateLabel || t.state}</span>
                      {onOpenTicket && <Icon n="right" size={15} />}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="ad-card">
            <div className="ad-prof-cardhead"><h4>Returns ({(c.returns || []).length})</h4></div>
            {!(c.returns || []).length && <Empty icon="box" title="No returns" text="Refunds and replacements they asked for appear here." />}
            {!!(c.returns || []).length && (
              <ul className="ad-prof-list">
                {c.returns.map((r) => (
                  <li key={r.id}>
                    <div>
                      <span><b>#{r.ref} · {r.kind === "replace" ? "Replacement" : "Refund"}</b><small>{[r.reason, r.at ? dateYear(r.at) : ""].filter(Boolean).join(" · ")}</small></span>
                      {!!r.amount && <b className="ad-nowrap">{money(r.amount, r.currency || currency)}</b>}
                      <span className={"ad-pill ad-t-" + (RETURN_TONE[r.state] || "grey")}><i />{r.stateLabel || r.state}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="ad-card">
            <div className="ad-prof-cardhead"><h4>Wallet history</h4></div>
            {!moves.length && <Empty icon="wallet" title="No wallet movements" text="Money added, spent, refunded or rewarded shows here." />}
            {!!moves.length && (
              <ul className="ad-prof-moves">
                {moves.map((m) => {
                  const credit = CREDIT.includes(m.kind);
                  return (
                    <li key={m.id}>
                      <span><b>{m.title}</b><small>{[m.sub, m.at ? dateYear(m.at) : ""].filter(Boolean).join(" · ")}</small></span>
                      <b className={credit ? "ad-prof-in" : "ad-prof-out"}>{credit ? "+" : "−"}{m.amountText || money(m.amount, currency)}</b>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
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
