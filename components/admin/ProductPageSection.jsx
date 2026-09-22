"use client";
/* ==========================================================================
   369 Mart — Admin · the product page

   The product page on the left, a panel on the right. Click a part of the
   page to change what it shows; the eye takes something off the page without
   deleting anything.

   The product page is not the home page, and the difference decides the
   screen. There is nothing here to add, delete or drag: the parts are fixed
   and the question is only which of them a shopper sees, and in what words.
   So the bands are an overlay measured from the real page rather than
   wrappers around it, and there are no handles.

   Two scopes, one switch at the top. "Whole shop" is the default for every
   product; "This product" is where one product is allowed to differ. Keeping
   that as a tab rather than a control on every row is what stops forty-eight
   fields turning into a wall.

   The parts come from the shop: one call to /admin/product/builder, which is
   mart369.product.field.builder_load() - the same call Odoo's own builder
   makes. Writes go back one field at a time, debounced, through the queue in
   editorKit.

   What this does NOT do yet: a shopper's page is still assembled by
   productDetails.js from a local sample, so switching something off changes
   this screen and the records behind it, and not yet the shop.
   ========================================================================== */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { useResource } from "@/lib/useFetch";
import { Confirm, Empty, Icon, Search, Switch } from "./AdminUI";
import { BandShell, ErrorStrip, Eye, SaveChip, uid, useAutosave } from "./editorKit";
import ProductDetail from "@/components/home/ProductDetail";
import { NavContext } from "@/components/home/nav";
import { OpenContext, WishContext } from "@/components/home/shared";
import "@/components/home/home.css";
import "./editor.css";
import "./productEditor.css";

/* Where each section of the page actually is, in the page's own markup.

   The overlay is measured from these. It is an enhancement and never the
   only way in: every section and every field is also reachable from the
   panel on the right, so a selector that drifts costs a convenience rather
   than the feature. */
const SECTION_AT = {
  gallery: ".pd-gallery",
  buy: ".pd-card.pd-buy",
  features: '[data-sec="features"]',
  info: '[data-sec="info"]',
  specs: '[data-sec="specs"]',
  description: '[data-sec="description"]',
  returns: '[data-sec="returns"]',
  reviews: "#pd-reviews",
  delivery: ".pd-deliver",
  bundle: ".pd-fbt",
  similar: ".pd-related",
};

/* The handful of fields that own a node of their own. The rest are rows in a
   table, and are edited from the panel. */
const FIELD_AT = {
  images: ".pd-stage",
  unit_tag: ".pd-unit-tag",
  brand: ".pd-brand",
  name: ".pd-name",
  rating_summary: ".pd-rating",
  price: ".pd-price > b",
  mrp: ".pd-price s",
  low_stock: ".pd-low",
  pack_sizes: ".pd-sizes",
  delivery_mode: ".pd-mode",
  features: ".pd-features",
  rating_bars: ".pd-bars",
  reviews: ".pd-rev-list",
  address: ".pd-addr",
  explore_category: ".pd-explore",
};

const SOURCE_NOTE = {
  odoo: (f) => `Comes from the product's own ${f.odoo_field || "record"} field. Change it on the product.`,
  computed: () => "Worked out by the app from the shop's own records.",
};

const noop = () => {};
const WISH_STUB = { has: () => false, toggle: noop };

/* -------------------------------------------------------------- the canvas */

/* The shop's own product page, drawn from the shop's own components.

   Everything inside is inert: the stage takes no pointer events, so no click
   in the preview can reach a storefront button. The hotspots put them back
   for themselves. */
