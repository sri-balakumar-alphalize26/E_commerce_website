"use client";
/* "Choose products" for a home page row.

   Top: the row as shoppers will see it - its title and subtitle and the
   products ticked so far, in the order they were ticked, drawn with the
   shop's own cards (six fit, then the arrow, as on the home page).
   Left: every category and sub-category with how many products it holds.
   Right: search, filters and a tick box per product.

   A row holds at most 12 (mart369_home `PICK_MAX`); at 12 a yellow bar says
   so and the other boxes stop. Saving makes the row hand-picked with exactly
   these products, in this order (PUT .../bands/section/<id>/products). */
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ProductCard, useRailScroll } from "@/components/home/shared";
import { api } from "@/lib/api";
import { money, setCurrency } from "@/lib/money";
import { Confirm, Icon } from "./AdminUI";

export const PICK_MAX = 12;

const STOCK_LABEL = { ok: "In stock", low: "Low", out: "Out" };

/* A picker row as the shop's card draws it - a bigger picture than the list's. */
const asCard = (p, stock) => ({
  id: String(p.id), name: p.name, price: p.price || 0, unit: "",
  images: p.image ? [p.image.replace(/image_128$/, "image_512")] : [],
  ...(stock === "out" ? { stock: 0 } : {}),
});

function PreviewRow({ title, subtitle, items, onUntick }) {
  const { ref, edge, by } = useRailScroll();
  return (
    <section className="hm-rail hm-in rp-rail">
      <div className="hm-rail-head"><div><h2>{title || "Untitled row"}</h2>{subtitle && <p>{subtitle}</p>}</div></div>
      <div className="hm-rail-box">
        <div className="hm-rail-track" ref={ref}>
          {items.map((p, i) => (
            <div key={p.id} className="rp-card">
              <ProductCard p={p} i={i} qty={0} setQty={() => {}} />
              <span className="rp-order" aria-hidden="true">{i + 1}</span>
              <button type="button" className="rp-untick" onClick={() => onUntick(p.id)} aria-label={`Take ${p.name} out of the row`}><Icon n="x" size={13} /></button>
            </div>
          ))}
          {!items.length && <div className="rp-empty-row">Tick products below - they appear here one by one, in the order you tick them.</div>}
        </div>
        {!edge.start && <button className="hm-arrow hm-arrow-l" onClick={() => by(-1)} aria-label="Scroll left"><Icon n="left" size={18} /></button>}
        {!edge.end && <button className="hm-arrow hm-arrow-r" onClick={() => by(1)} aria-label="Scroll right"><Icon n="right" size={18} /></button>}
      </div>
    </section>
  );
}

