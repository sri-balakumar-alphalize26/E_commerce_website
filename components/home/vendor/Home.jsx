"use client";
/* ==========================================================================
   369 Mart — Home (quick-commerce layout)
   White sticky header · category tabs · promo carousel · category strip ·
   product rails · free-delivery nudge · sticky cart bar.

   Next.js: app/page.jsx
     import Home from "@/components/home/Home";
     import "@/components/home/home.css";
     export default function Page() { return <Home />; }

   Pass real data through props (same shape as sampleData.js). Items with an
   `image` URL show the photo; items without one get a drawn placeholder.
   ========================================================================== */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flyToCart } from "@/lib/fly-to-cart";
import ProductArt from "./art";

const inr = (n) => "₹" + Number(n).toLocaleString("en-IN");

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
  scooter: <><circle cx="6" cy="17" r="2.5" /><circle cx="18" cy="17" r="2.5" /><path d="M8.5 17h6.5l2-6h-4l-2 4M15 5h3l1 6" /></>,
};
const Icon = ({ n, size = 20, className = "" }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} className={"hm-ic " + className} aria-hidden="true">{P[n]}</svg>
);

/* ---------- hooks ---------- */
function useInView(opts = { rootMargin: "0px 0px -8% 0px", threshold: 0.1 }) {
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

function useRailScroll() {
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


/* ---------- banners ---------- */
function Banner({ b, i }) {
  return (
    <a className={"hm-banner hm-tone-" + b.tone} href="#" onClick={(e) => e.preventDefault()} style={{ "--i": i }}>
      <div className="hm-banner-copy">
        <span className="hm-kicker">{b.kicker}</span>
        <strong>{b.title}</strong>
        <span className="hm-note">{b.note}</span>
        <span className="hm-shop">Shop now <Icon n="right" size={14} /></span>
      </div>
      <div className="hm-banner-art" aria-hidden="true">
        {b.art.map((a, k) => <span key={k} style={{ "--k": k }}><ProductArt art={a} /></span>)}
      </div>
    </a>
  );
}

function BannerCarousel({ banners, autoplay = true }) {
  const { ref, edge, by } = useRailScroll();
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (!autoplay || paused) return;
    const t = setInterval(() => {
      const el = ref.current;
      if (!el) return;
      if (el.scrollLeft >= el.scrollWidth - el.clientWidth - 4) el.scrollTo({ left: 0, behavior: "smooth" });
      else by(1);
    }, 5000);
    return () => clearInterval(t);
  }, [autoplay, paused]); // eslint-disable-line
  return (
    <section className="hm-banners" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} aria-label="Offers">
      <div className="hm-banner-track" ref={ref}>
        {banners.map((b, i) => <Banner key={b.id} b={b} i={i} />)}
      </div>
      {!edge.start && <button className="hm-arrow hm-arrow-l" onClick={() => by(-1)} aria-label="Previous offers"><Icon n="left" size={18} /></button>}
      {!edge.end && <button className="hm-arrow hm-arrow-r" onClick={() => by(1)} aria-label="More offers"><Icon n="right" size={18} /></button>}
    </section>
  );
}

function CategoryStrip({ cats }) {
  const [ref, inView] = useInView();
  return (
    <section className={"hm-cats" + (inView ? " hm-in" : "")} ref={ref} aria-label="Shop by category">
      {cats.map((c, i) => (
        <a key={c.key} href="#" onClick={(e) => e.preventDefault()} className="hm-cat" style={{ "--i": i }}>
          <span className="hm-cat-img" style={{ background: c.bg }}><ProductArt art={c.art} color={c.color} label={c.t} /></span>
          <span>{c.label}</span>
        </a>
      ))}
    </section>
  );
}