function Canvas({ stageRef, product, preview, hiddenKeys }) {
  return (
    <div className="pe-canvas">
      <div className="pe-chrome" aria-hidden="true">
        <span className="pe-dots"><i /><i /><i /></span>
        <span className="pe-url">369mart.com/product — the page, as shoppers see it</span>
      </div>
      <div className="pe-screen hm-page">
        <div className="hm-wrap pp-stage" ref={stageRef} data-hidden={hiddenKeys.join(" ")}>
          <NavContext.Provider value={noop}>
            <OpenContext.Provider value={noop}>
              <WishContext.Provider value={WISH_STUB}>
                <ProductDetail
                  p={product}
                  cart={{}} setQty={noop}
                  address={{ label: "Home", line: "12 Residency Road", city: "Kochi" }}
                  variants={preview?.variants || []}
                  bundle={preview?.bundle || []}
                  similar={preview?.similar || []}
                  related={preview?.related || []}
                  recent={[]}
                  onBack={noop} onChangeAddress={noop} onExplore={noop}
                  onViewSimilar={noop} onVariant={noop} onEditReview={null}
                />
              </WishContext.Provider>
            </OpenContext.Provider>
          </NavContext.Provider>
        </div>
      </div>
    </div>
  );
}

/* The bands, measured from the page rather than wrapped around it.

   `ProductDetail` renders one tree and we do not own its insides, so the only
   honest way to put a handle on a section is to find where it landed and draw
   over it. Re-measured whenever the page could have moved. */
function HotLayer({ stageRef, spots, selected, onSelect, onToggle, tick }) {
  const [rects, setRects] = useState([]);

  const measure = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const base = stage.getBoundingClientRect();
    const found = [];
    for (const spot of spots) {
      const el = stage.querySelector(spot.at);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (!r.width && !r.height) continue;
      found.push({
        ...spot,
        top: r.top - base.top, left: r.left - base.left,
        width: r.width, height: r.height,
      });
    }
    setRects(found);
  }, [spots, stageRef]);

  useLayoutEffect(() => {
    let frame = null;
    const soon = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    soon();
    const ro = new ResizeObserver(soon);
    if (stageRef.current) ro.observe(stageRef.current);
    window.addEventListener("resize", soon);
    /* The accordions animate open; measure again once they have settled. */
    const settle = setTimeout(soon, 400);
    return () => {
      cancelAnimationFrame(frame); clearTimeout(settle);
      ro.disconnect(); window.removeEventListener("resize", soon);
    };
  }, [measure, tick, stageRef]);

  return rects.map((r) => (
    <BandShell
      key={r.id}
      bandId={r.id}
      tag={r.tag}
      label={r.label}
      hidden={r.hidden}
      selected={selected === r.id}
      onSelect={() => onSelect(r)}
      onToggle={r.canToggle ? () => onToggle(r) : undefined}
      className={"pp-hot" + (r.sub ? " pp-hot-sub" : "")}
      style={{ top: r.top, left: r.left, width: r.width, height: r.height }}
    />
  ));
}

/* --------------------------------------------------------------- the screen */

/* ------------------------------------------------------------- the picker */

/* Choosing a product by browsing the shop, rather than by spelling its name.

   The search box this replaces only answered "is there a product called X?".
   The question an employee actually arrives with is "what is in the shop, and
   which of it have we already changed?" - so the shop's own categories are the
   index, the counts say where things are, and "only edited" answers the second
   question directly.

   One call to /admin/product/catalog, which is
   product.template.mart369_page_picker() - the same call Odoo's own editor
   makes, so the two screens cannot disagree about what is in the shop. */
