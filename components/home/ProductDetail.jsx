"use client";
/* ==========================================================================
   369 Mart — Product details
   Opens when a product card (or search result / cart line / My List item) is
   tapped.

   Left   vertical thumbnail strip (scrolls, up/down arrows) + main image
          (swipe / wheel / arrows / dots). Desktop hover: lens on the image and
          a magnified zoom pane on the right, like Flipkart / Amazon.
   Right  Quick/Express tag · brand · name · rating · wishlist + share ·
          price, MRP, % off · Add → stepper · "Show product details" with
          Key features, Product information, Item specifications, Description
          (view full), Return policy · ratings & reviews · delivery address.
   Pack sizes: each size is its own product; picking one swaps price, stock
          and URL in place (no reload) and the price rolls.
   Below  Frequently bought together (tick items, running total, add all) ·
          Similar products · Others you may also like · Recently viewed.

   Motion: image flies in from the tapped card (FLIP), info cascades, active
   thumbnail ring glides, slides snap, accordions ease their height, rating
   bars fill, price badge pops, wishlist heart bursts, share toast.
   ========================================================================== */
import { Fragment, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import ProductArt from "./art";
import { Icon, OpenContext, Rail, Thumb, WishContext, flyTo, flyToCart, money } from "./shared";
import { Crumbs } from "./Browse";
import { STAR_WORDS, fmtDate, useRemote } from "./accountStore";
import Lightbox, { ReviewMedia } from "./Lightbox";
import { addressText } from "@/lib/address";
import { api } from "@/lib/api";
import { toSafeHtml } from "@/lib/safeHtml";

const ZOOM = 2.6;

/* ---------------- gallery with thumbnails, scrolling, hover zoom ---------------- */
/* `p.media` is the variant's own gallery from the shop - photos and videos, its
   own before the product's (mart369 `_mart369_variant_media`); a card without
   it is drawn from its photo list as before. A video is its poster until it is
   the slide on show, then the player. */
const posterOf = (it) => (it ? (it.type === "video" ? it.poster || null : it.src) : null);

function DetailGallery({ p, fromRect }) {
  const items = useMemo(() => {
    if (p.media?.length) return p.media;
    const photos = p.images?.length ? p.images : p.image ? [p.image] : [null];
    return photos.map((src) => ({ type: "photo", src }));
  }, [p.media, p.images, p.image]);
  const imgs = items; /* kept for the counts and dots below */
  const [idx, setIdx] = useState(0);
  const [zoom, setZoom] = useState(null); // {x, y} in 0..1
  const track = useRef(null);
  const thumbs = useRef(null);
  const stage = useRef(null);
  const [thumbEdge, setThumbEdge] = useState({ top: true, bottom: false });
  const raf = useRef(0);

  /* fly in from the tapped card */
  useLayoutEffect(() => {
    const el = stage.current;
    if (!el || !fromRect || !el.animate || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const to = el.getBoundingClientRect();
    const sx = fromRect.width / to.width, sy = fromRect.height / to.height;
    el.animate(
      [{ transformOrigin: "0 0", transform: `translate(${fromRect.left - to.left}px, ${fromRect.top - to.top}px) scale(${sx}, ${sy})`, borderRadius: "14px", opacity: 0.6 },
       { transformOrigin: "0 0", transform: "none", borderRadius: "16px", opacity: 1 }],
      { duration: 520, easing: "cubic-bezier(.2,.8,.2,1)" }
    );
  }, []); // eslint-disable-line

  /* Another variant picked (a different colour): start again at its first photo. */
  const firstSrc = items[0]?.src;
  useEffect(() => {
    setIdx(0);
    track.current?.scrollTo?.({ left: 0 });
  }, [firstSrc]);

  const goTo = (n) => {
    const el = track.current;
    const next = Math.max(0, Math.min(imgs.length - 1, n));
    if (el) el.scrollTo({ left: next * el.clientWidth, behavior: "smooth" });
    setIdx(next);
    const t = thumbs.current?.children[next];
    t?.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "smooth" });
  };
  const onScroll = () => {
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => {
      const el = track.current;
      if (el) setIdx(Math.round(el.scrollLeft / Math.max(1, el.clientWidth)));
    });
  };
  const onThumbScroll = () => {
    const el = thumbs.current;
    if (!el) return;
    const vertical = el.scrollHeight > el.clientHeight + 2;
    const pos = vertical ? el.scrollTop : el.scrollLeft;
    const max = vertical ? el.scrollHeight - el.clientHeight : el.scrollWidth - el.clientWidth;
    setThumbEdge({ top: pos < 4, bottom: pos > max - 4 || max <= 0 });
  };
  useEffect(() => { onThumbScroll(); window.addEventListener("resize", onThumbScroll); return () => window.removeEventListener("resize", onThumbScroll); }, []);
  const scrollThumbs = (d) => {
    const el = thumbs.current;
    if (!el) return;
    if (el.scrollHeight > el.clientHeight + 2) el.scrollBy({ top: d * 180, behavior: "smooth" });
    else el.scrollBy({ left: d * 180, behavior: "smooth" });
  };

  /* hover zoom (fine pointers only) */
  const canZoom = typeof window !== "undefined" && window.matchMedia?.("(hover: hover) and (pointer: fine)").matches;
  const onMove = (e) => {
    if (!canZoom || items[idx]?.type === "video") return;
    const r = e.currentTarget.getBoundingClientRect();
    setZoom({ x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) });
  };
  const lens = 1 / ZOOM; // lens size as a fraction of the image box
  const lx = zoom ? Math.min(1 - lens, Math.max(0, zoom.x - lens / 2)) : 0;
  const ly = zoom ? Math.min(1 - lens, Math.max(0, zoom.y - lens / 2)) : 0;
  const cur = items[idx]?.type === "video" ? undefined : posterOf(items[idx]);

  return (
    <div className="pd-gallery">
      <div className="pd-thumbs-wrap">
        <button className="pd-tbtn pd-tup" onClick={() => scrollThumbs(-1)} disabled={thumbEdge.top} aria-label="Scroll thumbnails up"><Icon n="chev" size={16} /></button>
        <div className="pd-thumbs" ref={thumbs} onScroll={onThumbScroll} role="tablist" aria-label="Product images">
          {items.map((it, k) => (
            <button key={k} role="tab" aria-selected={k === idx} className={"pd-thumb" + (k === idx ? " pd-on" : "") + (it?.type === "video" ? " pd-thumb-video" : "")}
              style={{ "--k": k }} onClick={() => goTo(k)} onMouseEnter={() => canZoom && goTo(k)} aria-label={it?.type === "video" ? `Video ${k + 1}` : `Image ${k + 1}`}>
              {posterOf(it) ? <img src={posterOf(it)} alt="" /> : <ProductArt art={p.art} color={p.color} label={p.label} />}
              {it?.type === "video" && <span className="pd-play" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg></span>}
            </button>
          ))}
        </div>
        <button className="pd-tbtn pd-tdown" onClick={() => scrollThumbs(1)} disabled={thumbEdge.bottom} aria-label="Scroll thumbnails down"><Icon n="chev" size={16} /></button>
      </div>

      <div className="pd-stage" ref={stage}>
        <div className="pd-track" ref={track} onScroll={onScroll} tabIndex={0} aria-roledescription="carousel"
          onKeyDown={(e) => { if (e.key === "ArrowRight") goTo(idx + 1); if (e.key === "ArrowLeft") goTo(idx - 1); }}>
          {items.map((it, k) => (
            <div key={k} className={"pd-slide" + (k === idx ? " pd-cur" : "") + (it?.type === "video" ? " pd-slide-video" : "")} aria-label={`${k + 1} of ${items.length}`}
              onMouseMove={onMove} onMouseLeave={() => setZoom(null)}>
              {it?.type === "video" && k === idx ? (
                <iframe className="pd-video" src={it.src} title={`${p.name} video`} loading="lazy"
                  allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowFullScreen />
              ) : posterOf(it) ? (
                <>
                  <img src={posterOf(it)} alt={k === 0 ? p.name : ""} draggable="false" />
                  {it.type === "video" && <span className="pd-play pd-play-big" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg></span>}
                </>
              ) : <ProductArt art={p.art} color={p.color} label={p.label} />}
              {zoom && k === idx && <span className="pd-lens" style={{ left: `${lx * 100}%`, top: `${ly * 100}%`, width: `${lens * 100}%`, height: `${lens * 100}%` }} />}
            </div>
          ))}
        </div>
        {/* A real unit ("500 g", "1 L") only: Odoo's default "Units" tells a shopper nothing. */}
        {p.unit && !/^units?$/i.test(p.unit.trim()) && <span className="pd-unit-tag">{p.unit}</span>}
        {imgs.length > 1 && (
          <>
            <div className="pd-arrows">
              <button onClick={() => goTo(idx - 1)} disabled={idx === 0} aria-label="Previous image"><Icon n="left" size={16} /></button>
              <button onClick={() => goTo(idx + 1)} disabled={idx === imgs.length - 1} aria-label="Next image"><Icon n="right" size={16} /></button>
            </div>
            <div className="pd-dots">
              {imgs.map((_, k) => <button key={k} className={k === idx ? "pd-on" : ""} onClick={() => goTo(k)} aria-label={`Image ${k + 1}`} />)}
            </div>
            <span className="pd-count">{idx + 1} / {imgs.length}</span>
          </>
        )}

        {/* magnified pane — sits over the info column while hovering */}
        {zoom && cur !== undefined && (
          <div className="pd-zoom" aria-hidden="true">
            <div className="pd-zoom-inner" style={{ width: `${ZOOM * 100}%`, height: `${ZOOM * 100}%`, transform: `translate(${-lx * 100}%, ${-ly * 100}%)` }}>
              {cur ? <img src={cur} alt="" /> : <ProductArt art={p.art} color={p.color} label={p.label} />}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- building blocks ---------------- */
function Stars({ value, size = 14 }) {
  return (
    <span className="pd-stars" style={{ "--v": value / 5 }} aria-label={`${value} out of 5 stars`}>
      {[0, 1, 2, 3, 4].map((i) => <Icon key={i} n="star" size={size} />)}
      <span className="pd-stars-fill">{[0, 1, 2, 3, 4].map((i) => <Icon key={i} n="star" size={size} />)}</span>
    </span>
  );
}

/* `sec` names the band for anything that needs to find it from outside - the
   admin console draws its handles over these. An attribute rather than
   nth-of-type, because these five become conditional the moment the shop
   starts switching them off, and a positional selector would then point at
   whichever one happened to survive. */
function Section({ title, open, onToggle, children, i, sec }) {
  return (
    <section className={"pd-sec" + (open ? " pd-open" : "")} style={{ "--i": i }}
      data-sec={sec}>
      <button className="pd-sec-head" onClick={onToggle} aria-expanded={open}>{title}<Icon n="chev" size={18} className="pd-chev" /></button>
      <div className="pd-collapse"><div><div className="pd-sec-body">{children}</div></div></div>
    </section>
  );
}

/* ---------------- frequently bought together ---------------- */
function BoughtTogether({ p, items, cart, setQty }) {
  const all = [p, ...items];
  const open = useContext(OpenContext);
  const [on, setOn] = useState(() => all.map((x) => x.stock !== 0));
  const [added, setAdded] = useState(false);
  const btn = useRef(null);
  const chosen = all.filter((x, k) => on[k] && x.stock !== 0);
  const sum = chosen.reduce((s, x) => s + x.price, 0);
  const mrp = chosen.reduce((s, x) => s + (x.mrp || x.price), 0);
  const allIn = chosen.length > 0 && chosen.every((x) => cart[x.id]);
  const addAll = () => {
    const fresh = chosen.filter((x) => !cart[x.id]);
    if (!fresh.length) flyTo(btn.current);
    fresh.forEach((x, k) => setTimeout(() => flyToCart(document.querySelector(`[data-fbt="${x.id}"]`), { id: x.id }), k * 140));
    fresh.forEach((x) => setQty(x.id, 1));
    setAdded(true); setTimeout(() => setAdded(false), 1800);
  };
  return (
    <section className="pd-card pd-fbt" aria-label="Frequently bought together">
      <h2>Frequently bought together</h2>
      <div className="pd-fbt-row">
        <div className="pd-fbt-items">
          {all.map((x, k) => (
            <Fragment key={x.id}>
              {k > 0 && <span className="pd-fbt-plus" style={{ "--k": k }} aria-hidden="true"><Icon n="plus" size={16} /></span>}
              <div className={"pd-fbt-item" + (on[k] && x.stock !== 0 ? " pd-on" : "")} style={{ "--k": k }}>
                <button className="pd-fbt-img" data-fbt={x.id} onClick={() => k > 0 && open?.(x, null)} aria-label={k > 0 ? `Open ${x.name}` : x.name} tabIndex={k ? 0 : -1}><Thumb p={x} /></button>
                <label className="pd-fbt-pick">
                  <input type="checkbox" checked={!!on[k] && x.stock !== 0} disabled={x.stock === 0} onChange={() => setOn((o) => o.map((v, i) => (i === k ? !v : v)))} />
                  <span className="pd-fbt-box"><Icon n="check" size={11} /></span>
                  <span className="pd-fbt-name">{k === 0 && <em>This item · </em>}{x.name}</span>
                </label>
                <b className="pd-fbt-price">{money(x.price)}{x.stock === 0 && <small> · out of stock</small>}</b>
              </div>
            </Fragment>
          ))}
        </div>
        <div className="pd-fbt-total">
          <small>Total for {chosen.length} {chosen.length === 1 ? "item" : "items"}</small>
          <span className="pd-fbt-sum"><b key={sum}>{money(sum)}</b>{mrp > sum && <s>{money(mrp)}</s>}</span>
          {mrp > sum && <em className="pd-fbt-save" key={"s" + sum}>You save {money(mrp - sum)}</em>}
          <button ref={btn} className={"pd-add" + (added || allIn ? " pd-added" : "")} disabled={!chosen.length || allIn} onClick={addAll}>
            {added || allIn ? <><Icon n="check" size={16} />{allIn && !added ? "All in cart" : "Added"}</> : `Add ${chosen.length} to cart`}
          </button>
        </div>
      </div>
    </section>
  );
}

/* ---------------- pack size picker ---------------- */
function PackSizes({ p, variants, cart, onVariant }) {
  const row = useRef(null);
  const [ind, setInd] = useState(null);
  useLayoutEffect(() => {
    const el = row.current?.querySelector('[aria-checked="true"]');
    if (el) setInd({ x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight });
  }, [p.id]);
  return (
    <div className="pd-sizes">
      <span className="pd-sizes-label">Pack size: <b key={p.id}>{p.size}</b></span>
      <div className="pd-size-row" role="radiogroup" aria-label="Pack size" ref={row}>
        {ind && <span className="pd-size-ind" style={{ transform: `translate(${ind.x}px, ${ind.y}px)`, width: ind.w, height: ind.h }} aria-hidden="true" />}
        {variants.map((v, k) => {
          const vo = v.mrp ? Math.round(((v.mrp - v.price) / v.mrp) * 100) : 0;
          const per = unitPrice(v);
          return (
            <button key={v.id} role="radio" aria-checked={v.id === p.id} style={{ "--k": k }}
              className={"pd-size" + (v.id === p.id ? " pd-on" : "") + (v.stock === 0 ? " pd-size-oos" : "")}
              onClick={() => v.id !== p.id && onVariant?.(v)}>
              <b>{v.size}</b>
              <span className="pd-size-price">{money(v.price)}{v.mrp ? <s>{money(v.mrp)}</s> : null}</span>
              {v.stock === 0 ? <small className="pd-size-note">Out of stock</small> : vo ? <small className="pd-size-off">{vo}% off</small> : per ? <small className="pd-size-note">{per}</small> : <small className="pd-size-note">&nbsp;</small>}
              {cart[v.id] ? <i className="pd-size-in" aria-label={`${cart[v.id]} in cart`}>{cart[v.id]}</i> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
/* ---------------- variant picker ----------------
   One row per question the product asks (Brand, Processor, RAM, Colour), in
   the shop's attribute order, as the WhatsApp chat asks them. Picking a value
   keeps the other answers when that combination exists, else moves to the
   nearest variant that has the value. A value no variant has with the current
   answers is still pickable but drawn faded, so nothing is a dead end. */
/* ---------------- reviews: Helpful ---------------- */
/* Helpful, saved: one vote per customer (the shop says whether it counted).
   The public page cannot say who voted, so this browser remembers which
   reviews it has voted on. */
const VOTED_KEY = "369mart.helpful";
function useHelpful() {
  const [voted, setVoted] = useState(() => new Set());
  const [counts, setCounts] = useState({});
  const [msg, setMsg] = useState({});
  const [busy, setBusy] = useState(null);
  useEffect(() => {
    try { setVoted(new Set(JSON.parse(localStorage.getItem(VOTED_KEY) || "[]"))); } catch (e) {}
  }, []);
  const remember = (id) => setVoted((s) => {
    const next = new Set(s).add(id);
    try { localStorage.setItem(VOTED_KEY, JSON.stringify([...next].slice(-500))); } catch (e) {}
    return next;
  });
  const vote = async (id) => {
    setBusy(id);
    setMsg((m) => ({ ...m, [id]: "" }));
    try {
      const res = await api(`/reviews/${id}/vote`, { method: "POST", body: { kind: "helpful" } });
      setCounts((c) => ({ ...c, [id]: res.helpful }));
      remember(id);
      if (!res.counted) setMsg((m) => ({ ...m, [id]: "You already found this helpful." }));
    } catch (e) {
      setMsg((m) => ({ ...m, [id]: e?.status === 401 ? "Sign in to vote." : e?.message || "Couldn't save that - try again." }));
    } finally {
      setBusy(null);
    }
  };
  return {
    vote, msg, busy,
    voted: (id) => voted.has(id),
    count: (id, shown) => counts[id] ?? shown ?? 0,
  };
}

/* White, cream, light grey: a swatch that would vanish on a white page. */
function isLight(hex) {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(hex || "").trim());
  if (!m) return false;
  const h = m[1].length === 3 ? m[1].replace(/./g, "$&$&") : m[1];
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 215;
}

function VariantPicker({ p, variants, attrs, cart, onVariant }) {
  const combo = p.combo || {};
  const pick = (attrId, valueId) => {
    if (combo[attrId] === valueId) return;
    const want = { ...combo, [attrId]: valueId };
    const same = (v) => Object.entries(want).every(([a, val]) => v.combo?.[a] === val);
    const score = (v) => Object.entries(want).filter(([a, val]) => v.combo?.[a] === val).length;
    const next = variants.find(same)
      || variants.filter((v) => v.combo?.[attrId] === valueId).sort((a, b) => score(b) - score(a))[0];
    if (next && next.id !== p.id) onVariant?.(next);
  };
  const exists = (attrId, valueId) => variants.some((v) => v.combo?.[attrId] === valueId
    && Object.entries(combo).every(([a, val]) => a === attrId || v.combo?.[a] === val));
  const stockOf = (attrId, valueId) => variants.find((v) => v.combo?.[attrId] === valueId
    && Object.entries(combo).every(([a, val]) => a === attrId || v.combo?.[a] === val));
  return (
    <div className="pd-vars">
      {attrs.map((a) => {
        const current = a.values.find((v) => v.id === combo[a.id]);
        /* A colour (display "color", or an attribute called Colour) draws
           cards when its colours have pictures of their own. */
        const cards = (a.display === "color" || /^colou?r$/i.test(a.name || ""))
          && variants.some((x) => x.images?.length);
        return (
          <div className="pd-sizes pd-var" key={a.id}>
            <span className="pd-sizes-label">{a.name}: <b key={current?.id}>{current?.name || "Choose"}</b></span>
            <div className={cards ? "pd-var-row pd-var-cards" : "pd-var-row"} role="radiogroup" aria-label={a.name}>
              {a.values.map((v) => {
                const on = v.id === combo[a.id];
                const there = exists(a.id, v.id);
                const match = stockOf(a.id, v.id);
                const oos = there && match?.stock === 0;
                /* A colour attribute (display "color") with a colour set is a
                   round swatch, its name in the row's label and the tooltip;
                   one without a colour stays a named button. */
                const swatch = a.display === "color" && v.color;
                const tip = !there ? `${v.name}: not with these choices` : oos ? `${v.name}: out of stock` : v.name;
                if (cards) {
                  /* Amazon's colour cards: that colour's own picture and price. */
                  const shown = match || variants.find((x) => x.combo?.[a.id] === v.id);
                  const pic = shown?.images?.[0];
                  return (
                    <button key={v.id} role="radio" aria-checked={on} title={tip}
                      className={"pd-var-card" + (on ? " pd-on" : "") + (!there ? " pd-var-none" : "") + (oos ? " pd-size-oos" : "")}
                      onClick={() => pick(a.id, v.id)}>
                      <span className="pd-var-card-img">
                        {pic ? <img src={pic} alt="" loading="lazy" />
                          : <i className="pd-swatch-dot" style={{ background: v.color || "#e8edf1" }} aria-hidden="true" />}
                      </span>
                      <span className="pd-var-card-name">{v.name}</span>
                      {shown?.price != null && <b className="pd-var-card-price">{money(shown.price)}</b>}
                      {on && cart[p.id] ? <i className="pd-size-in" aria-label={`${cart[p.id]} in cart`}>{cart[p.id]}</i> : null}
                    </button>
                  );
                }
                return (
                  <button key={v.id} role="radio" aria-checked={on} aria-label={swatch ? tip : undefined}
                    className={"pd-var-opt" + (on ? " pd-on" : "") + (!there ? " pd-var-none" : "") + (oos ? " pd-size-oos" : "") + (swatch ? " pd-var-swatch" + (isLight(v.color) ? " pd-swatch-light" : "") : "")}
                    title={tip}
                    onClick={() => pick(a.id, v.id)}>
                    {swatch ? <i className="pd-swatch-dot" style={{ background: v.color }} aria-hidden="true" /> : <span>{v.name}</span>}
                    {on && cart[p.id] ? <i className="pd-size-in" aria-label={`${cart[p.id]} in cart`}>{cart[p.id]}</i> : null}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* The short table under the options: the product's own Product details,
   then the chosen variant's specs - a variant row with the same label wins,
   so "Colour" follows the colour picked. */
function keyDetails(rows, specs) {
  const out = new Map((rows || []).map(([k, v]) => [k, v]));
  Object.entries(specs || {}).forEach(([k, v]) => { if (v) out.set(k, v); });
  return [...out.entries()];
}

function KeyDetails({ rows }) {
  if (!rows.length) return null;
  return (
    <table className="pd-keys">
      <tbody>{rows.slice(0, 6).map(([k, v]) => <tr key={k}><th scope="row">{k}</th><td>{v}</td></tr>)}</tbody>
    </table>
  );
}

/* "About this item": the bold lead, then the rest. Five, then Show more. */
function AboutItem({ points }) {
  const [all, setAll] = useState(false);
  if (!points.length) return null;
  const shown = all ? points : points.slice(0, 5);
  return (
    <section className="pd-about" aria-labelledby="pd-about-h">
      <h2 id="pd-about-h">About this item</h2>
      <ul>{shown.map((pt, k) => <li key={k}>{pt.lead ? <><b>{pt.lead}</b> — </> : null}{pt.text}</li>)}</ul>
      {points.length > 5 && (
        <button className="pd-link pd-about-more" onClick={() => setAll((v) => !v)} aria-expanded={all}>
          {all ? "Show less" : `Show more (${points.length - 5})`}<Icon n="chev" size={14} className={all ? "pd-chev pd-up" : "pd-chev"} />
        </button>
      )}
    </section>
  );
}

/* ₹ per kg / L when the size says so — helps compare packs */
function unitPrice(v) {
  const m = String(v.size || "").match(/^([\d.]+)\s*(kg|g|L|ml)$/i);
  if (!m) return "";
  const n = parseFloat(m[1]), u = m[2].toLowerCase();
  const base = u === "g" || u === "ml" ? n / 1000 : n;
  return `${money(Math.round(v.price / base))} / ${u === "g" || u === "kg" ? "kg" : "L"}`;
}

/* ---------------- page ---------------- */
export default function ProductDetail({
  p, cart, setQty, address, onBack, onChangeAddress, onExplore, fromRect,
  related = [], variants = [], attrs = [], onVariant, bundle = [], similar = [], recent = [], onViewSimilar, onEditReview,
  optionsFailed = false, onRetryOptions, reviewInfo, info, about = [], details = [],
}) {
  /* Every product shows what its setup holds, as the WhatsApp confirmation
     page does: its photos, the Variant specs table and the Sales Description
     (PRODUCT_SETUP_FLOW.md) - plus the website's own real reviews. Nothing is
     made up: an empty table or description is simply not drawn. (getDetails()
     used to fill every gap with sample text - features, a manufacturer
     address, thousands of invented ratings.) */
  const senior = true;
  const d = useMemo(() => {
    const rv = reviewInfo || {};
    const count = rv.ratingCount ?? p.ratingCount ?? 0;
    return {
      /* A real Brand spec only: the listing's p.brand falls back to the unit
         ("Units"), which is no brand to print above the name. */
      brand: p.specs?.Brand || "",
      category: p.subName || p.catName || "",
      /* enrich() invents a rating for sorting; only real reviews count here. */
      rating: count ? (rv.rating ?? p.rating ?? null) : null,
      ratingCount: count,
      dist: rv.dist || [0, 0, 0, 0, 0],
      features: [],
      info: info || [],
      specs: p.specs || {},
      description: p.description || "",
      descriptionHtml: p.descriptionHtml || "",
      disclaimer: "",
      returnText: "",
      reviews: rv.list || [],
    };
  }, [p, reviewInfo, info]);
  const { data: reviewData } = useRemote("/reviews");
  const myReviews = reviewData?.reviews || {};
  /* Reviews and the wishlist belong to the product, not to one colour of it. */
  const ownId = p.variantGroup || p.id;
  const mine = myReviews[ownId];
  const wish = useContext(WishContext);
  const liked = wish?.has(ownId);
  const [showAll, setShowAll] = useState(true);
  const [open, setOpen] = useState({ features: true, info: true, specs: true, desc: true, returns: true, reviews: false });
  const [fullDesc, setFullDesc] = useState(false);
  /* The eCommerce Description's own formatting, made safe in the browser
     (lib/safeHtml.js); until then - and on the server - its plain text. */
  const [richDesc, setRichDesc] = useState(null);
  useEffect(() => setRichDesc(toSafeHtml(d.descriptionHtml)), [d.descriptionHtml]);
  const [viewer, setViewer] = useState(null); /* {items, start} for the review photo viewer */
  const helpful = useHelpful();
  const [toast, setToast] = useState("");
  const addBtn = useRef(null);
  const qty = cart[p.id] || 0;
  const off = p.mrp ? Math.round(((p.mrp - p.price) / p.mrp) * 100) : 0;
  const oos = p.stock === 0;
  const quick = !p.delivery;

  const group = p.variantGroup || p.id;
  useEffect(() => { window.scrollTo({ top: 0 }); }, [group]);
  const flash = (m) => { setToast(m); clearTimeout(flash.t); flash.t = setTimeout(() => setToast(""), 2200); };
  const share = async () => {
    const url = typeof location !== "undefined" ? location.origin + "/product/" + p.id : "";
    try {
      if (navigator.share) { await navigator.share({ title: p.name, url }); return; }
      await navigator.clipboard.writeText(url); flash("Link copied");
    } catch (e) { flash("Couldn't share — copy the address bar link instead"); }
  };
  const toggle = (k) => setOpen((o) => ({ ...o, [k]: !o[k] }));
  /* Nothing typed for this product: no toggle that opens onto an empty panel. */
  const hasDetails = d.features.length > 0 || d.info.length > 0 || Object.keys(d.specs).length > 0
    || !!d.description || !!d.returnText;

  return (
    <div className="pd-page" key={group}>
      {/* where this product sits in the catalogue: Home › category › subcategory › product */}
      <Crumbs items={[
        ["Home", ["home"]],
        ...(p.catName ? [[p.catName, ["category", p.cat]]] : []),
        ...(p.subName ? [[p.subName, ["category", `${p.cat}/${p.sub}`]]] : []),
        [p.name, null],
      ]} />
      <div className="pd-top">
        <DetailGallery p={p} fromRect={fromRect} />

        <div className="pd-info">
          <div className="pd-card pd-buy">
            <div className="pd-row pd-crumbs">
              <button className="pd-back" onClick={onBack}><Icon n="left" size={16} />Back</button>
              <span className={"pd-mode " + (quick ? "pd-quick" : "pd-express")}>
                <Icon n={quick ? "bolt" : "truck"} size={12} className={quick ? "hm-fill" : ""} />{quick ? "Quick · 10–20 mins" : `Express · ${p.delivery}`}
              </span>
              <span className="pd-actions">
                <button className={"pd-round" + (liked ? " pd-liked" : "")} onClick={() => wish?.toggle(ownId)} aria-pressed={!!liked} aria-label={liked ? "Remove from My List" : "Save to My List"}>
                  <Icon n={liked ? "heartFill" : "heart"} size={18} />
                </button>
                <button className="pd-round" onClick={share} aria-label="Share"><Icon n="share" size={17} /></button>
              </span>
            </div>
            {d.brand ? <a className="pd-brand" href="#" onClick={(e) => { e.preventDefault(); onExplore?.(); }}>{d.brand}</a> : null}
            <h1 className="pd-name" key={"n" + p.id}>{p.name}</h1>
            {d.rating != null && (
              <button className="pd-rating" onClick={() => { setOpen((o) => ({ ...o, reviews: true })); document.getElementById("pd-reviews")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
                <b>{d.rating.toFixed(1)}</b><Stars value={d.rating} /><span>({d.ratingCount.toLocaleString("en-IN")} ratings)</span>
              </button>
            )}

            <div className="pd-price">
              <b key={"p" + p.id} className={variants.length > 1 ? "pd-roll" : undefined}>{money(p.price)}</b>
              {p.mrp ? <><s>MRP {money(p.mrp)}</s><em key={"o" + p.id}>{off}% OFF</em></> : <small>MRP incl. of all taxes</small>}
            </div>
            {p.low ? <p className="pd-low">Only {p.low} left — order soon</p> : null}
            {attrs.length > 0 && variants.length > 1
              ? <VariantPicker p={p} variants={variants} attrs={attrs} cart={cart} onVariant={onVariant} />
              : variants.length > 1 && <PackSizes p={p} variants={variants} cart={cart} onVariant={onVariant} />}
            {p.hasVariants && !variants.length && (optionsFailed
              ? <p className="pd-var-wait">Couldn't load the options. <button className="pd-link" onClick={onRetryOptions}>Try again</button></p>
              : <p className="pd-var-wait">Loading the options…</p>)}

            <div className="pd-cta">
              {oos ? (
                <button className="pd-notify" onClick={() => flash("We'll notify you when it's back")}><Icon n="bell" size={16} />Notify me</button>
              ) : qty === 0 ? (
                <button ref={addBtn} className="pd-add" onClick={() => { flyToCart(addBtn.current.closest(".pd-page")?.querySelector(".pd-stage"), { id: p.id }); setQty(p.id, 1); }}>Add to cart</button>
              ) : (
                <div className="pd-stepper" role="group" aria-label="Quantity">
                  <button onClick={() => setQty(p.id, qty - 1)} aria-label="Remove one">−</button>
                  <span key={qty}>{qty} in cart</span>
                  <button onClick={() => setQty(p.id, Math.min(12, qty + 1))} aria-label="Add one">+</button>
                </div>
              )}
            </div>

            <KeyDetails rows={keyDetails(details, p.specs)} />
            <AboutItem points={about || []} />

            {hasDetails && <>
            <button className={"pd-toggle" + (showAll ? " pd-on" : "")} onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
              {showAll ? "Hide product details" : "Show product details"}<Icon n="chev" size={16} className="pd-chev" />
            </button>

            <div className={"pd-collapse pd-all" + (showAll ? " pd-show" : "")}>
              <div>
                <div className="pd-secs">
                  {d.features.length > 0 && <Section i={0} sec="features" title="Key features" open={open.features} onToggle={() => toggle("features")}>
                    <ul className="pd-features">{d.features.map((f, k) => <li key={k} style={{ "--k": k }}><Icon n="check" size={14} />{f}</li>)}</ul>
                  </Section>}
                  {d.info.length > 0 && <Section i={1} sec="info" title="Product information" open={open.info} onToggle={() => toggle("info")}>
                    <dl className="pd-table">
                      {d.info.map(([k, v], n) => (
                        <div key={k} style={{ "--k": n }}>
                          <dt>{k}</dt>
                          <dd>{k === "Brand" || k === "Sold by" ? <a href="#" onClick={(e) => { e.preventDefault(); onExplore?.(); }}>{v}</a> : v}</dd>
                        </div>
                      ))}
                    </dl>
                  </Section>}
                  {Object.keys(d.specs).length > 0 && <Section i={2} sec="specs" title="Item specifications" open={open.specs} onToggle={() => toggle("specs")}>
                    <dl className="pd-grid">
                      {Object.entries(d.specs).map(([k, v], n) => <div key={k} style={{ "--k": n }}><dt>{k}</dt><dd>{v}</dd></div>)}
                    </dl>
                  </Section>}
                  {(d.description || d.descriptionHtml) && <Section i={3} sec="description" title="Product description" open={open.desc} onToggle={() => toggle("desc")}>
                    <div className={"pd-desc" + (fullDesc || senior ? " pd-full" : "")}>
                      {richDesc ? <div className="pd-rich" dangerouslySetInnerHTML={{ __html: richDesc }} /> : <p>{d.description}</p>}
                      {d.disclaimer && <><h4>Disclaimer</h4><p>{d.disclaimer}</p></>}
                    </div>
                    {!senior && <button className="pd-more" onClick={() => setFullDesc((v) => !v)}>{fullDesc ? "Show less" : "View full description"}<Icon n="chev" size={14} className="pd-chev" /></button>}
                  </Section>}
                  {d.returnText && <Section i={4} sec="returns" title="Return policy" open={open.returns} onToggle={() => toggle("returns")}>
                    <p className="pd-return"><Icon n={d.returnable ? "check" : "info"} size={16} />{d.returnText}</p>
                    <a className="pd-link" href="/cancellation-policy">View policy</a>
                  </Section>}
                </div>
              </div>
            </div>
            </>}
          </div>

          {(d.rating != null || mine) && <section className="pd-card pd-reviews" id="pd-reviews">
            <button className="pd-sec-head" onClick={() => toggle("reviews")} aria-expanded={open.reviews}>
              Ratings &amp; reviews{d.rating != null && <span className="pd-mini"><b>{d.rating.toFixed(1)}</b><Icon n="star" size={13} /></span>}<Icon n="chev" size={18} className="pd-chev" />
            </button>
            <div className={"pd-collapse" + (open.reviews ? " pd-show" : "")}>
              <div>
                <div className="pd-rev-body">
                  {d.rating != null && <div className="pd-rev-summary">
                    <div className="pd-rev-score"><b>{d.rating.toFixed(1)}</b><Stars value={d.rating} size={16} /><small>{d.ratingCount.toLocaleString("en-IN")} ratings</small></div>
                    <div className="pd-bars">
                      {d.dist.map((pct, k) => (
                        <div key={k} className="pd-bar" style={{ "--p": pct / 100, "--k": k }}><span>{5 - k}★</span><i><em /></i><small>{pct}%</small></div>
                      ))}
                    </div>
                  </div>}
                  <ul className="pd-rev-list">
                    {mine && (
                      <li className="pd-mine" style={{ "--k": 0 }}>
                        <div className="pd-rev-top"><span className={"pd-chip s" + mine.stars}>{mine.stars}★</span><b className="pd-rev-title">{mine.title || STAR_WORDS[mine.stars]}</b><em>Your review</em></div>
                        <small className="pd-rev-meta">{fmtDate(mine.at)}{mine.verified && <> · <span className="pd-verified">Verified purchase</span></>}</small>
                        {mine.text && <p>{mine.text}</p>}
                        <ReviewMedia media={mine.media} own onOpen={setViewer} />
                        {mine.reply && <p className="pd-reply"><b>Reply from 369 Mart</b>{mine.reply}</p>}
                        {onEditReview && <button className="pd-helpful" onClick={onEditReview}>Edit in My reviews</button>}
                      </li>
                    )}
                    {d.reviews.map((r, k) => (
                      <li key={r.id ?? k} style={{ "--k": k }}>
                        <div className="pd-rev-top"><span className={"pd-chip s" + r.stars}>{r.stars}★</span><b className="pd-rev-title">{r.title || STAR_WORDS[r.stars]}</b></div>
                        <small className="pd-rev-meta">{r.name} · {r.when}{r.verified && <> · <span className="pd-verified">Verified purchase</span></>}</small>
                        {r.text && <p>{r.text}</p>}
                        <ReviewMedia media={r.media} onOpen={setViewer} />
                        {r.reply && <p className="pd-reply"><b>Reply from 369 Mart</b>{r.reply}</p>}
                        {r.id != null && (
                          <>
                            <button className={"pd-helpful" + (helpful.voted(r.id) ? " pd-voted" : "")} disabled={helpful.voted(r.id) || helpful.busy === r.id}
                              onClick={() => helpful.vote(r.id)}>Helpful ({helpful.count(r.id, r.helpful)})</button>
                            {helpful.msg[r.id] && <span className="pd-vote-msg" role="status">{helpful.msg[r.id]}</span>}
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
            {viewer && <Lightbox items={viewer.items} start={viewer.start} onClose={() => setViewer(null)} />}
          </section>}

          <section className="pd-deliver">
            <h3>Delivery address</h3>
            <button className="pd-card pd-addr" onClick={onChangeAddress}>
              <span className="pd-addr-ic"><Icon n="pin" size={18} /></span>
              <span className="pd-addr-txt">
                <b>{address ? address.label : "Add a delivery address"}</b>
                <small>{address ? addressText(address) : "See delivery time and charges for your area"}</small>
                <em className={quick ? "pd-quick" : "pd-express"}><Icon n={quick ? "bolt" : "truck"} size={11} className={quick ? "hm-fill" : ""} />{quick ? "Quick delivery in 10–20 mins" : `Express delivery in ${p.delivery}`}</em>
              </span>
              <Icon n="right" size={18} />
            </button>
            <button className="pd-card pd-explore" onClick={onExplore}>
              <span className="pd-addr-ic pd-alt"><Icon n="grid" size={17} /></span>
              <span>Explore more{d.category ? ` in ${d.category}` : ""}</span>
              <Icon n="right" size={18} />
            </button>
          </section>
        </div>
      </div>

      {bundle.length > 0 && <BoughtTogether key={"fbt-" + p.id} p={p} items={bundle} cart={cart} setQty={setQty} />}

      {similar.length > 0 && (
        <div className="pd-related">
          <Rail section={{ key: "pd-sim-" + group, title: "Similar products", subtitle: p.subName ? `More in ${p.subName}` : "", items: similar }} cart={cart} setQty={setQty} onViewAll={onViewSimilar} />
        </div>
      )}
      {related.length > 0 && (
        <div className="pd-related">
          <Rail section={{ key: "pd-rel-" + group, title: "Others you may also like", items: related }} cart={cart} setQty={setQty} />
        </div>
      )}
      {recent.length > 0 && (
        <div className="pd-related">
          <Rail section={{ key: "pd-recent", title: "Recently viewed", items: recent }} cart={cart} setQty={setQty} />
        </div>
      )}

      <div className={"pd-toast" + (toast ? " pd-show" : "")} role="status" aria-live="polite">{toast}</div>
    </div>
  );
}
