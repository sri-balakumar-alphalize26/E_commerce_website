"use client";

/* Getting pictures on screen before they are asked for. */

import { preconnect } from "react-dom";

/* Open the connection to wherever the pictures live, so the first one does not
   also pay for setting that up (about 0.35 s to the Image Server). */
const warmed = new Set();
export function warmUp(url) {
  const origin = /^https?:\/\/[^/]+/i.exec(url || "")?.[0];
  if (!origin || warmed.has(origin)) return;
  warmed.add(origin);
  preconnect(origin);
}

/* Fetch pictures into the browser's cache. Kept in `held` so an unfinished
   download is not dropped, and so each address is only asked for once. */
const held = new Map();
const HELD_MAX = 200;

/* Someone on a data saver or a very slow line pays for every picture fetched
   ahead of time, and most of them are never looked at. */
function worthFetching() {
  const net = typeof navigator !== "undefined" ? navigator.connection : null;
  return !net || (!net.saveData && !/2g/.test(net.effectiveType || ""));
}

export function preload(urls) {
  if (typeof window === "undefined" || !worthFetching()) return;
  for (const url of urls) {
    if (!url || held.has(url)) continue;
    if (held.size >= HELD_MAX) held.delete(held.keys().next().value);
    const img = new Image();
    img.decoding = "async";
    img.src = url;
    held.set(url, img);
  }
}

/* After the page has settled, so it never competes with the picture on show. */
export function whenIdle(fn) {
  if (typeof window === "undefined") return () => {};
  if (window.requestIdleCallback) {
    const id = window.requestIdleCallback(fn, { timeout: 1500 });
    return () => window.cancelIdleCallback(id);
  }
  const id = setTimeout(fn, 300);
  return () => clearTimeout(id);
}

/* A product's main pictures, photos and video posters alike. */
export function galleryOf(p) {
  if (p?.media?.length) return p.media.map((it) => (it.type === "video" ? it.poster : it.src)).filter(Boolean);
  return p?.images || [];
}