function ProductPicker({ chosen, onPick }) {
  const [categ, setCateg] = useState(null);       /* null = all, 0 = filed nowhere */
  const [term, setTerm] = useState("");
  const [onlyEdited, setOnlyEdited] = useState(false);
  const [debounced, setDebounced] = useState("");

  /* One request when the typing stops, not one per keystroke. */
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(term.trim()), 300);
    return () => clearTimeout(timer);
  }, [term]);

  const query = [
    categ === null ? "" : "categ_id=" + categ,
    debounced ? "q=" + encodeURIComponent(debounced) : "",
    onlyEdited ? "only_edited=1" : "",
  ].filter(Boolean).join("&");

  const { data, loading, error, reload } = useResource(
    "/admin/product/catalog" + (query ? "?" + query : ""),
    { deps: [categ, debounced, onlyEdited] });

  /* The flat list of categories, hung back into the tree the shop keeps it
     in. Two levels is what this shop has; deeper ones nest by the same rule. */
  const tree = useMemo(() => {
    const all = data?.categories || [];
    const kids = new Map();
    for (const c of all) {
      if (c.parent_id) {
        if (!kids.has(c.parent_id)) kids.set(c.parent_id, []);
        kids.get(c.parent_id).push(c);
      }
    }
    return all
      .filter((c) => !c.parent_id)
      .map((c) => ({ ...c, subs: kids.get(c.id) || [] }));
  }, [data]);

  const products = data?.products || [];
  const truncated = data && data.total > products.length;

  const Branch = ({ c, depth }) => (
    <>
      <button
        className={"pp-rail-row" + (categ === c.id ? " pp-rail-on" : "")}
        style={{ paddingLeft: 10 + depth * 14 }}
        onClick={() => setCateg(c.id)}
      >
        <span>{c.name}</span>
        <em>{c.count}</em>
      </button>
      {c.subs?.map((sub) => <Branch key={sub.id} c={sub} depth={depth + 1} />)}
    </>
  );

  return (
    <div className="pp-pick">
      <aside className="pp-rail" aria-label="Categories">
        <button className={"pp-rail-row" + (categ === null ? " pp-rail-on" : "")}
          onClick={() => setCateg(null)}>
          <span>All products</span>
          <em>{data?.all_count ?? ""}</em>
        </button>
        {tree.map((c) => <Branch key={c.id} c={c} depth={0} />)}
        {/* Without this the products filed under nothing are unreachable. */}
        {data?.uncategorised > 0 && (
          <button className={"pp-rail-row" + (categ === 0 ? " pp-rail-on" : "")}
            onClick={() => setCateg(0)}>
            <span>Uncategorised</span>
            <em>{data.uncategorised}</em>
          </button>
        )}
      </aside>

      <div className="pp-pick-main">
        <div className="pp-pick-bar">
          <Search value={term} onChange={setTerm} placeholder="Find a product" wide />
          <label className="pe-showhidden">
            <input type="checkbox" checked={onlyEdited}
              onChange={(e) => setOnlyEdited(e.target.checked)} />
            <span>Only ones already edited</span>
          </label>
        </div>

        <ErrorStrip error={error} onRetry={reload} />

        {loading && !data ? (
          <p className="pe-loading">Loading the shop…</p>
        ) : products.length === 0 ? (
          <Empty icon="box" title="Nothing here"
            text={onlyEdited
              ? "No product in this category has been given its own settings yet."
              : "No published product matches that."} />
        ) : (
          <>
            <div className="pp-grid">
              {products.map((p) => (
                <button key={p.id}
                  className={"pp-tile" + (chosen?.id === p.id ? " pp-tile-on" : "")}
                  onClick={() => onPick(p)}>
                  <span className="pp-tile-img">
                    <img src={p.image} alt="" loading="lazy" />
                  </span>
                  <b>{p.name}</b>
                  <small>{p.code || " "}</small>
                  {p.differs > 0 && (
                    <em className="pp-tile-chip">{p.differs} changed</em>
                  )}
                </button>
              ))}
            </div>
            {truncated && (
              <p className="pp-pick-more">
                Showing {products.length} of {data.total}. Narrow it down with a
                category or the search box.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function ProductPageSection({ flash }) {
  const [scope, setScope] = useState("shop");           /* shop | product */
  const [product, setProduct] = useState(null);         /* the chosen product */
  /* Choosing "One product" opens the shop to browse. The old toolbar search
     box only answered "is there a product called X?", which needed you to
     know the name first. */
  const [picking, setPicking] = useState(false);
  const [sel, setSel] = useState(null);                 /* {kind, id} */
  const [showHidden, setShowHidden] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [tick, setTick] = useState(0);                  /* forces a re-measure */
  const stageRef = useRef(null);

  /* One call for the whole screen, the same one Odoo's builder makes. */
  const { data, loading, error, reload } = useResource(
    "/admin/product/builder" + (product ? "?product_id=" + product.id : ""),
    { deps: [product?.id] });

  /* The server's answer, with the edits made since it arrived laid on top.
     Typing has to show under the cursor, not a moment later when the write
     lands - but the server stays the source of truth for everything else. */
  const [draft, setDraft] = useState({});
  const sections = useMemo(() => {
    const live = data?.sections || [];
    return live.map((sec) => ({
      ...sec,
      ...(draft["section:" + sec.id] || {}),
      rows: sec.rows.map((row) => ({ ...row, ...(draft["field:" + row.id] || {}) })),
    }));
  }, [data, draft]);

  /* A fresh load is the truth again; drop what we were holding over it. */
  useEffect(() => { setDraft({}); }, [data]);

  const allRows = useMemo(
    () => sections.flatMap((s) => s.rows.map((r) => ({ ...r, section: s }))),
    [sections]);

  const section = sel?.kind === "section"
    ? sections.find((s) => s.id === sel.id)
    : sel?.kind === "field"
      ? sections.find((s) => s.rows.some((r) => r.id === sel.id))
      : null;
  const field = sel?.kind === "field"
    ? allRows.find((r) => r.id === sel.id)
    : null;

  /* A field is on the page when its own switch is on and its section's master
     switch is on. The section wins, always - that is what a master switch is. */
  const isOn = useCallback((row, sec) => {
    if (!sec.show) return false;
    if (scope === "product" && row.state !== "follow") return row.state === "show";
    return row.show;
  }, [scope]);

  const hiddenKeys = useMemo(
    () => allRows.filter((r) => !isOn(r, r.section)).map((r) => r.key),
    [allRows, isOn]);

  const hiddenCount = hiddenKeys.length;

  /* ------------------------------------------------------------- the writes */

  const save = useAutosave({ invalidate: "/product" });

  /* Applied here at once, written a moment later. A switch passes `now`:
     there is no second keystroke coming, and a toggle that looks done but is
     not gets pressed twice. */
  const lay = (key, vals) => setDraft((d) => ({ ...d, [key]: { ...d[key], ...vals } }));

  const setSectionShow = (id, show) => {
    lay("section:" + id, { show });
    setTick((n) => n + 1);
    save.queue("section:" + id, `/admin/product/sections/${id}`, { show }, { now: true });
  };

  const patchField = (id, vals, { now = false } = {}) => {
    lay("field:" + id, vals);
    setTick((n) => n + 1);
    save.queue("field:" + id, `/admin/product/fields/${id}`, vals, { now });
  };

  const setState = (row, state) => {
    if (!product) return;
    lay("field:" + row.id, { state });
    setTick((n) => n + 1);
    save.queue(`field:${row.id}:p:${product.id}`,
      `/admin/product/fields/${row.id}/state`,
      { product_id: product.id, state }, { now: true, method: "POST" });
  };

  const setProductValue = (row, value) => {
    if (!product) return;
    lay("field:" + row.id, { product_value: value });
    save.queue(`field:${row.id}:v:${product.id}`,
      `/admin/product/fields/${row.id}/value`,
      { product_id: product.id, value });
  };

  const toggleRow = (row) => {
    const sec = sections.find((x) => x.rows.some((r) => r.id === row.id));
    const on = isOn(row, sec);
    if (scope === "product" && product) setState(row, on ? "hide" : "show");
    else patchField(row.id, { show: !row.show }, { now: true });
  };

  /* Not optimistic. `override_count` and `visible` are worked out by the
     server, and guessing them is how a panel starts lying. */
  const resetRow = async (row) => {
    if (!product) return;
    try {
      await api(`/admin/product/fields/reset`, {
        method: "POST",
        body: { product_id: product.id, field_ids: [row.id] },
      });
      api.invalidate("/product");
      await reload();
      flash?.("Put back to the shop default.");
    } catch (e) {
      flash?.(e?.message || "That did not work.", "bad");
    }
  };

  /* ----------------------------------------------------------- the hotspots */

  const spots = useMemo(() => {
    const out = [];
    for (const sec of sections) {
      const at = SECTION_AT[sec.key];
      if (!at) continue;
      const shownRows = sec.rows.filter((r) => isOn(r, sec)).length;
      out.push({
        id: uid("section", sec.id), at, kind: "section", recId: sec.id,
        tag: sec.name, label: sec.name,
        hidden: !sec.show, canToggle: true,
        sub: false, shownRows,
      });
    }
    /* Only the open section shows its fields. Forty-eight outlines at once is
       not a page you can read. */
    if (section) {
      for (const row of section.rows) {
        const at = FIELD_AT[row.key];
        if (!at) continue;
        out.push({
          id: uid("field", row.id), at, kind: "field", recId: row.id,
          tag: row.name, label: row.name,
          hidden: !isOn(row, section), canToggle: true, sub: true,
        });
      }
    }
    return out;
  }, [sections, section, isOn]);

  const onSpot = (spot) => setSel({ kind: spot.kind, id: spot.recId });
  const onSpotToggle = (spot) => {
    if (spot.kind === "section") {
      const sec = sections.find((s) => s.id === spot.recId);
      setSectionShow(sec.id, !sec.show);
    } else {
      toggleRow(allRows.find((r) => r.id === spot.recId));
    }
  };

  /* Selecting from the panel should take the canvas there too. */
  useEffect(() => { setTick((n) => n + 1); }, [sel, showHidden, scope]);

  /* ------------------------------------------------------------ the product */

  const pick = (item) => {
    setProduct(item);
    setPicking(false);
    setSel(null);
  };

  return (
    <div className="ad-stack pe pp">
      <header className="pe-head">
        <div className="pe-title">
          <h1>Product page</h1>
          <small>
            What every product page shows, and where its wording comes from.
          </small>
        </div>
      </header>

      <div className="pe-toolbar">
        {/* First control on the screen, because it decides what everything
            else means: a switch here changes one product or all of them. */}
        <div className="ad-tabs" role="tablist" aria-label="What you are changing">
          {[["shop", "Whole shop"], ["product", "One product"]].map(([k, label]) => (
            <button key={k} role="tab" aria-selected={scope === k}
              className={scope === k ? "ad-on" : ""}
              onClick={() => { setScope(k); if (k === "product") setPicking(true); }}>
              {label}
            </button>
          ))}
        </div>

        {scope === "product" && product && !picking && (
          <span className="pp-prod">
            {product.name}
            <button className="pe-tool" onClick={() => setPicking(true)}>Change</button>
          </span>
        )}

        {!picking && hiddenCount > 0 && (
          <label className="pe-showhidden">
            <input type="checkbox" checked={showHidden}
              onChange={(e) => setShowHidden(e.target.checked)} />
            <span>Show what is switched off ({hiddenCount})</span>
          </label>
        )}

        <span className="pe-toolbar-gap" />
        <SaveChip status={save.status} error={save.error} />
      </div>

      <p className="pe-hintbar">
        {picking
          ? "Pick the product whose page you want to change. The number on a "
            + "tile is how many of its parts already differ from the shop."
          : "Click any part of the page to change it. The eye takes something "
            + "off the page without deleting it. A section is a master switch: "
            + "turn it off and everything inside goes, whatever those parts say."}
      </p>

      {picking ? (
        <ProductPicker chosen={product} onPick={pick} />
      ) : (
      <>
      <ErrorStrip error={error} onRetry={reload} />

      <div className="pe-cols">
        <div className="pe-canvas-wrap">
          <div className="pp-canvas-holder">
            {data?.card ? (
              <Canvas stageRef={stageRef} product={data.card}
                preview={data.preview} hiddenKeys={hiddenKeys} />
            ) : (
              <div className="pe-canvas">
                <div className="pe-screen hm-page">
                  <p className="pe-loading">
                    {loading ? "Loading the page…" : "No published product to draw."}
                  </p>
                </div>
              </div>
            )}
            <HotLayer
              stageRef={stageRef} spots={spots} tick={tick}
              selected={sel ? uid(sel.kind, sel.id) : null}
              onSelect={onSpot} onToggle={onSpotToggle}
            />
          </div>
          <p className="pe-canvas-note">
            This is the shop's own product page. The parts you switch off here
            are the parts a shopper stops seeing.
          </p>
        </div>

        <aside className="ad-card pe-panel">
          <Panel
            sections={sections} section={section} field={field} scope={scope}
            product={product} isOn={isOn}
            onSelect={setSel} onBack={() => setSel(section ? { kind: "section", id: section.id } : null)}
            onSectionShow={setSectionShow} onField={patchField}
            onState={setState} onValue={setProductValue}
            onToggleRow={toggleRow} onReset={(row) => setConfirm(row)}
          />
        </aside>
      </div>
      </>
      )}

      {confirm && (
        <Confirm
          danger
          title="Put this back to the shop default?"
          text={"This clears both the show-or-hide choice and any wording typed "
            + "just for this product — they are kept together."}
          confirmLabel="Put it back"
          onCancel={() => setConfirm(null)}
          onConfirm={() => { resetRow(confirm); setConfirm(null); }}
        />
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- the panel */

function Panel({
  sections, section, field, scope, product, isOn,
  onSelect, onBack, onSectionShow, onField, onState, onValue,
  onToggleRow, onReset,
}) {
  if (field && section) {
    return <FieldPanel {...{ field, section, scope, product, isOn, onBack,
      onField, onState, onValue, onToggleRow, onReset }} />;
  }
  if (section) {
    return <SectionPanel {...{ section, scope, isOn, onSelect, onSectionShow, onToggleRow }} />;
  }
  return <WholePanel {...{ sections, isOn, onSelect }} />;
}

/* Nothing selected is not nothing to do: this is the page, listed. */
function WholePanel({ sections, isOn, onSelect }) {
  return (
    <>
      <header className="pe-panel-head">
        <div>
          <h2>The whole page</h2>
          <p>Eleven parts, top to bottom.</p>
        </div>
      </header>
      <ul className="pp-secs">
        {sections.map((s) => {
          const on = s.rows.filter((r) => isOn(r, s)).length;
          return (
            <li key={s.id}>
              <button className="pp-sec-row" onClick={() => onSelect({ kind: "section", id: s.id })}>
                <span className="pp-sec-name">
                  <b>{s.name}</b>
                  <em>{s.show ? `${on} of ${s.rows.length} shown` : "Switched off"}</em>
                </span>
                <Icon n="right" size={15} />
              </button>
            </li>
          );
        })}
      </ul>
      <p className="pe-panel-note">
        Click a part of the page on the left to open it here.
      </p>
    </>
  );
}

function SectionPanel({ section, scope, isOn, onSelect, onSectionShow, onToggleRow }) {
  return (
    <>
      <header className="pe-panel-head">
        <div>
          <h2>{section.name}</h2>
          <p>{section.rows.length} parts</p>
        </div>
        <label className="pp-switch-lbl">
          <span>{section.show ? "Shown" : "Off"}</span>
          <Switch on={section.show} onChange={(v) => onSectionShow(section.id, v)}
            label={`Show ${section.name}`} />
        </label>
      </header>

      {!section.show && (
        <p className="ad-hint pp-master-off">
          This whole part is switched off, so nothing inside it reaches a
          shopper — whatever the switches below say.
        </p>
      )}

      <ul className={"pp-fields" + (section.show ? "" : " pp-fields-off")}>
        {section.rows.map((row) => {
          const on = isOn(row, section);
          return (
            <li key={row.id} className={on ? "" : "pp-off"}>
              <button className="pe-tool" disabled={!section.show}
                aria-pressed={on}
                title={on ? "Hide this" : "Show this"}
                onClick={() => onToggleRow(row)}>
                <Eye off={!on} />
              </button>
              <button className="pp-field-row" onClick={() => onSelect({ kind: "field", id: row.id })}>
                <span className="pp-field-name">{row.name}</span>
                <span className="pp-src">{row.source === "text" ? "Wording" : row.source}</span>
                <Icon n="right" size={14} />
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function FieldPanel({
  field, section, scope, product, isOn, onBack,
  onField, onState, onValue, onToggleRow, onReset,
}) {
  const on = isOn(field, section);
  const note = SOURCE_NOTE[field.source]?.(field);

  return (
    <>
      <header className="pe-panel-head">
        <div>
          <button className="ad-link pp-back" onClick={onBack}>
            <Icon n="left" size={13} /> {section.name}
          </button>
          <h2>{field.name}</h2>
          <p className="pp-key">{field.key}</p>
        </div>
      </header>

      {scope === "shop" ? (
        <div className="pe-form ad-form">
          <label className="pp-switch-row">
            <span>Shown on every product</span>
            <Switch on={field.show} onChange={() => onToggleRow(field)}
              label={`Show ${field.name}`} />
          </label>

          {note ? (
            <p className="ad-hint pp-source">{note}</p>
          ) : (
            <label className="ad-field ad-span2">
              <span>What it says, by default</span>
              {field.value_kind === "lines" ? (
                <textarea rows={5} value={field.default_value || ""}
                  placeholder="One per line"
                  onChange={(e) => onField(field.id, { default_value: e.target.value })} />
              ) : field.value_kind === "bool" ? (
                <Switch on={!!field.default_value}
                  onChange={(v) => onField(field.id, { default_value: v ? "1" : "" })}
                  label={field.name} />
              ) : (
                <input value={field.default_value || ""}
                  onChange={(e) => onField(field.id, { default_value: e.target.value })} />
              )}
              {field.value_kind === "html" && (
                <em className="pe-hint">
                  Formatting is edited in Odoo; plain text typed here is kept as it is.
                </em>
              )}
            </label>
          )}

          {!field.per_product && (
            <p className="ad-hint">
              This one is the same on every product. It can still be hidden on
              a single product.
            </p>
          )}
        </div>
      ) : (
        <div className="pe-form ad-form">
          {!product && (
            <p className="ad-hint">
              Pick a product in the box above to give it something of its own.
            </p>
          )}
          <fieldset className="pp-radios" disabled={!product}>
            <legend>On this product</legend>
            {[
              ["follow", `Follow the shop default (currently ${field.show ? "shown" : "hidden"})`],
              ["show", "Always show it"],
              ["hide", "Always hide it"],
            ].map(([value, label]) => (
              <label key={value} className="pp-radio">
                <input type="radio" name={"state" + field.id} value={value}
                  checked={field.state === value}
                  onChange={() => onState(field, value)} />
                <span>{label}</span>
              </label>
            ))}
          </fieldset>

          {field.per_product && !note && (
            <label className="ad-field ad-span2">
              <span>Wording just for this product</span>
              <input value={field.product_value || ""}
                placeholder={field.default_value || "Same as the shop default"}
                disabled={!product}
                onChange={(e) => onValue(field, e.target.value)} />
              <em className="pe-hint">Leave it empty to use the default.</em>
            </label>
          )}

          {(field.state !== "follow" || field.product_value) && (
            <button className="ad-btn ad-danger" onClick={() => onReset(field)}>
              Put this one back
            </button>
          )}
        </div>
      )}

      <p className="pe-panel-note">
        {on
          ? "A shopper sees this on the page."
          : "A shopper does not see this."}
      </p>
    </>
  );
}
