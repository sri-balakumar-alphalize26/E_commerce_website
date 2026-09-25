"use client";
/* ==========================================================================
   369 Mart admin — Catalog

   The groups a shopper sees in the app, and how each one looks: the pale
   colour behind its page, the ink of its heading and the line under its
   title. New categories are made here too: a top-level aisle, or a
   sub-category inside one (the app shows two levels, so a parent is always
   top-level).

   Two things this screen will not change, on purpose. **The name** is Odoo's
   own field, leaned on by the catalogue, the product pages and every report.
   **The app address** is a URL a customer may have saved, and editing it
   breaks that link silently. Both are one click away in Odoo, where the change
   is made deliberately rather than in passing.

   The twin of the Odoo desk at /odoo/mart-catalog: both call
   `mart369_admin_list` on the model, so they cannot drift.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAction, useResource } from "@/lib/useFetch";
import { Drawer, Empty, Icon, Search, Select, Tabs } from "./AdminUI";

export function CategoriesSection({ flash }) {
  const [tab, setTab] = useState("all");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null);
  const [formError, setFormError] = useState("");
  const [fresh, setFresh] = useState(null);
  const [mode, setMode] = useState("look");
  const open = (r, m) => { setFormError(""); setMode(m); setEditing(r); };

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("tab", tab);
    if (q) p.set("q", q);
    const qs = p.toString();
    return "/admin/categories" + (qs ? `?${qs}` : "");
  }, [tab, q]);

  const { data, loading, error, reload } = useResource(path);
  /* Every category, whatever the tab, for the "Inside" choice of a new one. */
  const { data: everything, reload: reloadAll } = useResource("/admin/categories");
  const parents = (everything?.rows || []).filter((r) => r.topLevel);
  const act = useAction();

  const rows = data?.rows || [];
  const counts = data?.counts || {};
  const tiles = data?.tiles || {};

  /* Read-after-write. Which tab a category now belongs to is the server's
     answer, and a row toggled locally would sit in a tab it no longer
     matches until the next reload. */
  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      api.invalidate("/admin/categories");
      /* The shop's own catalogue feed is what a shopper sees; hiding a
         category that still shows for sixty seconds looks like a bug. */
      api.invalidate("/catalog");
      await reload();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  const write = (row, values, ok) =>
    run(() => api(`/admin/categories/${row.id}`, { method: "PATCH", body: values }), ok);

  const toggleShown = (row) =>
    write(row, { mart_in_app: !row.inApp },
      row.inApp ? `${row.name} is hidden from the app` : `${row.name} is back in the app`);

  /* Caught directly rather than read off `act.error`, which is one render
     stale in the same tick it is set. */
  async function saveDialog(values) {
    setFormError("");
    const isNew = editing === "new";
    try {
      const res = await api(isNew ? "/admin/categories" : `/admin/categories/${editing.id}`,
        { method: isNew ? "POST" : mode === "edit" ? "PUT" : "PATCH", body: values });
      /* Drawn highlighted in the list so the new one can be found. */
      if (isNew && res?.row?.id) { setTab("all"); setTerm(""); setFresh(res.row.id); }
    } catch (e) {
      setFormError(e?.message || "That could not be saved.");
      return;
    }
    api.invalidate("/admin/categories");
    api.invalidate("/catalog");
    await reload();
    reloadAll();
    flash?.(isNew ? `${values.name} added` : `${values.name || editing.name} saved`);
    setEditing(null);
  }

  /* Main categories as headings, each with its sub-categories under it. A
     sub-category that matches the filter when its main one does not still
     gets its heading, drawn plainly, so it is never shown without a home. */
  const groups = useMemo(() => {
    const byId = new Map(rows.map((r) => [r.id, r]));
    const out = [], index = new Map();
    for (const r of rows) {
      const key = r.parentId || r.id;
      let g = index.get(key);
      if (!g) {
        g = { main: r.parentId ? byId.get(r.parentId) || { id: r.parentId, name: r.parent, stub: true } : r, subs: [] };
        index.set(key, g); out.push(g);
      }
      if (r.parentId) g.subs.push(r);
    }
    return out;
  }, [rows]);
  const subCount = rows.filter((r) => r.parentId).length;
  const mains = rows.length - subCount;
  const rowClass = (r) => (r.inApp ? "" : "ad-cat-off") + (fresh === r.id ? " ad-cat-new" : "");

  const catRow = (r) => (
    <>
      {/* The two colours shown as what they are: ink on its own
          background, rather than two hex codes in a table. */}
      <span className="ad-cat-swatch"
        style={{ background: r.tone || "#f4f6f8", color: r.accent || "#0b4a6e" }}
        title={`Background ${r.tone}, heading ${r.accent}`}>Aa</span>

      <div className="ad-cat-body">
        <div className="ad-cat-top">
          <b>{r.name}</b>
          {!r.inApp && <span className="ad-pill ad-t-grey"><i />Hidden</span>}
          {!r.products && <span className="ad-pill ad-t-amber"><i />Nothing in it</span>}
        </div>
        <small>
          <code>/{r.slug}</code>
          {` · ${r.products} product${r.products === 1 ? "" : "s"}`}
          {r.parentId ? "" : ` · ${r.children || 0} sub-categor${r.children === 1 ? "y" : "ies"}`}
        </small>
        {r.blurb ? <p className="ad-cat-blurb">{r.blurb}</p> : null}
      </div>

      <div className="ad-cat-act">
        <button className="ad-btn ad-sm" disabled={act.busy}
          onClick={() => open(r, "edit")}><Icon n="edit" size={13} />Edit</button>
        <button className="ad-btn ad-sm" disabled={act.busy}
          onClick={() => open(r, "look")}>How it looks</button>
        <button className="ad-btn ad-sm" disabled={act.busy}
          onClick={() => toggleShown(r)}>{r.inApp ? "Hide" : "Show"}</button>
      </div>
    </>
  );

  return (
    <div className="ad-stack">
      {/* The tiles double as a filter, like the Odoo desk's. */}
      <section className="ad-mini-stats ad-cat-tiles">
        {[["live", "In the app", tiles.live], ["hidden", "Hidden", tiles.hidden], ["empty", "Standing empty", tiles.empty]].map(([k, label, n]) => (
          <button key={k} type="button" aria-pressed={tab === k}
            className={(tab === k ? "ad-on " : "") + (k === "empty" && n ? "ad-warn" : "")}
            onClick={() => setTab(tab === k ? "all" : k)}>
            <small>{label}</small><b>{n ?? 0}</b><i>{tab === k ? "Showing these" : "Show these"}</i>
          </button>
        ))}
        <span><small>Products a shopper can reach</small><b>{tiles.products ?? 0}</b><i>Counted once, however many groups they sit in</i></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[
            ["all", "All", counts.all ?? 0],
            ["live", "In the app", counts.live ?? 0],
            ["hidden", "Hidden", counts.hidden ?? 0],
            ["empty", "Standing empty", counts.empty ?? 0],
          ]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="A category or its app address" />
            <button type="button" className="ad-btn ad-primary" onClick={() => { setFormError(""); setEditing("new"); }}>
              <Icon n="plus" size={15} />New category
            </button>
          </div>
        </div>

        {error && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !rows.length && !error && (
          <Empty icon="layers" title="Loading…" text="Fetching categories." />
        )}
        {!error && !loading && !rows.length && (
          <Empty icon="layers"
            title={tab === "empty" ? "Every category has something in it" : "No category here"}
            text={tab === "empty"
              ? "That is the good version of this tab being empty."
              : q || tab !== "all"
                ? "Nothing matches that. Try another tab, or clear the search."
                : "Add one with New category."} />
        )}

        {!error && !!rows.length && (
          <>
          <p className="ad-cat-count">
            {mains} categor{mains === 1 ? "y" : "ies"} · {subCount} sub-categor{subCount === 1 ? "y" : "ies"}
          </p>
          {/* Each main category is a heading, its sub-categories listed under
              it - the two levels the app draws, drawn the same way here. */}
          <ul className="ad-cat-groups">
            {groups.map((g, gi) => (
              <li key={g.main.id} className="ad-cat-group" style={{ "--i": gi, "--tone": g.main.tone || "#f4f6f8", "--accent": g.main.accent || "#0b4a6e" }}>
                {g.main.stub ? (
                  <div className="ad-cat-head ad-cat-stub"><b>{g.main.name}</b><small>Main category · not in this list</small></div>
                ) : (
                  <div className={"ad-cat-head " + rowClass(g.main)}>{catRow(g.main, gi)}</div>
                )}
                {!!g.subs.length && (
                  <ul className="ad-cats ad-cat-subs" aria-label={`Sub-categories of ${g.main.name}`}>
                    {g.subs.map((r, i) => <li key={r.id} className={rowClass(r)} style={{ "--i": i }}>{catRow(r, i)}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ul>
          </>
        )}
      </section>

      {editing && (
        <CategoryDialog row={editing === "new" ? null : editing} mode={editing === "new" ? "new" : mode}
          parents={parents.filter((p) => editing === "new" || p.id !== editing.id)} error={formError} busy={act.busy}
          onCancel={() => setEditing(null)} onSave={saveDialog} />
      )}
    </div>
  );
}

/* How the app draws one category. A Drawer rather than a bespoke modal,
   because that is the shell every other form in this console uses - and the
   blurb and the two colours only make sense seen together, so a colour picked
   beside the words it sits behind is picked once. */
/* Pale background + readable heading ink, in pairs, so a tap cannot give
   ink the shopper cannot read. [background, heading, name] */
const PALETTE = [
  ["#f4f6f8", "#0b4a6e", "Default"],
  ["#eef3f7", "#12405e", "Steel"],
  ["#e8f3f9", "#0a78ab", "Sky"],
  ["#e8f5e9", "#1f7a4c", "Leaf"],
  ["#fdf3e2", "#9a5b00", "Amber"],
  ["#fdecec", "#a32020", "Berry"],
  ["#f3eefb", "#5b3aa6", "Violet"],
  ["#f8f4f2", "#6b3326", "Cocoa"],
  ["#eef6f4", "#0f6b5c", "Teal"],
  ["#f1f1f1", "#222222", "Ink"],
];

function CategoryDialog({ row, mode, parents, error, busy, onCancel, onSave }) {
  const isNew = !row;
  const isEdit = mode === "edit";
  /* Name and Under are asked for when making a category, and from the Edit
     button - not from How it looks. */
  const askPlace = isNew || isEdit;
  /* A main category with sub-categories cannot go under another one: its
     sub-categories would become a third level. */
  const placeLocked = isEdit && !row.parentId && row.children > 0;
  const [draft, setDraft] = useState({
    name: isEdit ? row.name || "" : "",
    parent_id: isEdit && row.parentId ? String(row.parentId) : "",
    mart_blurb: row?.blurb || "",
    mart_tone: row?.tone || "#f4f6f8",
    mart_accent: row?.accent || "#0b4a6e",
    mart_blurb_color: row?.blurbColor || "",
  });
  const [nameBad, setNameBad] = useState(false);
  const [picked, setPicked] = useState(isEdit);
  const set = (k) => (e) => {
    if (k === "mart_tone" || k === "mart_accent") setPicked(true);
    setDraft((d) => ({ ...d, [k]: e.target.value }));
  };
  /* Under chosen before any colour was picked: start from the main
     category's colours, or back to the defaults when Under goes back to None. */
  const setUnder = (v) => setDraft((d) => {
    if (picked) return { ...d, parent_id: v };
    const p = parents.find((x) => String(x.id) === v);
    return { ...d, parent_id: v, mart_tone: p?.tone || "#f4f6f8", mart_accent: p?.accent || "#0b4a6e" };
  });

  /* A sub-category - one being made with an Under chosen, or one that has a
     parent. The app draws it as a round tile, in its own colours. */
  const isSub = askPlace ? !!draft.parent_id : !!row.parentId;
  const main = askPlace
    ? (() => { const p = parents.find((x) => String(x.id) === draft.parent_id); return p ? { name: p.name, tone: p.tone, accent: p.accent, blurbColor: p.blurbColor } : null; })()
    : row.parentId ? { name: row.parent, tone: row.parentTone, accent: row.parentAccent, blurbColor: row.parentBlurbColor } : null;
  const shownName = askPlace ? draft.name.trim() || (isNew ? "New category" : row.name) : row.name;
  /* Empty Line colour = the default: the app's grey, or for a sub-category
     its main category's line colour. */
  const lineColour = draft.mart_blurb_color || (isSub && main?.blurbColor) || "#4a5a66";
  const line = draft.mart_blurb || "No line under the title";

  const submit = () => {
    const { name, parent_id, ...look } = draft;
    if (!askPlace) return onSave(look);
    if (!name.trim()) { setNameBad(true); return; }
    if (isEdit) return onSave({ ...look, name: name.trim(), ...(placeLocked ? {} : { parent_id: parent_id ? Number(parent_id) : false }) });
    onSave({ ...look, name: name.trim(), ...(parent_id ? { parent_id: Number(parent_id) } : {}) });
  };

  const colour = (key, label, hint, value, placeholder) => (
    <label className="ad-field"><span>{label}<em>{hint}</em></span>
      <span className="ad-colour">
        <input type="color" value={value} onChange={set(key)} aria-label={`Pick the ${label.toLowerCase()}`} />
        <input value={draft[key]} onChange={set(key)} placeholder={placeholder} />
      </span></label>
  );

  return (
    <Drawer wide
      title={isNew ? "New category" : isEdit ? `Edit ${row.name}` : row.name}
      sub={isNew
        ? "A new group for the app. Its app address is made from the name."
        : isEdit
        ? "Its name, where it sits, and how it looks. The app address stays the same, so a link a customer saved still works."
        : "How the app draws this category. The name and the app address are changed in Odoo - the address is a link a customer may have saved."}
      onClose={onCancel}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={busy} onClick={submit}>{isNew ? "Add category" : "Save"}</button>
        </>
      )}>
      {error && <p className="ad-hint ad-form-error" role="alert"><Icon n="info" size={14} />{error}</p>}

      <div className="ad-dlg-cols">
        <div className="ad-form">
          {askPlace && <>
            <label className="ad-field ad-span2"><span>Name</span>
              <input autoFocus value={draft.name} placeholder="e.g. Audio" aria-invalid={nameBad}
                onChange={(e) => { setNameBad(false); set("name")(e); }} />
              {nameBad && <small className="ad-form-error">A category needs a name.</small>}</label>
            {placeLocked ? (
              <div className="ad-field ad-span2"><span>Under</span>
                <p className="ad-cat-locked"><Icon n="lock" size={13} />
                  <span>Has {row.children} sub-categor{row.children === 1 ? "y" : "ies"}, so it stays a main category - move them first.</span></p>
              </div>
            ) : (
              <div className="ad-field ad-span2"><span>Under</span>
                <Select value={draft.parent_id} label="Parent category"
                  onChange={setUnder}
                  options={[["", "None - a top-level category"], ...parents.map((p) => [String(p.id), p.name])]} />
              </div>
            )}
            <ul className="ad-cat-how ad-span2">
              <li><b>Category:</b> just type the name - leave Under as None.</li>
              <li><b>Sub-category:</b> type the name, then choose the main category it goes under (e.g. Computers). Only main categories are listed - the app shows two levels.</li>
            </ul>
          </>}
          <label className="ad-field ad-span2"><span>One line under the title</span>
            <input value={draft.mart_blurb} onChange={set("mart_blurb")}
              placeholder="Switches, sockets and wiring accessories" />
            {isSub && <small className="ad-dim">Shown under the title when this sub-category is picked.</small>}</label>

          {/* Always the code in use, like the other two; the default is
              shown, but only saved once changed. */}
          <label className="ad-field"><span>Line colour<em>{draft.mart_blurb_color
              ? "Colours the one line under the title"
              : isSub && main?.blurbColor ? `Default: ${main.name}'s line colour` : "Default: the app's grey"}</em></span>
            <span className="ad-colour">
              <input type="color" value={lineColour} onChange={set("mart_blurb_color")} aria-label="Pick the line colour" />
              <input value={lineColour} onChange={set("mart_blurb_color")} />
            </span>
            {draft.mart_blurb_color && <button type="button" className="ad-link ad-line-reset"
              onClick={(e) => { e.preventDefault(); setDraft((d) => ({ ...d, mart_blurb_color: "" })); }}>Back to default</button>}
          </label>
          <div className="ad-field" />

          {/* A sub-category has its own colours too: they fill its circle. */}
          {isSub && (
            <p className="ad-hint ad-span2"><Icon n="info" size={14} />
              <span>Colours this sub-category&apos;s circle. It starts in <b>{main?.name || "its main category"}</b>&apos;s colours; a colour you pick stays, whatever Under is set to.</span></p>
          )}
          <>
            {/* One tap sets both colours; the pickers below fine-tune either. */}
            <div className="ad-field ad-span2"><span>Colours</span>
              <div className="ad-palette" role="group" aria-label="Colour presets">
                {PALETTE.map(([tone, accent, name]) => {
                  const on = draft.mart_tone.toLowerCase() === tone && draft.mart_accent.toLowerCase() === accent;
                  return (
                    <button key={tone} type="button" className={on ? "ad-on" : ""} aria-pressed={on} title={name}
                      style={{ background: tone, color: accent }}
                      onClick={() => { setPicked(true); setDraft((d) => ({ ...d, mart_tone: tone, mart_accent: accent })); }}>Aa</button>
                  );
                })}
              </div>
            </div>
            {colour("mart_tone", "Background", isSub ? "Fills the circle" : "Fills the category's header", draft.mart_tone)}
            {colour("mart_accent", "Heading colour", isSub ? "Rings the circle and colours its name" : "Colours the All tile; new sub-categories start with it", draft.mart_accent)}
          </>
        </div>

        {/* As the app draws it, live. A category: its page header filled with
            Background. A sub-category: a round tile in its main category's colours. */}
        <aside className="ad-dlg-right" aria-label="How it looks in the app">
          <p className="ad-dlg-cap">How it looks in the app</p>
          {!isSub ? (
            <div className="ad-prev-cat" style={{ "--tone": draft.mart_tone, "--accent": draft.mart_accent }}>
              <div className="ad-prev-hero">
                <div className="ad-prev-words">
                  <b>{shownName}</b>
                  <small style={{ color: lineColour }}>{line}</small>
                </div>
                <div className="ad-prev-art" aria-hidden="true">
                  <span><Icon n="box" size={18} /></span>
                  <span><Icon n="box" size={22} /></span>
                </div>
              </div>
              <p className="ad-prev-key"><i />Heading colour - the All tile, and where new sub-categories start</p>
            </div>
          ) : (
            <div className="ad-prev-sub" style={{ "--tone": draft.mart_tone, "--accent": draft.mart_accent }}>
              <i><Icon n="box" size={30} /></i>
              <b>{shownName}</b>
              <small>Under {main?.name || ""} · <span style={{ color: lineColour }}>{line}</span></small>
            </div>
          )}
        </aside>
      </div>
    </Drawer>
  );
}
