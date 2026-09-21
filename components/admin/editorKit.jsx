"use client";
/* ==========================================================================
   369 Mart — Admin · the parts every page editor is built from

   The home editor drew the shop's own page, wrapped each thing in a band you
   could click, and saved on its own. The product page editor wants all of
   that and none of the home page. So the machinery lives here and the two
   screens keep only what is actually about their own page.

   Nothing here knows what a banner or a section is. Anything that does
   belongs in the screen, not in this file.

   Two comments in here describe bugs that were paid for once already — the
   `finally` that releases the save latch, and the one-DndContext-per-group
   rule. They moved across with their reasons attached, deliberately.
   ========================================================================== */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter,
  useSensor, useSensors,
} from "@dnd-kit/core";
import {
  SortableContext, sortableKeyboardCoordinates, useSortable,
  verticalListSortingStrategy, horizontalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { api } from "@/lib/api";
import { Icon } from "./AdminUI";
import "./editor.css";

export const uid = (kind, id) => `${kind}:${id}`;

/* The storefront's icon set has no eye, and this is the one control whose
   meaning has to be obvious at a glance. */
export const Eye = ({ off }) => (
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

   Each job carries its own path, so two different routes still share one
   queue and one "Saved" chip. Two chips disagreeing about whether the page is
   saved would be worse than either.

   `invalidate` is the cache prefix to drop after a successful write — the
   shop's own copy of whatever was just changed. */
export function useAutosave({ onSaved, invalidate } = {}) {
  const [state, setState] = useState({ status: "idle", error: "" });
  const pending = useRef(new Map()); /* key -> {path, values, method} */
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
      const r = await api(job.path, { method: job.method || "PATCH", body: job.values });
      if (invalidate) api.invalidate(invalidate);
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
  }, [onSaved, invalidate]);

  const queue = useCallback((key, path, values, { now = false, method } = {}) => {
    const prev = pending.current.get(key);
    pending.current.set(key, {
      path, method: method || prev?.method,
      values: { ...prev?.values, ...values },
    });
    clearTimeout(timer.current);
    timer.current = setTimeout(flush, now ? 0 : 600);
  }, [flush]);

  useEffect(() => () => clearTimeout(timer.current), []);
  return { ...state, queue };
}

