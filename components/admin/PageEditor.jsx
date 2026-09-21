"use client";
/* ==========================================================================
   369 Mart — Admin · the home page editor

   The shop's own home page on the left, a panel on the right. Click anything
   on the page to edit it; drag the handle to reorder; every change saves on
   its own.

   The page is not a mock. It renders the storefront's own components from
   the storefront's own payload, so what the operator sees is what the
   customer gets — the same principle the Odoo builder was built on, and the
   reason a drifting copy of the shop is never drawn here.

   Adding, removing and restoring all happen here, on the page that is open.
   Odoo's own builder always edits whichever page is live, so adding a banner
   there while a festival page was on screen put the banner on the everyday
   page instead - which is why these routes name the page in the URL.

   What is still Odoo's: images, the products inside a row, and emptying the
   Trash for good.
   ========================================================================== */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter,
  useSensor, useSensors,
} from "@dnd-kit/core";
import {
  SortableContext, sortableKeyboardCoordinates, useSortable,
  verticalListSortingStrategy, horizontalListSortingStrategy, arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { api } from "@/lib/api";
import { useResource } from "@/lib/useFetch";
import {
  Banner, CategoryStrip, ModeSwitchOverlay, Tabs as StoreTabs, useModeSwitch,
} from "@/components/home/Home";
import { Rail } from "@/components/home/shared";
import "@/components/home/home.css";
import { Confirm, Drawer, Empty, Icon, useToast } from "./AdminUI";
import "./editor.css";

/* Which group each thing belongs to, what the server calls it, and which of
   its fields the panel may edit. The field lists match `BAND_FIELDS` in
   admin_api.py exactly: a panel that offers a field the server refuses is a
   form that silently does nothing. */
const KINDS = {
  banner: {
    group: "banners", src: "banners", title: "Banner", short: "Banner",
    fields: [
      ["kicker", "Kicker", "The small line above the headline"],
      ["name", "Headline", ""],
      ["note", "Note", "The line underneath"],
      ["tone", "Colour", "", "tones"],
      ["href", "Link", "Where clicking it goes, e.g. /category/ssd"],
    ],
  },
  tile: {
    group: "categories", src: "tiles", title: "Category tile", short: "Tile",
    fields: [
      ["name", "Label", ""],
      ["route", "Link", "The category slug, e.g. keyboards"],
    ],
  },
  tab: {
    group: "tabs", src: "tabs", title: "Tab", short: "Tab",
    fields: [
      ["name", "Label", ""],
      ["icon", "Icon", "", "icons"],
    ],
  },
  section: {
    group: "sections", src: "bands", title: "Row", short: "Row",
    fields: [
      ["name", "Title", ""],
      ["subtitle", "Subtitle", ""],
      ["view_all_route", "See all link", "Where “View all” goes"],
    ],
  },
};
const uid = (kind, id) => `${kind}:${id}`;

/* The storefront's icon set has no eye, and this is the one control whose
   meaning has to be obvious at a glance. */
const Eye = ({ off }) => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
    strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="2.8" />
    {off && <path d="M4 20 20 4" />}
  </svg>
);

/* ------------------------------------------------------------------ saving */

/* One thing at a time, debounced, one request in flight. The same shape as
   the Odoo builder's save queue: a later edit to the same thing replaces the
   pending one rather than queueing a second write of the same field.

   Each job carries its own path, so a band and the tab's own settings - which
   are different routes - share one queue and one "Saved" chip. Two chips
   disagreeing about whether the page is saved would be worse than either. */