export default function RowProductPicker({ row, initial = [], onClose, onSaved }) {
  /* The ticked products, in tick order, as cards. Starts from what the row
     already hand-picks (the editor passes its cards). */
  const [ticked, setTicked] = useState(initial);
  const startIds = useRef(initial.map((p) => p.id).join(","));
  const [categ, setCateg] = useState("all");
  const [open, setOpen] = useState({});
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [inStock, setInStock] = useState(false);
  const [onlyTicked, setOnlyTicked] = useState(false);
  const [sort, setSort] = useState("name");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [asking, setAsking] = useState(false);

  /* Search waits for a pause in typing. */
  useEffect(() => { const t = setTimeout(() => setTerm(q.trim()), 300); return () => clearTimeout(t); }, [q]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    const qs = new URLSearchParams();
    if (categ !== "all") qs.set("categ_id", categ);
    if (term) qs.set("q", term);
    api("/admin/product/catalog" + (qs.toString() ? "?" + qs : ""), { fresh: true })
      .then((d) => { if (!live) return; if (d?.currency) setCurrency(d.currency); setData(d); setError(""); })
      .catch((e) => live && setError(e?.message || "The products could not be loaded."))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [categ, term]);

  useEffect(() => {
    const k = (e) => { if (e.key === "Escape" && !asking) tryClose(); };
    window.addEventListener("keydown", k);
    document.documentElement.classList.add("ad-lock");
    return () => { window.removeEventListener("keydown", k); document.documentElement.classList.remove("ad-lock"); };
  }); // eslint-disable-line

  /* The flat category list as a tree: top level, then what sits under each. */
  const tree = useMemo(() => {
    const cats = data?.categories || [];
    const kids = {};
    cats.forEach((c) => { (kids[c.parent_id || 0] ||= []).push(c); });
    return { tops: kids[0] || [], kids };
  }, [data]);

  const stock = data?.stock || {};
  const stateOf = (id) => stock[id]?.[1];
  const tickedIds = useMemo(() => new Set(ticked.map((p) => p.id)), [ticked]);
  const full = ticked.length >= PICK_MAX;

  const list = useMemo(() => {
    let rows = data?.products || [];
    if (inStock) rows = rows.filter((p) => stateOf(p.id) !== "out");
    if (onlyTicked) rows = rows.filter((p) => tickedIds.has(String(p.id)));
    rows = [...rows];
    if (sort === "price-up") rows.sort((a, b) => (a.price || 0) - (b.price || 0));
    else if (sort === "price-down") rows.sort((a, b) => (b.price || 0) - (a.price || 0));
    return rows;
  }, [data, inStock, onlyTicked, sort, tickedIds]); // eslint-disable-line

  const toggle = (p) => {
    const id = String(p.id);
    if (tickedIds.has(id)) setTicked((t) => t.filter((x) => x.id !== id));
    else if (!full) setTicked((t) => [...t, asCard(p, stateOf(p.id))]);
  };
  const untick = (id) => setTicked((t) => t.filter((x) => x.id !== id));
  const changed = ticked.map((p) => p.id).join(",") !== startIds.current;
  const tryClose = () => (changed ? setAsking(true) : onClose());

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const res = await api(`/admin/home/bands/section/${row.id}/products`, {
        method: "PUT", body: { ids: ticked.map((p) => Number(p.id)) },
      });
      api.invalidate("/home");
      onSaved?.(res);
      onClose();
    } catch (e) {
      setError(e?.message || "The row could not be saved. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const catButton = (c, depth) => (
    <div key={c.id}>
      <div className={"rp-cat" + (String(categ) === String(c.id) ? " rp-on" : "")} style={{ "--d": depth }}>
        {tree.kids[c.id]?.length
          ? <button type="button" className="rp-twist" aria-label={open[c.id] ? "Hide sub-categories" : "Show sub-categories"} onClick={() => setOpen((o) => ({ ...o, [c.id]: !o[c.id] }))}><Icon n={open[c.id] ? "chev" : "right"} size={13} /></button>
          : <span className="rp-twist" />}
        <button type="button" className="rp-cat-name" onClick={() => setCateg(String(c.id))}>{c.name}<em>{c.count}</em></button>
      </div>
      {open[c.id] && (tree.kids[c.id] || []).map((k) => catButton(k, depth + 1))}
    </div>
  );

  if (typeof document === "undefined") return null;
  return createPortal(
    <>
    <div className="rp-wrap" onClick={tryClose}>
      <div className="rp" role="dialog" aria-modal="true" aria-label={`Choose products for ${row.name || "this row"}`} onClick={(e) => e.stopPropagation()}>
        <header className="rp-head">
          <div><h3>Choose products for “{row.name || "this row"}”</h3><p>Tick up to {PICK_MAX}. They show in the order you tick them.</p></div>
          <button className="ad-icon-btn" onClick={tryClose} aria-label="Close"><Icon n="x" size={17} /></button>
        </header>

        <div className="rp-preview">
          <div className="rp-preview-top">
            <span className="rp-label">Preview - how shoppers will see this row</span>
            <span className={"rp-count" + (full ? " rp-count-full" : "")}>{ticked.length} of {PICK_MAX}</span>
          </div>
          <div className="hm-page rp-stage">
            <PreviewRow key={ticked.length} title={row.name} subtitle={row.subtitle} items={ticked} onUntick={untick} />
          </div>
          {full && <p className="rp-full" role="status"><Icon n="info" size={15} />You&apos;ve reached {PICK_MAX} - this row is full. Untick one to add another.</p>}
        </div>

        <div className="rp-body">
          <nav className="rp-cats" aria-label="Categories">
            <span className="rp-label">Categories</span>
            <div className={"rp-cat" + (categ === "all" ? " rp-on" : "")} style={{ "--d": 0 }}>
              <span className="rp-twist" />
              <button type="button" className="rp-cat-name" onClick={() => setCateg("all")}>All products<em>{data?.all_count ?? ""}</em></button>
            </div>
            {tree.tops.map((c) => catButton(c, 0))}
            <select className="rp-cat-select" value={categ} onChange={(e) => setCateg(e.target.value)} aria-label="Category">
              <option value="all">All products</option>
              {tree.tops.map((c) => [
                <option key={c.id} value={c.id}>{c.name} ({c.count})</option>,
                ...(tree.kids[c.id] || []).map((k) => <option key={k.id} value={k.id}>   › {k.name} ({k.count})</option>),
              ])}
            </select>
          </nav>

          <div className="rp-list">
            <div className="rp-tools">
              <label className="rp-search"><Icon n="search" size={16} />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or code" aria-label="Search products" />
              </label>
              <label className="rp-check"><input type="checkbox" checked={inStock} onChange={(e) => setInStock(e.target.checked)} />In stock only</label>
              <label className="rp-check"><input type="checkbox" checked={onlyTicked} onChange={(e) => setOnlyTicked(e.target.checked)} />Ticked only</label>
              <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
                <option value="name">Sort: Name</option>
                <option value="price-up">Price: low to high</option>
                <option value="price-down">Price: high to low</option>
              </select>
            </div>

            {error && <p className="rp-error" role="alert">{error}</p>}
            {loading && !data ? <p className="rp-note">Loading products…</p> : (
              <ul className={"rp-rows" + (loading ? " rp-busy" : "")}>
                {list.map((p) => {
                  const id = String(p.id);
                  const on = tickedIds.has(id);
                  const st = stateOf(p.id);
                  return (
                    <li key={id} className={"rp-row" + (on ? " rp-row-on" : "") + (!on && full ? " rp-row-off" : "")}>
                      <label>
                        <input type="checkbox" checked={on} disabled={!on && full} onChange={() => toggle(p)} />
                        <span className="rp-thumb">{p.image ? <img src={p.image} alt="" loading="lazy" /> : null}</span>
                        <span className="rp-name"><b>{p.name}</b>{p.code && <small>{p.code}</small>}</span>
                        <span className="rp-price">{money(p.price || 0)}</span>
                        {st && <span className={"rp-stock rp-" + st}>{STOCK_LABEL[st] || st}</span>}
                        {on && <span className="rp-pos">#{ticked.findIndex((x) => x.id === id) + 1}</span>}
                      </label>
                    </li>
                  );
                })}
                {!list.length && !loading && <li className="rp-note">Nothing matches. Try another category or a shorter search.</li>}
              </ul>
            )}
            {data && data.total > (data.products || []).length && (
              <p className="rp-note">Showing the first {(data.products || []).length} of {data.total}. Pick a category or search to find others.</p>
            )}
          </div>
        </div>

        <footer className="rp-foot">
          <span className="rp-foot-note">{changed ? "Not saved yet" : "No changes"}</span>
          <button className="ad-btn" onClick={tryClose}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={saving || !changed} onClick={save}>
            {saving ? "Saving…" : `Save row (${ticked.length} product${ticked.length === 1 ? "" : "s"})`}
          </button>
        </footer>
      </div>
    </div>
    {/* Outside the scrim: a click on this box must not also reach the
        scrim behind it, which would ask again. */}
    {asking && (
      <Confirm title="Leave without saving?" text="The products you ticked will not be saved."
        confirmLabel="Leave" cancelLabel="Keep choosing" danger
        onCancel={() => setAsking(false)} onConfirm={() => { setAsking(false); onClose(); }} />
    )}
    </>,
    document.body
  );
}