export function SaveChip({ status, error }) {
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

/* The inline failure strip. A screen that swaps itself for an error card
   throws away everything the operator could still read. */
export function ErrorStrip({ error, onRetry }) {
  if (!error) return null;
  return (
    <p className="ad-hint pe-error" role="alert">
      <Icon n="info" size={14} />
      We could not reach the shop. {error.message}
      <button className="ad-link" onClick={onRetry}>Try again</button>
    </p>
  );
}

/* --------------------------------------------------------------- the bands */

/* One selectable, hideable band. No dragging — a page whose parts have a
   fixed order wants the shell without the sortable, and asking for one used
   to mean getting both.

   `grip` is whatever starts a drag, or nothing. The whole band stays
   clickable to select either way. */
export function BandShell({
  bandId, tag, label, hidden, selected, onSelect, onToggle, horizontal,
  grip, innerRef, style, className = "", children,
}) {
  return (
    <div
      ref={innerRef}
      data-band={bandId}
      className={"pe-band" + (selected ? " pe-on" : "") + (hidden ? " pe-hidden" : "")
        + (horizontal ? " pe-band-h" : "") + (className ? " " + className : "")}
      style={style}
      onClick={(e) => { if (!e.target.closest(".pe-tool")) onSelect?.(); }}
    >
      <div className="pe-tools">
        {/* The name sits with the handle and the eye rather than in the
            opposite corner: a chip in the top-left lands straight on a rail's
            heading, and covering the title of the thing you are naming is
            worse than not naming it. */}
        {tag && <span className="pe-tag">{tag}</span>}
        {hidden && <span className="pe-tag pe-tag-off">Hidden</span>}
        {grip}
        {onToggle && (
          <button className="pe-tool" onClick={onToggle}
            aria-pressed={!hidden}
            aria-label={hidden ? `Show ${label}` : `Hide ${label}`}
            title={hidden ? "Show this in the app" : "Hide this from the app"}>
            <Eye off={hidden} />
          </button>
        )}
      </div>
      <div className="pe-band-in" aria-hidden={hidden ? "true" : undefined}>{children}</div>
    </div>
  );
}

/* The same band, draggable. The handle is a real button, so the keyboard can
   pick it up (space, arrows, space) without a mouse. */
export function SortableBand({ id, label, ...rest }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef,
    transform, transition, isDragging } = useSortable({ id });
  const grip = (
    /* setActivatorNodeRef names this the handle. Without it dnd-kit has no
       activator to check against, and any focused thing inside the band could
       start a drag. */
    <button className="pe-tool pe-grip" ref={setActivatorNodeRef}
      {...attributes} {...listeners}
      aria-label={`Reorder ${label}`} title="Drag to reorder">
      <svg viewBox="0 0 10 16" width="10" height="16" aria-hidden="true">
        <circle cx="2.5" cy="3" r="1.3" /><circle cx="7.5" cy="3" r="1.3" />
        <circle cx="2.5" cy="8" r="1.3" /><circle cx="7.5" cy="8" r="1.3" />
        <circle cx="2.5" cy="13" r="1.3" /><circle cx="7.5" cy="13" r="1.3" />
      </svg>
    </button>
  );
  return (
    <BandShell
      bandId={id} label={label} grip={grip} innerRef={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={isDragging ? "pe-dragging" : ""}
      {...rest}
    />
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
export function SortGroup({
  kind, items, selected, onSelect, onToggle, onDragEnd, horizontal,
  className, render, tagOf, labelOf,
}) {
  const strategy = horizontal ? horizontalListSortingStrategy : verticalListSortingStrategy;
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <SortableContext items={items.map((it) => uid(kind, it.rid))} strategy={strategy}>
        <div className={className}>
          {items.map((it, i) => (
            <SortableBand key={it.rid} id={uid(kind, it.rid)} horizontal={horizontal}
              tag={tagOf(kind, it)}
              label={labelOf(kind, it)}
              hidden={!it.active}
              selected={selected?.kind === kind && selected?.id === it.rid}
              onSelect={() => onSelect(kind, it.rid)}
              onToggle={() => onToggle(kind, it.rid, !it.active)}>
              {render(it, i)}
            </SortableBand>
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}

/* ---------------------------------------------------------------- the form */

/* One renderer for a registry of `[field, label, hint, vocabKey?]` tuples.
   A select when the field has a vocabulary, an input otherwise. */
export function FieldRows({ fields, values, vocab, onChange }) {
  return fields.map(([field, label, hint, vocabKey]) => (
    <label key={field} className="ad-field ad-span2">
      <span>{label}</span>
      {vocabKey ? (
        <select value={values[field] || ""} onChange={(e) => onChange(field, e.target.value)}>
          {(vocab?.[vocabKey] || []).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      ) : (
        <input value={values[field] ?? ""} placeholder={hint} aria-label={label}
          onChange={(e) => onChange(field, e.target.value)} />
      )}
      {hint && !vocabKey && <em className="pe-hint">{hint}</em>}
    </label>
  ));
}

/* ------------------------------------------------------------- landing on it */

/* Something just added is at the bottom of a list you are not looking at.
   Take the screen there and flash it, or "+ Banner" looks broken.

   The retry loop is because the row is added by a reload, so the node does
   not exist on the tick the id arrives. Two seconds, then give up quietly
   rather than hold a timer open for the session. */
export function useLanded(key, onDone) {
  useEffect(() => {
    if (!key) return undefined;
    let tries = 0;
    let timer = null;
    const reduced = typeof window !== "undefined" && window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const look = () => {
      const el = document.querySelector(`[data-band="${key}"]`);
      if (!el) {
        if (tries++ < 40) timer = setTimeout(look, 50);
        else onDone?.();
        return;
      }
      el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
      el.classList.add("pe-landed");
      timer = setTimeout(() => { el.classList.remove("pe-landed"); onDone?.(); }, 1600);
    };
    look();
    return () => clearTimeout(timer);
  }, [key, onDone]);
}
