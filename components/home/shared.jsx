"use client";
/* Shared pieces used by Home.jsx and Cart.jsx */
import { createContext, useCallback, useContext, useEffect, useRef, useState, useSyncExternalStore } from "react";

/* wishlist shared by cards, search and the account "My List" page */
export const WishContext = createContext(null);
/* open the product page: open(product, rectOfTappedImage) */
export const OpenContext = createContext(null);
import ProductArt from "./art";

export const inr = (n) => "₹" + Number(n).toLocaleString("en-IN");
export const SEARCH_WORDS = ["Atta", "Bananas", "Coffee beans", "Headphones", "Green tea", "Dinner set"];

/* ---------- icons ---------- */
const P = {
  bag: <><path d="M5 8h14l-1 12H6z" /><path d="M9 8V6a3 3 0 0 1 6 0v2" /></>,
  basket: <><path d="M4 10h16l-1.6 9a2 2 0 0 1-2 1.6H7.6a2 2 0 0 1-2-1.6z" /><path d="m9 10 3-6 3 6" /></>,
  leaf: <><path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15" /><path d="M5 19l8-8" /></>,
  plug: <><path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0z" /><path d="M12 17v4" /></>,
  pot: <><path d="M4 10h16v6a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z" /><path d="M2 10h2M20 10h2M9 6c0-1 1-2 3-2s3 1 3 2" /></>,
  pen: <><path d="m4 20 1-4L16 5l3 3L8 19z" /><path d="m14 7 3 3" /></>,
  ticket: <><path d="M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-2a2 2 0 0 0 0-4z" /><path d="M10 6v12" strokeDasharray="2 2" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  bolt: <path d="M13 2 4 14h7l-1 8 9-12h-7z" />,
  chev: <path d="m6 9 6 6 6-6" />,
  right: <path d="m9 6 6 6-6 6" />,
  left: <path d="m15 6-6 6 6 6" />,
  pct: <><circle cx="12" cy="12" r="9" /><path d="m9 15 6-6" /><circle cx="9.2" cy="9.2" r=".6" /><circle cx="14.8" cy="14.8" r=".6" /></>,
  reorder: <><path d="M4 12a8 8 0 1 0 2.4-5.7" /><path d="M4 4v4.5h4.5" /><path d="M12 8v4l3 2" /></>,
  cart: <><path d="M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 8H6" /><circle cx="10" cy="20" r="1.3" /><circle cx="17" cy="20" r="1.3" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  heart: <path d="M12 20s-7.5-4.6-9.2-9.3C1.6 7.2 4 4 7.2 4c2 0 3.6 1.2 4.8 2.8C13.2 5.2 14.8 4 16.8 4 20 4 22.4 7.2 21.2 10.7 19.5 15.4 12 20 12 20z" />,
  bell: <><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z" /><path d="M10 20a2 2 0 0 0 4 0" /></>,
  check: <path d="M5 12.5 9.5 17 19 7.5" />,
  truck: <><path d="M3 6h11v10H3zM14 9h4l3 3.5V16h-7" /><circle cx="7" cy="17.5" r="1.8" /><circle cx="17.5" cy="17.5" r="1.8" /></>,
  shirt: <path d="m8 4-5 3 2 4 3-1v10h8V10l3 1 2-4-5-3a4 4 0 0 1-8 0z" />,
  book: <><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M4 19V5M8 7h7" /></>,
  grid: <><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></>,
  chat: <><path d="M4 20l1.3-3.9A8 8 0 1 1 8 19z" /><path d="M9 10.5c.5 1.8 2 3.3 3.8 3.8l1.2-1.1 1.8.8" /></>,
  note: <><path d="M5 4h14v11l-5 5H5z" /><path d="M14 20v-5h5M8 9h8M8 12h5" /></>,
  phoneOff: <><path d="M5 4h3l2 5-2 1a11 11 0 0 0 6 6l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" /><path d="M3 3l18 18" /></>,
  bellOff: <><path d="M6 16v-5a6 6 0 0 1 9.5-4.9M18 11v5l2 2H8" /><path d="M10 20a2 2 0 0 0 4 0M3 3l18 18" /></>,
  paw: <><circle cx="7" cy="10" r="1.8" /><circle cx="11" cy="6.5" r="1.8" /><circle cx="15.5" cy="7" r="1.8" /><circle cx="18" cy="11" r="1.8" /><path d="M12 12c-3 0-5.5 3.2-5.5 5.3 0 1.6 1.3 2.2 2.6 2.2 1.1 0 1.8-.6 2.9-.6s1.8.6 2.9.6c1.3 0 2.6-.6 2.6-2.2C17.5 15.2 15 12 12 12z" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  trash: <><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></>,
  shield: <><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="m9 12 2 2 4-4" /></>,
  cash: <><rect x="3" y="6" width="18" height="12" rx="2" /><circle cx="12" cy="12" r="2.5" /><path d="M6 9v.01M18 15v.01" /></>,
  card: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 10h18M7 15h4" /></>,
  gift: <><rect x="4" y="9" width="16" height="11" rx="1.5" /><path d="M3 9h18M12 9v11M12 9c-2-4-6-4-6-1.5S10 9 12 9zm0 0c2-4 6-4 6-1.5S14 9 12 9z" /></>,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  home: <><path d="M4 11 12 4l8 7v9H4z" /><path d="M10 20v-5h4v5" /></>,
  brief: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V5h6v2M3 12h18" /></>,
  pin: <><path d="M12 22s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12z" /><circle cx="12" cy="10" r="2.6" /></>,
  gps: <><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2.5" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  heartFill: <path d="M12 20s-7.5-4.6-9.2-9.3C1.6 7.2 4 4 7.2 4c2 0 3.6 1.2 4.8 2.8C13.2 5.2 14.8 4 16.8 4 20 4 22.4 7.2 21.2 10.7 19.5 15.4 12 20 12 20z" />,
  box: <><path d="M21 8 12 3 3 8v8l9 5 9-5z" /><path d="M3 8l9 5 9-5M12 13v8" /></>,
  help: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.5" /><path d="m5.6 5.6 3.9 3.9M14.5 14.5l3.9 3.9M18.4 5.6l-3.9 3.9M9.5 14.5l-3.9 3.9" /></>,
  legal: <><path d="M7 3h10v18H7a3 3 0 0 1-3-3v-1h13" /><path d="M10 8h5M10 12h5" /></>,
  logout: <><path d="M10 4H5v16h5" /><path d="M14 8l4 4-4 4M18 12H9" /></>,
  edit: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="m13 7 4 4" /></>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2.5" /><path d="m3.5 6.5 8.5 6.5 8.5-6.5" /></>,
  phone: <path d="M5 4h3l2 5-2 1a11 11 0 0 0 6 6l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />,
  star: <path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z" />,
  share: <><circle cx="18" cy="5" r="2.5" /><circle cx="6" cy="12" r="2.5" /><circle cx="18" cy="19" r="2.5" /><path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4" /></>,
  trend: <><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></>,
  printer: <><path d="M7 9V4h10v5" /><rect x="3" y="9" width="18" height="8" rx="2" /><path d="M7 14h10v6H7z" /><path d="M17.5 12h.01" /></>,
  scissors: <><circle cx="6" cy="7" r="2.6" /><circle cx="6" cy="17" r="2.6" /><path d="M8.2 8.4 20 17M8.2 15.6 20 7" /></>,
  volume: <><path d="M4 9h4l5-4v14l-5-4H4z" /><path d="M16.5 9a4 4 0 0 1 0 6M19 6.5a7.5 7.5 0 0 1 0 11" /></>,
  mute: <><path d="M4 9h4l5-4v14l-5-4H4z" /><path d="m16 9 5 6M21 9l-5 6" /></>,
  lock: <><rect x="5" y="10.5" width="14" height="10" rx="2" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" /></>,
  upi: <><path d="M9 4 5 20" /><path d="m13 4-4 16" /><path d="m15 7 4 5-6 7" /></>,
  bank: <><path d="M3 9.5 12 4l9 5.5" /><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18" /></>,
  wallet: <><path d="M4 7a2 2 0 0 1 2-2h11v4" /><rect x="3" y="7" width="18" height="13" rx="2.5" /><path d="M16 13.5h3" /></>,
  sort: <><path d="M7 4v16M3.5 16.5 7 20l3.5-3.5" /><path d="M17 20V4M13.5 7.5 17 4l3.5 3.5" /></>,
  filter: <><path d="M4 6h16M7 12h10M10 18h4" /></>,
  scooter: <><circle cx="6" cy="17" r="2.5" /><circle cx="18" cy="17" r="2.5" /><path d="M8.5 17h6.5l2-6h-4l-2 4M15 5h3l1 6" /></>,
};
export const Icon = ({ n, size = 20, className = "" }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} className={"hm-ic " + className} aria-hidden="true">{P[n]}</svg>
);

