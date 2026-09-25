"use client";
/* ==========================================================================
   369 Mart — searchable picker (address form: Country, State)
   Looks like the form's other boxes, label riding at the top. Opens a panel
   with a search box and grouped options - "Suggested" first - that answers
   to the keyboard like a native select: ↑ ↓ to move, Enter to choose, Esc to
   close, and typing to filter by name, code or dial code.
   The panel is portalled to <body>: the form sits inside folding panels that
   clip whatever overflows them.
   ========================================================================== */
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./shared";

const PANEL_MAX = 340;

/* options: [{ value, label, hint?, search }] - `search` is the lower-case text
   typing is matched against. groups: [{ label, items }] shown before a search. */
export default function Pick({
  label, value, options, groups, onChange, placeholder = "Select",
  searchLabel = "Search", emptyText = "Nothing matches", error, disabled, className = "",
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const [pos, setPos] = useState(null);
  const box = useRef(null);
  const btn = useRef(null);
  const pop = useRef(null);
  const find = useRef(null);
  const id = useId();

  const current = options.find((o) => o.value === value);
  const needle = q.trim().toLowerCase().replace(/^\+/, "");
  const shown = needle
    ? [{ label: "", items: options.filter((o) => o.search.includes(needle)) }]
    : (groups || [{ label: "", items: options }]).filter((g) => g.items.length);
  const flat = shown.flatMap((g) => g.items);

  /* Where the panel goes: under the box, or over it when the page has no room
     below. Follows the box while the page scrolls. */
  const place = () => {
    const r = box.current?.getBoundingClientRect();
    if (!r) return;
    const below = window.innerHeight - r.bottom;
    const up = below < Math.min(PANEL_MAX, 260) && r.top > below;
    setPos({ left: r.left, width: r.width, up, top: up ? undefined : r.bottom + 6, bottom: up ? window.innerHeight - r.top + 6 : undefined,
      max: Math.max(180, Math.min(PANEL_MAX, (up ? r.top : below) - 16)) });
  };

  useLayoutEffect(() => {
    if (!open) return;
    place();
    const at = flat.findIndex((o) => o.value === value);
    setActive(at < 0 ? 0 : at);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open]); // eslint-disable-line

  /* The panel only exists once it has a place, so focus waits for that. */
  const placed = open && !!pos;
  useEffect(() => { if (placed) find.current?.focus({ preventScroll: true }); }, [placed]);

  useEffect(() => {
    if (!open) return;
    const away = (e) => { if (!box.current?.contains(e.target) && !pop.current?.contains(e.target)) close(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("touchstart", away, { passive: true });
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("touchstart", away); };
  }, [open]); // eslint-disable-line

  useEffect(() => {
    if (open) pop.current?.querySelector(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, open, q]);

  const close = (refocus = true) => { setOpen(false); setQ(""); setPos(null); if (refocus) btn.current?.focus({ preventScroll: true }); };
  const choose = (o) => { if (o) { onChange(o.value); close(); } };

  const keys = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, flat.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(flat.length - 1); }
    else if (e.key === "Enter") { e.preventDefault(); choose(flat[active]); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Tab") close(false);
  };

  let n = -1;
  return (
    <div ref={box} className={"co-field af-pick" + (open ? " af-open" : "") + (error ? " co-err" : "") + (className ? " " + className : "")}>
      <button ref={btn} type="button" className="af-pick-btn" disabled={disabled}
        aria-haspopup="listbox" aria-expanded={open} aria-invalid={!!error}
        onClick={() => (open ? close() : setOpen(true))}
        onKeyDown={(e) => { if (!open && ["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); setOpen(true); } }}>
        <span className={"af-pick-val" + (current ? "" : " af-ph")}>{current ? current.label : placeholder}</span>
        {current?.hint && <small className="af-pick-hint">{current.hint}</small>}
        <Icon n="chev" size={16} className="af-pick-chev" />
      </button>
      <span>{label}</span>
      {error && <em key={error}>{error}</em>}
      {open && pos && createPortal(
        <div ref={pop} className={"af-pop" + (pos.up ? " af-up" : "")} role="dialog" aria-label={label}
          onKeyDown={(e) => { if (e.target !== find.current) keys(e); }}
          style={{ left: pos.left, width: pos.width, top: pos.top, bottom: pos.bottom, maxHeight: pos.max }}>
          <label className="af-pop-find">
            <Icon n="search" size={16} />
            <input ref={find} value={q} placeholder={searchLabel} autoComplete="off" spellCheck={false}
              role="combobox" aria-expanded="true" aria-controls={id} aria-activedescendant={flat.length ? `${id}-${active}` : undefined}
              onChange={(e) => { setQ(e.target.value); setActive(0); }} onKeyDown={keys} />
          </label>
          <ul id={id} role="listbox" aria-label={label} className="af-pop-list">
            {!flat.length && <li className="af-pop-empty" role="presentation">{emptyText}</li>}
            {shown.map((g, gi) => (
              <li key={gi} role="presentation">
                {g.label && <b className="af-pop-group" aria-hidden="true">{g.label}</b>}
                <ul role="group" aria-label={g.label || undefined}>
                  {g.items.map((o) => {
                    n += 1;
                    const i = n;
                    const on = o.value === value;
                    return (
                      <li key={o.value} id={`${id}-${i}`} data-i={i} role="option" aria-selected={on}
                        className={(i === active ? "af-act" : "") + (on ? " af-on" : "")}
                        onMouseMove={() => active !== i && setActive(i)}
                        onMouseDown={(e) => e.preventDefault()} onClick={() => choose(o)}>
                        <span>{o.label}</span>
                        {o.hint && <small>{o.hint}</small>}
                        <i className="af-tick">{on && <Icon n="check" size={15} />}</i>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ul>
        </div>,
        document.body,
      )}
    </div>
  );
}
