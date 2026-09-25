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
import { Icon, OpenContext, Rail, SEARCH_WORDS, Thumb, WishContext, flyTo, money, useInView, useRailScroll } from "./shared";
import AccountPage from "./Account";
import { useNotifications } from "./AccountExtras";
import ProductDetail from "./ProductDetail";
import SearchOverlay from "./SearchOverlay";
import LocationPicker from "./LocationPicker";
import CartPage from "./Cart";
import CheckoutPage from "./Checkout";
import MiniCart from "./MiniCart";
import SupportBot from "./SupportBot";
import ReceiptPrinter from "./Receipt";
import OrderTrack from "./OrderTrack";
import { installAudioUnlock } from "./sound";
import { SECTION_TO_ROUTE, TAB_TO_ROUTE, TILE_TO_ROUTE, listable } from "./catalog";
import { NavContext, pathToRoute, routeToPath } from "./nav";
import { useAction, useResource } from "@/lib/useFetch";
import { absorb, ensure, useProducts } from "@/lib/products";
import { setCurrency, useCurrency } from "@/lib/money";
import { ApiError, api } from "@/lib/api";
import { addressText } from "@/lib/address";
import { BuyAgainPage, CategoryPage, NotFoundView, OffersPage, SearchResults, SiteFooter } from "./Browse";

/* ---------- header ---------- */
function ModeToggle({ mode, onMode, copy }) {
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
      {/* The shop's own words for its two tabs, with the app's originals
          behind them. `title` reads as italic on Quick because that is how the
          toggle has always drawn it, not because of anything in the text. */}
      <button role="tab" data-m="quick" aria-selected={mode === "quick"} onClick={(e) => onMode("quick", e.currentTarget)}>
        <Icon n={copy?.quick?.icon || "bolt"} size={13} className="hm-fill" />
        <i>{copy?.quick?.title || "Quick"}</i>
      </button>
      <button role="tab" data-m="all" aria-selected={mode === "all"} onClick={(e) => onMode("all", e.currentTarget)}>
        <Icon n={copy?.all?.icon || "grid"} size={13} />{copy?.all?.title || "Express"}
      </button>
    </div>
  );
}

