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
import ProductArt from "./art";
import { Icon, ProductCard, Rail, SEARCH_WORDS, Thumb, WishContext, flyTo, inr, useInView, useRailScroll } from "./shared";
import AccountPage from "./Account";
import SearchOverlay from "./SearchOverlay";
import LocationPicker, { SAMPLE_ADDRESSES } from "./LocationPicker";
import CartPage from "./Cart";
import { ALL_BANNERS, ALL_CATEGORIES, ALL_SECTIONS, ALL_TABS, BANNERS, CATEGORIES, SECTIONS, TABS } from "./sampleData";

/* ---------- header ---------- */
function ModeToggle({ mode, onMode }) {
  const wrap = useRef(null);
  const [thumb, setThumb] = useState(null);
  useEffect(() => {
    const place = () => {
      const el = wrap.current?.querySelector(`[data-m="${mode}"]`);
      if (el) setThumb({ x: el.offsetLeft, w: el.offsetWidth });
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [mode]);
  return (
    <div className="hm-mode" role="tablist" aria-label="Shopping mode" data-mode={mode} ref={wrap}>
      {thumb && <span className="hm-mode-thumb" style={{ transform: `translateX(${thumb.x}px)`, width: thumb.w }} aria-hidden="true" />}
      <button role="tab" data-m="quick" aria-selected={mode === "quick"} onClick={(e) => onMode("quick", e.currentTarget)}>
        <Icon n="bolt" size={13} className="hm-fill" /><i>Quick</i>
      </button>
      <button role="tab" data-m="all" aria-selected={mode === "all"} onClick={(e) => onMode("all", e.currentTarget)}>
        <Icon n="grid" size={13} />Express
      </button>
    </div>
  );
}

function StoreHeader({ count, mode, onMode, onCart, onAccount, address, onLoc, locOpen, onSearch }) {
  const [scrolled, setScrolled] = useState(false);
  const [w, setW] = useState(0);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 4);
    on(); window.addEventListener("scroll", on, { passive: true });
    const t = setInterval(() => setW((i) => i + 1), 2600);
    return () => { window.removeEventListener("scroll", on); clearInterval(t); };
  }, []);
  const cur = w % SEARCH_WORDS.length, prev = (cur - 1 + SEARCH_WORDS.length) % SEARCH_WORDS.length;
  return (
    <header className={"hm-hdr" + (scrolled ? " hm-scrolled" : "")}>
      <div className="hm-wrap hm-hdr-row">
        <a className="hm-logo" href="/" aria-label="369 Mart home">
          <span className="hm-logo-mark">369</span>
          <svg viewBox="0 0 24 24" className="hm-logo-arrow" aria-hidden="true"><path d="M6 18 18 6M9 6h9v9" /></svg>
          <span>Mart</span>
        </a>
        <ModeToggle mode={mode} onMode={onMode} />
        <button className={"hm-loc" + (locOpen ? " hm-loc-open" : "")} onClick={onLoc} aria-haspopup="dialog" aria-expanded={!!locOpen}>
          <span className="hm-loc-ic" key={mode + (address?.id || "")}><Icon n={mode === "quick" ? "bolt" : "truck"} size={18} className={mode === "quick" ? "hm-fill" : ""} /></span>
          <span className="hm-loc-txt" key={address?.id || "none"}>
            <b>{address ? (mode === "quick" ? address.label : `Deliver to ${address.label}`) : (mode === "quick" ? "Delivery in minutes" : "Deliver to")} <Icon n="chev" size={14} className="hm-loc-chev" /></b>
            <small>{address ? `${address.line}${address.city ? ", " + address.city : ""}` : "Set your delivery location"}</small>
          </span>
        </button>
        <button className="hm-search" onClick={onSearch} aria-label="Search products">
          <Icon n="search" size={18} />
          <span className="hm-search-ph">Search for '
            <span className="hm-roll">
              {SEARCH_WORDS.map((word, i) => (
                <span key={word} data-s={i === cur ? "in" : i === prev ? "out" : ""}>{word}'</span>
              ))}
            </span>
          </span>
        </button>
        <nav className="hm-icons" aria-label="Account">
          <button className="hm-iconbtn hm-hide-sm" aria-label="Offers"><Icon n="pct" /></button>
          <button className="hm-iconbtn hm-hide-sm" aria-label="Reorder"><Icon n="reorder" /></button>
          <button className="hm-iconbtn" id="hm-cart-icon" onClick={onCart} aria-label={`Cart, ${count} items`}>
            <Icon n="cart" />
            {count > 0 && <span key={count} className="hm-badge">{count}</span>}
          </button>
          <button className="hm-avatar" aria-label="Account" onClick={onAccount}><Icon n="user" size={18} /></button>
        </nav>
      </div>
    </header>
  );
}

