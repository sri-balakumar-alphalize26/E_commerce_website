"use client";
/* Customers' review photos and videos, full size, over the page.
   The console's viewer (components/admin/AdminUI.jsx Lightbox), with the
   shop's own styles: items are { kind: "photo" | "video", src, label? };
   ← → move through them, Esc or a tap outside closes. */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./shared";

/* A review file's address as the browser reaches it: Odoo's /369mart/... goes
   through the shop's own /api/mart/..., which streams photo paths as they are. */
export const reviewMediaSrc = (url) => String(url || "").replace(/^\/369mart\//, "/api/mart/");

/* A review's photos and video as small tiles; a tap opens them full size.
   The public list only carries what staff approved; `own` is the shopper's
   own review, whose waiting items are labelled as such (and whose files the
   shop serves only once approved, so a waiting one shows its label alone). */
export function ReviewMedia({ media, own = false, onOpen }) {
  const list = (media || []).filter((m) => m?.url && (own || m.state !== "pending"));
  if (!list.length) return null;
  const shown = list.filter((m) => m.state !== "pending");
  const items = shown.map((m) => ({ kind: m.kind === "video" ? "video" : "photo", src: reviewMediaSrc(m.url) }));
  return (
    <div className="pd-rev-media">
      {list.map((m, k) => {
        const waiting = m.state === "pending";
        const at = shown.indexOf(m);
        const src = reviewMediaSrc(m.url);
        return (
          <button key={m.id ?? k} type="button" disabled={waiting} onClick={() => !waiting && onOpen?.({ items, start: at })}
            aria-label={waiting ? "Waiting for the shop to check it" : m.kind === "video" ? "Play the customer's video" : "View the customer's photo"}>
            {!waiting && (m.kind === "video" ? <video src={src} muted playsInline preload="metadata" /> : <img src={src} alt="" loading="lazy" />)}
            {!waiting && m.kind === "video" && <span className="pd-play" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg></span>}
            {waiting && <em>Waiting for check</em>}
          </button>
        );
      })}
    </div>
  );
}

export default function Lightbox({ items, start = 0, onClose }) {
  const [i, setI] = useState(start);
  const count = items.length;
  const go = (d) => setI((n) => (n + d + count) % count);
  useEffect(() => {
    const k = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); }
      else if (e.key === "ArrowRight" && count > 1) { e.stopPropagation(); go(1); }
      else if (e.key === "ArrowLeft" && count > 1) { e.stopPropagation(); go(-1); }
    };
    window.addEventListener("keydown", k, true);
    return () => window.removeEventListener("keydown", k, true);
  }); // eslint-disable-line
  if (typeof document === "undefined" || !count) return null;
  const item = items[Math.min(i, count - 1)];
  return createPortal(
    <div className="lb" role="dialog" aria-modal="true" aria-label={item.label || "Customer photo"} onClick={onClose}>
      <button className="lb-x" onClick={onClose} aria-label="Close" autoFocus><Icon n="x" size={20} /></button>
      {count > 1 && <span className="lb-count">{i + 1} / {count}</span>}
      <figure className="lb-stage" onClick={(e) => e.stopPropagation()}>
        {item.kind === "video"
          ? <video key={item.src} src={item.src} controls autoPlay playsInline />
          : <img key={item.src} src={item.src} alt={item.label || "Customer photo"} />}
      </figure>
      {count > 1 && (
        <>
          <button className="lb-nav lb-prev" onClick={(e) => { e.stopPropagation(); go(-1); }} aria-label="Previous"><Icon n="left" size={22} /></button>
          <button className="lb-nav lb-next" onClick={(e) => { e.stopPropagation(); go(1); }} aria-label="Next"><Icon n="right" size={22} /></button>
        </>
      )}
    </div>,
    document.body
  );
}
