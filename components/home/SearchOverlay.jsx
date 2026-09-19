"use client";
/* ==========================================================================
   369 Mart — Search overlay
   Tap the header search → page dims, a panel grows out of the bar itself
   (clip-path, so text never stretches), sections rise, chips/cards cascade.
   Typing shows live results with the match highlighted; rows re-cascade.
   Esc / backdrop / close → shrinks back into the bar. Full-screen sheet < 600px.
   ========================================================================== */
import { useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import ProductArt from "./art";
import { Icon, OpenContext, QtyControl, SEARCH_WORDS, Thumb, money } from "./shared";
import { useResource } from "@/lib/useFetch";
import { api } from "@/lib/api";
import { absorb, cards } from "@/lib/products";

/* Recent searches live on the shopper's account when there is one. This key
   is the signed-out fallback: a search box is no place for a 401. */
const STORE_KEY = "369mart.searches";
/* A signed-out shopper has no account history, and asking again every time
   the search box opens just fills the log with 401s. Ask once. */
let accountHistory = true;
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function insetOf(bar, p) {
  const c = (v) => Math.max(0, v).toFixed(1) + "px";
  return `inset(${c(bar.top - p.top)} ${c(p.right - bar.right)} ${c(p.bottom - bar.bottom)} ${c(bar.left - p.left)} round ${(bar.height / 2).toFixed(1)}px)`;
}


function Highlight({ text, q }) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text;
  return <>{text.slice(0, i)}<mark>{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</>;
}

export default function SearchOverlay({ open, onClose, products, picks, cart, setQty, onSubmit, initialQuery = "", triggerSelector = ".hm-search" }) {
  const [phase, setPhase] = useState("closed"); // closed | open | closing
  const [q, setQ] = useState("");
  const [past, setPast] = useState([]);
  const [clearing, setClearing] = useState(false);
  const [word, setWord] = useState(0);
  const [place, setPlace] = useState(null);
  const panel = useRef(null);
  const back = useRef(null);
  const input = useRef(null);
  const anims = useRef([]);
  const openProduct = useContext(OpenContext);

  /* restore / persist past searches */
  useEffect(() => {
    if (!open) return; /* nothing to restore until the box is actually opened */
    let alive = true;
    const local = () => { try { const s = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); if (Array.isArray(s)) setPast(s); } catch (e) {} };
    if (!accountHistory) { local(); return; }
    api("/search/recent").then((r) => { if (alive && Array.isArray(r?.recent)) setPast(r.recent); }).catch((e) => {
      if (e?.status === 401) accountHistory = false;
      /* signed out: fall back to what this browser remembers */
      local();
    });
    return () => { alive = false; };
  }, [open]);
  const savePast = (list) => { setPast(list); try { localStorage.setItem(STORE_KEY, JSON.stringify(list)); } catch (e) {} };
  const remember = (t) => {
    t = t.trim().toLowerCase();
    if (!t) return;
    savePast([t, ...past.filter((x) => x !== t)].slice(0, 8));
    if (accountHistory) api("/search/recent", { method: "POST", body: { q: t } }).catch(() => {});
  };

  /* rolling placeholder */
  useEffect(() => {
    if (phase === "closed") return;
    const t = setInterval(() => setWord((w) => w + 1), 2600);
    return () => clearInterval(t);
  }, [phase]);

  /* open/close requests from the parent */
  useEffect(() => {
    if (open && phase === "closed") {
      const bar = document.querySelector(triggerSelector)?.getBoundingClientRect() || null;
      const vw = document.documentElement.clientWidth;
      if (!bar || vw < 600) setPlace({ sheet: true, bar });
      else {
        const w = Math.min(Math.max(720, bar.width + 24), vw - 32);
        setPlace({ sheet: false, bar, x: Math.min(Math.max(16, bar.left - 12), vw - 16 - w), y: Math.max(8, bar.top - 10), w });
      }
      setQ(initialQuery); /* on the results page the current term is prefilled and selected */
      setPhase("open");
    }
    if (!open && phase === "open") close();
  }, [open]); // eslint-disable-line

  /* grow out of the bar */
  useLayoutEffect(() => {
    if (phase !== "open" || !panel.current) return;
    document.documentElement.classList.add("sr-lock");
    input.current?.focus({ preventScroll: true });
    if (initialQuery) input.current?.select();
    anims.current.forEach((a) => a.cancel());
    if (!reducedMotion() && panel.current.animate) {
      const p = panel.current.getBoundingClientRect();
      const r = getComputedStyle(panel.current).borderTopLeftRadius || "0px";
      const from = place?.bar ? insetOf(place.bar, p) : "inset(0px 0px 100% 0px round 16px)";
      anims.current = [
        panel.current.animate([{ clipPath: from }, { clipPath: `inset(0px 0px 0px 0px round ${r})` }], { duration: 420, easing: "cubic-bezier(.2,.9,.25,1)" }),
        back.current.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 260, easing: "ease-out" }),
      ];
    }
    const id = requestAnimationFrame(() => requestAnimationFrame(() => panel.current?.setAttribute("data-in", "")));
    return () => cancelAnimationFrame(id);
  }, [phase]); // eslint-disable-line

  function close() {
    if (phase !== "open") return;
    const el = panel.current;
    el?.removeAttribute("data-in");
    const done = () => {
      anims.current.forEach((a) => a.cancel());
      anims.current = [];
      document.documentElement.classList.remove("sr-lock");
      setPhase("closed"); setQ("");
      document.querySelector(triggerSelector)?.focus({ preventScroll: true });
      onClose?.();
    };
    if (reducedMotion() || !el?.animate) return done();
    setPhase("closing");
    const p = el.getBoundingClientRect();
    const bar = document.querySelector(triggerSelector)?.getBoundingClientRect();
    const r = getComputedStyle(el).borderTopLeftRadius || "0px";
    anims.current.forEach((a) => a.cancel());
    const a = el.animate(
      [{ clipPath: `inset(0px 0px 0px 0px round ${r})`, opacity: 1 }, { clipPath: bar ? insetOf(bar, p) : "inset(0px 0px 100% 0px round 16px)", opacity: 0.3 }],
      { duration: 260, easing: "cubic-bezier(.5,0,.75,0)", fill: "forwards" }
    );
    const b = back.current.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 260, fill: "forwards" });
    anims.current = [a, b];
    a.onfinish = done;
  }

  /* keyboard: Esc, focus trap */
  useEffect(() => {
    if (phase !== "open") return;
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); close(); }
      if (e.key === "Tab" && panel.current) {
        const f = [...panel.current.querySelectorAll("button:not([disabled]),input,a[href]")].filter((x) => x.offsetParent);
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }); // eslint-disable-line

  const term = q.trim();
  /* Eight rows, matched by the shop rather than by whatever the browser has
     already seen - which could only ever suggest what was already on screen. */
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(term), 220); return () => clearTimeout(t); }, [term]);
  const { data: sugg } = useResource(debounced ? `/search/suggest?q=${encodeURIComponent(debounced)}` : null, { enabled: !!debounced, deps: [debounced] });
  const { data: trend } = useResource("/search/trending");
  const TRENDING = useMemo(() => (trend?.trending || []).slice(0, 6), [trend]);
  const matches = useMemo(() => cards(sugg?.items), [sugg]);
  useEffect(() => { if (matches.length) absorb(matches); }, [matches]);
  const results = matches.slice(0, 8);
  /* Enter / "See all" → full results page (when the app provides one) */
  const submit = (t) => { remember(t); if (onSubmit) { close(); onSubmit(t); } };

  if (phase === "closed") return null;

  const clearPast = () => {
    if (accountHistory) api("/search/recent", { method: "DELETE" }).catch(() => {});
    setClearing(true);
    setTimeout(() => { setClearing(false); savePast([]); }, Math.min(past.length, 12) * 22 + 260);
  };
  const roll = (
    <span className="sr-roll" aria-hidden="true">
      {SEARCH_WORDS.map((w, i) => {
        const n = SEARCH_WORDS.length, cur = word % n, prev = (cur - 1 + n) % n;
        return <span key={w} data-s={i === cur ? "in" : i === prev ? "out" : ""}>{w}'</span>;
      })}
    </span>
  );

  return (
    <div className="sr-root">
      <div className="sr-back" ref={back} onClick={close} />
      <div ref={panel} className={"sr-panel" + (place?.sheet ? " sr-sheet" : "")} role="dialog" aria-modal="true" aria-label="Search"
        style={place && !place.sheet ? { left: place.x, top: place.y, width: place.w } : undefined}>
        <div className="sr-bar">
          <button className="sr-backbtn" onClick={close} aria-label="Close search"><Icon n="left" size={20} /></button>
          <label className="sr-field">
            <Icon n="search" size={18} />
            <input ref={input} type="search" value={q} placeholder=" " autoComplete="off" aria-label="Search products"
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && term) submit(term); }} />
            <span className="sr-ph">Search for '{roll}</span>
            {q && <button className="sr-clear" onClick={() => { setQ(""); input.current?.focus(); }} aria-label="Clear text"><Icon n="x" size={14} /></button>}
          </label>
          <button className="sr-esc" onClick={close} aria-label="Close search">Esc</button>
        </div>

        {!term ? (
          <div className="sr-body" key="idle">
            {past.length > 0 && (
              <section className="sr-block" style={{ "--b": 0 }}>
                <div className="sr-head"><h3>Past searches</h3><button className="sr-link" onClick={clearPast}>Clear</button></div>
                <div className={"sr-chips sr-stagger" + (clearing ? " sr-out" : "")}>
                  {past.map((t, i) => (
                    <button key={t} className="sr-chip" style={{ "--i": Math.min(i, 12) }} onClick={() => { setQ(t); input.current?.focus(); }}>
                      <Icon n="clock" size={13} />{t}
                    </button>
                  ))}
                </div>
              </section>
            )}
            <section className="sr-block" style={{ "--b": 1 }}>
              <div className="sr-head"><h3>Trending on 369 Mart</h3></div>
              <div className="sr-chips sr-stagger">
                {TRENDING.map((t, i) => (
                  <button key={t} className="sr-chip sr-trend" style={{ "--i": i }} onClick={() => { setQ(t); input.current?.focus(); }}>
                    <Icon n="trend" size={13} />{t}
                  </button>
                ))}
              </div>
            </section>
            <section className="sr-block" style={{ "--b": 2 }}>
              <div className="sr-head"><h3>Your quick picks</h3></div>
              <div className="sr-picks sr-stagger">
                {picks.map((p, i) => (
                  <article key={p.id} className="sr-pick" style={{ "--i": i }}>
                    <div className="sr-pick-img"><Thumb p={p} />
                      <div className="sr-pick-cta">
                        {p.stock === 0 ? <span className="sr-sold">Sold out</span> : <QtyControl qty={cart[p.id] || 0} id={p.id} name={p.name} onChange={(n) => setQty(p.id, n)} />}
                      </div>
                    </div>
                    <b>{p.name}</b>
                    <span className="sr-price">{money(p.price)}{p.mrp ? <s>{money(p.mrp)}</s> : null}</span>
                  </article>
                ))}
              </div>
            </section>
          </div>
        ) : (
          <div className="sr-body" key="live">
            <p className="sr-count" aria-live="polite">{results.length ? `${results.length} ${results.length === 1 ? "product" : "products"} for “${term}”` : ""}</p>
            {results.length ? (
              <ul className="sr-results" key={term}>
                {results.map((p, i) => (
                  <li key={p.id} className="sr-row" style={{ "--i": i }} data-open=""
                    onClick={(e) => {
                      if (!openProduct || e.target.closest("button")) return;
                      const r = e.currentTarget.querySelector(".sr-row-img")?.getBoundingClientRect();
                      remember(term); close(); openProduct(p, r);
                    }}>
                    <span className="sr-row-img"><Thumb p={p} /></span>
                    <span className="sr-row-txt">
                      <b><Highlight text={p.name} q={term} /></b>
                      <small>{p.unit}{p.delivery ? ` · ${p.delivery}` : " · Quick"}{p.stock === 0 ? " · out of stock" : ""}</small>
                    </span>
                    <span className="sr-row-price">{money(p.price)}</span>
                    {p.stock === 0 ? <span className="sr-sold">Sold out</span> : <QtyControl qty={cart[p.id] || 0} id={p.id} name={p.name} onChange={(n) => { remember(term); setQty(p.id, n); }} />}
                  </li>
                ))}
              </ul>
            ) : null}
            {term && onSubmit && (
              <button className="sr-all" onClick={() => submit(term)} style={{ "--i": results.length }}>
                <Icon n="search" size={15} />{matches.length ? `See all ${matches.length} results for “${term}”` : `Search 369 Mart for “${term}”`}<Icon n="right" size={15} />
              </button>
            )}
            {results.length ? null : (
              <div className="sr-empty">
                <Icon n="search" size={28} />
                <b>Nothing matches “{term}”</b>
                <span>Try “ssd”, “keyboard” or “router”.</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
