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

   Not connected yet: mart369_product has no admin route, so the parts below
   come from productPageData.js and nothing is saved. The shape is the one
   `builder_load()` already returns, so wiring it up is a change of source.
   ========================================================================== */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { Confirm, Empty, Icon, Search, Switch } from "./AdminUI";
import { BandShell, Eye, SaveChip, uid } from "./editorKit";
import { SECTIONS as SEED, SAMPLE_PRODUCT } from "./productPageData";
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
function Canvas({ stageRef, product, hiddenKeys }) {
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
                  variants={[]} bundle={[]} similar={[]} related={[]} recent={[]}
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

export default function ProductPageSection({ flash }) {
  const [sections, setSections] = useState(SEED);
  const [scope, setScope] = useState("shop");          /* shop | product */
  const [product, setProduct] = useState(null);         /* the chosen product */
  const [term, setTerm] = useState("");
  const [sel, setSel] = useState(null);                 /* {kind, id} */
  const [showHidden, setShowHidden] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [tick, setTick] = useState(0);                  /* forces a re-measure */
  const stageRef = useRef(null);

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

  /* Nothing is saved yet - there is no route to save to. The chip still moves,
     because the screen's behaviour is the thing being built, and a switch that
     does not answer is not the same screen. */
  const [chip, setChip] = useState({ status: "idle", error: "" });
  const touched = () => {
    setChip({ status: "saving", error: "" });
    setTimeout(() => setChip({
      status: "error",
      error: "Not saved — the shop has no product-page route yet.",
    }), 400);
  };

  const setSectionShow = (id, show) => {
    setSections((list) => list.map((s) => (s.id === id ? { ...s, show } : s)));
    setTick((n) => n + 1);
    touched();
  };

  const patchRow = (id, vals) => {
    setSections((list) => list.map((s) => ({
      ...s, rows: s.rows.map((r) => (r.id === id ? { ...r, ...vals } : r)),
    })));
    setTick((n) => n + 1);
    touched();
  };

  const toggleRow = (row) => {
    if (scope === "product") {
      const on = row.state === "follow" ? row.show : row.state === "show";
      patchRow(row.id, { state: on ? "hide" : "show" });
    } else {
      patchRow(row.id, { show: !row.show });
    }
  };

  const resetRow = (row) => {
    patchRow(row.id, { state: "follow", product_value: "" });
    flash?.("Put back to the shop default.");
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

  const matches = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return [];
    /* Nothing to search yet. When the route exists this becomes one debounced
       request; until then the box is honest about having no catalogue. */
    return [];
  }, [term]);

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
        <div className="pp-search">
          <Search value={term} onChange={setTerm} placeholder="Find a product" />
          {term.trim() && (
            <div className="pp-search-menu" role="listbox">
              {matches.length === 0 && (
                <p className="pp-search-empty">
                  No catalogue to search yet — this needs the shop's product-page
                  route. The page below is the real one; the product on it is a
                  stand-in.
                </p>
              )}
            </div>
          )}
        </div>

        {product && (
          <span className="pp-prod">
            {product.name}
            <button className="pe-tool" onClick={() => setProduct(null)}
              aria-label="Stop editing this product">×</button>
          </span>
        )}

        <div className="ad-tabs" role="tablist" aria-label="What you are changing">
          {[["shop", "Whole shop"], ["product", "This product"]].map(([k, label]) => (
            <button key={k} role="tab" aria-selected={scope === k}
              className={scope === k ? "ad-on" : ""}
              title={k === "product" && !product
                ? "Pick a product first"
                : undefined}
              onClick={() => setScope(k)}>
              {label}
            </button>
          ))}
        </div>

        {hiddenCount > 0 && (
          <label className="pe-showhidden">
            <input type="checkbox" checked={showHidden}
              onChange={(e) => setShowHidden(e.target.checked)} />
            <span>Show what is switched off ({hiddenCount})</span>
          </label>
        )}

        <span className="pe-toolbar-gap" />
        <SaveChip status={chip.status} error={chip.error} />
      </div>

      <p className="pe-hintbar">
        Click any part of the page to change it. The eye takes something off the
        page without deleting it. A section is a master switch: turn it off and
        everything inside goes, whatever those parts say.
      </p>

      <div className="pe-cols">
        <div className="pe-canvas-wrap">
          <div className="pp-canvas-holder">
            <Canvas stageRef={stageRef} product={SAMPLE_PRODUCT} hiddenKeys={hiddenKeys} />
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
            onSectionShow={setSectionShow} onRow={patchRow} onToggleRow={toggleRow}
            onReset={(row) => setConfirm(row)}
          />
        </aside>
      </div>

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
  onSelect, onBack, onSectionShow, onRow, onToggleRow, onReset,
}) {
  if (field && section) {
    return <FieldPanel {...{ field, section, scope, product, isOn, onBack, onRow, onToggleRow, onReset }} />;
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
  field, section, scope, product, isOn, onBack, onRow, onToggleRow, onReset,
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
                  onChange={(e) => onRow(field.id, { default_value: e.target.value })} />
              ) : field.value_kind === "bool" ? (
                <Switch on={!!field.default_value}
                  onChange={(v) => onRow(field.id, { default_value: v ? "1" : "" })}
                  label={field.name} />
              ) : (
                <input value={field.default_value || ""}
                  onChange={(e) => onRow(field.id, { default_value: e.target.value })} />
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
                  onChange={() => onRow(field.id, { state: value })} />
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
                onChange={(e) => onRow(field.id, { product_value: e.target.value })} />
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