/* ---------- hooks ---------- */
export function useInView(opts = { rootMargin: "0px 0px -8% 0px", threshold: 0.1 }) {
  const ref = useRef(null);
  const [inView, set] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || inView) return;
    if (typeof IntersectionObserver === "undefined") return set(true);
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { set(true); io.disconnect(); } }, opts);
    io.observe(el);
    const t = setTimeout(() => set(true), 3000); /* failsafe */
    return () => { io.disconnect(); clearTimeout(t); };
  }, [inView]); // eslint-disable-line
  return [ref, inView];
}

export function useRailScroll() {
  const ref = useRef(null);
  const [edge, setEdge] = useState({ start: true, end: false });
  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setEdge({ start: el.scrollLeft < 4, end: el.scrollLeft > max - 4 });
  }, []);
  useEffect(() => {
    update();
    const el = ref.current;
    el?.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => { el?.removeEventListener("scroll", update); window.removeEventListener("resize", update); };
  }, [update]);
  const by = (d) => ref.current?.scrollBy({ left: d * ref.current.clientWidth * 0.85, behavior: "smooth" });
  return { ref, edge, by };
}

/* small dot flight (buttons without a product image, e.g. Reorder all) */
export function flyTo(fromEl, targetSel, id) {
  if (typeof document === "undefined" || !fromEl) return;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  const target = (targetSel && targetSel !== "#hm-cart-icon" ? document.querySelector(targetSel) : null) || cartTarget(id);
  if (!target) return;
  const a = fromEl.getBoundingClientRect(), b = target.getBoundingClientRect();
  const x0 = a.left + a.width / 2, y0 = a.top + a.height / 2, x1 = b.left + b.width / 2, y1 = b.top + b.height / 2;
  const ox = document.createElement("div"), oy = document.createElement("div");
  ox.className = "hm-fly-x"; oy.className = "hm-fly-y"; ox.appendChild(oy); document.body.appendChild(ox);
  const dur = Math.min(850, Math.max(480, Math.hypot(x1 - x0, y1 - y0) * 0.8));
  ox.animate([{ transform: `translateX(${x0}px)` }, { transform: `translateX(${x1}px)` }], { duration: dur, easing: "cubic-bezier(.45,0,.55,1)", fill: "forwards" });
  const peak = Math.min(y0, y1) - 80;
  oy.animate([
    { transform: `translateY(${y0}px) scale(1)` },
    { transform: `translateY(${peak}px) scale(1.1)`, offset: 0.35, easing: "cubic-bezier(.55,0,1,.45)" },
    { transform: `translateY(${y1}px) scale(.5)` },
  ], { duration: dur, easing: "cubic-bezier(0,.55,.45,1)", fill: "forwards" }).onfinish = () => {
    ox.remove();
    landed(target);
  };
}

