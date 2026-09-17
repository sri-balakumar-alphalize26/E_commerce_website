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
import { Icon, OpenContext, Rail, SEARCH_WORDS, Thumb, WishContext, flyTo, inr, useInView, useRailScroll } from "./shared";
import { logWallet } from "./accountStore";
import AccountPage from "./Account";
import { useNotifications } from "./AccountExtras";
import ProductDetail from "./ProductDetail";
import SearchOverlay from "./SearchOverlay";
import LocationPicker, { SAMPLE_ADDRESSES } from "./LocationPicker";
import CartPage from "./Cart";
import CheckoutPage from "./Checkout";
import MiniCart from "./MiniCart";
import SupportBot from "./SupportBot";
import ReceiptPrinter from "./Receipt";
import OrderTrack from "./OrderTrack";
import { liveStatus } from "./orderState";
import { installAudioUnlock } from "./sound";
import { SAMPLE_ORDERS } from "./Account";
import { WALLET_BALANCE } from "./payment";
import { ALL_BANNERS, ALL_CATEGORIES, ALL_SECTIONS, ALL_TABS, BANNERS, CATEGORIES, SECTIONS, TABS } from "./sampleData";
import { SECTION_TO_ROUTE, TAB_TO_ROUTE, TILE_TO_ROUTE, buildIndex, enrich, listable, variantsOf } from "./catalog";
import { NavContext, pathToRoute, routeToPath } from "./nav";
import { BuyAgainPage, CategoryPage, NotFoundView, OffersPage, SearchResults, SiteFooter } from "./Browse";

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

function StoreHeader({ unread = 0, count, mode, onMode, onCart, onAccount, address, onLoc, locOpen, onSearch, onHome, onOffers, onBuyAgain, route, query }) {
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
        <a className="hm-logo" href="/" aria-label="369 Mart home" onClick={(e) => { if (onHome) { e.preventDefault(); onHome(); } }}>
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
          {query ? <span className="hm-search-q" key={query}>{query}</span> : (
          <span className="hm-search-ph">Search for '
            <span className="hm-roll">
              {SEARCH_WORDS.map((word, i) => (
                <span key={word} data-s={i === cur ? "in" : i === prev ? "out" : ""}>{word}'</span>
              ))}
            </span>
          </span>)}
        </button>
        <nav className="hm-icons" aria-label="Account">
          <button className={"hm-iconbtn hm-hide-sm" + (route === "offers" ? " hm-iconbtn-on" : "")} aria-label="Offers" title="Offers & coupons" onClick={onOffers}><Icon n="pct" /></button>
          <button className={"hm-iconbtn hm-hide-sm" + (route === "buyagain" ? " hm-iconbtn-on" : "")} aria-label="Buy again" title="Buy again" onClick={onBuyAgain}><Icon n="reorder" /></button>
          <button className="hm-iconbtn" id="hm-cart-icon" onClick={onCart} aria-label={`Cart, ${count} items`}>
            <Icon n="cart" />
            {count > 0 && <span key={count} className="hm-badge">{count}</span>}
          </button>
          <button className="hm-avatar" aria-label={unread ? `Account, ${unread} unread notifications` : "Account"} onClick={onAccount}><Icon n="user" size={18} />{unread > 0 && <i className="ax-avatar-dot" key={unread} />}</button>
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
      setInd(el ? { x: el.offsetLeft, w: el.offsetWidth } : null);
      el?.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "smooth" });
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

