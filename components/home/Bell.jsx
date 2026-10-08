"use client";
/* ==========================================================================
   369 Mart — the bell
   Header button with the unread count; opens the latest few notifications
   (the same feed as Account > Notifications, from the shop), mark all read,
   and an offer to turn on pop-ups for when the shop is closed.

   While the page is open the feed is re-read every minute, and at once when
   the pop-up worker (public/sw.js) says the shop just sent something - a new
   unread one slides in as a card at the top of the page.
   ========================================================================== */
import { useEffect, useRef, useState } from "react";
import { Icon } from "./shared";
import { ago } from "./accountStore";
import { usePush } from "@/lib/push";

const NOTE_IC = { order: "box", offer: "pct", wallet: "wallet" };
const SHOWN = 6;
const HIDE_OFFER = "369mart.pushOfferHidden";

const offerHidden = () => { try { return localStorage.getItem(HIDE_OFFER) === "1"; } catch (e) { return false; } };
const hideOffer = () => { try { localStorage.setItem(HIDE_OFFER, "1"); } catch (e) {} };

/* The bit of the bell that asks for pop-ups. Shown only where the browser can
   do them and the customer has neither said yes nor blocked them. */
export function PushOffer({ push, compact = false, onClose }) {
  if (push.state !== "off") return null;
  return (
    <div className={"bl-offer" + (compact ? " bl-offer-compact" : "")}>
      <span className="bl-offer-ic"><Icon n="bell" size={18} /></span>
      <span className="bl-offer-txt">
        <b>Get order updates as pop-ups</b>
        <small>Confirmed, on the way, delivered - even when this site is closed.</small>
        {push.error && <small className="bl-offer-err">{push.error}</small>}
      </span>
      <span className="bl-offer-act">
        <button className="bl-on" disabled={push.busy} onClick={push.turnOn}>{push.busy ? "Turning on…" : "Turn on"}</button>
        {onClose && <button className="bl-later" onClick={onClose}>Not now</button>}
      </span>
    </div>
  );
}

function Row({ n, now, onOpen }) {
  return (
    <button className={"bl-row" + (n.read ? "" : " bl-unread")} onClick={onOpen}>
      <span className={"bl-ic bl-t-" + n.type}><Icon n={NOTE_IC[n.type] || "bell"} size={16} /></span>
      <span className="bl-txt"><b>{n.title}</b><small>{n.text}</small><em>{n.at ? ago(n.at, now) : ""}</em></span>
      {!n.read && <i className="bl-dot" aria-label="Unread" />}
    </button>
  );
}

export default function Bell({ notes, onGo, onSeeAll }) {
  const { all, unread, send, reload } = notes;
  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const [offerOff, setOfferOff] = useState(true);
  const push = usePush(true);
  const wrap = useRef(null);
  const seen = useRef(null);

  useEffect(() => setOfferOff(offerHidden()), []);

  /* Close on a click elsewhere or Escape. */
  useEffect(() => {
    if (!open) return;
    const away = (e) => { if (!wrap.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);

  /* The shop just sent a pop-up and this page is in front: read the feed now. */
  const reloadRef = useRef(reload);
  reloadRef.current = reload;
  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.serviceWorker) return;
    const on = (e) => { if (e.data?.type === "369mart:push") reloadRef.current?.(); };
    navigator.serviceWorker.addEventListener("message", on);
    return () => navigator.serviceWorker.removeEventListener("message", on);
  }, []);

  /* Something new and unread since the page opened: a card for the newest.
     What was already there when the page loaded is not news. */
  useEffect(() => {
    if (!all.length && seen.current === null) return;
    if (seen.current === null) { seen.current = new Set(all.map((n) => n.id)); return; }
    const fresh = all.filter((n) => !n.read && !seen.current.has(n.id));
    all.forEach((n) => seen.current.add(n.id));
    if (fresh.length) setToast(fresh[0]);
  }, [all]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 7000);
    return () => clearTimeout(t);
  }, [toast]);

  const go = (n) => {
    if (!n.read) send("/notifications/read", { method: "POST", body: { ids: [n.id] } });
    setOpen(false);
    setToast(null);
    onGo?.(n.go || []);
  };
  const now = Date.now();
  const list = all.slice(0, SHOWN);

  return (
    <div className="bl-wrap" ref={wrap}>
      <button className={"hm-iconbtn bl-btn" + (open ? " hm-iconbtn-on" : "")} onClick={() => setOpen((v) => !v)}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"} aria-expanded={open} aria-haspopup="dialog">
        <Icon n="bell" />
        {unread > 0 && <span key={unread} className="hm-badge">{unread > 9 ? "9+" : unread}</span>}
      </button>

      {open && (
        <div className="bl-panel" role="dialog" aria-label="Notifications">
          <div className="bl-head">
            <b>Notifications</b>
            <button className="bl-link" disabled={!unread} onClick={() => send("/notifications/read", { method: "POST", body: { all: true } })}>
              <Icon n="check" size={14} />Mark all read
            </button>
          </div>
          {!offerOff && <PushOffer push={push} compact onClose={() => { hideOffer(); setOfferOff(true); }} />}
          <div className="bl-list">
            {list.length ? list.map((n) => <Row key={n.id} n={n} now={now} onOpen={() => go(n)} />) : (
              <div className="bl-empty"><Icon n="bell" size={26} /><b>You&apos;re all caught up</b><small>Order updates and offers will show up here.</small></div>
            )}
          </div>
          <button className="bl-all" onClick={() => { setOpen(false); onSeeAll?.(); }}>See all notifications<Icon n="right" size={14} /></button>
        </div>
      )}

      {toast && (
        <button className="bl-toast" onClick={() => go(toast)} role="status">
          <span className={"bl-ic bl-t-" + toast.type}><Icon n={NOTE_IC[toast.type] || "bell"} size={16} /></span>
          <span className="bl-txt"><b>{toast.title}</b><small>{toast.text}</small></span>
          <span className="bl-toast-x" role="button" aria-label="Close" onClick={(e) => { e.stopPropagation(); setToast(null); }}><Icon n="x" size={14} /></span>
        </button>
      )}
    </div>
  );
}