/* ---------- product card ---------- */
/* ---------- add-to-cart flight ----------
   The product image lifts out of its card (the card turns mint and empty),
   arcs up and down into the floating cart pill while shrinking and spinning,
   the pill gulps and the item's thumbnail pops in; the card image grows back.
   The target is re-measured every frame, so it still lands on the pill while
   the pill is springing in for the first item. */
const flying = new Map();
const flySubs = new Set();
const flyEmit = () => flySubs.forEach((f) => f());
const flySub = (f) => { flySubs.add(f); return () => flySubs.delete(f); };
export const useFlying = (id) => useSyncExternalStore(flySub, () => (flying.get(id) || 0) > 0, () => false);

const visible = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden"; };
function cartTarget(id) {
  const panel = document.querySelector(".mc-panel");
  if (visible(panel)) return panel.querySelector(`[data-row="${id}"] .mc-row-img`) || panel.querySelector(".mc-head-ic");
  const pill = document.querySelector(".mc-pill.mc-show");
  if (pill) return pill.querySelector(`[data-thumb="${id}"]`) || pill.querySelector(".mc-thumbs") || pill;
  return document.querySelector("#hm-cart-icon");
}
const SOURCE_BOX = ".hm-card-img, .sr-row-img, .sr-pick-img, .pd-stage, .ac-wish-img, .ct-thumb, .pd-fbt-img";