function CategoryStrip({ cats, onPick }) {
  const [ref, inView] = useInView();
  return (
    <section className={"hm-cats" + (inView ? " hm-in" : "")} ref={ref} aria-label="Shop by category">
      {cats.map((c, i) => (
        <a key={c.key} href={TILE_TO_ROUTE[c.key] ? "/category/" + TILE_TO_ROUTE[c.key] : "#"} onClick={(e) => { e.preventDefault(); onPick?.(c); }} className="hm-cat" style={{ "--i": i }}>
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


/* ---------- Quick <-> Express transition ---------- */
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
const RECENT_KEY = "369mart.recent";

export default function Home({
  modes = DEFAULT_MODES,
  initialMode = "quick",
  onModeChange,
  initialCart = {},
  onCartChange,
  onViewCart,
  onCheckout,
  onSearch,
  initialView = "home",  /* home | product | category | search | offers | buyagain | cart | account | notfound */
  initialParam = null,   /* product id · "slug/sub" · search term */
  initialProduct = null, /* kept for older callers: same as initialParam for the product view */
  onAccount,
  onSignOut,
  syncUrl = false,      /* true in the Next app: views update the address bar (/category/…, /search?q=…) */
  persistCart = false,  /* true in the Next app: cart survives reloads and route changes */
}) {
  const [mode, setMode] = useState(initialMode);
  const [route, setRoute] = useState({ view: initialView, param: initialParam ?? initialProduct });
  const view = route.view;
  const fromRect = useRef(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [locOpen, setLocOpen] = useState(false);
  const [address, setAddress] = useState(null);
  const [addresses, setAddresses] = useState(SAMPLE_ADDRESSES);
  const [wishIds, setWishIds] = useState([]);
  const [recentIds, setRecentIds] = useState([]);
  const [orders, setOrders] = useState(SAMPLE_ORDERS);
  const [wallet, setWallet] = useState(WALLET_BALANCE);
  const [draft, setDraft] = useState({});
  const [ready, setReady] = useState(!persistCart); /* true once saved cart / orders are loaded */
  const load = (k, fallback) => { try { const v = JSON.parse(localStorage.getItem(k) || "null"); return v ?? fallback; } catch (e) { return fallback; } };
  const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  useEffect(() => { installAudioUnlock(); }, []); /* first tap anywhere unlocks sound for the receipt printer */
  useEffect(() => {
    const w = load("369mart.list", null); if (Array.isArray(w)) setWishIds(w);
    const r = load(RECENT_KEY, null); if (Array.isArray(r)) setRecentIds(r);
    const o = load("369mart.orders", null);
    const patches = load("369mart.orderPatches", {});
    const list = [...(Array.isArray(o) ? o : []), ...SAMPLE_ORDERS].map((x) => (patches[x.id] ? { ...x, ...patches[x.id] } : x));
    setOrders(list);
    const wb = load("369mart.wallet", null); if (typeof wb === "number") setWallet(wb);
    const ad = load("369mart.addresses", null); if (Array.isArray(ad) && ad.length) setAddresses(ad);
    const sel = load("369mart.address", null); if (sel && sel.id) setAddress(sel);
    try { const d = JSON.parse(sessionStorage.getItem("369mart.checkout") || "null"); if (d) setDraft(d); } catch (e) {}
  }, []);
  const pickAddress = (a) => { setAddress(a); save("369mart.address", a); };
  const updateAddresses = (list) => { setAddresses(list); save("369mart.addresses", list); };
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
  const [cart, setCart] = useState(initialCart);
  const [fx, runSwitch] = useModeSwitch();

  /* one index for every view: home rails + browse catalogue + pack-size variants */
  const byId = useMemo(() => {
    const m = buildIndex();
    Object.values(modes).forEach((md) => md.sections.forEach((s) => s.items?.forEach((p) => { m[p.id] = enrich({ ...m[p.id], ...p }); })));
    return m;
  }, [modes]);
  const products = useMemo(() => listable(byId), [byId]);

  /* ---- navigation ---- */
  const nav = useCallback((v, param = null, opts = {}) => {
    if (v === "cart" && onViewCart) return onViewCart(); /* separate /cart route */
    if (v !== "product") fromRect.current = null;
    setSearchOpen(false);
    if (syncUrl) {
      const path = routeToPath(v, param);
      if (path !== location.pathname + location.search) history[opts.replace ? "replaceState" : "pushState"](null, "", path);
    }
    if (!opts.keepScroll) window.scrollTo({ top: 0 });
    setRoute({ view: v, param });
  }, [syncUrl, onViewCart]);

  useEffect(() => {
    if (!syncUrl) return;
    const onPop = () => { fromRect.current = null; setSearchOpen(false); setRoute(pathToRoute(location.pathname, location.search)); };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [syncUrl]);

  const switchMode = (to, el) => {
    if (to === mode || fx) return;
    runSwitch(to, el, async () => {
      setMode(to);
      if (view !== "home") nav("home");
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
  }, []);

  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      if (persistCart) {
        try {
          const saved = JSON.parse(localStorage.getItem("369mart.cart") || "null");
          if (saved && typeof saved === "object") { order.current = Object.keys(saved); setCart(saved); }
        } catch (e) { /* storage blocked */ }
        setReady(true);
      }
      return;
    }
    if (persistCart) { try { localStorage.setItem("369mart.cart", JSON.stringify(cart)); } catch (e) {} }
    onCartChange?.(cart);
  }, [cart]); // eslint-disable-line

  const lines = order.current.filter((id) => cart[id] && byId[id]).map((id) => ({ p: byId[id], qty: cart[id] }));
  const count = lines.reduce((s, l) => s + l.qty, 0);
  const total = lines.reduce((s, l) => s + l.qty * l.p.price, 0);
  const bannerById = Object.fromEntries(banners.map((b) => [b.id, b]));

  /* cart → checkout → order. Pass onCheckout to hand the cart to your own flow instead. */
  const startCheckout = (payload) => {
    if (onCheckout) return onCheckout(payload);
    setDraft(payload);
    try { sessionStorage.setItem("369mart.checkout", JSON.stringify(payload)); } catch (e) {}
    nav("checkout");
  };
  /* after-order changes (cancel, rating, return, demo skip) are stored as patches per order id */
  const patchOrder = useCallback((id, patch) => {
    setOrders((list) => list.map((x) => (x.id === id ? { ...x, ...patch } : x)));
    const all = load("369mart.orderPatches", {});
    all[id] = { ...(all[id] || {}), ...patch };
    save("369mart.orderPatches", all);
  }, []); // eslint-disable-line
  const reorder = (o, el) => { flyTo(el); o.items.forEach(([id, q]) => byId[id] && byId[id].stock !== 0 && setQty(id, (cart[id] || 0) + q)); };
  /* account + buy again show the live status of demo orders */
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (view !== "account" && view !== "buyagain") return;
    const t = setInterval(() => setTick((n) => n + 1), 5000);
    return () => clearInterval(t);
  }, [view]);
  const ordersView = useMemo(() => orders.map((x) => {
    if (!x.at || x.status === "cancelled") return x;
    const st = liveStatus(x);
    return st.key === x.status ? x : { ...x, status: st.key, eta: st.key === "delivered" ? "Delivered" : st.mode === "quick" ? `${st.etaMin} mins` : x.eta };
  }), [orders, tick]); // eslint-disable-line

  /* wallet credits from the account page (add money, scratch cards) and refunds */
  const walletMove = (amount, entry) => {
    setWallet((w) => { const n = Math.max(0, w + amount); save("369mart.wallet", n); return n; });
    if (entry) logWallet({ amount: Math.abs(amount), ...entry });
  };
  const { unread } = useNotifications(ordersView);
  const orderPlaced = (o) => {
    const saved = load("369mart.orders", []);
    save("369mart.orders", [o, ...(Array.isArray(saved) ? saved : [])].slice(0, 30));
    setOrders((list) => [o, ...list]);
    if (o.walletUsed) { const left = Math.max(0, wallet - o.walletUsed); setWallet(left); save("369mart.wallet", left); logWallet({ kind: "spend", amount: o.walletUsed, title: "Paid for order", sub: `Order #${o.id}` }); }
    order.current = []; setCart({});
    try { sessionStorage.removeItem("369mart.checkout"); } catch (e) {}
    nav("order", o.id, { replace: true });
  };

  const openProduct = useCallback((p, rect) => {
    fromRect.current = rect || null;
    setSearchOpen(false);
    if (syncUrl) history.pushState(null, "", routeToPath("product", p.id));
    setRoute({ view: "product", param: p.id });
  }, [syncUrl]);

  /* ---- product page data ---- */
  const product = view === "product" ? byId[route.param] : null;
  useEffect(() => {
    if (!product) return;
    setRecentIds((r) => {
      const next = [product.id, ...r.filter((x) => x !== product.id)].slice(0, 12);
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch (e) {}
      return next;
    });
  }, [product?.id]); // eslint-disable-line
  const pd = useMemo(() => {
    if (!product) return null;
    const self = new Set([product.id, ...variantsOf(product, byId).map((v) => v.id)]);
    const pool = products.filter((x) => !self.has(x.id));
    const similar = pool.filter((x) => product.sub && x.cat === product.cat && x.sub === product.sub);
    const sameCat = pool.filter((x) => product.cat && x.cat === product.cat && x.sub !== product.sub);
    const sameMode = pool.filter((x) => !!x.delivery === !!product.delivery && x.cat !== product.cat);
    const byPop = (list) => list.filter((x) => x.stock !== 0).sort((a, b) => b.popularity - a.popularity);
    /* one pick per other subcategory first (atta → oil, dal…), then anything with the same delivery type */
    const perSub = Object.values(byPop(sameCat).reduce((m, x) => { if (!m[x.sub] || x.price < m[x.sub].price) m[x.sub] = x; return m; }, {})).sort((a, b) => a.price - b.price);
    const bundle = [...perSub, ...byPop(sameMode)].slice(0, 2);
    const also = [...sameCat, ...sameMode].filter((x) => !bundle.includes(x)).slice(0, 10);
    return { variants: variantsOf(product, byId), similar, bundle, also };
  }, [product, byId, products]);
  const recent = recentIds.map((id) => byId[id]).filter(Boolean);

  /* ---- tabs follow the route ---- */
  const activeTab = useMemo(() => {
    if (view === "home") return tabs[0]?.key;
    const hit = tabs.find((t) => {
      const r = TAB_TO_ROUTE[t.key];
      if (!r) return false;
      if (view === "offers") return r[0] === "offers";
      return view === "category" && r[0] === "category" && String(route.param || "").split("/")[0] === r[1];
    });
    return hit?.key || null;
  }, [view, route.param, tabs]);
  const pickTab = (key) => { const r = TAB_TO_ROUTE[key]; if (r) nav(r[0], r[1] ?? null); };

  const quickPicks = useMemo(() => modes[mode].sections.flatMap((s) => s.items || []).map((p) => byId[p.id] || p).filter((p) => p.stock !== 0).slice(0, 6), [mode, modes, byId]);
  useEffect(() => {
    const k = (e) => {
      const tag = document.activeElement?.tagName || "";
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(tag) && !e.metaKey && !e.ctrlKey) { e.preventDefault(); setSearchOpen(true); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  const pick = (md) => modes[md].sections.flatMap((s) => s.items || []).map((p) => byId[p.id] || p).filter((p) => !cart[p.id] && p.stock !== 0);
  const recommended = useMemo(() => pick("quick").slice(0, 8), [view]); // eslint-disable-line
  const alsoLike = useMemo(() => pick("all").slice(0, 8), [view]); // eslint-disable-line

  const withTabs = view === "home" || view === "category" || view === "offers";
  const browsing = ["home", "product", "category", "search", "offers", "buyagain", "track"].includes(view);
  const viewAll = (s) => SECTION_TO_ROUTE[s.key] && nav("category", SECTION_TO_ROUTE[s.key]);
  const common = { byId, cart, setQty };

  let body;
  if (view === "product") {
    body = product ? (
      <main className="hm-wrap hm-view-product" key={"product-" + (product.variantGroup || product.id)}>
        <ProductDetail onEditReview={() => nav("account", "reviews")} p={product} cart={cart} setQty={setQty} address={address}
          fromRect={fromRect.current}
          variants={pd.variants}
          onVariant={(v) => nav("product", v.id, { replace: true, keepScroll: true })}
          bundle={pd.bundle}
          similar={pd.similar}
          related={pd.also}
          recent={recent.filter((x) => x.id !== product.id)}
          onViewSimilar={product.sub ? () => nav("category", `${product.cat}/${product.sub}`) : undefined}
          onBack={() => { if (syncUrl && history.length > 1) history.back(); else nav("home"); }}
          onChangeAddress={() => setLocOpen(true)}
          onExplore={() => (product.cat ? nav("category", product.cat) : nav("home"))} />
      </main>
    ) : (
      <main className="hm-wrap hm-view-browse" key="product-missing">
        <NotFoundView title="Product not found" text="It may have been removed or the link is incomplete." />
      </main>
    );
  } else if (view === "account") {
    body = (
      <main className="hm-wrap hm-view-account" key={"account-" + (route.param || "")}>
        <AccountPage byId={byId} cart={cart} setQty={setQty} section={route.param || undefined}
          addresses={addresses} setAddresses={updateAddresses} selectedAddress={address} onSelectAddress={pickAddress} orders={ordersView}
          onBrowse={() => nav("home")}
          onReorder={reorder} onTrack={(o) => nav("track", o.id)}
          wallet={wallet} onWallet={walletMove} onNav={nav}
          onSection={(k) => { if (syncUrl) history.replaceState(null, "", routeToPath("account", k)); }}
          onSignOut={() => { onSignOut ? onSignOut() : nav("home"); }} />
      </main>
    );
  } else if (view === "cart") {
    body = (
      <main className="hm-wrap hm-view-cart" key="cart">
        <CartPage cart={cart} setQty={setQty} byId={byId} recommended={recommended} alsoLike={alsoLike}
          onBack={() => nav("home")} onCheckout={startCheckout} />
      </main>
    );
  } else if (view === "checkout") {
    body = (
      <main className="hm-wrap hm-view-checkout" key="checkout">
        <CheckoutPage cart={cart} byId={byId} draft={draft} ready={ready}
          addresses={addresses} setAddresses={updateAddresses} address={address} onSelectAddress={pickAddress}
          walletBalance={wallet} onBack={() => nav("cart")} onPlaced={orderPlaced} />
      </main>
    );
  } else if (view === "track") {
    const o = orders.find((x) => x.id === route.param);
    body = (
      <main className="hm-wrap hm-view-track" key={"track-" + route.param}>
        {o ? (
          <OrderTrack order={o} byId={byId} patchOrder={patchOrder}
            onBack={() => nav("account", "orders")} onReceipt={() => nav("order", o.id)} onShop={() => nav("home")}
            onReorder={reorder}
            onRefundWallet={(amt) => walletMove(amt, { kind: "refund", title: "Refund for cancelled order", sub: `Order #${o.id}` })} />
        ) : ready ? (
          <NotFoundView title="Order not found" text="This order isn't on this device. Your orders are listed in your account." />
        ) : <div className="co-skel"><span /><span /></div>}
      </main>
    );
  } else if (view === "order") {
    const o = orders.find((x) => x.id === route.param);
    body = (
      <main className="hm-wrap hm-view-order" key={"order-" + route.param}>
        {o && o.bill ? (
          <ReceiptPrinter order={o} byId={byId} onTrack={() => nav("track", o.id)} onShop={() => nav("home")} />
        ) : ready ? (
          <NotFoundView title="Order not found" text="This receipt isn't on this device. Your orders are listed in your account." />
        ) : <div className="co-skel"><span /><span /></div>}
      </main>
    );
  } else if (view === "category") {
    const [slug, sub] = String(route.param || "").split("/");
    body = <main className="hm-wrap hm-view-browse" key={"cat-" + slug}><CategoryPage slug={slug} subSlug={sub} {...common} /></main>;
  } else if (view === "search") {
    body = <main className="hm-wrap hm-view-browse" key="search"><SearchResults q={route.param || ""} mode={mode} {...common} /></main>;
  } else if (view === "offers") {
    body = <main className="hm-wrap hm-view-browse" key="offers"><OffersPage {...common} /></main>;
  } else if (view === "buyagain") {
    body = <main className="hm-wrap hm-view-browse" key="buyagain"><BuyAgainPage {...common} orders={ordersView} /></main>;
  } else if (view === "notfound") {
    body = <main className="hm-wrap hm-view-browse" key="nf"><NotFoundView /></main>;
  } else {
    body = (
      <main className="hm-wrap hm-main hm-view-home" key={"m" + mode}>
        <BannerCarousel banners={banners} />
        <CategoryStrip cats={categories} onPick={(c) => TILE_TO_ROUTE[c.key] && nav("category", TILE_TO_ROUTE[c.key])} />
        {sections.map((s, i) =>
          s.banner ? (
            <div className="hm-inline-banners" key={"bn" + i}>
              {s.banner.map((id, k) => bannerById[id] && <Banner key={id} b={bannerById[id]} i={k} />)}
            </div>
          ) : (
            <Rail key={s.key} section={{ ...s, items: s.items.map((p) => byId[p.id] || p) }} cart={cart} setQty={setQty} onViewAll={SECTION_TO_ROUTE[s.key] ? viewAll : undefined} />
          )
        )}
        {recent.length > 1 && <Rail key="recent" section={{ key: "recent", title: "Recently viewed", subtitle: "Pick up where you left off", items: recent }} cart={cart} setQty={setQty} />}
      </main>
    );
  }

  return (
    <NavContext.Provider value={nav}>
    <WishContext.Provider value={wish}>
    <OpenContext.Provider value={openProduct}>
    <div className={"hm-page" + (count > 0 && browsing ? " hm-has-cart" : "") + (view !== "home" ? " hm-in-cart" : "") + " hm-at-" + view} data-mode={mode}>
      <StoreHeader unread={unread} count={count} mode={mode} onMode={switchMode} onCart={() => nav("cart")} onAccount={onAccount || (() => nav("account"))}
        onHome={() => nav("home")} onOffers={() => nav("offers")} onBuyAgain={() => nav("buyagain")} route={view} query={view === "search" ? route.param || "" : ""}
        onSearch={() => { onSearch?.(); setSearchOpen(true); }} address={address} locOpen={locOpen} onLoc={() => setLocOpen(true)} />
      {withTabs && <Tabs key={"t" + mode} tabs={tabs} active={activeTab} onChange={pickTab} />}
      {body}
      {!["cart", "checkout", "order"].includes(view) && <SiteFooter />}
      {view === "home" && <FreeDelivery total={total} threshold={freeDeliveryAt} />}
      {browsing && (
        <MiniCart lines={lines} count={count} total={total} freeAt={freeDeliveryAt} setQty={setQty}
          onViewCart={() => nav("cart")} onCheckout={() => startCheckout({ how: "online" })} hidden={!!fx} />
      )}
      <SupportBot orders={ordersView} wallet={wallet} onNav={nav}
        hidden={!!fx || ["checkout", "order", "track"].includes(view)}
        lift={view === "cart" ? 3 : browsing && count > 0 ? (view === "home" ? 2 : 1) : 0} />
      <ModeSwitchOverlay fx={fx} />
      <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} products={products} picks={quickPicks} cart={cart} setQty={setQty}
        initialQuery={view === "search" ? route.param || "" : ""}
        onSubmit={(term) => nav("search", term)} />
      <LocationPicker open={locOpen} onClose={() => setLocOpen(false)} selected={address} onSelect={pickAddress} addresses={addresses} />
    </div>
    </OpenContext.Provider>
    </WishContext.Provider>
    </NavContext.Provider>
  );
}
