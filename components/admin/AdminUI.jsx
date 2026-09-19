"use client";
/* ==========================================================================
   369 Mart admin — shared UI pieces (.ad-*)
   Icon set (admin extras + storefront icons), status pill, drawer, confirm,
   toolbar bits, switch, avatar, empty state, toast.
   ========================================================================== */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon as HomeIcon } from "../home/shared";
import { STATUS, initials } from "./adminData";

const EXTRA = {
  dash: <><rect x="3.5" y="3.5" width="7" height="9" rx="2" /><rect x="13.5" y="3.5" width="7" height="5" rx="2" /><rect x="3.5" y="15.5" width="7" height="5" rx="2" /><rect x="13.5" y="11.5" width="7" height="9" rx="2" /></>,
  users: <><circle cx="9" cy="8" r="3.4" /><path d="M3 20a6 6 0 0 1 12 0" /><path d="M16 5.2a3.4 3.4 0 0 1 0 6.6M17 14.4A6 6 0 0 1 21 20" /></>,
  gear: <><circle cx="12" cy="12" r="3.2" /><path d="M12 3.5v2.2M12 18.3v2.2M4.9 7.8l1.9 1.1M17.2 15.1l1.9 1.1M4.9 16.2l1.9-1.1M17.2 8.9l1.9-1.1" /></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
  download: <><path d="M12 4v11M8 11.5l4 4 4-4" /><path d="M5 20h14" /></>,
  dots: <><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></>,
  up: <><path d="M12 19V6M6.5 11.5 12 6l5.5 5.5" /></>,
  down: <><path d="M12 5v13M6.5 12.5 12 18l5.5-5.5" /></>,
  store: <><path d="M4 9.5 5.6 5h12.8L20 9.5" /><path d="M4 9.5a2.4 2.4 0 0 0 4 1.6 2.4 2.4 0 0 0 4 0 2.4 2.4 0 0 0 4 0 2.4 2.4 0 0 0 4-1.6" /><path d="M5.5 11.6V20h13v-8.4" /><path d="M10 20v-5h4v5" /></>,
  layers: <><path d="m12 3 9 5-9 5-9-5z" /><path d="m3 13 9 5 9-5" /></>,
  live: <><circle cx="12" cy="12" r="3" /><path d="M7.5 7.5a6.4 6.4 0 0 0 0 9M16.5 16.5a6.4 6.4 0 0 0 0-9M4.5 4.5a10.6 10.6 0 0 0 0 15M19.5 19.5a10.6 10.6 0 0 0 0-15" /></>,
};

export const Icon = ({ n, size = 20, className = "" }) =>
  EXTRA[n] ? (
    <svg className={"hm-ic " + className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{EXTRA[n]}</svg>
  ) : <HomeIcon n={n} size={size} className={className} />;

export const Pill = ({ s }) => {
  const m = STATUS[s] || { label: s, tone: "grey" };
  return <span className={"ad-pill ad-t-" + m.tone}><i />{m.label}</span>;
};

export const Avatar = ({ name, tone = "", size = 38 }) => (
  <span className={"ad-avatar " + tone} style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }}>{initials(name)}</span>
);

export function Switch({ on, onChange, label }) {
  return (
    <label className={"ad-switch" + (on ? " ad-on" : "")}>
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} aria-label={label} />
      <i aria-hidden="true" />
    </label>
  );
}

export function Search({ value, onChange, placeholder = "Search", wide }) {
  return (
    <label className={"ad-search" + (wide ? " ad-wide" : "")}>
      <Icon n="search" size={17} />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      {value && <button onClick={() => onChange("")} aria-label="Clear"><Icon n="x" size={13} /></button>}
    </label>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="ad-tabs" role="tablist">
      {tabs.map(([k, label, count]) => (
        <button key={k} role="tab" aria-selected={value === k} className={value === k ? "ad-on" : ""} onClick={() => onChange(k)}>
          {label}{count != null && <em>{count}</em>}
        </button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, options, label }) {
  return (
    <label className="ad-select">
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <Icon n="chev" size={16} />
    </label>
  );
}

export function Empty({ icon = "box", title, text, action, onAction }) {
  return (
    <div className="ad-empty">
      <span><Icon n={icon} size={26} /></span>
      <b>{title}</b><p>{text}</p>
      {action && <button className="ad-btn ad-primary" onClick={onAction}>{action}</button>}
    </div>
  );
}

/* right-side drawer (bottom sheet on phones) */
export function Drawer({ title, sub, onClose, children, foot, wide }) {
  const [out, setOut] = useState(false);
  const close = () => { setOut(true); setTimeout(onClose, 220); };
  useEffect(() => {
    const k = (e) => e.key === "Escape" && close();
    window.addEventListener("keydown", k);
    document.documentElement.classList.add("ad-lock");
    return () => { window.removeEventListener("keydown", k); document.documentElement.classList.remove("ad-lock"); };
  }); // eslint-disable-line
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className={"ad-drawer-wrap" + (out ? " ad-out" : "")} onClick={close}>
      <section className={"ad-drawer" + (wide ? " ad-drawer-wide" : "")} role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header>
          <div><h3>{title}</h3>{sub && <small>{sub}</small>}</div>
          <button className="ad-icon-btn" onClick={close} aria-label="Close"><Icon n="x" size={17} /></button>
        </header>
        <div className="ad-drawer-body">{children}</div>
        {foot && <footer>{typeof foot === "function" ? foot(close) : foot}</footer>}
      </section>
    </div>,
    document.body
  );
}

export function Confirm({ title, text, danger, confirmLabel = "Confirm", onCancel, onConfirm }) {
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="ad-modal-wrap" onClick={onCancel}>
      <div className="ad-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <span className={"ad-modal-ic" + (danger ? " ad-danger-ic" : "")}><Icon n={danger ? "trash" : "check"} size={22} /></span>
        <h3>{title}</h3><p>{text}</p>
        <div>
          <button className="ad-btn" onClick={onCancel} autoFocus>Cancel</button>
          <button className={"ad-btn " + (danger ? "ad-danger" : "ad-primary")} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>,
    document.body
  );
}

export function useToast() {
  const [toast, setToast] = useState(null);
  const t = useRef(null);
  const flash = (text, tone = "") => { setToast({ text, tone }); clearTimeout(t.current); t.current = setTimeout(() => setToast(null), 2600); };
  useEffect(() => () => clearTimeout(t.current), []);
  const node = <div className={"ad-toast" + (toast ? " ad-show " : " ") + (toast?.tone || "")} role="status" aria-live="polite">{toast && <><Icon n={toast.tone === "bad" ? "info" : "check"} size={16} />{toast.text}</>}</div>;
  return [node, flash];
}