function StoreHeader({ unread = 0, count, mode, onMode, modeText, onCart, onAccount, address, onLoc, locOpen, onSearch, onHome, onOffers, onBuyAgain, route, query }) {
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
        <ModeToggle mode={mode} onMode={onMode} copy={modeText} />
        <button className={"hm-loc" + (locOpen ? " hm-loc-open" : "")} onClick={onLoc} aria-haspopup="dialog" aria-expanded={!!locOpen}>
          <span className="hm-loc-ic" key={mode + (address?.id || "")}><Icon n={mode === "quick" ? "bolt" : "truck"} size={18} className={mode === "quick" ? "hm-fill" : ""} /></span>
          <span className="hm-loc-txt" key={address?.id || "none"}>
            <b>{address ? (mode === "quick" ? address.label : `Deliver to ${address.label}`) : (mode === "quick" ? "Delivery in minutes" : "Deliver to")} <Icon n="chev" size={14} className="hm-loc-chev" /></b>
            <small>{address ? addressText(address) : "Set your delivery location"}</small>
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

export function Tabs({ tabs, active, onChange }) {
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
export function Banner({ b, i }) {
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

export function BannerCarousel({ banners, autoplay = true }) {
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

export function CategoryStrip({ cats, onPick }) {
  const [ref, inView] = useInView();
  return (
    <section className={"hm-cats" + (inView ? " hm-in" : "")} ref={ref} aria-label="Shop by category">
      {cats.map((c, i) => (
        <a key={c.key} href={c.route || TILE_TO_ROUTE[c.key] ? "/category/" + (c.route || TILE_TO_ROUTE[c.key]) : "#"} onClick={(e) => { e.preventDefault(); onPick?.(c); }} className="hm-cat" style={{ "--i": i }}>
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
        <span>{done ? <><b>Free delivery unlocked</b> on this order</> : <>Shop for <b>{money(left)}</b> more to unlock <b>free delivery</b></>}</span>
        <span className="hm-free-bar"><i style={{ width: pct + "%" }} /></span>
      </span>
    </div>
  );
}


/* ---------- Quick <-> Express transition ---------- */
/* What the two tabs are called and what they promise.
 *
 * These used to be written in here, which meant "in minutes" and "2–5 day
 * delivery" — statements about what the shop will actually do for a customer —
 * could only be corrected by a developer and a deploy. They come from the feed
 * now, per saved page, so a festival page can promise something different.
 *
 * These stay as the fallback: the exact words the app had before, for a shop
 * that has not been asked yet or cannot be reached. */
const MODE_COPY = {
  quick: { icon: "bolt", title: "Quick", sub: "Parts & peripherals in minutes" },
  all: { icon: "grid", title: "Express", sub: "Electronics, home & more · 2–5 day delivery" },
};

/* The shop's own wording for one mode, falling back to the above. */
const modeCopy = (key, feed) => ({
  icon: feed?.icon || MODE_COPY[key].icon,
  title: feed?.label || MODE_COPY[key].title,
  sub: feed?.tagline || MODE_COPY[key].sub,
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* in: colour floods out of the toggle · hold: swap content underneath · out: curtain lifts */
export function useModeSwitch() {
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

export function ModeSwitchOverlay({ fx, copy }) {
  if (!fx) return null;
  const c = copy || MODE_COPY[fx.to];
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

/* What the page is made of before the shop's own home feed arrives.

   It used to be a full sample catalogue, which meant that when the backend
   could not be reached the shop quietly showed a different shop - groceries in
   a computer store - with no sign anything was wrong. An empty frame that
   admits it knows nothing is the honest version.

   It must stay an object with both mode keys. `liveModes[mode]` is destructured
   without a guard below, and `pick("quick")` / `pick("all")` name both modes
   outright, so null here white-screens the page before any error state could
   render. */
const EMPTY_MODE = { tabs: [], banners: [], categories: [], sections: [], freeDeliveryAt: 0 };
const DEFAULT_MODES = { quick: EMPTY_MODE, all: EMPTY_MODE };
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
  /* The address book lives on the account. Which one is the default is the
     shop's answer too - it is what an order will actually ship to, so a copy
     kept in this browser could only ever disagree with it. */
  const { data: addrData, reload: reloadAddresses } = useResource("/addresses");
  const addresses = useMemo(() => addrData?.addresses || [], [addrData]);
  /* The card tapped, while the shop is being told. A round trip to Oman takes
     seconds, and a radio that sits still that long reads as a tap that missed.
     It goes back to the shop's answer the moment that answer is in - or the
     save fails - so it can never outlive a disagreement. */
  const [picking, setPicking] = useState(null);
  const address = useMemo(() => addresses.find((a) => a.id === (picking ?? addrData?.selected)) || null, [addresses, addrData, picking]);
  /* What the address form needs from the shop: phone prefix, pincode length,
     the country's states. The shop delivers in one country; the form follows. */
  const { data: addressForm } = useResource("/addresses/form");
  /* "Use my location" fills the form rather than saving half an address. */
  const [addrPrefill, setAddrPrefill] = useState(null);
  const addrAct = useAction();
  const [recentIds, setRecentIds] = useState([]);
  const [draft, setDraft] = useState({});
  const [me, setMe] = useState(null); /* the signed-in customer, from /api/auth/me */
  useEffect(() => {
    fetch("/api/auth/me").then((r) => (r.ok ? r.json() : null)).then((d) => { if (d?.ok) setMe({ name: d.name, email: d.email, phone: d.phone || "" }); }).catch(() => {});
  }, []);
  const [ready, setReady] = useState(!persistCart); /* true once saved cart / orders are loaded */
  const load = (k, fallback) => { try { const v = JSON.parse(localStorage.getItem(k) || "null"); return v ?? fallback; } catch (e) { return fallback; } };
  const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  useEffect(() => { installAudioUnlock(); }, []); /* first tap anywhere unlocks sound for the receipt printer */
  useEffect(() => {
    const r = load(RECENT_KEY, null); if (Array.isArray(r)) setRecentIds(r);
    try { const d = JSON.parse(sessionStorage.getItem("369mart.checkout") || "null"); if (d) setDraft(d); } catch (e) {}
  }, []);
  /* Choosing an address is telling the shop which one to ship to. */
  const pickAddress = async (a) => {
    setPicking(a.id);
    try {
      await addrAct.run(async () => { await api(`/addresses/${a.id}/default`, { method: "POST" }); api.invalidate("/addresses"); await reloadAddresses(); });
    } finally {
      setPicking((p) => (p === a.id ? null : p)); /* a later tap keeps its own */
    }
  };
  /* Add (id null) or change one address. Answers {address} or {error}, the
     error still carrying the field the shop named so the form can put it
     under the right box. */
  const saveAddress = async (id, body) => {
    try {
      const r = await api(id ? `/addresses/${id}` : "/addresses", { method: id ? "PATCH" : "POST", body });
      api.invalidate("/addresses"); await reloadAddresses();
      return { address: r?.address || null };
    } catch (e) {
      return { error: e instanceof ApiError ? e : new ApiError(e?.message || "Could not save that address. Try again.") };
    }
  };
  const removeAddress = (a) =>
    addrAct.run(async () => { await api(`/addresses/${a.id}`, { method: "DELETE" }); api.invalidate("/addresses"); await reloadAddresses(); });
  /* One line for anything the page has to say back to a tap - a heart is the
     first thing here with no screen of its own to say it on. */
  const [notice, setNotice] = useState("");
  const noticeT = useRef(null);
  const notify = useCallback((m) => {
    setNotice(m);
    clearTimeout(noticeT.current);
    noticeT.current = setTimeout(() => setNotice(""), 2200);
  }, []);
  /* The list belongs to the shopper, not to this browser, so it comes from the
     account - which also means a guest has nowhere to put one, and is told so
     rather than handed a list that quietly dies with the cache. Every answer
     carries the whole list back, so a toggle needs no second trip. The heart
     fills before the trip though: one that waits for Oman reads as broken. */
  /* What the wallet holds is the shop's ledger, not a number this browser
     keeps adding to. Spending it and topping it up are payments, and they are
     the last thing left to move across. */
  const { data: walletData, reload: reloadWallet } = useResource("/wallet", { enabled: !!me });
  const wallet = walletData?.balance ?? 0;
  const { data: wishData } = useResource("/wishlist", { enabled: !!me });
  const [wishIds, setWishIds] = useState([]);
  const wishAct = useAction();
  useEffect(() => { if (Array.isArray(wishData?.ids)) setWishIds(wishData.ids); }, [wishData]);
  /* The orders are the shop's record, not this browser's. There is no seeded
     history any more, and nothing here decides that an order has moved on -
     it is polled while a screen is showing one, because a rider setting off
     is news that arrives from the warehouse, not from a timer in a page. */
  const { data: ordersData, reload: reloadOrders } = useResource("/orders", { enabled: !!me, pollMs: view === "track" || view === "account" ? 20000 : 0 });
  const orders = useMemo(() => ordersData?.orders || [], [ordersData]);

  const wish = useMemo(() => ({
    ids: wishIds,
    has: (id) => wishIds.includes(id),
    toggle: (id) => {
      if (!me) return notify("Sign in to save this");
      const had = wishIds.includes(id);
      const before = wishIds;
      setWishIds(had ? before.filter((x) => x !== id) : [id, ...before]);
      wishAct
        .run(async () => {
          const r = had
            ? await api(`/wishlist/${id}`, { method: "DELETE" })
            : await api("/wishlist", { method: "POST", body: { id } });
          api.invalidate("/wishlist");
          if (Array.isArray(r?.ids)) setWishIds(r.ids);
          notify(had ? "Removed from My List" : "Saved to My List");
        })
        .then((ok) => { if (ok === null) { setWishIds(before); notify("Couldn't update your list"); } });
    },
  }), [wishIds, me, notify, wishAct]);
  /* The home feed, from Odoo: one key per active mode, in the shape the page
     already reads. `stale` is how many seconds old the answer is when the shop
     could not be reached and the proxy handed back the last one it kept - the
     page still shows real products, and says so. */
  const { data: feed, error: feedError, loading: feedLoading, stale: feedStale, reload: reloadFeed } = useResource("/home");
  /* The shop says what its money looks like on the feed every screen loads.
     Kept out of the merge below, which is a map of modes and nothing else. */
  useEffect(() => { if (feed?.currency) setCurrency(feed.currency); }, [feed]);
  useCurrency(); /* redraw the tree the moment it arrives */
  const liveModes = useMemo(() => {
    if (!feed) return modes;
    const { currency, ...byMode } = feed;
    return { ...modes, ...byMode };
  }, [feed, modes]);

  const { tabs, banners, categories, sections, freeDeliveryAt } = liveModes[mode];
  /* What the shop calls its two tabs and what it promises for each. From the
     feed, so a delivery promise can be corrected without a deploy. */
  const modeText = useMemo(() => ({
    quick: modeCopy("quick", liveModes.quick),
    all: modeCopy("all", liveModes.all),
  }), [liveModes]);
  const [cart, setCart] = useState(initialCart);
  const [fx, runSwitch] = useModeSwitch();

  /* Every product this session has actually been told about, and nothing else.

     It used to start from buildIndex(), the sample catalogue, which is why a
     basket or a recently-viewed row could still be holding groceries months
     after the shop stopped selling them: the ids were stale, but the sample
     data still had something to resolve them to. Now an id the shop has never
     mentioned resolves to nothing, and nothing is what gets drawn. */
  const byId = useProducts();
  useEffect(() => {
    if (!feed) return;
    Object.values(feed).forEach((md) => (md?.sections || []).forEach((s) => absorb(s.items || [])));
  }, [feed]);
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
  const reorder = (o, el) => { flyTo(el); o.items.forEach(([id, q]) => byId[id] && byId[id].stock !== 0 && setQty(id, (cart[id] || 0) + q)); };

  /* A refund is the shop crediting the wallet, so there is nothing to add up
     here - only the ledger to read again once it has. */
  const walletMove = () => reloadWallet();
  const { unread } = useNotifications(orders);
  /* The order is the shop's now; there is nothing to keep here but the
     knowledge that the basket it came from is spent. */
  const orderPlaced = (o) => {
    reloadOrders();
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
    /* Pack sizes come from the shop with the product page. They used to be
       read out of a hand-written table of grocery sizes. */
    const variants = [];
    const self = new Set([product.id, ...variants.map((v) => v.id)]);
    const pool = products.filter((x) => !self.has(x.id));
    const similar = pool.filter((x) => product.sub && x.cat === product.cat && x.sub === product.sub);
    const sameCat = pool.filter((x) => product.cat && x.cat === product.cat && x.sub !== product.sub);
    const sameMode = pool.filter((x) => !!x.delivery === !!product.delivery && x.cat !== product.cat);
    const byPop = (list) => list.filter((x) => x.stock !== 0).sort((a, b) => b.popularity - a.popularity);
    /* one pick per other subcategory first (atta → oil, dal…), then anything with the same delivery type */
    const perSub = Object.values(byPop(sameCat).reduce((m, x) => { if (!m[x.sub] || x.price < m[x.sub].price) m[x.sub] = x; return m; }, {})).sort((a, b) => a.price - b.price);
    const bundle = [...perSub, ...byPop(sameMode)].slice(0, 2);
    const also = [...sameCat, ...sameMode].filter((x) => !bundle.includes(x)).slice(0, 10);
    return { variants, similar, bundle, also };
  }, [product, byId, products]);
  /* The ids the browser kept - recently viewed, the basket, the wishlist - are
     just strings, and nothing seeds them any more. Fetch the ones we have not
     been told about; whatever the shop no longer has quietly stays unresolved
     and is not drawn. */
  useEffect(() => {
    ensure([
      ...(view === "product" && route.param ? [route.param] : []), /* a shared link lands here knowing nothing */
      ...recentIds, ...Object.keys(cart), ...wishIds,
    ]);
  }, [view, route.param, recentIds, cart, wishIds]);
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
  /* A tab only tells us its key, so the key has to be the category's address.
     The old map is kept for the handful of keys that are not categories at all
     - home, offers - and anything it does not know is taken at face value. */
  const pickTab = (key) => { const r = TAB_TO_ROUTE[key] || ["category", key]; nav(r[0], r[1] ?? null); };

  const quickPicks = useMemo(() => liveModes[mode].sections.flatMap((s) => s.items || []).map((p) => byId[p.id] || p).filter((p) => p.stock !== 0).slice(0, 6), [mode, liveModes, byId]);
  useEffect(() => {
    const k = (e) => {
      const tag = document.activeElement?.tagName || "";
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(tag) && !e.metaKey && !e.ctrlKey) { e.preventDefault(); setSearchOpen(true); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  const pick = (md) => liveModes[md].sections.flatMap((s) => s.items || []).map((p) => byId[p.id] || p).filter((p) => !cart[p.id] && p.stock !== 0);
  const recommended = useMemo(() => pick("quick").slice(0, 8), [view]); // eslint-disable-line
  const alsoLike = useMemo(() => pick("all").slice(0, 8), [view]); // eslint-disable-line

  const withTabs = view === "home" || view === "category" || view === "offers";
  const browsing = ["home", "product", "category", "search", "offers", "buyagain", "track"].includes(view);
  const viewAll = (s) => (s.route || SECTION_TO_ROUTE[s.key]) && nav("category", s.route || SECTION_TO_ROUTE[s.key]);
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
        <AccountPage user={me || undefined} byId={byId} cart={cart} setQty={setQty} section={route.param || undefined}
          addresses={addresses} onSaveAddress={saveAddress} addressForm={addressForm} addrMe={me}
          addrPrefill={addrPrefill} onPrefillUsed={() => setAddrPrefill(null)} onRemoveAddress={removeAddress}
          selectedAddress={address} onSelectAddress={pickAddress} addrBusy={addrAct.busy} addrError={addrAct.error?.message} orders={orders}
          onBrowse={() => nav("home")}
          onReorder={reorder} onTrack={(o) => nav("track", o.id)}
          wallet={wallet} onWallet={walletMove} onNav={nav}
          onSection={(k) => { if (syncUrl) history.replaceState(null, "", routeToPath("account", k)); }}
          onSignOut={async () => { try { await fetch("/api/auth/logout", { method: "POST" }); } catch (e) {} setMe(null); onSignOut ? onSignOut() : nav("home"); }} />
      </main>
    );
  } else if (view === "cart") {
    body = (
      <main className="hm-wrap hm-view-cart" key="cart">
        <CartPage cart={cart} setQty={setQty} byId={byId} recommended={recommended} alsoLike={alsoLike} addressId={address?.id}
          onBack={() => nav("home")} onCheckout={startCheckout} />
      </main>
    );
  } else if (view === "checkout") {
    body = (
      <main className="hm-wrap hm-view-checkout" key="checkout">
        <CheckoutPage cart={cart} byId={byId} draft={draft} ready={ready}
          addresses={addresses} onSaveAddress={saveAddress} addressForm={addressForm} me={me} address={address} onSelectAddress={pickAddress} addrBusy={addrAct.busy}
          walletBalance={wallet} onBack={() => nav("cart")} onPlaced={orderPlaced} />
      </main>
    );
  } else if (view === "track") {
    const o = orders.find((x) => x.id === route.param);
    body = (
      <main className="hm-wrap hm-view-track" key={"track-" + route.param}>
        {o ? (
          <OrderTrack order={o} byId={byId} onChanged={reloadOrders}
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
    body = <main className="hm-wrap hm-view-browse" key="buyagain"><BuyAgainPage {...common} orders={orders} /></main>;
  } else if (view === "notfound") {
    body = <main className="hm-wrap hm-view-browse" key="nf"><NotFoundView /></main>;
  } else {
    body = (
      <main className="hm-wrap hm-main hm-view-home" key={"m" + mode}>
        {feedLoading && !sections.length ? (
          /* Nothing to show yet. A frame, not a guess. */
          <div className="co-skel" aria-label="Loading the shop"><span /><span /><span /></div>
        ) : feedError && !sections.length ? (
          /* Nothing kept either. Say so plainly and offer the one useful action. */
          <div className="ls-empty" role="alert">
            <div className="ls-empty-art"><ProductArt art="Router" color="#1f3b4d" /></div>
            <h3>We can&apos;t reach the store</h3>
            <p>{feedError.message}</p>
            <button className="ls-primary" onClick={reloadFeed}>Try again</button>
          </div>
        ) : null}
        {feedStale > 0 && (
          <p className="hm-stale" role="status">
            Showing the last update from {new Date(Date.now() - feedStale * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            {" "}&mdash; we can&apos;t reach the store right now.
          </p>
        )}
        <BannerCarousel banners={banners} />
        <CategoryStrip cats={categories} onPick={(c) => (c.route || TILE_TO_ROUTE[c.key]) && nav("category", c.route || TILE_TO_ROUTE[c.key])} />
        {sections.map((s, i) =>
          s.banner ? (
            <div className="hm-inline-banners" key={"bn" + i}>
              {s.banner.map((id, k) => bannerById[id] && <Banner key={id} b={bannerById[id]} i={k} />)}
            </div>
          ) : (
            <Rail key={s.key} section={{ ...s, items: s.items.map((p) => byId[p.id] || p) }} cart={cart} setQty={setQty} onViewAll={s.route || SECTION_TO_ROUTE[s.key] ? viewAll : undefined} />
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
      <StoreHeader unread={unread} count={count} mode={mode} onMode={switchMode} modeText={modeText} onCart={() => nav("cart")} onAccount={onAccount || (() => nav("account"))}
        onHome={() => nav("home")} onOffers={() => nav("offers")} onBuyAgain={() => nav("buyagain")} route={view} query={view === "search" ? route.param || "" : ""}
        onSearch={() => { onSearch?.(); setSearchOpen(true); }} address={address} locOpen={locOpen} onLoc={() => setLocOpen(true)} />
      {withTabs && <Tabs key={"t" + mode} tabs={tabs} active={activeTab} onChange={pickTab} />}
      {body}
      {!["cart", "checkout", "order"].includes(view) && <SiteFooter />}
      {view === "home" && freeDeliveryAt > 0 && <FreeDelivery total={total} threshold={freeDeliveryAt} />}
      {browsing && (
        <MiniCart lines={lines} count={count} total={total} freeAt={freeDeliveryAt} setQty={setQty}
          onViewCart={() => nav("cart")} onCheckout={() => startCheckout({ how: "online" })} hidden={!!fx} />
      )}
      <SupportBot onNav={nav}
        hidden={!!fx || ["checkout", "order", "track"].includes(view)}
        lift={view === "cart" ? 3 : browsing && count > 0 ? (view === "home" ? 2 : 1) : 0} />
      <ModeSwitchOverlay fx={fx} copy={fx ? modeText[fx.to] : null} />
      <div className={"hm-toast" + (notice ? " hm-show" : "")} role="status" aria-live="polite">{notice}</div>
      <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} products={products} picks={quickPicks} cart={cart} setQty={setQty}
        initialQuery={view === "search" ? route.param || "" : ""}
        onSubmit={(term) => nav("search", term)} />
      <LocationPicker open={locOpen} onClose={() => setLocOpen(false)} selected={address} onSelect={pickAddress} addresses={addresses}
        onAddAddress={() => { setLocOpen(false); nav("account", "address"); }}
        onCheckPincode={(pin) => api(`/serviceability?pin=${encodeURIComponent(pin)}`, { raw: true })}
        onLocate={async (c) => {
          /* A GPS fix gives the area, town, state and pincode - never the flat
             number or who to hand it to. So it opens the address form filled
             in, and the shopper finishes it. If the lookup fails the form
             still opens, empty, with the map pin kept. */
          const g = await api("/geocode/reverse", { method: "POST", body: { lat: c.latitude, lng: c.longitude }, raw: true });
          const found = g?.ok ? { area: g.area || g.line || "", town: g.city || "", pin: g.zip || "", state_id: g.state_id || "" } : {};
          setAddrPrefill({ ...found, lat: c.latitude, lng: c.longitude, key: Date.now() });
          nav("account", "address");
          return { prefill: true };
        }} />
    </div>
    </OpenContext.Provider>
    </WishContext.Provider>
    </NavContext.Provider>
  );
}