function Tabs({ tabs, active, onChange }) {
  const wrap = useRef(null);
  const [ind, setInd] = useState(null);
  useEffect(() => {
    const place = () => {
      const el = wrap.current?.querySelector(`[data-k="${active}"]`);
      if (el) setInd({ x: el.offsetLeft, w: el.offsetWidth });
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [active]);
  return (
    <div className="hm-tabs-bar">
      <div className="hm-wrap">
        <div className="hm-tabs" ref={wrap} role="tablist">
          {ind && <span className="hm-tab-ind" style={{ transform: `translateX(${ind.x}px)`, width: ind.w }} aria-hidden="true" />}
          {tabs.map((t, i) => (
            <button key={t.key} data-k={t.key} role="tab" aria-selected={active === t.key} style={{ "--i": i }}
              onClick={() => onChange(t.key)}>
              <Icon n={t.icon} size={17} />{t.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
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
          <span className="hm-cat-img" style={{ background: c.bg }}>{c.image ? <img src={c.image} alt="" loading="lazy" /> : <ProductArt art={c.art} color={c.color} label={c.t} />}</span>
          <span>{c.label}</span>
        </a>
      ))}
    </section>
  );
}

/* ---------- cart nudges ---------- */
function FreeDelivery({ total, threshold }) {
  const left = Math.max(0, threshold - total);
  const pct = Math.min(100, (total / threshold) * 100);
  const done = left === 0;
  return (
    <div className={"hm-free" + (total > 0 ? " hm-show" : "") + (done ? " hm-free-done" : "")} aria-live="polite">
      <span className="hm-free-ic"><Icon n={done ? "check" : "scooter"} size={18} /></span>
      <span className="hm-free-txt">
        <span>{done ? <><b>Free delivery unlocked</b> on this order</> : <>Shop for <b>{inr(left)}</b> more to unlock <b>free delivery</b></>}</span>
        <span className="hm-free-bar"><i style={{ width: pct + "%" }} /></span>
      </span>
    </div>
  );
}

function CartBar({ lines, count, total, onView }) {
  const thumbs = lines.slice(-3).reverse();
  return (
    <div className={"hm-cartbar" + (count > 0 ? " hm-show" : "")} aria-hidden={count === 0}>
      <div className="hm-wrap hm-cartbar-row">
        <div className="hm-cartbar-left">
          <span className="hm-thumbs" id="hm-cartbar-thumbs">
            {thumbs.map((l) => (
              <span key={l.p.id} className="hm-thumb"><Thumb p={l.p} /></span>
            ))}
          </span>
          <span className="hm-cartbar-txt">
            <b key={count} className="hm-count-pop">{count} {count === 1 ? "item" : "items"}</b>
            <small>{inr(total)}</small>
          </span>
        </div>
        <button className="hm-viewcart" onClick={onView} tabIndex={count ? 0 : -1}>View Cart <Icon n="right" size={16} /></button>
      </div>
    </div>
  );
}

/* ---------- Quick <-> Shop all transition ---------- */
const MODE_COPY = {
  quick: { icon: "bolt", title: "Quick", sub: "Groceries & essentials in minutes" },
  all: { icon: "grid", title: "Express", sub: "Electronics, home & more · 2–5 day delivery" },
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* in: colour floods out of the toggle · hold: swap content underneath · out: curtain lifts */
function useModeSwitch() {
  const [fx, setFx] = useState(null);
  const busy = useRef(false);
  const run = useCallback(async (to, originEl, swap) => {
    if (busy.current) return;
    const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || !originEl) { await swap(); window.scrollTo(0, 0); return; }
    busy.current = true;
    const r = originEl.getBoundingClientRect();
    setFx({ to, x: r.left + r.width / 2, y: r.top + r.height / 2, phase: "in" });
    await sleep(520);
    setFx((f) => ({ ...f, phase: "hold" }));
    window.scrollTo(0, 0);
    await Promise.all([Promise.resolve(swap()), sleep(380)]);
    setFx((f) => ({ ...f, phase: "out" }));
    await sleep(560);
    setFx(null);
    busy.current = false;
  }, []);
  return [fx, run];
}

function ModeSwitchOverlay({ fx }) {
  if (!fx) return null;
  const c = MODE_COPY[fx.to];
  return (
    <div className={"hm-switch hm-switch-" + fx.phase} data-to={fx.to}
      style={{ "--x": fx.x + "px", "--y": fx.y + "px" }} role="status" aria-live="polite">
      <div className="hm-switch-card">
        <span className="hm-switch-ic"><Icon n={c.icon} size={34} className={fx.to === "quick" ? "hm-fill" : ""} /></span>
        <strong>{c.title}</strong>
        <span>{c.sub}</span>
        <i className="hm-switch-bar" />
      </div>
    </div>
  );
}

/* ---------- page ---------- */
const DEFAULT_MODES = {
  quick: { tabs: TABS, banners: BANNERS, categories: CATEGORIES, sections: SECTIONS, freeDeliveryAt: 499 },
  all: { tabs: ALL_TABS, banners: ALL_BANNERS, categories: ALL_CATEGORIES, sections: ALL_SECTIONS, freeDeliveryAt: 999 },
};

export default function Home({
  modes = DEFAULT_MODES,
  initialMode = "quick",
  onModeChange,
  initialCart = {},
  onCartChange,
  onViewCart,
  onCheckout,
  onSearch,
  initialView = "home",
  onAccount,
  onSignOut,
  syncUrl = false,      /* true in the Next app: header/cart switches update /cart in the address bar */
  persistCart = false,  /* true in the Next app: cart survives reloads and the /cart route */
}) {
  const [mode, setMode] = useState(initialMode);
  const [view, setView] = useState(initialView);
  const [searchOpen, setSearchOpen] = useState(false);
  const [locOpen, setLocOpen] = useState(false);
  const [address, setAddress] = useState(null);
  const [addresses, setAddresses] = useState(SAMPLE_ADDRESSES);
  const [wishIds, setWishIds] = useState([]);
  useEffect(() => {
    try { const w = JSON.parse(localStorage.getItem("369mart.list") || "null"); if (Array.isArray(w)) setWishIds(w); } catch (e) {}
  }, []);
  const wish = useMemo(() => ({
    ids: wishIds,
    has: (id) => wishIds.includes(id),
    toggle: (id) => setWishIds((w) => {
      const next = w.includes(id) ? w.filter((x) => x !== id) : [id, ...w];
      try { localStorage.setItem("369mart.list", JSON.stringify(next)); } catch (e) {}
      return next;
    }),
  }), [wishIds]);
  const { tabs, banners, categories, sections, freeDeliveryAt } = modes[mode];
  const [tab, setTab] = useState(tabs[0]?.key);
  const [cart, setCart] = useState(initialCart);
  const [fx, runSwitch] = useModeSwitch();
  const byId = useMemo(() => {
    const m = {};
    Object.values(modes).forEach((md) => md.sections.forEach((s) => s.items?.forEach((p) => { m[p.id] = p; })));
    return m;
  }, [modes]);

  const switchMode = (to, el) => {
    if (to === mode || fx) return;
    runSwitch(to, el, async () => {
      setMode(to);
      setTab(modes[to].tabs[0]?.key);
      await onModeChange?.(to); /* e.g. router.push("/shop") — the curtain waits for it */
    });
  };
  const order = useRef(Object.keys(initialCart));

  const setQty = useCallback((id, n) => {
    setCart((c) => {
      const next = { ...c };
      if (n <= 0) { delete next[id]; order.current = order.current.filter((x) => x !== id); }
      else { if (!order.current.includes(id)) order.current = [...order.current, id]; next[id] = n; }
      return next;
    });
  }, [onCartChange]);

  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      if (persistCart) {
        try {
          const saved = JSON.parse(localStorage.getItem("369mart.cart") || "null");
          if (saved && typeof saved === "object") { order.current = Object.keys(saved); setCart(saved); }
        } catch (e) { /* storage blocked */ }
      }
      return;
    }
    if (persistCart) { try { localStorage.setItem("369mart.cart", JSON.stringify(cart)); } catch (e) {} }
    onCartChange?.(cart);
  }, [cart]); // eslint-disable-line

  useEffect(() => {
    if (!syncUrl) return;
    const onPop = () => setView(location.pathname.startsWith("/cart") ? "cart" : location.pathname.startsWith("/account") ? "account" : "home");
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [syncUrl]);

  const lines = order.current.filter((id) => cart[id] && byId[id]).map((id) => ({ p: byId[id], qty: cart[id] }));
  const count = lines.reduce((s, l) => s + l.qty, 0);
  const total = lines.reduce((s, l) => s + l.qty * l.p.price, 0);
  const bannerById = Object.fromEntries(banners.map((b) => [b.id, b]));

  const go = (v) => {
    if (v === "cart" && onViewCart) return onViewCart(); /* separate /cart route */
    window.scrollTo({ top: 0 });
    if (syncUrl && v !== view) history.pushState(null, "", v === "home" ? "/" : "/" + v);
    setView(v);
  };
  const allProducts = useMemo(() => Object.values(byId), [byId]);
  const quickPicks = useMemo(() => modes[mode].sections.flatMap((s) => s.items || []).filter((p) => p.stock !== 0).slice(0, 6), [mode, modes]);
  useEffect(() => {
    const k = (e) => {
      const tag = document.activeElement?.tagName || "";
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(tag) && !e.metaKey && !e.ctrlKey) { e.preventDefault(); setSearchOpen(true); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  const pick = (md) => modes[md].sections.flatMap((s) => s.items || []).filter((p) => !cart[p.id] && p.stock !== 0);
  const recommended = useMemo(() => pick("quick").slice(0, 8), [view]); // eslint-disable-line
  const alsoLike = useMemo(() => pick("all").slice(0, 8), [view]); // eslint-disable-line

  return (
    <WishContext.Provider value={wish}>
    <div className={"hm-page" + (count > 0 && view === "home" ? " hm-has-cart" : "") + (view !== "home" ? " hm-in-cart" : "")} data-mode={mode}>
      <StoreHeader count={count} mode={mode} onMode={switchMode} onCart={() => go("cart")} onAccount={onAccount || (() => go("account"))}
        onSearch={() => { onSearch?.(); setSearchOpen(true); }} address={address} locOpen={locOpen} onLoc={() => setLocOpen(true)} />
      {view === "account" ? (
        <main className="hm-wrap hm-view-account" key="account">
          <AccountPage byId={byId} cart={cart} setQty={setQty}
            addresses={addresses} setAddresses={setAddresses} selectedAddress={address} onSelectAddress={setAddress}
            onBrowse={() => go("home")}
            onReorder={(o, el) => { flyTo(el, "#hm-cart-icon"); o.items.forEach(([id, q]) => byId[id] && byId[id].stock !== 0 && setQty(id, (cart[id] || 0) + q)); }}
            onSignOut={() => { onSignOut ? onSignOut() : go("home"); }} />
        </main>
      ) : view === "cart" ? (
        <main className="hm-wrap hm-view-cart" key="cart">
          <CartPage cart={cart} setQty={setQty} byId={byId} recommended={recommended} alsoLike={alsoLike}
            onBack={() => go("home")} onCheckout={onCheckout} />
        </main>
      ) : (<>
      <Tabs key={"t" + mode} tabs={tabs} active={tab} onChange={setTab} />
      <main className="hm-wrap hm-main hm-view-home" key={"m" + mode}>
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
      <FreeDelivery total={total} threshold={freeDeliveryAt} />
      <CartBar lines={lines} count={count} total={total} onView={() => go("cart")} />
      </>)}
      <ModeSwitchOverlay fx={fx} />
      <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} products={allProducts} picks={quickPicks} cart={cart} setQty={setQty} />
      <LocationPicker open={locOpen} onClose={() => setLocOpen(false)} selected={address} onSelect={setAddress} addresses={addresses} />
    </div>
    </WishContext.Provider>
  );
}