export function flyToCart(fromEl, { id } = {}) {
  if (typeof document === "undefined" || !fromEl) return;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  const box = fromEl.closest?.(SOURCE_BOX) || (fromEl.matches?.(SOURCE_BOX) ? fromEl : null);
  const src = box && [".hm-gal-slide.hm-cur img", ".pd-slide.pd-cur img", ".pd-slide.pd-cur svg.hm-art", "img", "svg.hm-art"].reduce((f, sel) => f || box.querySelector(sel), null);
  if (!src) return flyTo(fromEl, null, id);

  const a = src.getBoundingClientRect();
  if (!a.width) return flyTo(fromEl, null, id);
  const ghost = document.createElement("div");
  ghost.className = "hm-fly-img";
  ghost.style.width = a.width + "px"; ghost.style.height = a.height + "px";
  const clone = src.tagName === "IMG" ? Object.assign(document.createElement("img"), { src: src.currentSrc || src.src, alt: "" }) : src.cloneNode(true);
  ghost.appendChild(clone);
  document.body.appendChild(ghost);

  if (id) { flying.set(id, (flying.get(id) || 0) + 1); flyEmit(); }
  box.classList.remove("hm-regrow"); box.classList.add("hm-lift");
  box.closest(".hm-card")?.classList.add("hm-card-adding");

  const x0 = a.left + a.width / 2, y0 = a.top + a.height / 2;
  const first = cartTarget(id)?.getBoundingClientRect();
  const dist = first ? Math.hypot(first.left - x0, first.top - y0) : 600;
  const D = Math.min(1050, Math.max(700, dist * 0.95));
  const LIFT = 0.2;
  const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const t0 = performance.now();
  let regrown = false;

  const frame = (now) => {
    const k = Math.min(1, (now - t0) / D);
    const tgt = cartTarget(id);
    const b = tgt?.getBoundingClientRect() || { left: innerWidth - 40, top: innerHeight - 40, width: 30, height: 30 };
    const x1 = b.left + b.width / 2, y1 = b.top + b.height / 2;
    const endScale = Math.max(0.12, Math.min(b.width, b.height, 40) / Math.max(a.width, a.height));
    let x, y, sc, rot, op = 1;
    if (k < LIFT) {
      const u = easeInOut(k / LIFT);
      x = x0; y = y0 - 16 * u; sc = 1 + 0.12 * u; rot = -7 * u;
    } else {
      const u = easeInOut((k - LIFT) / (1 - LIFT));
      const sx = x0, sy = y0 - 16;
      const cx = sx + (x1 - sx) * 0.55, cy = Math.min(sy, y1) - Math.max(90, Math.abs(x1 - sx) * 0.18);
      x = (1 - u) * (1 - u) * sx + 2 * (1 - u) * u * cx + u * u * x1;
      y = (1 - u) * (1 - u) * sy + 2 * (1 - u) * u * cy + u * u * y1;
      sc = 1.12 + (endScale - 1.12) * Math.pow(u, 1.4);
      rot = -7 + 367 * u;
      op = u > 0.88 ? 1 - (u - 0.88) / 0.12 : 1;
    }
    ghost.style.transform = `translate(${x - a.width / 2}px, ${y - a.height / 2}px) rotate(${rot}deg) scale(${sc})`;
    ghost.style.opacity = op;
    if (!regrown && k > 0.72) {
      regrown = true;
      box.classList.remove("hm-lift"); box.classList.add("hm-regrow");
      setTimeout(() => box.classList.remove("hm-regrow"), 650);
      setTimeout(() => box.closest(".hm-card")?.classList.remove("hm-card-adding"), 900);
    }
    if (k < 1) return requestAnimationFrame(frame);
    ghost.remove();
    if (id) { flying.set(id, Math.max(0, (flying.get(id) || 1) - 1)); flyEmit(); }
    landed(tgt);
  };
  requestAnimationFrame(frame);
}

function landed(tgt) {
  const pill = tgt?.closest?.(".mc-pill");
  (pill || tgt)?.animate?.(
    pill
      ? [{ transform: "scale(1,1)" }, { transform: "scale(1.07,.9)" }, { transform: "scale(.97,1.04)" }, { transform: "scale(1,1)" }]
      : [{ transform: "scale(1)" }, { transform: "scale(1.18)" }, { transform: "scale(1)" }],
    { duration: 460, easing: "cubic-bezier(.34,1.56,.64,1)" }
  );
  if (pill) {
    const ring = document.createElement("i");
    ring.className = "mc-ripple";
    pill.appendChild(ring);
    setTimeout(() => ring.remove(), 700);
  }
}

