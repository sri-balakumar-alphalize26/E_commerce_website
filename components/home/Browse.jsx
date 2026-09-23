"use client";
/* ==========================================================================
   369 Mart — Browsing
   CategoryPage   /category/<slug>[/<sub>]  subcategory tiles + listing
   SearchResults  /search?q=               listing, did-you-mean, related
   OffersPage     /offers                  deal countdown, coupons, deals grid
   BuyAgainPage   /buy-again               items from past orders
   Listing        filters (brand, price, discount, rating, stock,
                  delivery), sort, active chips, infinite scroll, skeletons,
                  mobile filter/sort sheets
   SiteFooter · NotFoundView · SkeletonCard
   ========================================================================== */
import { useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ProductArt from "./art";
import { Icon, ProductCard, Thumb, flyTo, money } from "./shared";
import { listable } from "./catalog";
import { useRules } from "./Cart";
import { fmtPlaced } from "./orderState";
import { NavContext } from "./nav";
import { useResource } from "@/lib/useFetch";
import { absorb, cards } from "@/lib/products";

const PAGE = 12;
const SORTS = [
  ["relevance", "Relevance"], ["popular", "Popularity"], ["price-asc", "Price: low to high"],
  ["price-desc", "Price: high to low"], ["discount", "Biggest discount"], ["rating", "Customer rating"],
];
const DISCOUNTS = [0, 10, 25, 40];

export function SkeletonCard({ i = 0 }) {
  return (
    <div className="sk-card" style={{ "--i": i }} aria-hidden="true">
      <div className="sk sk-img" />
      <div className="sk sk-line sk-short" />
      <div className="sk sk-line" />
      <div className="sk sk-line sk-mid" />
    </div>
  );
}

export function Crumbs({ items }) {
  const nav = useContext(NavContext);
  return (
    <nav className="ls-crumbs" aria-label="Breadcrumb">
      {items.map(([label, to], k) => (
        <span key={k}>
          {k > 0 && <Icon n="right" size={12} />}
          {to ? <a href="#" onClick={(e) => { e.preventDefault(); nav(...to); }}>{label}</a> : <b>{label}</b>}
        </span>
      ))}
    </nav>
  );
}

/* ---------------- filter panel (sidebar on desktop, sheet on phones) ---------------- */
function FilterGroup({ title, open, onToggle, children }) {
  return (
    <section className={"ls-fg" + (open ? " ls-open" : "")}>
      <button className="ls-fg-head" onClick={onToggle} aria-expanded={open}>{title}<Icon n="chev" size={16} className="ls-chev" /></button>
      <div className="ls-collapse"><div><div className="ls-fg-body">{children}</div></div></div>
    </section>
  );
}

function Filters({ facets, f, setF, onClear }) {
  const [brandQ, setBrandQ] = useState("");
  const [open, setOpen] = useState({ brand: true, price: true, discount: true, rating: true, more: true });
  const brands = facets.brands.filter(([b]) => b.toLowerCase().includes(brandQ.toLowerCase()));
  const g = (k) => ({ open: open[k], onToggle: () => setOpen((o) => ({ ...o, [k]: !o[k] })) });
  const pct = (v) => ((v - facets.min) / Math.max(1, facets.max - facets.min)) * 100;
  return (
    <div className="ls-filters">
      <div className="ls-filters-head"><h3>Filters</h3>{f.active > 0 && <button className="ls-link" onClick={onClear}>Clear all</button>}</div>

      {facets.brands.length > 1 && (
        <FilterGroup title="Brand" {...g("brand")}>
          {facets.brands.length > 6 && <input className="ls-brand-q" placeholder="Search brand" value={brandQ} onChange={(e) => setBrandQ(e.target.value)} />}
          <div className="ls-checks">
            {brands.map(([b, n]) => (
              <label key={b} className="ls-check">
                <input type="checkbox" checked={f.brands.includes(b)} onChange={() => setF({ brands: f.brands.includes(b) ? f.brands.filter((x) => x !== b) : [...f.brands, b] })} />
                <span className="ls-box"><Icon n="check" size={11} /></span>{b}<small>{n}</small>
              </label>
            ))}
          </div>
        </FilterGroup>
      )}

      <FilterGroup title="Price" {...g("price")}>
        <div className="ls-range" style={{ "--a": pct(f.price[0]) + "%", "--b": pct(f.price[1]) + "%" }}>
          <div className="ls-range-track"><i /></div>
          <input type="range" min={facets.min} max={facets.max} step={1} value={f.price[0]} aria-label="Minimum price"
            onChange={(e) => setF({ price: [Math.min(+e.target.value, f.price[1]), f.price[1]] })} />
          <input type="range" min={facets.min} max={facets.max} step={1} value={f.price[1]} aria-label="Maximum price"
            onChange={(e) => setF({ price: [f.price[0], Math.max(+e.target.value, f.price[0])] })} />
        </div>
        <div className="ls-range-vals"><span>{money(f.price[0])}</span><span>{money(f.price[1])}</span></div>
      </FilterGroup>

      <FilterGroup title="Discount" {...g("discount")}>
        <div className="ls-pills">
          {DISCOUNTS.map((d) => (
            <button key={d} className={f.discount === d ? "ls-on" : ""} onClick={() => setF({ discount: d })}>{d ? `${d}% or more` : "Any"}</button>
          ))}
        </div>
      </FilterGroup>

      <FilterGroup title="Customer rating" {...g("rating")}>
        <div className="ls-pills">
          {[0, 4, 4.5].map((r) => (
            <button key={r} className={f.rating === r ? "ls-on" : ""} onClick={() => setF({ rating: r })}>{r ? <>{r}<Icon n="star" size={12} className="ls-star" /> & up</> : "Any"}</button>
          ))}
        </div>
      </FilterGroup>

      <FilterGroup title="More filters" {...g("more")}>
        <label className="ls-toggle"><span>In stock only</span><input type="checkbox" checked={f.inStock} onChange={(e) => setF({ inStock: e.target.checked })} /><em /></label>
        {facets.hasQuick && facets.hasExpress && (
          <div className="ls-pills ls-mt">
            {[["any", "Any delivery"], ["quick", "Quick"], ["express", "Express"]].map(([k, l]) => (
              <button key={k} className={f.delivery === k ? "ls-on" : ""} onClick={() => setF({ delivery: k })}>
                {k === "quick" && <Icon n="bolt" size={12} className="hm-fill ls-bolt" />}{k === "express" && <Icon n="truck" size={12} />}{l}
              </button>
            ))}
          </div>
        )}
      </FilterGroup>
    </div>
  );
}

/* ---------------- filter + sort state, shared by listing and search ---------------- */
export function useProductFilters(items) {
  /* identity of the list — cart updates re-render parents, but must not reset filters */
  const sig = items.map((p) => p.id).join(",");
  const facets = useMemo(() => {
    const brands = {};
    let min = Infinity, max = 0, hasQuick = false, hasExpress = false;
    items.forEach((p) => {
      brands[p.brand] = (brands[p.brand] || 0) + 1;
      min = Math.min(min, p.price); max = Math.max(max, p.price);
      hasQuick = hasQuick || !p.delivery; hasExpress = hasExpress || !!p.delivery;
    });
    if (!items.length) { min = 0; max = 0; }
    return { brands: Object.entries(brands).sort((a, b) => b[1] - a[1]), min, max, hasQuick, hasExpress };
  }, [sig]); // eslint-disable-line

  const fresh = () => ({ brands: [], price: [facets.min, facets.max], discount: 0, rating: 0, inStock: false, delivery: "any" });
  const [f, setFState] = useState(fresh);
  const [sort, setSortState] = useState("relevance");
  const [pulse, setPulse] = useState(0);
  useEffect(() => { setFState(fresh()); }, [facets]); // eslint-disable-line

  const setF = (patch) => { setFState((s) => ({ ...s, ...patch })); setPulse((n) => n + 1); };
  const clear = () => { setFState(fresh()); setPulse((n) => n + 1); };
  const setSort = (v) => { setSortState(v); setPulse((n) => n + 1); };

  const priceOn = f.price[0] > facets.min || f.price[1] < facets.max;
  const active = f.brands.length + (priceOn ? 1 : 0) + (f.discount ? 1 : 0) + (f.rating ? 1 : 0) + (f.inStock ? 1 : 0) + (f.delivery !== "any" ? 1 : 0);

  const results = useMemo(() => {
    let r = items.filter((p) =>
      (!f.brands.length || f.brands.includes(p.brand)) &&
      p.price >= f.price[0] && p.price <= f.price[1] &&
      p.off >= f.discount && p.rating >= f.rating &&
      (!f.inStock || p.stock !== 0) &&
      (f.delivery === "any" || (f.delivery === "quick" ? !p.delivery : !!p.delivery)));
    const by = {
      popular: (a, b) => b.popularity - a.popularity,
      "price-asc": (a, b) => a.price - b.price,
      "price-desc": (a, b) => b.price - a.price,
      discount: (a, b) => b.off - a.off,
      rating: (a, b) => b.rating - a.rating,
    }[sort];
    if (by) r = [...r].sort(by);
    /* out of stock always last */
    return [...r.filter((p) => p.stock !== 0), ...r.filter((p) => p.stock === 0)];
  }, [items, f, sort]);

  const chips = [
    ...f.brands.map((b) => [b, () => setF({ brands: f.brands.filter((x) => x !== b) })]),
    ...(priceOn ? [[`${money(f.price[0])} – ${money(f.price[1])}`, () => setF({ price: [facets.min, facets.max] })]] : []),
    ...(f.discount ? [[`${f.discount}%+ off`, () => setF({ discount: 0 })]] : []),
    ...(f.rating ? [[`${f.rating}★ & up`, () => setF({ rating: 0 })]] : []),
    ...(f.inStock ? [["In stock", () => setF({ inStock: false })]] : []),
    ...(f.delivery !== "any" ? [[f.delivery === "quick" ? "Quick delivery" : "Express delivery", () => setF({ delivery: "any" })]] : []),
  ];

  return { sig, facets, f, setF, clear, sort, setSort, pulse, active, priceOn, results, chips };
}

/* ---------------- listing ---------------- */
export function Listing({ items, cart, setQty, heading, sub, loading: busy, emptyTitle = "No products match these filters", emptyText, onEmptyAction, emptyAction, query }) {
  const { sig, facets, f, setF, clear, sort, setSort, pulse, active, results, chips } = useProductFilters(items);
  const [shown, setShown] = useState(PAGE);
  const [loading, setLoading] = useState(true);
  const [sheet, setSheet] = useState(null); // "filter" | "sort" | null
  const sentinel = useRef(null);
  const top = useRef(null);

  useEffect(() => { setShown(PAGE); }, [pulse, sig]);
  /* A caller that fetches its own list tells us when it is waiting. The timer
     is only for lists that are already in hand. */
  useEffect(() => {
    if (busy !== undefined) { setLoading(busy); return; }
    setLoading(true); const t = setTimeout(() => setLoading(false), 450); return () => clearTimeout(t);
  }, [sig, busy]);

  /* infinite scroll */
  const [more, setMore] = useState(false);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && shown < results.length && !more && !loading) {
        setMore(true);
        setTimeout(() => { setShown((s) => s + PAGE); setMore(false); }, 550);
      }
    }, { rootMargin: "300px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [shown, results.length, more, loading]);

  useEffect(() => {
    if (!sheet) return;
    const k = (e) => e.key === "Escape" && setSheet(null);
    document.documentElement.classList.add("ls-lock");
    window.addEventListener("keydown", k);
    return () => { window.removeEventListener("keydown", k); document.documentElement.classList.remove("ls-lock"); };
  }, [sheet]);

  const filters = <Filters facets={facets} f={{ ...f, active }} setF={setF} onClear={clear} />;

  return (
    <div className="ls" ref={top}>
      <aside className="ls-side">{filters}</aside>

      <div className="ls-main">
        <div className="ls-bar">
          <div className="ls-count">
            {heading && <h2>{heading}</h2>}
            <span key={results.length + "-" + pulse} className="ls-count-n">{loading ? "Loading products…" : `${results.length} ${results.length === 1 ? "product" : "products"}${query ? ` for “${query}”` : ""}`}</span>
            {sub}
          </div>
          <label className="ls-sort">
            <span>Sort by</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <Icon n="chev" size={14} />
          </label>
        </div>

        {chips.length > 0 && (
          <div className="ls-chips">
            {chips.map(([label, off], k) => (
              <button key={label} className="ls-chip" style={{ "--k": k }} onClick={off}>{label}<Icon n="x" size={12} /></button>
            ))}
            <button className="ls-link" onClick={clear}>Clear all</button>
          </div>
        )}

        {loading ? (
          <div className="ls-grid">{Array.from({ length: 8 }, (_, k) => <SkeletonCard key={k} i={k} />)}</div>
        ) : results.length === 0 ? (
          <div className="ls-empty">
            <span className="ls-empty-art"><ProductArt art="Basket" /></span>
            <h3>{emptyTitle}</h3>
            <p>{emptyText || "Try removing a filter or two."}</p>
            {active > 0 ? <button className="ls-primary" onClick={clear}>Clear filters</button> : emptyAction && <button className="ls-primary" onClick={onEmptyAction}>{emptyAction}</button>}
          </div>
        ) : (
          <>
            <div className="ls-grid" key={pulse}>
              {results.slice(0, shown).map((p, i) => <ProductCard key={p.id} p={p} i={i % PAGE} qty={cart[p.id] || 0} setQty={setQty} />)}
              {more && Array.from({ length: 4 }, (_, k) => <SkeletonCard key={"m" + k} i={k} />)}
            </div>
            <div ref={sentinel} className="ls-sentinel" aria-hidden="true" />
            {shown >= results.length && results.length > PAGE && (
              <p className="ls-end"><Icon n="check" size={14} />You've seen all {results.length} products
                <button className="ls-link" onClick={() => top.current?.scrollIntoView({ behavior: "smooth" })}>Back to top</button></p>
            )}
          </>
        )}
      </div>

      {/* phone: sort + filter bar and sheets */}
      <div className="ls-mbar">
        <button onClick={() => setSheet("sort")}><Icon n="sort" size={16} />Sort</button>
        <button onClick={() => setSheet("filter")}><Icon n="filter" size={16} />Filter{active > 0 && <em>{active}</em>}</button>
      </div>
      {sheet && (
        <div className="ls-sheet-wrap" onClick={() => setSheet(null)}>
          <div className={"ls-sheet ls-sheet-" + sheet} role="dialog" aria-modal="true" aria-label={sheet === "sort" ? "Sort" : "Filters"} onClick={(e) => e.stopPropagation()}>
            <span className="ls-grab" />
            {sheet === "sort" ? (
              <div className="ls-sortlist">
                <h3>Sort by</h3>
                {SORTS.map(([k, l]) => (
                  <button key={k} className={sort === k ? "ls-on" : ""} onClick={() => { setSort(k); setSheet(null); }}>
                    {l}<span className="ls-radio"><i /></span>
                  </button>
                ))}
              </div>
            ) : (
              <>
                <div className="ls-sheet-body">{filters}</div>
                <div className="ls-sheet-foot">
                  <button className="ls-ghost" onClick={clear}>Clear</button>
                  <button className="ls-primary" onClick={() => setSheet(null)}>Show {results.length} products</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- category page ---------------- */
export function CategoryPage({ slug, subSlug, cart, setQty }) {
  const nav = useContext(NavContext);
  const listRef = useRef(null);
  const path = subSlug ? `/browse/${slug}/${subSlug}` : `/browse/${slug}`;
  /* Every hook has to run before the not-found return below, so the fetch
     lives up here rather than next to the thing it feeds. */
  const { data, loading, error } = useResource(path, { deps: [slug, subSlug] });
  const { data: catalog } = useResource("/catalog");
  const items = useMemo(() => cards(data?.items), [data]);
  useEffect(() => { if (items.length) absorb(items); }, [items]);

  const c = data?.category;
  const subs = c?.subs || [];
  const sub = subSlug || "all";

  /* A 404 is the shop saying the category is not there. Anything else - still
     loading, or the shop unreachable - is not, and must not be dressed up as
     one, or every category flashes "not found" on its way in. */
  if (error?.status === 404) return <NotFoundView title="Category not found" text="The category you're looking for doesn't exist." />;
  if (error) {
    return (
      <div className="ls-empty" role="alert">
        <div className="ls-empty-art"><ProductArt art="Router" color="#1f3b4d" /></div>
        <h3>We can&apos;t reach the store</h3>
        <p>{error.message}</p>
        <button className="ls-primary" onClick={() => nav("category", slug)}>Try again</button>
      </div>
    );
  }
  if (!c && loading) return <div className="co-skel" aria-label="Loading"><span /><span /><span /></div>;
  if (!c) return <NotFoundView title="Category not found" text="The category you're looking for doesn't exist." />;

  const pick = (s) => {
    nav("category", s === "all" ? c.slug : `${c.slug}/${s}`, { replace: true, keepScroll: true });
    setTimeout(() => listRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };
  const others = (catalog?.categories || []).filter((x) => x.slug !== c.slug);
  const subName = subs.find((s) => s.slug === sub)?.name;

  return (
    <div className="cg-page" style={{ "--tone": c.tone, "--accent": c.accent }}>
      <Crumbs items={[["Home", ["home"]], [c.name, sub === "all" ? null : ["category", c.slug]], ...(sub !== "all" ? [[subName]] : [])]} />
      <header className="cg-hero">
        <div>
          <span className="cg-mode">{c.mode === "quick" ? <><Icon n="bolt" size={12} className="hm-fill" />Quick delivery</> : <><Icon n="truck" size={12} />Express delivery</>}</span>
          <h1>{c.name}</h1>
          <p>{c.blurb}{sub === "all" && items.length ? ` · ${items.length} products` : ""}</p>
        </div>
        <div className="cg-hero-art" aria-hidden="true">
          {items.slice(0, 3).map((p, k) => <span key={p.id} style={{ "--k": k }}><Thumb p={p} /></span>)}
        </div>
      </header>

      {!subs.length && !items.length && !loading ? (
        <div className="ls-empty cg-soon">
          <span className="ls-empty-art cg-soon-art"><Icon n="gift" size={40} /></span>
          <h3>{c.name} is coming soon</h3>
          <p>We&apos;re adding products to this category. Explore what&apos;s available today.</p>
          <div className="cg-soon-links">{others.slice(0, 4).map((o, k) => <button key={o.slug} style={{ "--k": k }} onClick={() => nav("category", o.slug)}>{o.name}<Icon n="right" size={14} /></button>)}</div>
        </div>
      ) : (
        <>
          {subs.length > 0 && (
            <section className="cg-subs" aria-label="Subcategories">
              <button className={"cg-sub" + (sub === "all" ? " cg-on" : "")} style={{ "--k": 0 }} onClick={() => pick("all")}>
                <span className="cg-sub-img cg-all"><Icon n="grid" size={26} /></span><span>All</span>
              </button>
              {subs.map((s, k) => (
                <button key={s.slug} className={"cg-sub" + (sub === s.slug ? " cg-on" : "")} style={{ "--k": k + 1 }} onClick={() => pick(s.slug)}>
                  {/* Only the subcategory being viewed has its products loaded, so
                      the others show the same placeholder the "All" tile uses
                      rather than borrowing somebody else's picture. */}
                  <span className={"cg-sub-img" + (sub === s.slug ? "" : " cg-all")}>
                    {sub === s.slug
                      ? items.slice(0, 2).map((p, n) => <span key={p.id} className={"cg-sub-pic cg-p" + n}><Thumb p={p} /></span>)
                      : <Icon n="box" size={24} />}
                  </span>
                  <span>{s.name}</span>
                </button>
              ))}
            </section>
          )}
          <div ref={listRef} className="cg-list-anchor" />
          <Listing key={c.slug + "/" + sub} items={items} loading={loading} cart={cart} setQty={setQty}
            heading={sub === "all" ? `All ${c.name}` : subName} />
        </>
      )}
    </div>
  );
}

/* ---------------- search results ---------------- */
const lev = (a, b) => {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
};

export const SCOPES = {
  quick: { label: "Quick", icon: "bolt", note: "Delivery in 10–20 minutes" },
  express: { label: "Express", icon: "truck", note: "Delivery in 2 days or more" },
};
const otherScope = (s) => (s === "quick" ? "express" : "quick");
const scopeOf = (p) => (p.delivery ? "express" : "quick");
const singular = (w) => (w.length > 4 && /(sh|ch|x|ss)es$/.test(w) ? w.slice(0, -2) : w.length > 3 && w.endsWith("s") && !w.endsWith("ss") ? w.slice(0, -1) : w);

/* Matches first (name hits rank highest), then related products from the same
   subcategories — e.g. "neem" → neem soaps, then the other bath soaps.
   A block with nothing matched falls back to the same categories, so Express
   still offers combos when only Quick had a direct hit. */
export function searchCatalog(all, term) {
  const words = term.toLowerCase().split(/\s+/).filter(Boolean).map(singular);
  if (!words.length) return { quick: [], express: [], matches: 0 };
  const pop = (a, b) => b.popularity - a.popularity;
  const hits = all
    .map((p) => {
      const hay = `${p.name} ${p.brand} ${p.catName || ""} ${p.subName || ""} ${p.unit || ""}`.toLowerCase();
      const name = p.name.toLowerCase();
      const n = words.filter((w) => hay.includes(w)).length;
      return [p, n, (name.startsWith(words[0]) ? 3 : 0) + words.filter((w) => name.includes(w)).length * 2 + (p.brand?.toLowerCase().includes(words[0]) ? 1 : 0)];
    })
    .filter(([, n]) => n === words.length)
    .sort((a, b) => b[2] - a[2] || pop(a[0], b[0]))
    .map(([p]) => p);
  const matched = new Set(hits.map((p) => p.id));
  const subs = new Set(hits.filter((p) => p.sub).map((p) => p.cat + "/" + p.sub));
  const cats = new Set(hits.filter((p) => p.cat).map((p) => p.cat));
  const related = all.filter((p) => !matched.has(p.id) && p.sub && subs.has(p.cat + "/" + p.sub)).sort(pop);
  const out = { matches: hits.length };
  ["quick", "express"].forEach((sc) => {
    let list = [...hits.filter((p) => scopeOf(p) === sc), ...related.filter((p) => scopeOf(p) === sc)];
    if (!list.length && hits.length) list = all.filter((p) => scopeOf(p) === sc && p.cat && cats.has(p.cat)).sort(pop).slice(0, 10);
    out[sc] = list;
  });
  return out;
}

function ScopeWord({ scope }) {
  const s = SCOPES[scope];
  return <span className={"sp-word sp-word-" + scope}><Icon n={s.icon} size={13} className={scope === "quick" ? "hm-fill" : ""} />{s.label}</span>;
}

/* JioMart-style chip bar: Sort by · Brands · Price · Discount · All filters.
   Chips open a popover (bottom sheet on phones); results update live. */
/* The bounds are this page's own choice of bands; the labels are not -
   they name real prices, so they are printed in the money those prices are
   quoted in. They read "Under ₹100" against an Omani shelf before. */
const PRICE_BANDS = [[0, 99], [100, 499], [500, 999], [1000, Infinity]];
const bandLabel = ([lo, hi]) =>
  (hi === Infinity ? `${money(lo)} & above` : lo === 0 ? `Under ${money(hi + 1)}` : `${money(lo)} – ${money(hi)}`);

function FilterBar({ F, onAll }) {
  const { facets, f, setF, clear, sort, setSort, active, priceOn, results } = F;
  const [open, setOpen] = useState(null); // { k, r }
  const [brandQ, setBrandQ] = useState("");
  const [phone, setPhone] = useState(false);
  /* the popover is portalled to .hm-page so the sticky toolbar's stacking context can't trap it under the header */
  const barRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(null);
    const key = (e) => e.key === "Escape" && close();
    const onScroll = () => { if (!phone) close(); };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", close);
    window.addEventListener("keydown", key);
    if (phone) document.documentElement.classList.add("ls-lock");
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", close); window.removeEventListener("keydown", key); document.documentElement.classList.remove("ls-lock"); };
  }, [open, phone]);
  const toggle = (k, e) => {
    if (open?.k === k) return setOpen(null);
    setPhone(window.innerWidth < 600);
    setBrandQ("");
    setOpen({ k, r: e.currentTarget.getBoundingClientRect() });
  };
  const sortLabel = SORTS.find(([k]) => k === sort)?.[1];
  const pct = (v) => ((v - facets.min) / Math.max(1, facets.max - facets.min)) * 100;
  /* Labelled at render, not at import: the shop says what money looks like
     a moment after the page starts. */
  const buckets = PRICE_BANDS.filter(([a, b]) => b >= facets.min && a <= facets.max)
    .map((b) => [b[0], b[1], bandLabel(b)]);
  const brands = facets.brands.filter(([b]) => b.toLowerCase().includes(brandQ.toLowerCase()));

  const chip = (k, label, on, extra) => (
    <button className={"sp-chip" + (on ? " sp-on" : "") + (open?.k === k ? " sp-open" : "")} onClick={(e) => toggle(k, e)} aria-expanded={open?.k === k} aria-haspopup="dialog">
      {k === "sort" && <Icon n="sort" size={14} />}{label}{extra}{k !== "all" && <Icon n="chev" size={14} className="sp-chip-chev" />}
    </button>
  );
  const body = open && {
    sort: (
      <div className="ls-sortlist sp-pop-list">
        {SORTS.map(([k, l], n) => (
          <button key={k} className={sort === k ? "ls-on" : ""} style={{ "--n": n }} onClick={() => { setSort(k); setOpen(null); }}>{l}<span className="ls-radio"><i /></span></button>
        ))}
      </div>
    ),
    brand: (
      <div className="sp-pop-body">
        {facets.brands.length > 6 && <input className="ls-brand-q" placeholder="Search brand" value={brandQ} onChange={(e) => setBrandQ(e.target.value)} autoFocus={!phone} />}
        <div className="ls-checks">
          {brands.map(([b, n]) => (
            <label key={b} className="ls-check">
              <input type="checkbox" checked={f.brands.includes(b)} onChange={() => setF({ brands: f.brands.includes(b) ? f.brands.filter((x) => x !== b) : [...f.brands, b] })} />
              <span className="ls-box"><Icon n="check" size={11} /></span>{b}<small>{n}</small>
            </label>
          ))}
          {!brands.length && <p className="sp-pop-none">No brand matches “{brandQ}”</p>}
        </div>
      </div>
    ),
    price: (
      <div className="sp-pop-body">
        <div className="ls-pills sp-buckets">
          {buckets.map(([a, b, l]) => {
            const lo = Math.max(facets.min, a), hi = Math.min(facets.max, b);
            const on = f.price[0] === lo && f.price[1] === hi && priceOn;
            return <button key={l} className={on ? "ls-on" : ""} onClick={() => setF({ price: on ? [facets.min, facets.max] : [lo, hi] })}>{l}</button>;
          })}
        </div>
        <div className="ls-range" style={{ "--a": pct(f.price[0]) + "%", "--b": pct(f.price[1]) + "%" }}>
          <div className="ls-range-track"><i /></div>
          <input type="range" min={facets.min} max={facets.max} value={f.price[0]} aria-label="Minimum price" onChange={(e) => setF({ price: [Math.min(+e.target.value, f.price[1]), f.price[1]] })} />
          <input type="range" min={facets.min} max={facets.max} value={f.price[1]} aria-label="Maximum price" onChange={(e) => setF({ price: [f.price[0], Math.max(+e.target.value, f.price[0])] })} />
        </div>
        <div className="ls-range-vals"><span>{money(f.price[0])}</span><span>{money(f.price[1])}</span></div>
      </div>
    ),
    discount: (
      <div className="sp-pop-body">
        <div className="ls-pills">
          {DISCOUNTS.map((d) => <button key={d} className={f.discount === d ? "ls-on" : ""} onClick={() => setF({ discount: d })}>{d ? `${d}% or more` : "Any"}</button>)}
        </div>
      </div>
    ),
  }[open.k];
  const titles = { sort: "Sort by", brand: "Brands", price: "Price", discount: "Discount" };
  const W = 300;
  const place = open && !phone ? { left: Math.max(12, Math.min(open.r.left, window.innerWidth - W - 12)), top: open.r.bottom + 8, width: W } : undefined;

  return (
    <>
      <div className="sp-bar2" role="toolbar" aria-label="Sort and filter" ref={barRef}>
        {chip("sort", sort === "relevance" ? "Sort by" : sortLabel, sort !== "relevance")}
        {facets.brands.length > 1 && chip("brand", "Brands", f.brands.length > 0, f.brands.length > 0 && <em key={f.brands.length}>{f.brands.length}</em>)}
        {facets.max > facets.min && chip("price", "Price", priceOn)}
        {chip("discount", f.discount ? `${f.discount}%+ off` : "Discount", !!f.discount)}
        <button className={"sp-chip sp-chip-all" + (active ? " sp-on" : "")} onClick={() => { setOpen(null); onAll(); }}>
          <Icon n="filter" size={14} />All filters{active > 0 && <em key={active}>{active}</em>}
        </button>
        {active > 0 && <button className="ls-link sp-clear-all" onClick={clear}>Clear all</button>}
      </div>
      {open && body && barRef.current && createPortal(
        <div className={"sp-pop-wrap" + (phone ? " sp-pop-phone" : "")} onClick={() => setOpen(null)}>
          <div className="sp-pop" role="dialog" aria-label={titles[open.k]} style={place} onClick={(e) => e.stopPropagation()}>
            {phone && <span className="ls-grab" />}
            <div className="sp-pop-head"><b>{titles[open.k]}</b><button onClick={() => setOpen(null)} aria-label="Close"><Icon n="x" size={16} /></button></div>
            {body}
            {open.k !== "sort" && (
              <div className="sp-pop-foot">
                <span key={results.length} className="sp-pop-count">{results.length} {results.length === 1 ? "product" : "products"}</span>
                <button className="ls-primary" onClick={() => setOpen(null)}>Done</button>
              </div>
            )}
          </div>
        </div>,
        barRef.current.closest(".hm-page") || document.body
      )}
    </>
  );
}

function FilterDrawer({ F, onClose }) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const k = (e) => e.key === "Escape" && closeRef.current();
    document.documentElement.classList.add("ls-lock");
    window.addEventListener("keydown", k);
    return () => { window.removeEventListener("keydown", k); document.documentElement.classList.remove("ls-lock"); };
  }, []);
  return (
    <div className="sp-drawer-wrap" onClick={onClose}>
      <aside className="sp-drawer" role="dialog" aria-modal="true" aria-label="All filters" onClick={(e) => e.stopPropagation()}>
        <button className="sp-drawer-x" onClick={onClose} aria-label="Close filters"><Icon n="x" size={18} /></button>
        <div className="ls-sheet-body"><Filters facets={F.facets} f={{ ...F.f, active: F.active }} setF={F.setF} onClear={F.clear} /></div>
        <div className="ls-sheet-foot">
          <button className="ls-ghost" onClick={F.clear}>Clear</button>
          <button className="ls-primary" onClick={onClose}>Show {F.results.length} products</button>
        </div>
      </aside>
    </div>
  );
}

export function SearchResults({ q, cart, setQty, mode = "quick" }) {
  const nav = useContext(NavContext);
  const term = q.trim();
  /* The corpus is what the shop returned for this search, not whatever the
     browser happens to be holding - which could only ever find what was
     already on screen. */
  const { data, loading: fetching, error: searchError } = useResource(term ? `/search?q=${encodeURIComponent(term)}` : null, { enabled: !!term, deps: [term] });
  const { data: catalog } = useResource("/catalog");
  const all = useMemo(() => cards(data?.items), [data]);
  useEffect(() => { if (all.length) absorb(all); }, [all]);
  const found = useMemo(() => searchCatalog(all, term), [all, term]);
  const pref = mode === "all" ? "express" : "quick";
  const firstScope = found[pref].length || !found[otherScope(pref)].length ? pref : otherScope(pref);
  const [scope, setScope] = useState(firstScope);
  useEffect(() => { setScope(firstScope); }, [term]); // eslint-disable-line
  const other = otherScope(scope);
  const items = found[scope];
  const F = useProductFilters(items);

  const [shown, setShown] = useState(PAGE);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [drawer, setDrawer] = useState(false);
  useEffect(() => { setShown(PAGE); }, [F.pulse, F.sig]);
  useEffect(() => { setLoading(fetching); }, [fetching, F.sig]);

  /* sliding thumb behind the Quick / Express pills */
  const seg = useRef(null);
  const [thumb, setThumb] = useState(null);
  useLayoutEffect(() => {
    const el = seg.current?.querySelector('[aria-selected="true"]');
    if (el) setThumb({ x: el.offsetLeft, w: el.offsetWidth });
  }, [scope, found]);

  const switchScope = (s) => {
    if (s === scope) return;
    setScope(s);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const showMore = () => { setMore(true); setTimeout(() => { setShown((n) => n + PAGE); setMore(false); }, 480); };

  const vocab = useMemo(() => [...new Set(all.flatMap((p) => `${p.name} ${p.brand} ${p.subName || ""}`.toLowerCase().split(/[^a-z]+/)).filter((w) => w.length > 3))], [all]);
  const suggestion = useMemo(() => {
    if (found.matches || !term) return null;
    const w = term.toLowerCase().split(/\s+/)[0];
    let best = null, bd = w.length > 5 ? 3 : 2;
    vocab.forEach((v) => { const d = lev(w, v); if (d <= bd && (!best || d < bd)) { bd = d; best = v; } });
    return best;
  }, [found.matches, term, vocab]);
  const cats = useMemo(() => {
    const m = {};
    [...found.quick, ...found.express].forEach((p) => { if (p.cat && !m[p.cat + "/" + p.sub]) m[p.cat + "/" + p.sub] = [p.subName, p.cat + "/" + p.sub]; });
    return Object.values(m).slice(0, 6);
  }, [found]);
  const total = found.quick.length + found.express.length;

  if (!term || !total) {
    return (
      <div className="sp-page">
        <div className="ls-empty sp-empty">
          <span className="ls-empty-art"><ProductArt art="Basket" /></span>
          <h3>{term ? <>No results for “{q}”</> : "Search 369 Mart"}</h3>
          {suggestion
            ? <p className="sp-dym">Did you mean <button onClick={() => nav("search", suggestion)}>“{suggestion}”</button>?</p>
            : <p>{term ? "Check the spelling, or try a more general word like “ssd”, “keyboard” or “router”." : "Find processors, monitors, peripherals and more."}</p>}
          <div className="cg-soon-links">
            {(catalog?.categories || []).slice(0, 5).map((c, k) => <button key={c.slug} style={{ "--k": k }} onClick={() => nav("category", c.slug)}>{c.name}<Icon n="right" size={14} /></button>)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="sp-page">
      <div className="sp-tools">
        <div className="sp-scope" role="tablist" aria-label="Delivery type" ref={seg}>
          {thumb && <span className={"sp-scope-thumb sp-thumb-" + scope} style={{ transform: `translateX(${thumb.x}px)`, width: thumb.w }} aria-hidden="true" />}
          {["quick", "express"].map((sc) => (
            <button key={sc} role="tab" aria-selected={scope === sc} className={"sp-scope-btn sp-sc-" + sc} onClick={() => switchScope(sc)}>
              <Icon n={SCOPES[sc].icon} size={13} className={sc === "quick" ? "hm-fill" : ""} />{SCOPES[sc].label}<small>{found[sc].length}</small>
            </button>
          ))}
        </div>
        {items.length > 0 && <FilterBar key={scope + term} F={F} onAll={() => setDrawer(true)} />}
      </div>

      <section className={"sp-sec sp-sec-" + scope} key={"main-" + scope + term}>
        <div className="sp-sec-head">
          <h2>Showing results for <q>{q}</q> in <ScopeWord scope={scope} /></h2>
          <p>{SCOPES[scope].note}{items.length ? <> · <span key={F.results.length + "-" + F.pulse} className="ls-count-n">{F.results.length} products</span></> : null}</p>
        </div>
        {cats.length > 0 && (
          <div className="sp-related">
            <span>In categories:</span>
            {cats.map(([name, path], k) => <button key={path} style={{ "--k": k }} onClick={() => nav("category", path)}>{name}</button>)}
          </div>
        )}
        {F.chips.length > 0 && (
          <div className="ls-chips">
            {F.chips.map(([label, off], k) => <button key={label} className="ls-chip" style={{ "--k": k }} onClick={off}>{label}<Icon n="x" size={12} /></button>)}
            <button className="ls-link" onClick={F.clear}>Clear all</button>
          </div>
        )}

        {!items.length ? (
          <div className="sp-none">
            <span><Icon n={SCOPES[scope].icon} size={18} /></span>
            <p>No {SCOPES[scope].label} results for <q>{q}</q>.</p>
            <button className="ls-primary" onClick={() => switchScope(other)}>See {found[other].length} results in {SCOPES[other].label}</button>
          </div>
        ) : loading ? (
          <div className="ls-grid sp-grid">{Array.from({ length: 10 }, (_, k) => <SkeletonCard key={k} i={k} />)}</div>
        ) : !F.results.length ? (
          <div className="ls-empty">
            <span className="ls-empty-art"><ProductArt art="Basket" /></span>
            <h3>No products match these filters</h3>
            <p>Try removing a filter or two.</p>
            <button className="ls-primary" onClick={F.clear}>Clear filters</button>
          </div>
        ) : (
          <>
            <div className="ls-grid sp-grid" key={F.pulse}>
              {F.results.slice(0, shown).map((p, i) => <ProductCard key={p.id} p={p} i={i % PAGE} qty={cart[p.id] || 0} setQty={setQty} />)}
              {more && Array.from({ length: 5 }, (_, k) => <SkeletonCard key={"m" + k} i={k} />)}
            </div>
            {shown < F.results.length ? (
              <button className={"sp-more" + (more ? " sp-busy" : "")} onClick={showMore} disabled={more}>
                {more ? <i className="sp-spin" aria-hidden="true" /> : null}Show more results from <ScopeWord scope={scope} /><small>{F.results.length - shown} more</small>
              </button>
            ) : F.results.length > PAGE ? (
              <p className="ls-end"><Icon n="check" size={14} />That's all {F.results.length} {SCOPES[scope].label} results</p>
            ) : null}
          </>
        )}
      </section>

      {found[other].length > 0 && (
        <section className={"sp-sec sp-alt sp-alt-" + other} key={"alt-" + other + term}>
          <div className="sp-sec-head">
            <h2>Showing results for <q>{q}</q> in <ScopeWord scope={other} /></h2>
            <p>{SCOPES[other].note}</p>
          </div>
          <div className="sp-row">
            {found[other].slice(0, 5).map((p, i) => <ProductCard key={p.id} p={p} i={i} qty={cart[p.id] || 0} setQty={setQty} />)}
          </div>
          <button className="sp-more sp-more-alt" onClick={() => switchScope(other)}>
            See all {found[other].length} results in <ScopeWord scope={other} /><Icon n="right" size={15} />
          </button>
        </section>
      )}

      {drawer && <FilterDrawer F={F} onClose={() => setDrawer(false)} />}
    </div>
  );
}

/* ---------------- offers ---------------- */
function useCountdown() {
  const [now, setNow] = useState(null); /* null on the server render, so hydration matches */
  useEffect(() => { setNow(Date.now()); const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  if (now === null) return ["--", "--", "--"];
  const end = new Date(now); end.setHours(23, 59, 59, 999);
  const s = Math.max(0, Math.floor((end - now) / 1000));
  return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60].map((n) => String(n).padStart(2, "0"));
}

export function OffersPage({ cart, setQty }) {
  const [h, m, s] = useCountdown();
  const [min, setMin] = useState(0);
  const [copied, setCopied] = useState("");
  /* Deriving this from the browsed store would show a shopper only the deals
     they had already walked past. The shop knows them all. */
  const { data, loading: fetching } = useResource("/offers");
  const { coupons } = useRules();
  const deals = useMemo(() => cards(data?.deals), [data]);
  useEffect(() => { if (deals.length) absorb(deals); }, [deals]);
  const shown = deals.filter((p) => p.off >= min);
  const copy = async (code) => {
    try { await navigator.clipboard.writeText(code); } catch (e) { /* clipboard blocked: still show the state */ }
    setCopied(code); setTimeout(() => setCopied(""), 1800);
  };
  return (
    <div className="of-page">
      <Crumbs items={[["Home", ["home"]], ["Offers"]]} />
      <header className="of-hero">
        <div>
          <span className="of-kicker"><Icon n="pct" size={14} />Deals of the day</span>
          <h1>Up to {deals[0]?.off || 0}% off across 369 Mart</h1>
          <p>Prices reset at midnight.</p>
        </div>
        <div className="of-timer" aria-label={`Ends in ${h} hours ${m} minutes`}>
          {[[h, "hrs"], [m, "min"], [s, "sec"]].map(([v, l], k) => (
            <span key={l} className="of-cell"><b key={v}>{v}</b><small>{l}</small></span>
          ))}
        </div>
      </header>

      <section className="of-coupons" aria-label="Coupons">
        <h2>Coupons for you</h2>
        <div className="of-coupon-row">
          {coupons.map((c, k) => (
            <article key={c.code} className="of-coupon" style={{ "--k": k }}>
              <div className="of-coupon-l"><Icon n="ticket" size={22} /></div>
              <div className="of-coupon-r">
                <b>{c.title}</b>
                <small>{c.note}</small>
                <button className={copied === c.code ? "of-copied" : ""} onClick={() => copy(c.code)}>
                  <span>{c.code}</span><em>{copied === c.code ? <><Icon n="check" size={12} />Copied</> : "Copy"}</em>
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="of-deals">
        <div className="of-deals-head">
          <h2>Top deals</h2>
          <div className="ls-pills">
            {[0, 20, 30, 40].map((d) => <button key={d} className={min === d ? "ls-on" : ""} onClick={() => setMin(d)}>{d ? `${d}%+ off` : "All deals"}</button>)}
          </div>
        </div>
        <div className="ls-grid" key={min}>
          {shown.map((p, i) => <ProductCard key={p.id} p={p} i={i % 12} qty={cart[p.id] || 0} setQty={setQty} />)}
        </div>
      </section>
    </div>
  );
}

/* ---------------- buy again ---------------- */
export function BuyAgainPage({ byId, cart, setQty, orders = [] }) {
  const nav = useContext(NavContext);
  const bought = useMemo(() => {
    const m = {};
    orders.filter((o) => o.status !== "cancelled").forEach((o) => o.items.forEach(([id, q]) => {
      if (!byId[id]) return;
      m[id] = m[id] || { p: byId[id], times: 0, qty: 0, last: o.at };
      m[id].times += 1; m[id].qty += q;
    }));
    return Object.values(m);
  }, [orders, byId]);
  const last = orders.find((o) => o.status !== "cancelled");
  const reorderAll = (el) => {
    flyTo(el, "#hm-cart-icon");
    last.items.forEach(([id, q]) => byId[id] && byId[id].stock !== 0 && setQty(id, (cart[id] || 0) + q));
  };
  return (
    <div className="ba-page">
      <Crumbs items={[["Home", ["home"]], ["Buy again"]]} />
      <header className="ba-head">
        <div><h1>Buy again</h1><p>Your usual items, one tap away.</p></div>
        {last && (
          <div className="ba-last">
            <span className="ba-thumbs">{last.items.slice(0, 3).map(([id]) => byId[id] && <span key={id}><Thumb p={byId[id]} /></span>)}</span>
            <span className="ba-last-txt"><b>Last order · {fmtPlaced(last.at)}</b><small>{last.items.length} items · {money(last.total)}</small></span>
            <button className="ls-primary" onClick={(e) => reorderAll(e.currentTarget)}>Reorder all</button>
          </div>
        )}
      </header>
      {bought.length ? (
        <div className="ls-grid ba-grid">
          {bought.map(({ p, times, last: when }, i) => (
            <div key={p.id} className="ba-item" style={{ "--i": i }}>
              <ProductCard p={p} i={i} qty={cart[p.id] || 0} setQty={setQty} />
              <span className="ba-meta"><Icon n="reorder" size={12} />Bought {times}× · {when}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="ls-empty">
          <span className="ls-empty-art"><ProductArt art="Basket" /></span>
          <h3>Nothing to buy again yet</h3>
          <p>Items from your delivered orders will show up here.</p>
          <button className="ls-primary" onClick={() => nav("home")}>Start shopping</button>
        </div>
      )}
    </div>
  );
}

/* ---------------- footer ---------------- */
export function SiteFooter() {
  const nav = useContext(NavContext);
  const [ref, setRef] = useState(null);
  const [inView, setIn] = useState(false);
  useEffect(() => {
    if (!ref || typeof IntersectionObserver === "undefined") return setIn(true);
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setIn(true); io.disconnect(); } }, { rootMargin: "0px 0px -10% 0px" });
    io.observe(ref);
    return () => io.disconnect();
  }, [ref]);
  /* The shop's own sections, from the shop. Hard-coding them here is how the
     footer ended up advertising groceries long after the shop stopped selling
     them - rename a section in Odoo and this follows. If it cannot be reached
     the column is simply shorter; it never guesses. */
  const { data: catalog } = useResource("/catalog");
  const shop = (catalog?.categories || []).map((c) => [c.name, () => nav("category", c.slug)]);
  const cols = [
    ["Shop", shop.concat([["Offers", () => nav("offers")]])],
    ["Help", [["Track your order", () => nav("account")], ["Cancellations & returns", null], ["Delivery areas", null], ["FAQs", () => nav("account")], ["Contact us", null]]],
    ["Company", [["About 369 Mart", null], ["Careers", null], ["Sell on 369 Mart", null], ["Press", null]]],
    ["Policies", [["Terms of use", null], ["Privacy policy", null], ["Shipping policy", null], ["Grievance redressal", null]]],
  ];
  return (
    <footer className={"ft" + (inView ? " ft-in" : "")} ref={setRef}>
      <div className="hm-wrap">
        <div className="ft-top">
          <div className="ft-brand">
            <a className="ft-logo" href="/" onClick={(e) => { e.preventDefault(); nav("home"); }}>369<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 18 18 6M9 6h9v9" /></svg>Mart</a>
            <p>Computer parts and gear. In minutes, or in days.</p>
            <div className="ft-apps">
              <a href="#" onClick={(e) => e.preventDefault()}><Icon n="phone" size={16} /><span><small>Get it for</small>Android</span></a>
              <a href="#" onClick={(e) => e.preventDefault()}><Icon n="phone" size={16} /><span><small>Get it for</small>iPhone</span></a>
            </div>
          </div>
          {cols.map(([title, links], k) => (
            <nav key={title} className="ft-col" style={{ "--k": k }} aria-label={title}>
              <h4>{title}</h4>
              {links.map(([l, fn]) => <a key={l} href="#" onClick={(e) => { e.preventDefault(); fn?.(); }}>{l}</a>)}
            </nav>
          ))}
        </div>
        <div className="ft-pay">
          <span>We accept</span>
          {["UPI", "Credit & debit cards", "Net banking", "Cash on delivery", "369 Wallet"].map((x, k) => <em key={x} style={{ "--k": k }}>{x}</em>)}
        </div>
        <div className="ft-bottom">
          <span>© {new Date().getFullYear()} 369 Mart. All rights reserved.</span>
          <button className="ft-top-btn" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}><Icon n="chev" size={16} />Back to top</button>
        </div>
      </div>
    </footer>
  );
}

/* ---------------- not found ---------------- */
export function NotFoundView({ title = "Page not found", text = "The page you're looking for has moved or never existed." }) {
  const nav = useContext(NavContext);
  const [q, setQ] = useState("");
  return (
    <div className="nf">
      <div className="nf-art" aria-hidden="true">
        <span className="nf-4">4</span>
        <span className="nf-basket"><ProductArt art="Basket" /><i className="nf-drop d1" /><i className="nf-drop d2" /></span>
        <span className="nf-4">4</span>
      </div>
      <h1>{title}</h1>
      <p>{text}</p>
      <form className="sp-bar nf-search" onSubmit={(e) => { e.preventDefault(); if (q.trim()) nav("search", q.trim()); }}>
        <Icon n="search" size={18} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search 369 Mart" aria-label="Search" />
        <button className="ls-primary" type="submit">Search</button>
      </form>
      <button className="ls-ghost" onClick={() => nav("home")}><Icon n="home" size={16} />Back to home</button>
    </div>
  );
}
