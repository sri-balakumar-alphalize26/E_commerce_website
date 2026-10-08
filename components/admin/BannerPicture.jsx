"use client";
/* A banner's or a category tile's own picture, for the home page editor's
   side panel.

   Upload, Replace, Remove. A home banner is 5:2 (1600 x 640), a tile square
   (512 x 512): a picture already that shape goes straight in, shrunk to size;
   any other shape opens "Position your picture" - drag to move it, the slider to zoom, and
   what is inside the frame is what the shop shows. It is saved as a JPEG, so
   a phone photo of several MB arrives as a few hundred KB.

   The server checks it again (mart369_home `_mart369_check_picture`). */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./AdminUI";

const TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_FILE = 15 * 1024 * 1024;

function loadImage(file) {
  return new Promise((ok, bad) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => ok({ img, url });
    img.onerror = () => { URL.revokeObjectURL(url); bad(new Error("That file is not a picture we can open.")); };
    img.src = url;
  });
}

/* Draw the picture into an `out` sized frame ({w, h}: 1600 x 640 for a
   banner) and hand back a JPEG data URL. `place` is where the picture sits in
   a frame `frameW` wide. */
function render(img, place, frameW, out) {
  const k = out.w / frameW;
  const canvas = document.createElement("canvas");
  canvas.width = out.w;
  canvas.height = out.h;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, out.w, out.h);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, place.x * k, place.y * k, place.w * k, place.h * k);
  return canvas.toDataURL("image/jpeg", 0.88);
}

function Cropper({ img, out, onCancel, onDone }) {
  const frame = useRef(null);
  const RATIO = out.w / out.h;
  /* A square frame as wide as a banner's would not fit the screen. */
  const [frameW, setFrameW] = useState(RATIO < 1.5 ? 420 : 720);
  const frameH = frameW / RATIO;
  const iw = img.naturalWidth, ih = img.naturalHeight;
  /* Zoom 1 = the picture covers the frame; below 1 shows all of it (white
     around it), up to 3x closer. */
  const cover = Math.max(frameW / iw, frameH / ih);
  const contain = Math.min(frameW / iw, frameH / ih);
  const minZoom = contain / cover;
  const [zoom, setZoom] = useState(1);
  const [pos, setPos] = useState(null); /* top-left of the picture in the frame */
  const drag = useRef(null);

  useEffect(() => {
    const measure = () => frame.current && setFrameW(frame.current.clientWidth);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  const w = iw * cover * zoom, h = ih * cover * zoom;
  const clamp = (x, y) => ({
    x: w <= frameW ? (frameW - w) / 2 : Math.min(0, Math.max(frameW - w, x)),
    y: h <= frameH ? (frameH - h) / 2 : Math.min(0, Math.max(frameH - h, y)),
  });
  const at = clamp(pos ? pos.x : (frameW - w) / 2, pos ? pos.y : (frameH - h) / 2);

  const zoomTo = (z) => {
    /* Zoom around the frame's centre, so the part being looked at stays put. */
    const cx = frameW / 2, cy = frameH / 2;
    const f = z / zoom;
    setPos({ x: cx - (cx - at.x) * f, y: cy - (cy - at.y) * f });
    setZoom(z);
  };
  return createPortal(
    <div className="bp-wrap" role="dialog" aria-modal="true" aria-label="Position your picture">
      <div className="bp-dialog">
        <header className="bp-head">
          <div><h3>Position your picture</h3><p>Drag it to move, use the slider to zoom. What is inside the frame is what shoppers see.</p></div>
          <button className="bp-x" onClick={onCancel} aria-label="Cancel"><Icon n="x" size={18} /></button>
        </header>
        <div className={"bp-frame" + (RATIO < 1.5 ? " bp-frame-sq" : "")} ref={frame}
          onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); drag.current = { x: e.clientX - at.x, y: e.clientY - at.y }; }}
          onPointerMove={(e) => drag.current && setPos(clamp(e.clientX - drag.current.x, e.clientY - drag.current.y))}
          onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
          style={{ height: frameH }}>
          <img src={img.src} alt="" draggable="false" style={{ left: at.x, top: at.y, width: w, height: h }} />
        </div>
        <div className="bp-tools">
          <button className="ad-btn" onClick={() => zoomTo(minZoom)} disabled={zoom <= minZoom + 0.001}>Show all of it</button>
          <label className="bp-zoom"><span>Zoom</span>
            <input type="range" min={minZoom} max={3} step={0.01} value={zoom} onChange={(e) => zoomTo(Number(e.target.value))} aria-label="Zoom" />
          </label>
          <button className="ad-btn" onClick={() => zoomTo(1)} disabled={Math.abs(zoom - 1) < 0.001}>Fill the frame</button>
        </div>
        {iw < out.w * 0.6 && <p className="bp-warn"><Icon n="info" size={14} />This picture is small ({iw} × {ih}). It may look blurry on big screens; {out.w} × {out.h} looks sharpest.</p>}
        <footer className="bp-foot">
          <button className="ad-btn" onClick={onCancel}>Cancel</button>
          <button className="ad-btn ad-primary" onClick={() => onDone(render(img, { x: at.x, y: at.y, w, h }, frameW, out))}>Use this picture</button>
        </footer>
      </div>
    </div>,
    document.body
  );
}