export function QtyControl({ qty, onChange, name, id }) {
  const btn = useRef(null);
  const [added, setAdded] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => clearTimeout(timer.current), []);
  if (qty <= 0) {
    return (
      <button ref={btn} className="hm-add" onClick={() => {
        flyToCart(btn.current, { id });
        onChange(1);
        setAdded(true); clearTimeout(timer.current); timer.current = setTimeout(() => setAdded(false), 1100);
      }} aria-label={`Add ${name}`}><Icon n="plus" size={13} />Add</button>
    );
  }
  if (added) {
    return (
      <button className="hm-added" onClick={() => setAdded(false)} aria-label={`${name} added. Change quantity`}>
        <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path d="M5 12.5 9.5 17 19 7.5" /></svg>Added
      </button>
    );
  }
  return (
    <div className="hm-stepper" role="group" aria-label={`${name} quantity`}>
      <button onClick={() => onChange(qty - 1)} aria-label="Remove one">−</button>
      <span key={qty} className="hm-stepper-n" aria-live="polite">{qty}</span>
      <button onClick={() => onChange(Math.min(qty + 1, 12))} aria-label="Add one">+</button>
    </div>
  );
}

/* first photo of an item, or its drawn placeholder */
export const firstImage = (p) => (p.images && p.images[0]) || p.image || null;
export function Thumb({ p }) {
  const src = firstImage(p);
  return src ? <img src={src} alt="" loading="lazy" /> : <ProductArt art={p.art} color={p.color} label={p.label} />;
}

/* multi-image view: swipe / arrows / dots. Single image → plain image, no controls. */
export function Gallery({ p }) {
  const imgs = p.images?.length ? p.images : p.image ? [p.image] : [];
  const track = useRef(null);
  const [idx, setIdx] = useState(0);
  const raf = useRef(0);
  const count = imgs.length;
  const onScroll = () => {
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => {
      const el = track.current;
      if (el) setIdx(Math.round(el.scrollLeft / Math.max(1, el.clientWidth)));
    });
  };
  const go = (n, e) => {
    e?.stopPropagation();
    const el = track.current;
    if (!el) return;
    const next = Math.max(0, Math.min(count - 1, n));
    el.scrollTo({ left: next * el.clientWidth, behavior: "smooth" });
    setIdx(next);
  };
  if (count === 0) return <div className="hm-gal-one"><ProductArt art={p.art} color={p.color} label={p.label} /></div>;
  if (count === 1) return <div className="hm-gal-one"><img src={imgs[0]} alt={p.name} loading="lazy" /></div>;
  return (
    <div className="hm-gal" data-count={count}
      onKeyDown={(e) => { if (e.key === "ArrowRight") go(idx + 1, e); if (e.key === "ArrowLeft") go(idx - 1, e); }}>
      <div className="hm-gal-track" ref={track} onScroll={onScroll} tabIndex={0} aria-roledescription="carousel" aria-label={`${p.name} images`}>
        {imgs.map((src, k) => (
          <div className={"hm-gal-slide" + (k === idx ? " hm-cur" : "")} key={src + k} aria-roledescription="slide" aria-label={`${k + 1} of ${count}`}>
            <img src={src} alt={k === 0 ? p.name : ""} loading={k === 0 ? "eager" : "lazy"} draggable="false" />
          </div>
        ))}
      </div>
      <button className="hm-gal-btn hm-gal-prev" onClick={(e) => go(idx - 1, e)} disabled={idx === 0} aria-label="Previous image"><Icon n="left" size={14} /></button>
      <button className="hm-gal-btn hm-gal-next" onClick={(e) => go(idx + 1, e)} disabled={idx === count - 1} aria-label="Next image"><Icon n="right" size={14} /></button>
      <div className="hm-gal-dots" role="tablist" aria-label="Choose image">
        {imgs.map((_, k) => (
          <button key={k} role="tab" aria-selected={k === idx} aria-label={`Image ${k + 1}`} className={k === idx ? "hm-on" : ""} onClick={(e) => go(k, e)} />
        ))}
      </div>
    </div>
  );
}

