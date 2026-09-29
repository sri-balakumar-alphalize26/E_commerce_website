"use client";
/* ==========================================================================
   369 Mart admin — a category's logo

   Two sizes, because the app draws the two levels differently:

   - a **main category**'s logo is the small mark beside its name on the pill
     in the top bar - 18px, so it has to read as a shape;
   - a **sub-category**'s fills its whole tile - 104px on the home page,
     88px on the category page.

   Either is one the app draws itself (built-in) or an uploaded picture,
   which wins. An upload always goes through the cropper: a square, shown at
   the size the shopper will see it, saved at a fixed size (128 or 512 px) -
   so what is picked here is what the app shows.

   No crop library: the whole job is one drawImage onto a canvas.

   The Odoo desk has the same field (mart369_catalog/static/src/desk), and
   both write the same three values: mart_icon, mart_art, mart_logo.
   ========================================================================== */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ProductArt from "@/components/home/art";
import { Icon as ShopIcon } from "@/components/home/shared";
import { Icon } from "./AdminUI";
import "./logo.css";

/* The built-in logos. Kept in step with ICON_CHOICES and ART_CHOICES in
   odoo_modules/mart369/models/serializers.py - the server refuses anything
   else. */
export const LOGO_ICONS = [
  ["keyboard", "Keyboard"], ["plug", "Plug"], ["wifi", "Wi-Fi"], ["cpu", "Chip"],
  ["laptop", "Laptop"], ["monitor", "Monitor"], ["ticket", "Ticket"], ["grid", "Grid"],
  ["bolt", "Lightning"], ["bag", "Bag"], ["basket", "Basket"], ["leaf", "Leaf"],
  ["pot", "Pot"], ["pen", "Pen"], ["shirt", "Shirt"], ["book", "Book"],
];
export const LOGO_ART = [
  ["Keyboard", "Keyboard"], ["Mouse", "Mouse"], ["Headphones", "Headphones"], ["Webcam", "Webcam"],
  ["Monitor", "Monitor"], ["Laptop", "Laptop"], ["Cabinet", "PC case"], ["Cpu", "Processor"],
  ["Gpu", "Graphics card"], ["Motherboard", "Motherboard"], ["Ram", "Memory"], ["Ssd", "Storage"],
  ["Psu", "Power supply"], ["Cooler", "Cooler"], ["Router", "Router"], ["Adapter", "Adapter"],
  ["Cable", "Cable"], ["Charger", "Charger"], ["Speaker", "Speaker"], ["Lamp", "Lamp"],
  ["Box", "Box"], ["Pack", "Pack"], ["Bottle", "Bottle"], ["Jar", "Jar"],
  ["Bar", "Chocolate"], ["Basket", "Basket"], ["Apple", "Apple"], ["Banana", "Banana"],
  ["Orange", "Orange"], ["Grapes", "Grapes"], ["Pomegranate", "Pomegranate"], ["Tomato", "Tomato"],
  ["Onion", "Onion"], ["Leafy", "Leafy greens"], ["Soap", "Soap bottle"], ["SoapBar", "Soap bar"],
  ["Towels", "Towels"], ["Plates", "Plates"], ["Flask", "Flask"], ["Board", "Chopping board"],
];

/* What each level is drawn at, and saved as. */
export const LOGO_SIZES = {
  main: {
    out: 128, min: 128,
    hint: "Shown at 18 × 18 px beside the name on the top bar. Use a simple, bold mark - a PNG with a transparent background reads best. Saved as 128 × 128.",
  },
  sub: {
    out: 512, min: 512,
    hint: "Fills the whole tile - 104 × 104 px on the home page, 88 × 88 on the category page. Use a picture at least 512 × 512. Saved as 512 × 512.",
  },
};

const readFile = (file) => new Promise((ok, bad) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result));
  r.onerror = () => bad(r.error);
  r.readAsDataURL(file);
});

