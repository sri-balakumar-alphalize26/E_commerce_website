"use client";
/* ==========================================================================
   369 Mart admin — Catalog

   The groups a shopper sees in the app, and how each one looks: the pale
   colour behind its page, the ink of its heading, the line under its title,
   and which storefront it belongs to — Quick, the ten-minute run, or Express,
   which ships over days.

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

const MODES = { quick: "Quick", all: "Express" };

export function CategoriesSection({ flash }) {
  const [tab, setTab] = useState("all");
  const [mode, setMode] = useState("");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("tab", tab);
    if (mode) p.set("mode", mode);
    if (q) p.set("q", q);
    const qs = p.toString();
    return "/admin/categories" + (qs ? `?${qs}` : "");
  }, [tab, mode, q]);

  const { data, loading, error, reload } = useResource(path);
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
    try {
      await api(`/admin/categories/${editing.id}`, { method: "PATCH", body: values });
    } catch (e) {
      setFormError(e?.message || "That could not be saved.");
      return;
    }
    api.invalidate("/admin/categories");
    api.invalidate("/catalog");
    await reload();
    flash?.(`${editing.name} saved`);
    setEditing(null);
  }

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>In the app</small><b>{tiles.live ?? 0}</b></span>
        <span><small>Hidden</small><b>{tiles.hidden ?? 0}</b></span>
        <span className={tiles.empty ? "ad-warn" : ""}>
          <small>Standing empty</small><b>{tiles.empty ?? 0}</b>
        </span>
        <span><small>Products a shopper can reach</small><b>{tiles.products ?? 0}</b></span>
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
            <Select value={mode} onChange={setMode} label="Storefront"
              options={[["", "Both storefronts"], ["quick", "Quick"], ["all", "Express"]]} />
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
              : q || tab !== "all" || mode
                ? "Nothing matches that. Try another tab, or clear the search."
                : "Categories are added in Odoo, and appear here the moment they exist."} />
        )}

        {!error && !!rows.length && (
          <ul className="ad-cats">
            {rows.map((r, i) => (
              <li key={r.id} className={r.inApp ? "" : "ad-cat-off"} style={{ "--i": i }}>
                {/* The two colours shown as what they are: ink on its own
                    background, rather than two hex codes in a table. */}
                <span className="ad-cat-swatch"
                  style={{ background: r.tone || "#f4f6f8", color: r.accent || "#0b4a6e" }}
                  title={`Background ${r.tone}, heading ${r.accent}`}>Aa</span>

                <div className="ad-cat-body">
                  <div className="ad-cat-top">
                    <b>{r.name}</b>
                    <span className={"ad-pill " + (r.mode === "all" ? "ad-t-violet" : "ad-t-blue")}>
                      <i />{MODES[r.mode] || r.mode}
                    </span>
                    {!r.inApp && <span className="ad-pill ad-t-grey"><i />Hidden</span>}
                    {!r.products && <span className="ad-pill ad-t-amber"><i />Nothing in it</span>}
                  </div>
                  <small>
                    <code>/{r.slug}</code>
                    {r.parent ? ` · under ${r.parent}` : ""}
                    {` · ${r.products} product${r.products === 1 ? "" : "s"}`}
                    {r.children ? ` · ${r.children} sub${r.children === 1 ? "" : "s"}` : ""}
                  </small>
                  {r.blurb ? <p className="ad-cat-blurb">{r.blurb}</p> : null}
                </div>

                <div className="ad-cat-act">
                  <button className="ad-btn ad-sm" disabled={act.busy}
                    onClick={() => { setFormError(""); setEditing(r); }}>How it looks</button>
                  <button className="ad-btn ad-sm" disabled={act.busy}
                    onClick={() => toggleShown(r)}>{r.inApp ? "Hide" : "Show"}</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {editing && (
        <CategoryDialog row={editing} error={formError} busy={act.busy}
          onCancel={() => setEditing(null)} onSave={saveDialog} />
      )}
    </div>
  );
}

/* How the app draws one category. A Drawer rather than a bespoke modal,
   because that is the shell every other form in this console uses - and the
   blurb and the two colours only make sense seen together, so a colour picked
   beside the words it sits behind is picked once. */
function CategoryDialog({ row, error, busy, onCancel, onSave }) {
  const [draft, setDraft] = useState({
    mart_blurb: row.blurb || "",
    mart_tone: row.tone || "#f4f6f8",
    mart_accent: row.accent || "#0b4a6e",
    mart_mode: row.ownMode || "quick",
  });
  const set = (k) => (e) => setDraft((d) => ({ ...d, [k]: e.target.value }));

  const submit = () => {
    const values = { ...draft };
    /* A sub-category follows its top-level parent, so sending a storefront
       for one would be refused by the model - correctly. Do not send it. */
    if (!row.topLevel) delete values.mart_mode;
    onSave(values);
  };

  return (
    <Drawer
      title={row.name}
      sub="How the app draws this category. The name and the app address are changed in Odoo - the address is a link a customer may have saved."
      onClose={onCancel}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={busy} onClick={submit}>Save</button>
        </>
      )}>
      {error && <p className="ad-hint ad-form-error" role="alert"><Icon n="info" size={14} />{error}</p>}

      {/* What the shopper will see, above the controls that change it. */}
      <div className="ad-cat-preview"
        style={{ background: draft.mart_tone, color: draft.mart_accent }}>
        <b>{row.name}</b>
        <small>{draft.mart_blurb || "No line under the title"}</small>
      </div>

      <div className="ad-form">
        <label className="ad-field ad-span2"><span>One line under the title</span>
          <input value={draft.mart_blurb} onChange={set("mart_blurb")}
            placeholder="Farm-fresh produce, picked daily" /></label>

        <label className="ad-field"><span>Background</span>
          <span className="ad-colour">
            <input type="color" value={draft.mart_tone} onChange={set("mart_tone")} />
            <input value={draft.mart_tone} onChange={set("mart_tone")} />
          </span></label>

        <label className="ad-field"><span>Heading colour</span>
          <span className="ad-colour">
            <input type="color" value={draft.mart_accent} onChange={set("mart_accent")} />
            <input value={draft.mart_accent} onChange={set("mart_accent")} />
          </span></label>

        {row.topLevel ? (
          <label className="ad-field ad-span2"><span>Storefront</span>
            <select value={draft.mart_mode} onChange={set("mart_mode")}>
              <option value="quick">Quick - the 10-minute run</option>
              <option value="all">Express - ships over days</option>
            </select></label>
        ) : (
          <p className="ad-hint ad-span2">
            <Icon n="info" size={14} />
            This follows <b>{row.parent}</b>, which is in <b>{MODES[row.mode]}</b>.
            Change the storefront on the top-level category.
          </p>
        )}
      </div>
    </Drawer>
  );
}
