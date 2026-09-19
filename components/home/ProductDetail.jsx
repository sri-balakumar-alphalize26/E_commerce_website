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
import { Icon, OpenContext, Rail, Thumb, WishContext, flyTo, flyToCart, inr } from "./shared";
import { getDetails } from "./productDetails";
import { Crumbs } from "./Browse";
import { STAR_WORDS, fmtDate, useRemote } from "./accountStore";

const ZOOM = 2.6;

/* ---------------- gallery with thumbnails, scrolling, hover zoom ---------------- */
function DetailGallery({ p, fromRect }) {
  const imgs = p.images?.length ? p.images : p.image ? [p.image] : [null];
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
    if (!canZoom) return;
    const r = e.currentTarget.getBoundingClientRect();
    setZoom({ x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) });
  };
  const lens = 1 / ZOOM; // lens size as a fraction of the image box
  const lx = zoom ? Math.min(1 - lens, Math.max(0, zoom.x - lens / 2)) : 0;
  const ly = zoom ? Math.min(1 - lens, Math.max(0, zoom.y - lens / 2)) : 0;
  const cur = imgs[idx];

  return (
    <div className="pd-gallery">
      <div className="pd-thumbs-wrap">
        <button className="pd-tbtn pd-tup" onClick={() => scrollThumbs(-1)} disabled={thumbEdge.top} aria-label="Scroll thumbnails up"><Icon n="chev" size={16} /></button>
        <div className="pd-thumbs" ref={thumbs} onScroll={onThumbScroll} role="tablist" aria-label="Product images">
          {imgs.map((src, k) => (
            <button key={k} role="tab" aria-selected={k === idx} className={"pd-thumb" + (k === idx ? " pd-on" : "")}
              style={{ "--k": k }} onClick={() => goTo(k)} onMouseEnter={() => canZoom && goTo(k)} aria-label={`Image ${k + 1}`}>
              {src ? <img src={src} alt="" /> : <ProductArt art={p.art} color={p.color} label={p.label} />}
            </button>
          ))}
        </div>
        <button className="pd-tbtn pd-tdown" onClick={() => scrollThumbs(1)} disabled={thumbEdge.bottom} aria-label="Scroll thumbnails down"><Icon n="chev" size={16} /></button>
      </div>

      <div className="pd-stage" ref={stage}>
        <div className="pd-track" ref={track} onScroll={onScroll} tabIndex={0} aria-roledescription="carousel"
          onKeyDown={(e) => { if (e.key === "ArrowRight") goTo(idx + 1); if (e.key === "ArrowLeft") goTo(idx - 1); }}>
          {imgs.map((src, k) => (
            <div key={k} className={"pd-slide" + (k === idx ? " pd-cur" : "")} aria-label={`${k + 1} of ${imgs.length}`}
              onMouseMove={onMove} onMouseLeave={() => setZoom(null)}>
              {src ? <img src={src} alt={k === 0 ? p.name : ""} draggable="false" /> : <ProductArt art={p.art} color={p.color} label={p.label} />}
              {zoom && k === idx && <span className="pd-lens" style={{ left: `${lx * 100}%`, top: `${ly * 100}%`, width: `${lens * 100}%`, height: `${lens * 100}%` }} />}
            </div>
          ))}
        </div>
        {p.unit && <span className="pd-unit-tag">{p.unit}</span>}
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

function Section({ title, open, onToggle, children, i }) {
  return (
    <section className={"pd-sec" + (open ? " pd-open" : "")} style={{ "--i": i }}>
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
                <b className="pd-fbt-price">{inr(x.price)}{x.stock === 0 && <small> · out of stock</small>}</b>
              </div>
            </Fragment>
          ))}
        </div>
        <div className="pd-fbt-total">
          <small>Total for {chosen.length} {chosen.length === 1 ? "item" : "items"}</small>
          <span className="pd-fbt-sum"><b key={sum}>{inr(sum)}</b>{mrp > sum && <s>{inr(mrp)}</s>}</span>
          {mrp > sum && <em className="pd-fbt-save" key={"s" + sum}>You save {inr(mrp - sum)}</em>}
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
              <span className="pd-size-price">{inr(v.price)}{v.mrp ? <s>{inr(v.mrp)}</s> : null}</span>
              {v.stock === 0 ? <small className="pd-size-note">Out of stock</small> : vo ? <small className="pd-size-off">{vo}% off</small> : per ? <small className="pd-size-note">{per}</small> : <small className="pd-size-note">&nbsp;</small>}
              {cart[v.id] ? <i className="pd-size-in" aria-label={`${cart[v.id]} in cart`}>{cart[v.id]}</i> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
/* ₹ per kg / L when the size says so — helps compare packs */
function unitPrice(v) {
  const m = String(v.size || "").match(/^([\d.]+)\s*(kg|g|L|ml)$/i);
  if (!m) return "";
  const n = parseFloat(m[1]), u = m[2].toLowerCase();
  const base = u === "g" || u === "ml" ? n / 1000 : n;
  return `${inr(Math.round(v.price / base))} / ${u === "g" || u === "kg" ? "kg" : "L"}`;
}

/* ---------------- page ---------------- */
export default function ProductDetail({
  p, cart, setQty, address, onBack, onChangeAddress, onExplore, fromRect,
  related = [], variants = [], onVariant, bundle = [], similar = [], recent = [], onViewSimilar, onEditReview,
}) {
  const d = useMemo(() => getDetails(p), [p]);
  const { data: reviewData } = useRemote("/reviews");
  const myReviews = reviewData?.reviews || {};
  const mine = myReviews[p.id];
  const wish = useContext(WishContext);
  const liked = wish?.has(p.id);
  const [showAll, setShowAll] = useState(true);
  const [open, setOpen] = useState({ features: true, info: true, specs: true, desc: true, returns: true, reviews: false });
  const [fullDesc, setFullDesc] = useState(false);
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
                <button className={"pd-round" + (liked ? " pd-liked" : "")} onClick={() => wish?.toggle(p.id)} aria-pressed={!!liked} aria-label={liked ? "Remove from My List" : "Save to My List"}>
                  <Icon n={liked ? "heartFill" : "heart"} size={18} />
                </button>
                <button className="pd-round" onClick={share} aria-label="Share"><Icon n="share" size={17} /></button>
              </span>
            </div>
            <a className="pd-brand" href="#" onClick={(e) => { e.preventDefault(); onExplore?.(); }}>{d.brand}</a>
            <h1 className="pd-name" key={"n" + p.id}>{p.name}</h1>
            <button className="pd-rating" onClick={() => { setOpen((o) => ({ ...o, reviews: true })); document.getElementById("pd-reviews")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
              <b>{d.rating.toFixed(1)}</b><Stars value={d.rating} /><span>({d.ratingCount.toLocaleString("en-IN")} ratings)</span>
            </button>

            <div className="pd-price">
              <b key={"p" + p.id} className={variants.length > 1 ? "pd-roll" : undefined}>{inr(p.price)}</b>
              {p.mrp ? <><s>MRP {inr(p.mrp)}</s><em key={"o" + p.id}>{off}% OFF</em></> : <small>MRP incl. of all taxes</small>}
            </div>
            {p.low ? <p className="pd-low">Only {p.low} left — order soon</p> : null}
            {variants.length > 1 && <PackSizes p={p} variants={variants} cart={cart} onVariant={onVariant} />}

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

            <button className={"pd-toggle" + (showAll ? " pd-on" : "")} onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
              {showAll ? "Hide product details" : "Show product details"}<Icon n="chev" size={16} className="pd-chev" />
            </button>

            <div className={"pd-collapse pd-all" + (showAll ? " pd-show" : "")}>
              <div>
                <div className="pd-secs">
                  <Section i={0} title="Key features" open={open.features} onToggle={() => toggle("features")}>
                    <ul className="pd-features">{d.features.map((f, k) => <li key={k} style={{ "--k": k }}><Icon n="check" size={14} />{f}</li>)}</ul>
                  </Section>
                  <Section i={1} title="Product information" open={open.info} onToggle={() => toggle("info")}>
                    <dl className="pd-table">
                      {d.info.map(([k, v], n) => (
                        <div key={k} style={{ "--k": n }}>
                          <dt>{k}</dt>
                          <dd>{v === "veg" ? <span className="pd-veg"><i /></span> : k === "Brand" || k === "Sold by" ? <a href="#" onClick={(e) => { e.preventDefault(); onExplore?.(); }}>{v}</a> : v}</dd>
                        </div>
                      ))}
                    </dl>
                  </Section>
                  <Section i={2} title="Item specifications" open={open.specs} onToggle={() => toggle("specs")}>
                    <dl className="pd-grid">
                      {Object.entries(d.specs).map(([k, v], n) => <div key={k} style={{ "--k": n }}><dt>{k}</dt><dd>{v}</dd></div>)}
                    </dl>
                  </Section>
                  <Section i={3} title="Product description" open={open.desc} onToggle={() => toggle("desc")}>
                    <div className={"pd-desc" + (fullDesc ? " pd-full" : "")}>
                      <p>{d.description}</p>
                      <h4>Disclaimer</h4>
                      <p>{d.disclaimer}</p>
                    </div>
                    <button className="pd-more" onClick={() => setFullDesc((v) => !v)}>{fullDesc ? "Show less" : "View full description"}<Icon n="chev" size={14} className="pd-chev" /></button>
                  </Section>
                  <Section i={4} title="Return policy" open={open.returns} onToggle={() => toggle("returns")}>
                    <p className="pd-return"><Icon n={d.returnable ? "check" : "info"} size={16} />{d.returnText}</p>
                    <a className="pd-link" href="/cancellation-policy">View policy</a>
                  </Section>
                </div>
              </div>
            </div>
          </div>

          <section className="pd-card pd-reviews" id="pd-reviews">
            <button className="pd-sec-head" onClick={() => toggle("reviews")} aria-expanded={open.reviews}>
              Ratings &amp; reviews<span className="pd-mini"><b>{d.rating.toFixed(1)}</b><Icon n="star" size={13} /></span><Icon n="chev" size={18} className="pd-chev" />
            </button>
            <div className={"pd-collapse" + (open.reviews ? " pd-show" : "")}>
              <div>
                <div className="pd-rev-body">
                  <div className="pd-rev-summary">
                    <div className="pd-rev-score"><b>{d.rating.toFixed(1)}</b><Stars value={d.rating} size={16} /><small>{d.ratingCount.toLocaleString("en-IN")} ratings</small></div>
                    <div className="pd-bars">
                      {d.dist.map((pct, k) => (
                        <div key={k} className="pd-bar" style={{ "--p": pct / 100, "--k": k }}><span>{5 - k}★</span><i><em /></i><small>{pct}%</small></div>
                      ))}
                    </div>
                  </div>
                  <ul className="pd-rev-list">
                    {mine && (
                      <li className="pd-mine" style={{ "--k": 0 }}>
                        <div className="pd-rev-top"><span className={"pd-chip s" + mine.stars}>{mine.stars}★</span><b>{mine.title || STAR_WORDS[mine.stars]}</b><em>Your review</em><small>· {fmtDate(mine.at)} · Verified purchase</small></div>
                        {mine.text && <p>{mine.text}</p>}
                        {onEditReview && <button className="pd-helpful" onClick={onEditReview}>Edit in My reviews</button>}
                      </li>
                    )}
                    {d.reviews.map((r, k) => (
                      <li key={k} style={{ "--k": k }}>
                        <div className="pd-rev-top"><span className={"pd-chip s" + r.stars}>{r.stars}★</span><b>{r.name}</b><small>· {r.when} · Verified purchase</small></div>
                        <p>{r.text}</p>
                        <button className="pd-helpful" onClick={(e) => { e.currentTarget.classList.add("pd-voted"); e.currentTarget.disabled = true; }}>Helpful ({r.helpful})</button>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </section>

          <section className="pd-deliver">
            <h3>Delivery address</h3>
            <button className="pd-card pd-addr" onClick={onChangeAddress}>
              <span className="pd-addr-ic"><Icon n="pin" size={18} /></span>
              <span className="pd-addr-txt">
                <b>{address ? address.label : "Add a delivery address"}</b>
                <small>{address ? `${address.line}${address.city ? ", " + address.city : ""}` : "See delivery time and charges for your area"}</small>
                <em className={quick ? "pd-quick" : "pd-express"}><Icon n={quick ? "bolt" : "truck"} size={11} className={quick ? "hm-fill" : ""} />{quick ? "Quick delivery in 10–20 mins" : `Express delivery in ${p.delivery}`}</em>
              </span>
              <Icon n="right" size={18} />
            </button>
            <button className="pd-card pd-explore" onClick={onExplore}>
              <span className="pd-addr-ic pd-alt"><Icon n="grid" size={17} /></span>
              <span>Explore more in {d.category}</span>
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