/* The logo as drawn: the picture, else the built-in one. */
export function LogoMark({ level, icon, art, image, color, size = 20 }) {
  if (image) return <img className="lf-mark-img" src={image} alt="" style={{ width: size, height: size }} />;
  if (level === "main") return <ShopIcon n={icon || "grid"} size={size} />;
  return <span className="lf-mark-art" style={{ width: size, height: size }}><ProductArt art={art || "Box"} color={color} /></span>;
}

/* value: { icon, art, image } - image is the picture's address, a fresh
   data: URL from the cropper, or "" for none.
   onChange gets the fields to send: { mart_icon } / { mart_art } /
   { mart_logo: dataUrl | false }. */
export function LogoField({ level, value, name, tone, accent, onChange }) {
  const size = LOGO_SIZES[level];
  const [pane, setPane] = useState(value.image ? "upload" : "builtin");
  const [source, setSource] = useState(null);
  const [fileError, setFileError] = useState("");
  const input = useRef(null);
  const builtIn = level === "main" ? LOGO_ICONS : LOGO_ART;
  const current = level === "main" ? value.icon : value.art;

  const pickFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    setFileError("");
    if (!file) return;
    if (!/^image\/(png|jpe?g|webp|gif|svg\+xml)$/.test(file.type)) { setFileError("Choose a PNG, JPEG, WebP, GIF or SVG picture."); return; }
    if (file.size > 15 * 1024 * 1024) { setFileError("That file is over 15 MB. Choose a smaller one."); return; }
    try { setSource(await readFile(file)); } catch { setFileError("That file could not be read."); }
  };

  return (
    <div className="ad-field ad-span2 lf">
      <span>Logo<em>{level === "main" ? "The small mark on its pill in the top bar" : "Fills its tile on the home page and its circle on the category page"}</em></span>

      <div className="lf-seg" role="tablist" aria-label="Where the logo comes from">
        {[["builtin", "Built-in"], ["upload", "Upload your own"]].map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={pane === k} className={pane === k ? "ad-on" : ""}
            onClick={() => setPane(k)}>{label}</button>
        ))}
      </div>

      {pane === "builtin" ? (
        <>
          {value.image && <p className="lf-note"><Icon n="info" size={13} />An uploaded picture is in use. Picking one here replaces it.</p>}
          <div className={"lf-grid lf-grid-" + level} role="listbox" aria-label="Built-in logos">
            {builtIn.map(([k, label]) => {
              const on = !value.image && current === k;
              return (
                <button key={k} type="button" role="option" aria-selected={on} title={label}
                  className={on ? "ad-on" : ""} style={{ "--tone": tone, "--accent": accent }}
                  onClick={() => onChange({ [level === "main" ? "mart_icon" : "mart_art"]: k, ...(value.image ? { mart_logo: false } : {}) })}>
                  {level === "main" ? <ShopIcon n={k} size={20} /> : <span className="lf-art"><ProductArt art={k} color={accent} /></span>}
                  <small>{label}</small>
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <div className="lf-upload">
          <span className={"lf-up-prev lf-up-" + level} style={{ "--tone": tone, "--accent": accent }}>
            {value.image
              ? <img src={value.image} alt="The uploaded logo" />
              : <Icon n="camera" size={22} />}
          </span>
          <div className="lf-up-body">
            <p className="lf-size"><b>{level === "main" ? "Small: 18 × 18 px" : "Full tile: 104 × 104 px"}</b>{size.hint}</p>
            <div className="lf-up-btns">
              <button type="button" className="ad-btn ad-sm" onClick={() => input.current?.click()}>
                <Icon n="up" size={13} />{value.image ? "Replace" : "Choose a picture"}
              </button>
              {value.image && <button type="button" className="ad-btn ad-sm" onClick={() => onChange({ mart_logo: false })}>Remove</button>}
            </div>
            {fileError && <small className="ad-form-error">{fileError}</small>}
          </div>
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml" hidden onChange={pickFile} />
        </div>
      )}

      {source && (
        <LogoCropper src={source} level={level} name={name} tone={tone} accent={accent}
          onCancel={() => setSource(null)}
          onDone={(dataUrl) => { setSource(null); setPane("upload"); onChange({ mart_logo: dataUrl }); }} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------ the cropper */

const VIEW = 280; // the crop square, in CSS px
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/* Where the picture sits in the square: its scale and top-left corner. A
   picture bigger than the square cannot leave a gap; a smaller one (zoomed
   out to fit a whole logo) stays inside it. */
function place(img, scale, x, y) {
  const w = img.w * scale, h = img.h * scale;
  return {
    scale,
    x: clamp(x, Math.min(0, VIEW - w), Math.max(0, VIEW - w)),
    y: clamp(y, Math.min(0, VIEW - h), Math.max(0, VIEW - h)),
  };
}

export function LogoCropper({ src, level, name, tone, accent, onCancel, onDone }) {
  const size = LOGO_SIZES[level];
  const [img, setImg] = useState(null);
  const [view, setView] = useState(null);
  const [error, setError] = useState("");
  const drag = useRef(null);
  const el = useRef(null);

  useEffect(() => {
    const i = new Image();
    i.onload = () => {
      const w = i.naturalWidth || 512, h = i.naturalHeight || 512;
      const pic = { el: i, w, h, fit: Math.min(VIEW / w, VIEW / h), fill: Math.max(VIEW / w, VIEW / h) };
      setImg(pic);
      /* A small mark starts whole; a tile starts filled, edge to edge. */
      const s = level === "main" ? pic.fit : pic.fill;
      setView(place(pic, s, (VIEW - w * s) / 2, (VIEW - h * s) / 2));
    };
    i.onerror = () => setError("That picture could not be opened.");
    i.src = src;
  }, [src, level]);

  /* Escape closes the cropper, not the drawer behind it. */
  useEffect(() => {
    const k = (e) => { if (e.key === "Escape") { e.stopImmediatePropagation(); onCancel(); } };
    window.addEventListener("keydown", k, true);
    return () => window.removeEventListener("keydown", k, true);
  }, [onCancel]);

  const minScale = img ? img.fit : 1;
  const maxScale = img ? img.fill * 4 : 1;

  /* Zoom about the middle of the square, so the part being looked at stays put. */
  const zoomTo = (s) => setView((v) => {
    if (!v || !img) return v;
    const next = clamp(s, minScale, maxScale);
    const cx = (VIEW / 2 - v.x) / v.scale, cy = (VIEW / 2 - v.y) / v.scale;
    return place(img, next, VIEW / 2 - cx * next, VIEW / 2 - cy * next);
  });

  const down = (e) => {
    if (!view) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const r = el.current.getBoundingClientRect();
    drag.current = { px: e.clientX, py: e.clientY, x: view.x, y: view.y, k: VIEW / r.width };
  };
  const move = (e) => {
    const d = drag.current;
    if (!d) return;
    setView((v) => place(img, v.scale, d.x + (e.clientX - d.px) * d.k, d.y + (e.clientY - d.py) * d.k));
  };
  const up = () => { drag.current = null; };
  const wheel = (e) => { if (view) zoomTo(view.scale * (e.deltaY < 0 ? 1.08 : 1 / 1.08)); };
  const key = (e) => {
    const step = e.shiftKey ? 20 : 4;
    const by = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
    if (by) { e.preventDefault(); setView((v) => place(img, v.scale, v.x + by[0], v.y + by[1])); }
    if (e.key === "+" || e.key === "=") zoomTo(view.scale * 1.1);
    if (e.key === "-") zoomTo(view.scale / 1.1);
  };

  const save = () => {
    const n = size.out, k = n / VIEW;
    const canvas = document.createElement("canvas");
    canvas.width = n; canvas.height = n;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img.el, view.x * k, view.y * k, img.w * view.scale * k, img.h * view.scale * k);
    try { onDone(canvas.toDataURL("image/png")); }
    catch { setError("That picture could not be cropped here. Save it as a PNG or JPEG and try again."); }
  };

  /* The same framing, drawn at another size - for the previews. */
  const shot = (px) => {
    if (!view) return null;
    const k = px / VIEW;
    return <img src={src} alt="" draggable={false}
      style={{ left: view.x * k, top: view.y * k, width: img.w * view.scale * k, height: img.h * view.scale * k }} />;
  };

  const small = img && Math.min(img.w, img.h) < size.min;
  const pct = view ? Math.round(((view.scale - minScale) / (maxScale - minScale || 1)) * 100) : 0;

  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="ad-modal-wrap lf-crop-wrap" onClick={(e) => { e.stopPropagation(); onCancel(); }}>
      <section className="lf-crop" role="dialog" aria-modal="true" aria-label="Crop the logo" onClick={(e) => e.stopPropagation()}>
        <header>
          <div><h3>Crop the logo</h3>
            <small>{level === "main" ? "Main category - a small mark on the top bar" : "Sub-category - fills the whole tile"}</small></div>
          <button type="button" className="ad-icon-btn" onClick={onCancel} aria-label="Close"><Icon n="x" size={17} /></button>
        </header>

        <div className="lf-crop-body">
          <div className="lf-crop-left">
            <div ref={el} className={"lf-stage lf-stage-" + level} tabIndex={0} aria-label="Drag to move the picture. Arrow keys move it, plus and minus zoom."
              style={{ "--tone": tone }}
              onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onWheel={wheel} onKeyDown={key}>
              {shot(VIEW)}
              {/* The rounded corners the app clips a tile to, and thirds to line things up by. */}
              <i className="lf-guide" aria-hidden="true" />
            </div>
            <label className="lf-zoom">
              <span className="lf-zoom-sign" aria-hidden="true">−</span>
              <input type="range" min={0} max={100} value={pct} aria-label="Zoom"
                onChange={(e) => zoomTo(minScale + (Number(e.target.value) / 100) * (maxScale - minScale))} />
              <Icon n="plus" size={14} />
            </label>
            <div className="lf-crop-quick">
              <button type="button" className="ad-link" onClick={() => img && setView(place(img, img.fit, (VIEW - img.w * img.fit) / 2, (VIEW - img.h * img.fit) / 2))}>Show it all</button>
              <button type="button" className="ad-link" onClick={() => img && setView(place(img, img.fill, (VIEW - img.w * img.fill) / 2, (VIEW - img.h * img.fill) / 2))}>Fill the square</button>
            </div>
          </div>

          <div className="lf-crop-right">
            <p className="lf-size"><b>{level === "main" ? "Small: 18 × 18 px" : "Full tile: 104 × 104 px"}</b>{size.hint}</p>
            {img && <p className={"lf-src" + (small ? " lf-warn" : "")}>
              <Icon n={small ? "info" : "check"} size={13} />
              {small
                ? `This picture is ${img.w} × ${img.h}. It will look soft - ${size.min} × ${size.min} or bigger is best.`
                : `This picture is ${img.w} × ${img.h} - big enough.`}
            </p>}

            <p className="ad-dlg-cap">As the app will show it</p>
            {level === "main" ? (
              <div className="lf-prev-main">
                <span className="lf-pill lf-pill-on"><span className="lf-shot" style={{ width: 18, height: 18 }}>{shot(18)}</span>{name || "Category"}</span>
                <span className="lf-pill"><ShopIcon n="bag" size={17} />My Home</span>
                <span className="lf-shot lf-shot-big" style={{ width: 64, height: 64 }}>{shot(64)}</span>
              </div>
            ) : (
              <div className="lf-prev-sub" style={{ "--tone": tone, "--accent": accent }}>
                <figure><span className="lf-shot lf-shot-tile" style={{ width: 104, height: 104 }}>{shot(104)}</span><figcaption>{name || "Sub-category"}<small>Home page</small></figcaption></figure>
                <figure><span className="lf-shot lf-shot-circle" style={{ width: 88, height: 88 }}>{shot(88)}</span><figcaption>{name || "Sub-category"}<small>Category page</small></figcaption></figure>
              </div>
            )}
            {error && <p className="ad-hint ad-form-error" role="alert"><Icon n="info" size={14} />{error}</p>}
          </div>
        </div>

        <footer>
          <button type="button" className="ad-btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="ad-btn ad-primary" disabled={!view} onClick={save}>Use this logo</button>
        </footer>
      </section>
    </div>,
    document.body
  );
}