/* `out` is the saved size: a banner's 1600 x 640 unless told otherwise (a
   tile passes 512 x 512). `note` replaces the line under an empty preview. */
export default function BannerPicture({ url, tone = "green", onPick, onRemove,
  out = { w: 1600, h: 640 }, note = "No picture yet - the banner shows its colour and drawings.", square = false }) {
  const input = useRef(null);
  const RATIO = out.w / out.h;
  const [crop, setCrop] = useState(null); /* {img, url} */
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const pick = async (file) => {
    setError("");
    if (!file) return;
    if (!TYPES.includes(file.type)) return setError("Please use a JPG, PNG or WebP picture.");
    if (file.size > MAX_FILE) return setError("That file is too big. Please use one under 15 MB.");
    setBusy(true);
    try {
      const loaded = await loadImage(file);
      const ratio = loaded.img.naturalWidth / loaded.img.naturalHeight;
      if (Math.abs(ratio - RATIO) / RATIO < 0.02) {
        /* Already the banner's shape: straight in. */
        onPick(render(loaded.img, { x: 0, y: 0, w: 720, h: 720 / RATIO }, 720, out));
        URL.revokeObjectURL(loaded.url);
      } else {
        setCrop(loaded);
      }
    } catch (e) {
      setError(e.message || "That picture could not be opened.");
    } finally {
      setBusy(false);
    }
  };
  const close = () => { if (crop) URL.revokeObjectURL(crop.url); setCrop(null); };

  return (
    <div className="bp">
      <div className={"bp-preview hm-tone-" + tone + (square ? " bp-square" : "")}>
        {url ? <img src={url} alt="The picture" /> : <span>{note}</span>}
      </div>
      <div className="bp-actions">
        <button type="button" className="ad-btn" disabled={busy} onClick={() => input.current?.click()}>
          <Icon n="camera" size={14} />{busy ? "Opening…" : url ? "Replace picture" : "Upload picture"}
        </button>
        {url && <button type="button" className="ad-btn" onClick={onRemove}>Remove picture</button>}
        <input ref={input} type="file" accept={TYPES.join(",")} hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      <em className="pe-hint">Best size {out.w} × {out.h}. Any picture works - you can position it after picking.</em>
      {error && <em className="pe-hint bp-error" role="alert">{error}</em>}
      {crop && <Cropper img={crop.img} out={out} onCancel={close} onDone={(dataUrl) => { close(); onPick(dataUrl); }} />}
    </div>
  );
}
