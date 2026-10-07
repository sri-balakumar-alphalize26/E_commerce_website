"use client";
/* ==========================================================================
   Country code, searchable - the chip in front of a mobile number.

   Tap the chip: a panel opens under the field with a search box already
   focused. Type a name ("ind"), a code ("in") or the digits ("91", "+91") -
   exact code and dial matches come first, then names. Enter picks the
   highlighted row (the top one), ↑/↓ move, Esc or a click outside closes.
   The shop's own country sits at the top until something is typed.

   Used by the customer sign-in (SignIn.jsx) and the staff sign-in.
   ========================================================================== */
import { useEffect, useMemo, useRef, useState } from "react";

/* 🇮🇳 from "IN" - regional indicator letters. */
export const flag = (code) =>
  (code || "").length === 2
    ? String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
    : "";

function rank(c, q) {
  const digits = q.replace(/\D/g, "");
  const dial = (c.dial || "").replace(/\D/g, "");
  const name = (c.name || "").toLowerCase();
  const code = (c.code || "").toLowerCase();
  const word = q.toLowerCase().replace(/^\+/, "").trim();
  if (digits && dial === digits) return 0;
  if (word && code === word) return 1;
  if (word && name.startsWith(word)) return 2;
  if (digits && dial.startsWith(digits)) return 3;
  if (word && name.split(/[\s(-]+/).some((w) => w.startsWith(word))) return 4;
  if (word && name.includes(word)) return 5;
  return -1;
}

export default function CountryPicker({ countries, value, onChange, home, onPicked, label = "Country code" }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  const box = useRef(null);
  const search = useRef(null);
  const list = useRef(null);
  const current = countries.find((c) => c.code === value) || { code: value, dial: "" };

  const shown = useMemo(() => {
    const term = q.trim();
    if (!term) {
      const top = countries.filter((c) => c.code === home);
      return [...top, ...countries.filter((c) => c.code !== home)];
    }
    return countries
      .map((c) => [rank(c, term), c])
      .filter(([r]) => r >= 0)
      .sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name))
      .map(([, c]) => c);
  }, [countries, q, home]);

  useEffect(() => { setHi(0); }, [q]);
  useEffect(() => {
    if (!open) return undefined;
    search.current?.focus();
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  useEffect(() => {
    list.current?.querySelector(`[data-i="${hi}"]`)?.scrollIntoView({ block: "nearest" });
  }, [hi]);

  const pick = (c) => {
    if (!c) return;
    onChange(c.code);
    setOpen(false);
    setQ("");
    onPicked?.();
  };

  const keys = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((i) => Math.min(i + 1, shown.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); pick(shown[hi]); }
    else if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
  };

  return (
    <span className="cp" ref={box}>
      <button type="button" className="cp-chip" aria-haspopup="listbox" aria-expanded={open}
        aria-label={`${label}: ${current.name || current.code} ${current.dial}`} onClick={() => setOpen((o) => !o)}>
        <span aria-hidden="true">{flag(current.code)} {current.dial}</span>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {open && (
        <div className="cp-panel">
          <input ref={search} className="cp-search" type="search" role="combobox" aria-expanded="true"
            aria-controls="cp-list" aria-activedescendant={shown[hi] ? `cp-${shown[hi].code}` : undefined}
            placeholder="Search country or code, e.g. India or 91" value={q}
            onChange={(e) => setQ(e.target.value)} onKeyDown={keys} />
          <ul id="cp-list" role="listbox" ref={list} className="cp-list" aria-label={label}>
            {shown.length ? shown.map((c, i) => (
              <li key={c.code} id={`cp-${c.code}`} data-i={i} role="option" aria-selected={c.code === value}
                className={(i === hi ? "cp-hi " : "") + (c.code === value ? "cp-on" : "")}
                onPointerEnter={() => setHi(i)} onClick={() => pick(c)}>
                <span className="cp-flag" aria-hidden="true">{flag(c.code)}</span>
                <span className="cp-name">{c.name}</span>
                <span className="cp-dial">{c.dial}</span>
              </li>
            )) : <li className="cp-none" aria-disabled="true">No country matches “{q}”</li>}
          </ul>
        </div>
      )}
    </span>
  );
}