/* ---------- product card ---------- */
function QtyControl({ qty, onChange, name }) {
  const btn = useRef(null);
  if (qty <= 0) {
    return (
      <button ref={btn} className="hm-add" onClick={() => { flyToCart(btn.current); onChange(1); }}
        aria-label={`Add ${name}`}>Add</button>
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

/**
 * The card's image area: every pack-shot a product has, on a scroll-snap
 * track with arrows.
 *
 * Adopting this design replaced a card that already paged through a
 * product's images, so this restores that. It is a NATIVE scroller rather
 * than a slider: snap points plus an index read back off scrollLeft, so
 * swipe, momentum and rubber-banding come from the browser and there is no
 * transform to animate. That matters more here than on a banner, because
 * this component is mounted twenty times on a grid.
 *
 * Arrows are pointer-only and out of the tab order. A thirty-card grid
 * would otherwise grow sixty keyboard stops that all lead somewhere the
 * product page already reaches, and they wrap rather than disabling at the
 * ends so the control never vanishes from under the cursor that just
 * clicked it.
 *
 * Images after the first mount only once the card is touched, hovered or
 * focused. Four pack-shots across twenty cards is eighty requests behind
 * the fold for pictures most customers never ask to see.
 */
function CardGallery({ p }) {
  const imgs = Array.isArray(p.images) && p.images.length ? p.images : p.image ? [p.image] : [];
  const many = imgs.length > 1;
  const track = useRef(null);
  const [idx, setIdx] = useState(0);
  const [woke, setWoke] = useState(false);

  if (!imgs.length) return <ProductArt art={p.art} color={p.color} label={p.label} />;

  const go = (d) => {
    const el = track.current;
    if (!el) return;
    setWoke(true);
    el.scrollTo({ left: ((idx + d + imgs.length) % imgs.length) * el.clientWidth, behavior: "smooth" });
  };

  return (
    <div
      className="hm-gal"
      onPointerEnter={() => setWoke(true)}
      onTouchStart={() => setWoke(true)}
      onFocusCapture={() => setWoke(true)}
    >
      <div
        ref={track}
        className={"hm-gal-track" + (many ? " hm-gal-snap" : "")}
        onScroll={many ? (e) => { setWoke(true); setIdx(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth)); } : undefined}
      >
        {imgs.map((src, k) => (
          <div className="hm-gal-slide" key={src} aria-hidden={k === 0 ? undefined : true}>
            {k === 0 || woke ? <img src={src} alt="" loading={k === 0 ? undefined : "lazy"} /> : <span className="hm-gal-hold" />}
          </div>
        ))}
      </div>

      {many && (
        <>
          <button type="button" className="hm-gal-arw hm-gal-prev" tabIndex={-1} aria-hidden="true" onClick={() => go(-1)}>
            <svg viewBox="0 0 24 24" width="15" height="15" className="hm-ic" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
          </button>
          <button type="button" className="hm-gal-arw hm-gal-next" tabIndex={-1} aria-hidden="true" onClick={() => go(1)}>
            <svg viewBox="0 0 24 24" width="15" height="15" className="hm-ic" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
          </button>
          <span className="hm-gal-dots" aria-hidden="true">
            {imgs.map((src, k) => <i key={src} data-on={k === idx ? "" : undefined} />)}
          </span>
        </>
      )}
    </div>
  );
}

function ProductCard({ p, qty, setQty, i }) {
  const [liked, setLiked] = useState(false);
  const [notified, setNotified] = useState(false);
  const oos = p.stock === 0;
  const off = p.mrp ? Math.round(((p.mrp - p.price) / p.mrp) * 100) : 0;
  return (
    <article className={"hm-card" + (oos ? " hm-oos" : "")} style={{ "--i": i }}>
      <div className="hm-card-img">
        <CardGallery p={p} />
        <button className={"hm-heart" + (liked ? " hm-liked" : "")} aria-pressed={liked} aria-label={liked ? "Remove from wishlist" : "Save to wishlist"} onClick={() => setLiked((v) => !v)}>
          <Icon n="heart" size={18} />
        </button>
        <div className="hm-card-cta">
          {oos ? (
            <button className={"hm-notify" + (notified ? " hm-done" : "")} onClick={() => setNotified(true)}>
              <Icon n={notified ? "check" : "bell"} size={13} />{notified ? "We'll notify" : "Notify"}
            </button>
          ) : <QtyControl qty={qty} name={p.name} onChange={(n) => setQty(p.id, n)} />}
        </div>
        {off >= 10 && !oos && <span className="hm-off">{off}% OFF</span>}
        {p.tag && <span className="hm-off hm-new">{p.tag}</span>}
        {p.veg && <span className="hm-veg" title="Vegetarian" aria-label="Vegetarian"><i /></span>}
        {oos && <span className="hm-oos-tag">Out of stock</span>}
      </div>
      <div className="hm-card-body">
        <div className="hm-unit">{p.unit}</div>
        <h3 className="hm-name" title={p.name}>{p.name}</h3>
        {p.note && <div className="hm-subnote">({p.note})</div>}
        <div className="hm-price">
          <b>{inr(p.price)}</b>
          {p.mrp ? <s>{inr(p.mrp)}</s> : null}
          {p.perUnit && <small>({p.perUnit})</small>}
        </div>
        <div className="hm-meta">
          {/* Conditional: this rendered for every product, asserting that
              the whole catalogue was stocked for fast delivery when only
              part of it is. */}
          {p.quick ? <span className="hm-quick"><Icon n="bolt" size={11} className="hm-fill" />Quick</span> : null}
          {p.low ? <span className="hm-low">Only {p.low} left</span> : null}
        </div>
      </div>
    </article>
  );
}

function Rail({ section, cart, setQty }) {
  const [ioRef, inView] = useInView();
  const { ref, edge, by } = useRailScroll();
  return (
    <section className={"hm-rail" + (inView ? " hm-in" : "")} ref={ioRef} aria-labelledby={"rail-" + section.key}>
      <div className="hm-rail-head">
        <div>
          <h2 id={"rail-" + section.key}>{section.title}</h2>
          {section.subtitle && <p>{section.subtitle}</p>}
        </div>
        <a href="#" onClick={(e) => e.preventDefault()} className="hm-viewall">View all<Icon n="right" size={15} /></a>
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



/* ---------- page ---------- */
/**
 * Controlled, deliberately.
 *
 * Upstream held the cart in useState and reported it outward. Two problems
 * here: the app clamps every quantity through clampQty (pack rules and the
 * stock ceiling), so uncontrolled local state would disagree with the real
 * cart the moment a clamp fired; and an id->qty map discards the name,
 * price, image and pack rules a CartLine carries. So the store stays
 * authoritative and this renders what it is given.
 */
export default function Home({
  banners = [],
  categories = [],
  sections = [],
  cart = {},
  onQtyChange,
}) {
  const order = useRef([]);

  const setQty = useCallback(
    (id, n) => {
      if (n > 0 && !order.current.includes(id)) order.current = [...order.current, id];
      if (n <= 0) order.current = order.current.filter((x) => x !== id);
      onQtyChange?.(id, n);
    },
    [onQtyChange],
  );

  const count = Object.values(cart).reduce((n, q) => n + q, 0);
  const bannerById = Object.fromEntries(banners.map((b) => [b.id, b]));

  return (
    <div className={"hm-page" + (count > 0 ? " hm-has-cart" : "")}>
      <main className="hm-wrap hm-main">
        <BannerCarousel banners={banners} />
        <CategoryStrip cats={categories} />
        {sections.map((s, i) =>
          s.banner ? (
            <div className="hm-inline-banners" key={"bn" + i}>
              {s.banner.map((id, k) => bannerById[id] && <Banner key={id} b={bannerById[id]} i={k} />)}
            </div>
          ) : (
            <Rail key={s.key} section={s} cart={cart} setQty={setQty} />
          )
        )}
      </main>
    </div>
  );
}