function useAutosave(onSaved) {
  const [state, setState] = useState({ status: "idle", error: "" });
  const pending = useRef(new Map()); /* key -> {path, values} */
  const timer = useRef(null);
  const busy = useRef(false);

  const flush = useCallback(async () => {
    if (!pending.current.size) return;
    /* Already saving: come back when it lands, rather than dropping this edit
       on the floor. `queue` has already merged it into `pending`, so all that
       is needed is another attempt. */
    if (busy.current) {
      clearTimeout(timer.current);
      timer.current = setTimeout(flush, 250);
      return;
    }
    /* Everything from here down is inside the try, so `finally` always
       releases the latch. It was not, and one request that never settled left
       `busy` true for good: every later save returned at the guard above
       before touching the state, and the chip sat on "Saving…" for the rest
       of the session with no way back. */
    try {
      busy.current = true;
      setState({ status: "saving", error: "" });
      const [key, job] = pending.current.entries().next().value;
      pending.current.delete(key);
      const r = await api(job.path, { method: "PATCH", body: job.values });
      api.invalidate("/home");
      onSaved?.(job, r);
      setState({ status: pending.current.size ? "saving" : "saved", error: "" });
    } catch (e) {
      /* The draft stays on screen. Losing what somebody just typed because
         the shop blinked is worse than an error that sits there. */
      setState({ status: "error", error: e?.message || "That did not save." });
    } finally {
      busy.current = false;
      if (pending.current.size) flush();
    }
  }, [onSaved]);

  const queue = useCallback((key, path, values, { now = false } = {}) => {
    const prev = pending.current.get(key);
    pending.current.set(key, { path, values: { ...prev?.values, ...values } });
    clearTimeout(timer.current);
    timer.current = setTimeout(flush, now ? 0 : 600);
  }, [flush]);

  useEffect(() => () => clearTimeout(timer.current), []);
  return { ...state, queue };
}

function SaveChip({ status, error }) {
  if (status === "idle") return null;
  const label = status === "saving" ? "Saving…"
    : status === "saved" ? "Saved"
      : error || "Not saved";
  return (
    <span className={"pe-chip pe-chip-" + status} role="status" aria-live="polite">
      <Icon n={status === "error" ? "info" : status === "saved" ? "check" : "clock"} size={13} />
      {label}
    </span>
  );
}

/* -------------------------------------------------------------- the page */

/* One draggable, selectable, hideable band of the page. The handle is a
   real button, so the whole band is still clickable to select and the
   keyboard can pick it up (space, arrows, space) without a mouse. */
function Band({ kind, id, label, kindLabel, hidden, selected, onSelect, onToggle, horizontal, children }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef,
    transform, transition, isDragging } = useSortable({ id: uid(kind, id) });
  return (
    <div
      ref={setNodeRef}
      data-band={uid(kind, id)}
      className={"pe-band" + (selected ? " pe-on" : "") + (hidden ? " pe-hidden" : "")
        + (isDragging ? " pe-dragging" : "") + (horizontal ? " pe-band-h" : "")}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      onClick={(e) => { if (!e.target.closest(".pe-tool")) onSelect(); }}
    >
      <div className="pe-tools">
        {/* The name sits with the handle and the eye rather than in the
            opposite corner: a chip in the top-left lands straight on a rail's
            heading, and covering the title of the thing you are naming is
            worse than not naming it. */}
        <span className="pe-tag">{kindLabel}</span>
        {hidden && <span className="pe-tag pe-tag-off">Hidden</span>}
        {/* setActivatorNodeRef names this the handle. Without it dnd-kit has
            no activator to check against, and any focused thing inside the
            band could start a drag. */}
        <button className="pe-tool pe-grip" ref={setActivatorNodeRef}
          {...attributes} {...listeners}
          aria-label={`Reorder ${label}`} title="Drag to reorder">
          <svg viewBox="0 0 10 16" width="10" height="16" aria-hidden="true">
            <circle cx="2.5" cy="3" r="1.3" /><circle cx="7.5" cy="3" r="1.3" />
            <circle cx="2.5" cy="8" r="1.3" /><circle cx="7.5" cy="8" r="1.3" />
            <circle cx="2.5" cy="13" r="1.3" /><circle cx="7.5" cy="13" r="1.3" />
          </svg>
        </button>
        <button className="pe-tool" onClick={onToggle}
          aria-pressed={!hidden}
          aria-label={hidden ? `Show ${label}` : `Hide ${label}`}
          title={hidden ? "Show this in the app" : "Hide this from the app"}>
          <Eye off={hidden} />
        </button>
      </div>
      <div className="pe-band-in" aria-hidden={hidden ? "true" : undefined}>{children}</div>
    </div>
  );
}