export function ProductCard({ p, qty, setQty, i }) {
  const wish = useContext(WishContext);
  const [localLiked, setLocalLiked] = useState(false);
  const liked = wish ? wish.has(p.id) : localLiked;
  const setLiked = () => (wish ? wish.toggle(p.id) : setLocalLiked((v) => !v));
  const [notified, setNotified] = useState(false);
  const open = useContext(OpenContext);
  const oos = p.stock === 0;
  const off = p.mrp ? Math.round(((p.mrp - p.price) / p.mrp) * 100) : 0;
  return (
    <article className={"hm-card" + (oos ? " hm-oos" : "")} style={{ "--i": i }} data-open={open ? "" : undefined}
      onClick={(e) => {
        if (!open || e.target.closest("button, a, input, .hm-card-cta")) return;
        open(p, e.currentTarget.querySelector(".hm-card-img")?.getBoundingClientRect());
      }}>
      <div className="hm-card-img">
        <Gallery p={p} />
        <button className={"hm-heart" + (liked ? " hm-liked" : "")} aria-pressed={liked} aria-label={liked ? "Remove from wishlist" : "Save to wishlist"} onClick={setLiked}>
          <Icon n="heart" size={18} />
        </button>
        <div className="hm-card-cta">
          {oos ? (
            <button className={"hm-notify" + (notified ? " hm-done" : "")} onClick={() => setNotified(true)}>
              <Icon n={notified ? "check" : "bell"} size={13} />{notified ? "We'll notify" : "Notify"}
            </button>
          ) : <QtyControl qty={qty} id={p.id} name={p.name} onChange={(n) => setQty(p.id, n)} />}
        </div>
        {off >= 10 && !oos && !p.tag && <span className="hm-off">{off}% OFF</span>}
        {p.tag && <span className="hm-off hm-new">{p.tag}</span>}
        {p.veg && <span className="hm-veg" title="Vegetarian" aria-label="Vegetarian"><i /></span>}
        {oos && <span className="hm-oos-tag">Out of stock</span>}
      </div>
      <div className="hm-card-body">
        <div className="hm-unit">{p.unit}</div>
        <h3 className="hm-name" title={p.name}>{open ? <a href={`/product/${p.id}`} onClick={(e) => { e.preventDefault(); open(p, e.currentTarget.closest(".hm-card")?.querySelector(".hm-card-img")?.getBoundingClientRect()); }}>{p.name}</a> : p.name}</h3>
        {p.note && <div className="hm-subnote">({p.note})</div>}
        <div className="hm-price">
          <b>{inr(p.price)}</b>
          {p.mrp ? <s>{inr(p.mrp)}</s> : null}
          {p.perUnit && <small>({p.perUnit})</small>}
        </div>
        <div className="hm-meta">
          {p.delivery
            ? <span className="hm-quick hm-ship"><Icon n="truck" size={12} />{p.delivery}</span>
            : <span className="hm-quick"><Icon n="bolt" size={11} className="hm-fill" />Quick</span>}
          {p.low ? <span className="hm-low">Only {p.low} left</span> : null}
        </div>
      </div>
    </article>
  );
}

export function Rail({ section, cart, setQty, tone, onViewAll }) {
  const [ioRef, inView] = useInView();
  const { ref, edge, by } = useRailScroll();
  return (
    <section className={"hm-rail" + (inView ? " hm-in" : "") + (tone ? " hm-rail-" + tone : "")} ref={ioRef} aria-labelledby={"rail-" + section.key}>
      <div className="hm-rail-head">
        <div>
          <h2 id={"rail-" + section.key}>{section.title}</h2>
          {section.subtitle && <p>{section.subtitle}</p>}
        </div>
        {onViewAll && <a href="#" onClick={(e) => { e.preventDefault(); onViewAll?.(section); }} className="hm-viewall">View all<Icon n="right" size={15} /></a>}
      </div>
      <div className="hm-rail-box">
        <div className="hm-rail-track" ref={ref}>
          {section.items.map((p, i) => <ProductCard key={p.id} p={p} i={i} qty={cart[p.id] || 0} setQty={setQty} />)}
        </div>
        {!edge.start && <button className="hm-arrow hm-arrow-l" onClick={() => by(-1)} aria-label="Scroll left"><Icon n="left" size={18} /></button>}
        {!edge.end && <button className="hm-arrow hm-arrow-r" onClick={() => by(1)} aria-label="Scroll right"><Icon n="right" size={18} /></button>}
      </div>
    </section>
  );
}