/* One DndContext per group, not one for the page.

   dnd-kit's keyboard coordinate getter does not confine itself to the active
   item's SortableContext - it walks every droppable registered in the
   surrounding DndContext. With all four groups sharing one, pressing the
   arrow key on a tab resolved onto whichever banner happened to sit below it,
   `onDragEnd` could not find that id in the tab list, and the drag was
   silently dropped. Keyboard reordering did nothing at all, while the mouse
   usually got away with it because the pointer stays inside its own group.

   Scoping the context to the group makes the candidates the right ones by
   construction, which is better than filtering the wrong ones out afterwards. */
function Group({ kind, items, selected, onSelect, onToggle, onDragEnd, horizontal, className, render }) {
  const strategy = horizontal ? horizontalListSortingStrategy : verticalListSortingStrategy;
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <SortableContext items={items.map((it) => uid(kind, it.rid))} strategy={strategy}>
        <div className={className}>
          {items.map((it, i) => (
            <Band key={it.rid} kind={kind} id={it.rid} horizontal={horizontal}
              kindLabel={KINDS[kind].short}
              label={it.title || it.label || KINDS[kind].title}
              hidden={!it.active}
              selected={selected?.kind === kind && selected?.id === it.rid}
              onSelect={() => onSelect(kind, it.rid)}
              onToggle={() => onToggle(kind, it.rid, !it.active)}>
              {render(it, i)}
            </Band>
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}

/* --------------------------------------------------------------- the panel */

/* The tab's own settings, shown when no band is selected.
 *
 * This is where the panel used to say "click something" and nothing else. The
 * fields here belong to the tab rather than to anything on it, and one of them
 * matters more than the rest: the promise. "in minutes" and "2–5 day delivery"
 * are what the shop tells a customer it will do, and they were written into
 * the storefront's source until now. */
function ModePanel({ mode, modeKey, vocab, onModeField, onRemove }) {
  const fields = [
    ["label", "Shown as", "What the tab is called: Quick, Express"],
    ["tagline", "Promise", "The line shown when someone switches to this tab"],
    ["icon", "Icon", "", "icons"],
    ["free_delivery_at", "Free delivery above", "0 for no nudge"],
  ];
  return (
    <>
      <header className="pe-panel-head">
        <div>
          <h2>{modeKey === "quick" ? "Quick" : "Express"} tab</h2>
          <p>What shoppers are told this tab is</p>
        </div>
      </header>

      <div className="ad-form pe-form">
        {fields.map(([field, label, hint, vocabKey]) => (
          <label key={field} className="ad-field ad-span2">
            <span>{label}</span>
            {vocabKey ? (
              <select value={mode?.[field] || ""}
                onChange={(e) => onModeField(field, e.target.value)}>
                {(vocab?.[vocabKey] || []).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            ) : (
              <input value={mode?.[field] ?? ""} placeholder={hint} aria-label={label}
                inputMode={field === "free_delivery_at" ? "decimal" : undefined}
                onChange={(e) => onModeField(field, e.target.value)} />
            )}
            {hint && !vocabKey && <em className="pe-hint">{hint}</em>}
          </label>
        ))}
      </div>

      <p className="ad-hint pe-note"><Icon n="info" size={14} />
        The promise is what a customer is told before they order. Switch tabs
        above to see it, and keep it true.
      </p>
      <p className="ad-hint"><Icon n="edit" size={14} />
        Click anything on the page to edit that instead.
      </p>
    </>
  );
}

function Panel({ selected, vals, vocab, onField, onToggle, onRemove, busy,
  mode, modeKey, onModeField }) {
  if (!selected) {
    return (
      <ModePanel mode={mode} modeKey={modeKey} vocab={vocab}
        onModeField={onModeField} />
    );
  }
  const spec = KINDS[selected.kind];
  if (!vals) return <div className="pe-empty"><b>That is gone. Reload the page.</b></div>;

  return (
    <>
      <header className="pe-panel-head">
        <div><h2>{spec.title}</h2><p>{vals.name || vals.label || "Untitled"}</p></div>
        <label className="ad-switch-lbl">
          <span>{vals.active ? "Shown" : "Hidden"}</span>
          <button className={"ad-switch" + (vals.active ? " ad-on" : "")}
            role="switch" aria-checked={!!vals.active}
            onClick={() => onToggle(selected.kind, selected.id, !vals.active)}>
            <i aria-hidden="true" />
          </button>
        </label>
      </header>

      <div className="ad-form pe-form">
        {spec.fields.map(([field, label, hint, vocabKey]) => (
          <label key={field} className="ad-field ad-span2">
            <span>{label}</span>
            {vocabKey ? (
              <select value={vals[field] || ""}
                onChange={(e) => onField(selected.kind, selected.id, field, e.target.value)}>
                {(vocab?.[vocabKey] || []).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            ) : (
              <input value={vals[field] ?? ""} placeholder={hint} aria-label={label}
                onChange={(e) => onField(selected.kind, selected.id, field, e.target.value)} />
            )}
            {hint && !vocabKey && <em className="pe-hint">{hint}</em>}
          </label>
        ))}
      </div>

      <div className="pe-panel-foot">
        <button className="ad-btn ad-danger" disabled={!!busy}
          onClick={() => onRemove(selected.kind, selected.id)}>
          <Icon n="trash" size={14} />Remove
        </button>
      </div>

      <p className="ad-hint pe-note"><Icon n="info" size={14} />
        Removing puts it in the Trash, where it can be put back. Images, the
        products inside a row, and the Trash itself are still in Odoo.
      </p>
    </>
  );
}

/* --------------------------------------------------------------- the Trash */

/* Removed things, grouped by what they are.
 *
 * Grouped rather than one flat list because "Banner · New banner" repeated
 * eleven times tells you nothing at a glance, while "Banners (3)" does. The
 * heading is the kind; under it is every one of that kind waiting to be put
 * back, newest first, with how long is left before it goes for good. */
/* One removed band, drawn the way the page draws it.
 *
 * A line of text is not enough to decide whether to put something back: two
 * banners both called "Onam" say nothing, and a row's name says nothing about
 * what was in it. So the Trash shows the thing itself, from the same
 * serialized payload the canvas uses. */
function TrashPreview({ kind, vals }) {
  if (!vals) {
    return <p className="pe-trash-gone">No preview — this one can still be put back.</p>;
  }
  if (kind === "banner") return <Banner b={{ ...vals, art: vals.art || [] }} i={0} />;
  if (kind === "tile") return <div className="hm-cats pe-trash-tile"><CategoryStrip cats={[vals]} onPick={() => {}} /></div>;
  if (kind === "tab") return <div className="pe-trash-tab"><StoreTabs tabs={[vals]} active={vals.key} onChange={() => {}} /></div>;
  if (vals.banner) return <p className="pe-trash-gone">A banner strip of {vals.banner.length}.</p>;
  if (vals.empty || !vals.items?.length) {
    return <p className="pe-trash-gone">This row had nothing in it.</p>;
  }
  return <Rail section={vals} cart={{}} setQty={() => {}} />;
}

function TrashDrawer({ rows, drawings, days, onRestore, onClose, busy }) {
  const groups = Object.entries(KINDS)
    .map(([kind, spec]) => [spec, rows.filter((r) => r.kind === kind)])
    .filter(([, items]) => items.length);

  return (
    <Drawer title="Trash" onClose={onClose}
      sub={rows.length
        ? `${rows.length} removed ${rows.length === 1 ? "item" : "items"}`
        : "Nothing removed"}>
      {!rows.length ? (
        <Empty icon="trash" title="The Trash is empty"
          text="Anything you remove from this page waits here before it is deleted for good." />
      ) : (
        <>
          <p className="ad-hint pe-trash-note"><Icon n="info" size={14} />
            {days
              ? `Removed items wait ${days} days, then go for good. Putting one back returns it exactly as it was — shown if it was shown, hidden if it was hidden.`
              : "Removed items are kept until you delete them for good. Putting one back returns it exactly as it was."}
          </p>
          {groups.map(([spec, items]) => (
            <section key={spec.short} className="pe-trash-group">
              <h4>{spec.title}s<em>{items.length}</em></h4>
              <ul>
                {items.map((row) => (
                  <li key={`${row.kind}:${row.id}`}>
                    <div className="pe-trash-head">
                      <span className="pe-trash-txt">
                        <b>{row.name || "Untitled"}</b>
                        <small>
                          Removed {row.deleted_at ? row.deleted_at.slice(0, 16) : ""}
                          {days ? ` · ${row.days_left} day${row.days_left === 1 ? "" : "s"} left` : ""}
                        </small>
                      </span>
                      <button className="ad-btn ad-sm" disabled={!!busy}
                        onClick={() => onRestore(row.kind, row.id)}>
                        Put back
                      </button>
                    </div>
                    <div className="pe-trash-preview hm-page">
                      <TrashPreview kind={row.kind}
                        vals={drawings?.[`${row.kind}:${row.id}`]} />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </>
      )}
    </Drawer>
  );
}

/* ================================== screen =============================== */

export default function PageEditor({ pageId }) {
  const router = useRouter();
  const [mode, setMode] = useState("quick");
  const { data, loading, error, reload } = useResource(
    `/admin/home/pages/${pageId}/builder?mode=${mode}`, { deps: [pageId, mode] });

  /* The server's answer, then this screen's own edits on top. Kept apart so a
     reload is a reload and not a merge conflict with what is on screen. */
  const [preview, setPreview] = useState(null);
  const [vals, setVals] = useState({});   /* "kind:id" -> editable values */
  const [selected, setSelected] = useState(null);
  const [showHidden, setShowHidden] = useState(false);

  useEffect(() => {
    if (!data?.ok) return;
    setPreview(data.preview || {});
    const next = {};
    for (const [kind, spec] of Object.entries(KINDS)) {
      for (const row of data[spec.src] || []) {
        next[uid(kind, row.id)] = { ...row };
      }
    }
    setVals(next);
    setModeVals({
      label: data.mode?.label || "",
      tagline: data.mode?.tagline || "",
      icon: data.mode?.icon || "grid",
      free_delivery_at: data.mode?.free_delivery_at ?? 0,
    });
    setSelected((s) => (s && next[uid(s.kind, s.id)] ? s : null));
  }, [data]);

  const save = useAutosave();

  const groups = preview || {};
  /* The canvas is the shop, so by default it draws exactly what the shop
     draws: the live bands, in order. Switched-off ones are still in the
     payload - they have to be, or there would be no way back - but showing
     them by default puts a page in front of the operator that no shopper will
     ever see, which is the one thing this screen must not do. */
  const all = (kind) => groups[KINDS[kind].group] || [];
  const byKind = (kind) => (showHidden ? all(kind) : all(kind).filter((it) => it.active));
  const hiddenCount = Object.keys(KINDS).reduce(
    (n, kind) => n + all(kind).filter((it) => !it.active).length, 0);

  /* An edit shows on the page at once and goes to the shop debounced. The
     page reads the app's own field names, the panel reads Odoo's, so one
     edit touches both. */
  const PREVIEW_FIELD = {
    banner: { name: "title", kicker: "kicker", note: "note", tone: "tone", href: "href" },
    tile: { name: "label", route: "route" },
    tab: { name: "label", icon: "icon" },
    section: { name: "title", subtitle: "subtitle", view_all_route: "route" },
  };

  const patchPreview = (kind, id, patch) =>
    setPreview((p) => (!p ? p : {
      ...p,
      [KINDS[kind].group]: (p[KINDS[kind].group] || []).map(
        (it) => (it.rid === id ? { ...it, ...patch } : it)),
    }));

  const onField = (kind, id, field, value) => {
    setVals((v) => ({ ...v, [uid(kind, id)]: { ...v[uid(kind, id)], [field]: value } }));
    const mapped = PREVIEW_FIELD[kind]?.[field];
    if (mapped) patchPreview(kind, id, { [mapped]: value });
    save.queue(uid(kind, id), `/admin/home/bands/${kind}/${id}`, { [field]: value });
  };

  const onToggle = (kind, id, active) => {
    setVals((v) => ({ ...v, [uid(kind, id)]: { ...v[uid(kind, id)], active } }));
    patchPreview(kind, id, { active });
    save.queue(uid(kind, id), `/admin/home/bands/${kind}/${id}`, { active }, { now: true });
  };

  const onDragEnd = async ({ active, over }) => {
    if (!over || active.id === over.id) return;
    const [kind] = String(active.id).split(":");
    const group = KINDS[kind].group;
    const list = groups[group] || [];
    const from = list.findIndex((it) => uid(kind, it.rid) === active.id);
    const to = list.findIndex((it) => uid(kind, it.rid) === over.id);
    if (from < 0 || to < 0) return;
    const moved = arrayMove(list, from, to);
    setPreview((p) => ({ ...p, [group]: moved }));
    try {
      await api(`/admin/home/bands/${kind}/reorder`, {
        method: "POST", body: { ids: moved.map((it) => it.rid) },
      });
      api.invalidate("/home");
    } catch (e) {
      /* Put it back rather than leave the screen claiming an order the shop
         does not have. */
      setPreview((p) => ({ ...p, [group]: list }));
      flash(e?.message || "That order did not save.", "bad");
    }
  };

  /* Adding and removing go to the shop and then re-read, rather than guessing
     what the new band looks like. The server decides the key, the sequence and
     every default, so a band made here and one made in Odoo's own builder are
     the same kind of thing. */
  const [busy, setBusy] = useState("");
  const [justAdded, setJustAdded] = useState(null);
  const [trashOpen, setTrashOpen] = useState(false);
  const [modeVals, setModeVals] = useState({});
  const [switchCopy, setSwitchCopy] = useState(null);
  /* The storefront's own switch animation, from the storefront's own hook, so
     changing tab here feels the way it feels in the shop. */
  const [fx, runSwitch] = useModeSwitch();
  const [confirm, setConfirm] = useState(null);
  const [toast, flash] = useToast();

  /* Scroll to the new band once it has actually been drawn. It cannot be done
     inside onAdd: the element does not exist until the reload lands and React
     has painted it. */
  useEffect(() => {
    if (!justAdded) return;
    let tries = 0;
    let timer = null;
    /* The band may not be painted the first time this runs: the reload's state
       and this one land in the same batch. Look again for a few frames rather
       than giving up and leaving the operator staring at an unchanged page. */
    const go = () => {
      const el = document.querySelector(`[data-band="${justAdded}"]`);
      if (!el) {
        if (tries++ < 40) timer = setTimeout(go, 50);
        return;
      }
      setJustAdded(null);
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      /* A beat of highlight: a smooth scroll that ends on a band looking like
         every other band leaves them hunting for what changed. */
      el.classList.add("pe-landed");
      timer = setTimeout(() => el.classList.remove("pe-landed"), 1600);
    };
    go();
    return () => clearTimeout(timer);
  }, [justAdded, preview]);

  const onAdd = async (kind) => {
    setBusy(kind);
    try {
      const r = await api(`/admin/home/pages/${pageId}/bands/${kind}`, {
        method: "POST", body: { mode },
      });
      api.invalidate("/home");
      await reload();
      /* Open it straight away, and take the operator to it. A new band is
         called "New banner" and goes to the bottom of its group, which on a
         full home page is well below the fold: without this, pressing the
         button looks like it did nothing at all. */
      setSelected({ kind, id: Number(r.band.id) });
      setShowHidden(false);
      setJustAdded(uid(kind, r.band.id));
    } catch (e) {
      flash(e?.message || "That could not be added.", "bad");
    } finally {
      setBusy("");
    }
  };

  /* The tab's own fields save the same way a band's do: shown at once, sent
     debounced. They go to their own route because they belong to the mode, not
     to anything on it. */
  const onModeField = (field, value) => {
    setModeVals((v) => ({ ...v, [field]: value }));
    save.queue(`mode:${mode}`, `/admin/home/pages/${pageId}/modes/${mode}`,
      { [field]: value });
  };

  const onRestore = async (kind, id) => {
    setBusy(kind);
    try {
      await api(`/admin/home/bands/${kind}/${id}/restore`, { method: "POST" });
      api.invalidate("/home");
      await reload();
      setSelected({ kind, id: Number(id) });
      setJustAdded(uid(kind, id));
      setTrashOpen(false);
    } catch (e) {
      flash(e?.message || "That could not be put back.", "bad");
    } finally {
      setBusy("");
    }
  };

  /* Asking goes through the console's own Confirm, not window.confirm. A
     native dialog is drawn by the browser, not by this app: it names the
     origin, it cannot say "Remove banner" on its button, and on a screen this
     carefully matched to the shop it looks like something went wrong. */
  const onRemove = (kind, id) => setConfirm({ kind, id });

  const doRemove = async ({ kind, id }) => {
    setConfirm(null);
    setBusy(kind);
    try {
      await api(`/admin/home/bands/${kind}/${id}`, { method: "DELETE" });
      api.invalidate("/home");
      setSelected(null);
      await reload();
      flash(`${KINDS[kind].title} moved to the Trash`);
    } catch (e) {
      flash(e?.message || "That could not be removed.", "bad");
    } finally {
      setBusy("");
    }
  };

  /* The wording of one tab, for the switch card.
   *
   * Read when the switch *starts*, not on every render: `runSwitch` swaps
   * `mode` half-way through the animation, and a card that recomputed after
   * that found `key === mode` and showed the tab being left instead of the one
   * being moved to. */
  const copyFor = (key) => {
    if (key === mode) {
      return { icon: modeVals.icon, title: modeVals.label, sub: modeVals.tagline };
    }
    const m = (data?.modes || []).find((x) => x.key === key);
    return { icon: m?.icon, title: m?.label, sub: m?.tagline };
  };

  const trash = data?.trash || [];
  const noop = useMemo(() => () => {}, []);
  const page = data?.page;
  const bannerById = useMemo(
    () => Object.fromEntries((groups.banners || []).map((b) => [b.id, b])), [groups.banners]);

  return (
    <div className="pe">
      <header className="pe-head">
        <button className="ad-btn" onClick={() => router.push("/admin/home")}>
          <Icon n="left" size={15} />All pages
        </button>
        <div className="pe-title">
          <h1>{page?.name || "Home page"}</h1>
          <small>{page?.stateNote || ""}</small>
        </div>
      </header>

      {/* Every control in one strip, rather than three of them loose in the
          top-right corner. */}
      <div className="pe-toolbar">
        <div className="ad-tabs" role="tablist">
          {[["quick", "Quick"], ["all", "Express"]].map(([k, l]) => (
            <button key={k} role="tab" aria-selected={mode === k}
              className={mode === k ? "ad-on" : ""}
              onClick={(e) => {
                if (mode === k) return;
                /* Same effect the shop plays, driven by the same hook. The
                   card's words are read now, before the swap moves `mode`. */
                setSwitchCopy(copyFor(k));
                runSwitch(k, e.currentTarget, () => setMode(k));
              }}>{l}</button>
          ))}
        </div>
        {hiddenCount > 0 && (
          <label className="pe-showhidden">
            <input type="checkbox" checked={showHidden}
              onChange={(e) => setShowHidden(e.target.checked)} />
            Show hidden ({hiddenCount})
          </label>
        )}
        <span className="pe-toolbar-gap" />
        {/* On the page that is open, not on whichever one happens to be live.
            Odoo's own builder always edits the live page, so adding a banner
            while a festival page was on screen put it on the everyday one. */}
        <span className="pe-adds">
          {["banner", "tile", "tab", "section"].map((kind) => (
            <button key={kind} className="ad-btn ad-sm" disabled={!!busy}
              onClick={() => onAdd(kind)}>
              <Icon n="plus" size={13} />{KINDS[kind].short}
            </button>
          ))}
        </span>
        <button className="ad-btn ad-sm pe-trash-btn" onClick={() => setTrashOpen(true)}>
          <Icon n="trash" size={13} />Trash{trash.length ? <em>{trash.length}</em> : null}
        </button>
        <SaveChip status={save.status} error={save.error} />
      </div>

      <p className="pe-hintbar">
        <Icon n="edit" size={14} />
        Click any part of the page to edit it. Drag the handle to reorder, or
        use the eye to hide it from the shop.
      </p>

      {error && (
        <p className="ad-hint pe-error" role="alert">
          <Icon n="info" size={14} />We could not reach the shop. {error.message}
          <button className="ad-link" onClick={reload}>Try again</button>
        </p>
      )}

      <div className="pe-cols">
          <div className="pe-canvas-wrap">
            <div className="pe-canvas">
              <div className="pe-chrome" aria-hidden="true">
                <span className="pe-dots"><i /><i /><i /></span>
                <span className="pe-url">369mart.com — the home page, as shoppers see it</span>
              </div>
              <div className="pe-screen hm-page" data-mode={mode}>
                <div className="hm-wrap pe-body">
                  {loading && !preview && <p className="pe-loading">Loading the page…</p>}

                {!!byKind("tab").length && (
                  <Group kind="tab" horizontal className="pe-tabs hm-tabs"
                    items={byKind("tab")} selected={selected}
                    onSelect={(k, id) => setSelected({ kind: k, id })} onToggle={onToggle}
                    onDragEnd={onDragEnd}
                    render={(t) => (
                      <StoreTabs tabs={[{ key: t.key, label: t.label, icon: t.icon }]}
                        active={t.key} onChange={noop} />
                    )} />
                )}

                {!!byKind("banner").length && (
                  <Group kind="banner" horizontal className="pe-banners hm-banner-track"
                    items={byKind("banner")} selected={selected}
                    onSelect={(k, id) => setSelected({ kind: k, id })} onToggle={onToggle}
                    onDragEnd={onDragEnd}
                    render={(b, i) => <Banner b={{ ...b, art: b.art || [] }} i={i} />} />
                )}

                {!!byKind("tile").length && (
                  <Group kind="tile" horizontal className="pe-tiles hm-cats hm-in"
                    items={byKind("tile")} selected={selected}
                    onSelect={(k, id) => setSelected({ kind: k, id })} onToggle={onToggle}
                    onDragEnd={onDragEnd}
                    render={(c) => <CategoryStrip cats={[c]} onPick={noop} />} />
                )}

                {!!byKind("section").length && (
                  <Group kind="section" className="pe-sections"
                    items={byKind("section")} selected={selected}
                    onSelect={(k, id) => setSelected({ kind: k, id })} onToggle={onToggle}
                    onDragEnd={onDragEnd}
                    render={(s) => (
                      s.banner ? (
                        <div className="hm-inline-banners">
                          {s.banner.map((key, k) => bannerById[key]
                            && <Banner key={key} b={bannerById[key]} i={k} />)}
                        </div>
                      ) : s.empty || !s.items?.length ? (
                        <p className="pe-row-empty">
                          <b>{s.title || "Untitled row"}</b>
                          <span>Nothing to show — no products match this row yet.</span>
                        </p>
                      ) : (
                        <Rail section={s} cart={{}} setQty={noop} />
                      )
                    )} />
                )}

                {preview && !byKind("banner").length && !byKind("section").length
                  && !byKind("tile").length && (
                  <p className="pe-loading">
                    {hiddenCount && !showHidden
                      ? "Everything on this tab is switched off. Turn on “Show hidden” to bring one back."
                      : "This tab has nothing on it yet."}
                  </p>
                )}
                </div>
              </div>
            </div>
            <p className="pe-canvas-note">
              The real home page, drawn with the shop’s own components from the
              same feed shoppers are served — not a mock of it. The shop swipes
              through the banners and tabs; here they are all laid out, so every
              one of them can be reached.
            </p>
          </div>

        <aside className="ad-card pe-panel">
          <Panel selected={selected}
            vals={selected ? vals[uid(selected.kind, selected.id)] : null}
            vocab={data?.vocab} onField={onField} onToggle={onToggle}
            onRemove={onRemove} busy={busy}
            mode={modeVals} modeKey={mode} onModeField={onModeField} />
        </aside>
      </div>

      {trashOpen && (
        <TrashDrawer rows={trash} drawings={data?.trash_preview} days={data?.trash_days} busy={busy}
          onRestore={onRestore} onClose={() => setTrashOpen(false)} />
      )}

      {confirm && (
        <Confirm danger
          title={`Remove this ${KINDS[confirm.kind].title.toLowerCase()}?`}
          text={data?.trash_days
            ? `It goes to the Trash, where you can put it back for ${data.trash_days} days.`
            : "It goes to the Trash, where you can put it back."}
          confirmLabel={`Remove ${KINDS[confirm.kind].short.toLowerCase()}`}
          onCancel={() => setConfirm(null)}
          onConfirm={() => doRemove(confirm)} />
      )}
      {toast}
      {/* The shop's own switch card, showing the words of the tab being
          switched *to* — which is the whole point of the card, and which the
          payload carries for both tabs so it does not have to wait for the
          reload to know them. */}
      <ModeSwitchOverlay fx={fx} copy={switchCopy} />
    </div>
  );
}
