"use client";
/* ==========================================================================
   369 Mart admin — the product editor (.pdk-*)

   A port of the Odoo Products desk's editor
   (odoo_modules/mart369_product/static/src/products/product_editor.js), so the
   two screens that make a product ask the same questions in the same words.

   The boxes are not listed here. They come from `mart369_desk_form` through
   GET /admin/products/form, which reads the live field definitions and the
   page's hidden-box list - a renamed column reaches this screen without
   anybody remembering to change it here too. Saving goes through the same
   `mart369_desk_save`, so the allowlist of what may be written is Odoo's.

   Everything is kept in local state until Save; nothing is written as you
   type. Photographs follow the desk's bookkeeping exactly (add / remove /
   promote / demote), so "use on the card" never loses the old card picture.
   ========================================================================== */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, invalidate } from "@/lib/api";
import { money } from "@/lib/money";
import { useAction } from "@/lib/useFetch";
import { Confirm, Empty, Icon, Select } from "./AdminUI";
import "./productDesk.css";

/* Where each box shows up for the shopper. `card` and `page` light up that
   spot on the preview; `note` has no spot and says where it is used instead.
   `sample` fills an empty box so the preview always has something to show. */
export const PREVIEW = {
  name: { where: "card", sample: "USB-C Fast Charger" },
  mart_brand: { where: "note", note: "The brand line on the product page, above the name. Empty falls back to the shop's brand." },
  default_code: { where: "note", note: "Not shown to shoppers. It is your own code for the product, used in search and on your records." },
  public_categ_ids: { where: "note", note: "Decides which aisles the product is listed under in the app, and which page settings apply to it." },
  list_price: { where: "card", sample: "12.5" },
  compare_list_price: { where: "card", sample: "15" },
  standard_price: { where: "note", note: "Not shown to shoppers. What the product costs you - Odoo uses it for margins and stock value." },
  mart_unit_text: { where: "card", sample: "250 g" },
  mart_per_unit: { where: "card", sample: "17.25 per 250 g" },
  mart_note: { where: "card", sample: "Approx 250-400 g" },
  mart_home_tag: { where: "card", sample: "New" },
  mart_low_stock_at: { where: "card", sample: "3" },
  mart_delivery_text: { where: "card", sample: "3-5 days" },
  mart_features: { where: "page", sample: "Fast charging\nFoldable plug" },
  mart_in_the_box: { where: "page", sample: "Charger, cable" },
  mart_material: { where: "page", sample: "Plastic" },
  mart_item_height: { where: "page", sample: "12 cm" },
  mart_item_length: { where: "page", sample: "8 cm" },
  mart_item_width: { where: "page", sample: "6 cm" },
  weight: { where: "page", sample: "0.25" },
  description_ecommerce: { where: "page", sample: "A short paragraph about the product." },
};

const OTHER = "__other";
const NUMBER = /^\d+(?:\.\d+)?$/;
const RANGE = /^\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?$/;
const unitIn = (units, word) => units.find((u) => u.toLowerCase() === (word || "").toLowerCase());

/** A saved value split into the parts its boxes edit. Anything that does not
 *  fit keeps its text in `other`, so nothing is lost on the way in. */
export function splitValue(box, raw) {
  if (box.numeric) return { value: raw ? String(raw) : "", unit: box.units[0], other: null };
  const text = String(raw || "").trim();
  if (box.kind === "points") {
    const list = text ? text.split(box.sep ? /,/ : /\n/).map((l) => l.trim()).filter(Boolean) : [];
    return { list: list.length ? list : [""] };
  }
  if (box.kind === "choice") {
    if (!text) return { choice: "", other: "" };
    const hit = box.options.find((o) => o.toLowerCase() === text.toLowerCase());
    return hit ? { choice: hit, other: "" } : { choice: OTHER, other: text };
  }
  const units = box.units || [];
  if (box.kind === "per_unit") {
    if (!text) return { price: "", value: "", unit: units[0], other: null };
    const m = text.match(/^(\d+(?:\.\d+)?)\s*(?:per|\/)\s*(\d+(?:\.\d+)?)?\s*(\S+)$/i);
    if (m && unitIn(units, m[3])) return { price: m[1], value: m[2] || "", unit: unitIn(units, m[3]), other: null };
    return { price: "", value: "", unit: units[0], other: text };
  }
  if (!text) return { value: "", unit: units[0], other: null };
  const m = text.match(/^(\S+?)\s*([a-zA-Z]+)$/);
  const ok = m && (box.range ? RANGE : NUMBER).test(m[1]) && unitIn(units, m[2]);
  return ok ? { value: m[1], unit: unitIn(units, m[2]), other: null } : { value: "", unit: units[0], other: text };
}

/** The parts back into the one value the column holds. */
export function joinValue(box, p) {
  if (box.kind === "points") return p.list.map((l) => l.trim()).filter(Boolean).join(box.sep || "\n");
  if (box.kind === "choice") return p.choice === OTHER ? p.other.trim() : p.choice;
  if (box.numeric) {
    if (!p.value) return "";
    const n = Number(p.value);
    return p.unit === box.units[0] ? n : n / 1000; /* 250 g is saved as 0.25 kg */
  }
  if (p.other !== null) return p.other.trim();
  if (box.kind === "per_unit") return p.price ? `${p.price} per ${p.value ? p.value + " " : ""}${p.unit}` : "";
  return p.value ? `${p.value} ${p.unit}` : "";
}

/** Digits and one point, plus one dash where a range is allowed. */
function cleanNumber(raw, range) {
  const oneDot = (s) => { const [a, ...rest] = s.split("."); return rest.length ? `${a}.${rest.join("")}` : a; };
  const v = raw.replace(range ? /[^\d.\-]/g : /[^\d.]/g, "");
  const [from, ...to] = v.split("-");
  return to.length ? `${oneDot(from)}-${oneDot(to.join(""))}` : oneDot(from);
}

/** The plain number boxes, as the Odoo desk's onPlainNumber: not the browser's
 *  number box, which lets "e", "+" and "-" through. Digits and one point, or
 *  digits alone where it counts whole things. */
const plainNumber = (raw, whole) => {
  const v = String(raw).replace(whole ? /[^\d]/g : /[^\d.]/g, "");
  const [a, ...rest] = v.split(".");
  return rest.length ? `${a}.${rest.join("")}` : a;
};

/* Kinds whose value is text split into boxes; select/bool/tags/digits hold the value as is. */
const TEXT_KINDS = ["measure", "per_unit", "choice", "points"];

function formFrom(data) {
  const boxes = {};
  const parts = {};
  for (const g of data.groups) for (const b of g.boxes) {
    boxes[b.name] = b;
    if (TEXT_KINDS.includes(b.kind)) parts[b.name] = splitValue(b, data.values[b.name]);
  }
  return {
    id: data.id, groups: data.groups, boxes, parts,
    values: { ...data.values }, categories: data.categories || [],
    photo: data.photo || "", photos: data.photos || [],
    add: [], remove: [], promoted: null, demote: false, demotedUrl: "",
  };
}

const readFile = (file) => new Promise((ok, bad) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result));
  r.onerror = () => bad(r.error);
  r.readAsDataURL(file);
});

/* ------------------------------------------------------------ the popup */
export function PhotoViewer({ list, index, onIndex, onClose, onUseOnCard, onRemove }) {
  const box = useRef(null);
  const n = list.length;
  const step = useCallback((by) => onIndex((index + by + n) % n), [index, n, onIndex]);
  useEffect(() => {
    box.current?.focus();
    const key = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); }
      else if (e.key === "ArrowRight" && n > 1) step(1);
      else if (e.key === "ArrowLeft" && n > 1) step(-1);
    };
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
  }, [n, step, onClose]);
  const item = list[index];
  if (!item || typeof document === "undefined") return null;
  const tag = { main: "On the card", new: "Not saved yet", demoted: "Was on the card" }[item.kind];
  return createPortal(
    <div className="pdk-viewer" onClick={onClose}>
      <div className="pdk-viewer-box" role="dialog" aria-modal="true" aria-label="Photograph" tabIndex={-1} ref={box} onClick={(e) => e.stopPropagation()}>
        <header>
          <span><b>{index + 1}</b> of {n}{tag && <em>{tag}</em>}</span>
          {onUseOnCard && item.kind !== "main" && <button className="ad-btn ad-sm" onClick={() => onUseOnCard(item)}><Icon n="star" size={14} />Use on the card</button>}
          {onRemove && <button className="ad-btn ad-sm pdk-danger-ghost" onClick={() => onRemove(item)}><Icon n="trash" size={14} />Remove</button>}
          <button className="ad-icon-btn" onClick={onClose} aria-label="Close"><Icon n="x" size={17} /></button>
        </header>
        <div className="pdk-viewer-img">
          {n > 1 && <button className="pdk-viewer-step" onClick={() => step(-1)} aria-label="Previous"><Icon n="left" size={20} /></button>}
          <img src={item.url} alt="" />
          {n > 1 && <button className="pdk-viewer-step pdk-next" onClick={() => step(1)} aria-label="Next"><Icon n="right" size={20} /></button>}
        </div>
        {n > 1 && (
          <div className="pdk-viewer-strip">
            {list.map((p, i) => (
              <button key={p.kind + i} className={i === index ? "pdk-on" : ""} onClick={() => onIndex(i)} aria-label={`Photograph ${i + 1}`}><img src={p.url} alt="" /></button>
            ))}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}

/* ---------------------------------------------------------- the editor */
export default function ProductEditor({ productId, currency, onClose, onSaved, flash }) {
  const [form, setForm] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [focus, setFocus] = useState(null);   /* the box lit on the preview */
  /* Pointing at a box that is already lit pulses its spot again - otherwise a
     second hover changes nothing and the spot is easy to miss. The class comes
     off for one frame so the animation starts over. */
  const [beat, setBeat] = useState(null);
  const point = (name) => { setFocus(name); setBeat(null); requestAnimationFrame(() => setBeat(name)); };
  const [viewing, setViewing] = useState(null);
  const [asking, setAsking] = useState(false);
  const [nameBad, setNameBad] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [categQ, setCategQ] = useState("");
  const save = useAction();
  const nameRef = useRef(null);
  const pendingFocus = useRef(null);
  const root = useRef(null);

  const load = useCallback(() => {
    setLoadError(null);
    api("/admin/products/form" + (productId ? `?id=${productId}` : ""), { fresh: true })
      .then((data) => setForm(formFrom(data)))
      .catch((e) => setLoadError(e));
  }, [productId]);
  useEffect(load, [load]);

  /* Leaving the page with unsaved work asks the browser's own question. */
  useEffect(() => {
    if (!dirty) return undefined;
    const guard = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);

  /* Enter in a point focuses the new one once it exists. */
  useEffect(() => {
    const p = pendingFocus.current;
    if (!p) return;
    pendingFocus.current = null;
    root.current?.querySelector(`.pdk-points[data-name="${p.name}"] input[data-i="${p.i}"]`)?.focus();
  });

  /* Every change goes through one updater, so "dirty" cannot be forgotten. */
  const edit = (fn) => { setDirty(true); setForm((f) => { const next = { ...f, values: { ...f.values }, parts: { ...f.parts } }; fn(next); return next; }); };
  const setField = (name, value) => { edit((f) => { f.values[name] = value; }); if (name === "name" && value.trim()) setNameBad(false); };
  const setPart = (name, key, value) => edit((f) => {
    f.parts[name] = { ...f.parts[name], [key]: value };
    f.values[name] = joinValue(f.boxes[name], f.parts[name]);
  });

  /* --------------------------------------------------------- photographs */
  const photoList = useMemo(() => {
    if (!form) return [];
    const list = [];
    if (form.photo) list.push({ kind: "main", url: form.photo });
    if (form.demote && form.demotedUrl) list.push({ kind: "demoted", url: form.demotedUrl });
    for (const ph of form.photos) list.push({ kind: "saved", url: ph.url, photo: ph });
    for (const ph of form.add) list.push({ kind: "new", url: ph.url, photo: ph });
    return list;
  }, [form]);

  const addFiles = async (files) => {
    const images = [...files].filter((f) => f.type.startsWith("image/"));
    if (!images.length) { if (files.length) flash?.("Only pictures can be added.", "bad"); return; }
    const read = [];
    for (const file of images) {
      const url = await readFile(file);
      read.push({ name: file.name, data: url.split(",")[1], url });
    }
    edit((f) => {
      f.add = [...f.add];
      for (const ph of read) {
        if (!f.photo) { f.values.image_1920 = ph.data; f.photo = ph.url; }
        else f.add.push(ph);
      }
    });
  };

  /* Ticked photographs, by kind and address, for "Remove selected". */
  const [picked, setPicked] = useState(() => new Set());
  const photoKey = (ph) => `${ph.kind}:${ph.url.slice(-48)}`;
  const togglePick = (ph) => setPicked((s) => { const n = new Set(s); n.has(photoKey(ph)) ? n.delete(photoKey(ph)) : n.add(photoKey(ph)); return n; });
  const dropPicked = () => {
    photoList.filter((ph) => picked.has(photoKey(ph))).forEach(dropOne);
    setPicked(new Set());
    setViewing(null);
  };

  const dropPhoto = (item) => {
    dropOne(item);
    setPicked((s) => { const n = new Set(s); n.delete(photoKey(item)); return n; });
    const left = photoList.length - 1;
    setViewing((v) => (v === null || left <= 0 ? null : Math.min(v, left - 1)));
  };

  function dropOne(item) {
    edit((f) => {
      if (item.kind === "main") {
        f.values.image_1920 = ""; /* '' = take it away, not "not mentioned" */
        f.photo = "";
        if (f.promoted) { f.remove = [...f.remove, f.promoted.id]; f.promoted = null; }
      } else if (item.kind === "demoted") {
        f.demote = false; f.demotedUrl = "";
      } else if (item.kind === "saved") {
        f.remove = [...f.remove, item.photo.id];
        f.photos = f.photos.filter((p) => p.id !== item.photo.id);
      } else {
        f.add = f.add.filter((p) => p !== item.photo);
      }
    });
  }

  const useOnCard = (item) => {
    if (item.kind === "main") return;
    edit((f) => {
      if (f.photo) {
        if (f.promoted) f.photos = [f.promoted, ...f.photos];
        else if (f.values.image_1920) f.add = [{ name: "photo", data: f.values.image_1920, url: f.photo }, ...f.add];
        else if (!f.demote) { f.demote = true; f.demotedUrl = f.photo; }
      }
      f.promoted = null;
      if (item.kind === "new") {
        f.values.image_1920 = item.photo.data;
        f.add = f.add.filter((p) => p !== item.photo);
      } else if (item.kind === "saved") {
        f.promoted = item.photo;
        f.photos = f.photos.filter((p) => p.id !== item.photo.id);
        delete f.values.image_1920;
      } else if (item.kind === "demoted") {
        f.demote = false; f.demotedUrl = "";
        delete f.values.image_1920;
      }
      f.photo = item.url;
    });
    setViewing(0);
  };

  /* ----------------------------------------------------------------- points */
  const setPoint = (name, i, value) => { const list = [...form.parts[name].list]; list[i] = value; setPart(name, "list", list); };
  const onPointKey = (e, name, i) => {
    const list = form.parts[name].list;
    if (e.key === "Enter") {
      e.preventDefault();
      setPart(name, "list", [...list.slice(0, i + 1), "", ...list.slice(i + 1)]);
      pendingFocus.current = { name, i: i + 1 };
    } else if (e.key === "Backspace" && !e.currentTarget.value && list.length > 1) {
      e.preventDefault();
      setPart(name, "list", list.filter((_, j) => j !== i));
      pendingFocus.current = { name, i: Math.max(0, i - 1) };
    }
  };
  const addPoint = (name) => { const list = form.parts[name].list; setPart(name, "list", [...list, ""]); pendingFocus.current = { name, i: list.length }; };
  const removePoint = (name, i) => { const list = form.parts[name].list; setPart(name, "list", list.length > 1 ? list.filter((_, j) => j !== i) : [""]); };

  /* ------------------------------------------------------------- categories */
  const chosen = form?.values.public_categ_ids || [];
  const toggleCategory = (id) => edit((f) => {
    const now = f.values.public_categ_ids || [];
    f.values.public_categ_ids = now.includes(id) ? now.filter((c) => c !== id) : [...now, id];
  });
  const shownCategories = useMemo(() => {
    if (!form) return [];
    const q = categQ.trim().toLowerCase();
    const hits = form.categories.filter((c) => !q || c.name.toLowerCase().includes(q));
    return [...hits.filter((c) => chosen.includes(c.id)), ...hits.filter((c) => !chosen.includes(c.id))];
  }, [form, categQ, chosen]);
  /* The category list opens as a panel over the form, not in it, so the
     boxes below never jump down while you choose. */
  const [categOpen, setCategOpen] = useState(false);
  const categWrap = useRef(null);
  useEffect(() => {
    if (!categOpen) return undefined;
    const away = (e) => { if (!categWrap.current?.contains(e.target)) setCategOpen(false); };
    const key = (e) => { if (e.key === "Escape") setCategOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", key); };
  }, [categOpen]);

  /* ------------------------------------------------------------ save/cancel */
  const cancel = () => (dirty ? setAsking(true) : onClose());

  const submit = async () => {
    if (!(form.values.name || "").trim()) {
      setNameBad(true);
      nameRef.current?.focus();
      nameRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    const body = {
      values: form.values,
      photos: {
        add: form.add.map(({ name, data }) => ({ name, data })), /* not the data: URL twice */
        remove: form.remove,
        promote: form.promoted ? form.promoted.id : null,
        demote: form.demote,
      },
    };
    const res = await save.run(() => (form.id
      ? api(`/admin/products/${form.id}`, { method: "PATCH", body })
      : api("/admin/products", { method: "POST", body })));
    if (!res) return;
    invalidate("/admin/products");
    setDirty(false);
    flash?.(form.id ? "Product saved" : `${form.values.name.trim()} is now in the shop`);
    onSaved(res.id);
  };

  /* Ctrl/Cmd+S saves, like every other editor people already know. */
  const submitRef = useRef(submit);
  submitRef.current = submit;
  useEffect(() => {
    const k = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); submitRef.current?.(); } };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  /* ----------------------------------------------------------------- draw */
  const title = productId ? "Edit product" : "New product";
  const head = (
    <header className="pdk-bar">
      <button className="ad-btn ad-sm" onClick={cancel}><Icon n="left" size={15} />Back</button>
      <div className="pdk-bar-title">
        <h2>{title}</h2>
        <small>{form ? (form.values.name || (productId ? "" : "Not saved yet")) : "Loading…"}{dirty && <em className="pdk-unsaved">Unsaved changes</em>}</small>
      </div>
      <div className="pdk-bar-act">
        <button className="ad-btn" onClick={cancel} disabled={save.busy}>Cancel</button>
        <button className="ad-btn ad-primary" onClick={submit} disabled={!form || save.busy}>
          <Icon n="check" size={15} />{save.busy ? "Saving…" : productId ? "Save" : "Create product"}
        </button>
      </div>
    </header>
  );

  if (loadError) return <div className="pdk-editor">{head}<section className="ad-card"><Empty icon="info" title="We could not open the product" text={loadError.message} action="Try again" onAction={load} /></section></div>;
  if (!form) return <div className="pdk-editor">{head}<section className="ad-card"><Empty icon="layers" title="Loading…" text="Fetching the product's boxes." /></section></div>;

  const cur = currency;
  const v = form.values;
  const mrpWarning = Number(v.compare_list_price || 0) > 0 && Number(v.list_price || 0) > 0 && Number(v.compare_list_price) <= Number(v.list_price);
  const lit = (name) => (focus === name ? " pdk-lit" + (beat === name ? " pdk-beat" : "") : "");
  const pv = (name) => {
    const typed = v[name];
    const has = typed !== undefined && typed !== null && typed !== "" && typed !== 0;
    return { text: has ? String(typed) : PREVIEW[name]?.sample || "", sample: !has };
  };
  const cls = (name) => (pv(name).sample ? " pdk-sample" : "") + lit(name);
  const show = (name) => !pv(name).sample || focus === name;
  const focusProps = (name) => ({ onFocus: () => setFocus(name) });
  const note = focus && PREVIEW[focus]?.where === "note" ? { label: form.boxes[focus]?.label || focus, text: PREVIEW[focus].note } : null;

  const label = (b) => (
    <span className="pdk-label">
      {b.label}{b.required && <i className="pdk-req" aria-hidden="true">*</i>}
      {PREVIEW[b.name] && (
        <button type="button" className={"pdk-eye" + (focus === b.name ? " pdk-on" : "")} aria-label={`Show where ${b.label} appears in the app`} title="Where it shows"
          onMouseEnter={() => point(b.name)} onClick={() => point(b.name)}><Icon n="info" size={12} /></button>
      )}
    </span>
  );

  const box = (b) => {
    if (b.showIf && !v[b.showIf]) return null;
    const pt = form.parts[b.name];
    if (b.kind === "select") {
      return (
        <div key={b.name} className="pdk-field">
          {label(b)}
          <Select value={v[b.name] == null || v[b.name] === false ? "" : String(v[b.name])} label={b.label}
            onChange={(x) => { setFocus(b.name); setField(b.name, x); }} options={b.options.map(([o, l]) => [String(o), l])} />
          {b.help && <small>{b.help}</small>}
        </div>
      );
    }
    if (b.kind === "digits" || b.name === "barcode") { /* barcode by name too, for a server not restarted since the digits kind came in */
      const max = b.max || 14;
      const val = v[b.name] || "";
      const old = val && !/^\d*$/.test(val);
      return (
        <div key={b.name} className="pdk-field">
          {label(b)}
          <input type="text" inputMode="numeric" maxLength={old ? undefined : max} value={val}
            onChange={(e) => setField(b.name, e.target.value.replace(/\D/g, "").slice(0, max))} {...focusProps(b.name)} />
          {old ? <small>Old barcode with letters - type a new one with digits only to change it.</small>
            : b.help && <small>{b.help}</small>}
        </div>
      );
    }
    if (b.kind === "bool") {
      return (
        <div key={b.name} className="pdk-field">
          {label(b)}
          <label className="pdk-check">
            <input type="checkbox" checked={!!v[b.name]} onChange={(e) => setField(b.name, e.target.checked)} {...focusProps(b.name)} />
            <span>{v[b.name] ? "Yes" : "No"}</span>
          </label>
          {b.help && <small>{b.help}</small>}
        </div>
      );
    }
    if (b.kind === "tags") {
      const ids = Array.isArray(v[b.name]) ? v[b.name] : [];
      return (
        <div key={b.name} className="pdk-field pdk-wide">
          {label(b)}
          {/* Like the Odoo desk: a chip per chosen one, a dropdown to add more. */}
          <div className="pdk-categs">
            {b.options.filter(([id]) => ids.includes(id)).map(([id, l]) => (
              <button key={id} type="button" className="pdk-categ pdk-on" aria-label={`Remove ${l}`}
                onClick={() => { setFocus(b.name); setField(b.name, ids.filter((x) => x !== id)); }}>
                {l}<Icon n="x" size={12} />
              </button>
            ))}
            {!ids.length && <span className="ad-dim">None chosen.</span>}
          </div>
          {b.options.some(([id]) => !ids.includes(id)) && (
            <Select value="" label={`Add to ${b.label}`}
              onChange={(x) => { if (x) { setFocus(b.name); setField(b.name, [...ids, Number(x)]); } }}
              options={[["", "Add…"], ...b.options.filter(([id]) => !ids.includes(id)).map(([id, l]) => [String(id), l])]} />
          )}
          {b.help && <small>{b.help}</small>}
        </div>
      );
    }
    if (b.kind === "measure" || b.kind === "per_unit") {
      return (
        <div key={b.name} className={"pdk-field" + (b.kind === "per_unit" ? " pdk-wide" : "")}>
          {label(b)}
          {pt.other !== null ? (
            <div className="pdk-unit">
              <input type="text" value={pt.other} onChange={(e) => setPart(b.name, "other", e.target.value)} {...focusProps(b.name)} />
              <button type="button" className="ad-link" onClick={() => setPart(b.name, "other", null)}>Use number and unit</button>
            </div>
          ) : (
            <div className="pdk-unit">
              {b.kind === "per_unit" && <>
                <input type="text" inputMode="decimal" placeholder="Price" className="pdk-num" value={pt.price} aria-label={`${b.label} price`}
                  onChange={(e) => setPart(b.name, "price", cleanNumber(e.target.value, false))} {...focusProps(b.name)} />
                <span className="pdk-per">per</span>
              </>}
              <input type="text" inputMode="decimal" className="pdk-num" value={pt.value} aria-label={`${b.label} value`}
                placeholder={b.range ? "e.g. 3-5" : b.kind === "per_unit" ? "e.g. 250" : "Value"}
                onChange={(e) => setPart(b.name, "value", cleanNumber(e.target.value, !!b.range))} {...focusProps(b.name)} />
              <Select value={pt.unit} onChange={(u) => setPart(b.name, "unit", u)} label={`${b.label} unit`} options={b.units.map((u) => [u, u])} />
            </div>
          )}
          {pt.other !== null && <small>This was typed before the boxes existed. Keep it, or choose number and unit.</small>}
        </div>
      );
    }
    if (b.kind === "choice") {
      return (
        <div key={b.name} className="pdk-field">
          {label(b)}
          <Select value={pt.choice} onChange={(c) => { setFocus(b.name); setPart(b.name, "choice", c); }} label={b.label}
            options={[["", "None"], ...b.options.map((o) => [o, o]), [OTHER, "Other…"]]} />
          {pt.choice === OTHER && <input type="text" placeholder="Type your own" value={pt.other} aria-label={`${b.label}, your own`}
            onChange={(e) => setPart(b.name, "other", e.target.value)} {...focusProps(b.name)} />}
        </div>
      );
    }
    if (b.kind === "points") {
      return (
        <div key={b.name} className="pdk-field pdk-wide">
          {label(b)}
          <ol className="pdk-points" data-name={b.name}>
            {pt.list.map((line, i) => (
              <li key={i}>
                <input type="text" data-i={i} value={line} placeholder={b.sep ? "An item, then Enter" : "A feature, then Enter"}
                  aria-label={`${b.label} ${i + 1}`}
                  onChange={(e) => setPoint(b.name, i, e.target.value)} onKeyDown={(e) => onPointKey(e, b.name, i)} {...focusProps(b.name)} />
                <button type="button" className="ad-icon-btn" aria-label="Remove this point" onClick={() => removePoint(b.name, i)}><Icon n="x" size={13} /></button>
              </li>
            ))}
          </ol>
          <button type="button" className="ad-link pdk-add-point" onClick={() => addPoint(b.name)}><Icon n="plus" size={13} />{b.sep ? "Add an item" : "Add a point"}</button>
        </div>
      );
    }
    if (b.widget === "categories") {
      return (
        <div key={b.name} className="pdk-field pdk-wide">
          {label(b)}
          <div className={"pdk-cdrop" + (categOpen ? " pdk-open" : "")} ref={categWrap}>
            <button type="button" className="pdk-cdrop-btn" aria-haspopup="listbox" aria-expanded={categOpen}
              onClick={() => { setFocus(b.name); setCategOpen((o) => !o); }}>
              <span className={chosen.length ? "" : "ad-dim"}>
                {chosen.length
                  ? form.categories.filter((c) => chosen.includes(c.id)).map((c) => c.name).join(", ")
                  : "Choose categories"}
              </span>
              <Icon n="chev" size={15} />
            </button>
            {categOpen && (
              <div className="pdk-cdrop-panel">
                <label className="ad-search">
                  <Icon n="search" size={15} />
                  <input autoFocus value={categQ} onChange={(e) => setCategQ(e.target.value)} placeholder="Find a category" aria-label="Find a category" />
                </label>
                <ul className="pdk-cdrop-list" role="listbox" aria-multiselectable="true" aria-label={b.label}>
                  {!shownCategories.length && <li className="ad-dim pdk-cdrop-none">No category matches.</li>}
                  {shownCategories.map((c) => (
                    <li key={c.id}>
                      <label className="pdk-cdrop-row">
                        <input type="checkbox" checked={chosen.includes(c.id)} onChange={() => toggleCategory(c.id)} />
                        <span>{c.name}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <small>{chosen.length ? `${chosen.length} chosen` : "Not in any category yet - shoppers will only find it by searching."}</small>
        </div>
      );
    }
    if (b.widget === "text" || b.widget === "html") {
      return (
        <div key={b.name} className="pdk-field pdk-wide">
          {label(b)}
          <textarea rows={4} value={v[b.name] || ""} onChange={(e) => setField(b.name, e.target.value)} {...focusProps(b.name)} />
          {b.help && <small>{b.help}</small>}
        </div>
      );
    }
    if (b.widget === "number" || b.widget === "integer") {
      const isMoney = ["list_price", "compare_list_price", "standard_price"].includes(b.name);
      return (
        <div key={b.name} className="pdk-field">
          {label(b)}
          <div className="pdk-affix">
            {isMoney && cur?.symbol && <em>{cur.symbol}</em>}
            <input type="text" inputMode={b.widget === "integer" ? "numeric" : "decimal"} value={v[b.name] ?? ""} readOnly={!!b.readonly}
              onChange={(e) => setField(b.name, plainNumber(e.target.value, b.widget === "integer"))} {...focusProps(b.name)} />
          </div>
          {b.name === "compare_list_price" && mrpWarning && <small className="pdk-warn">MRP is not above the price, so no discount will show.</small>}
          {b.help && <small>{b.help}</small>}
        </div>
      );
    }
    const isName = b.name === "name";
    return (
      <div key={b.name} className={"pdk-field" + (isName ? " pdk-wide" : "") + (isName && nameBad ? " pdk-bad" : "")}>
        {label(b)}
        <input type="text" ref={isName ? nameRef : undefined} value={v[b.name] || ""} required={b.required} aria-invalid={isName && nameBad}
          onChange={(e) => setField(b.name, e.target.value)} {...focusProps(b.name)} />
        {isName && nameBad && <small className="pdk-err">A product needs a name.</small>}
        {b.help && <small>{b.help}</small>}
      </div>
    );
  };

  const tag = pv("mart_home_tag");
  return (
    <div className="pdk-editor" ref={root}>
      {head}
      {save.error && <p className="ad-form-error" role="alert">{save.error.message}</p>}

      <div className="pdk-cols">
        <div className="pdk-form">
          <section className={"ad-card pdk-sec pdk-photos-sec" + (dragging ? " pdk-drag" : "")}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false); }}
            onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}>
            <header className="pdk-sec-head"><h3>Photographs</h3><small>{photoList.length ? `${photoList.length} in all` : "None yet"}</small></header>
            {picked.size > 0 && (
              <div className="pdk-photo-bar">
                <b>{picked.size} selected</b>
                <button type="button" className="ad-link" onClick={() => setPicked(new Set(photoList.map(photoKey)))}>Select all</button>
                <button type="button" className="ad-link" onClick={() => setPicked(new Set())}>Clear</button>
                <button type="button" className="ad-btn pdk-danger" onClick={dropPicked}><Icon n="x" size={13} />Remove selected</button>
              </div>
            )}
            <div className={"pdk-photos" + (picked.size ? " pdk-picking" : "")}>
              {photoList.map((ph, i) => {
                const on = picked.has(photoKey(ph));
                return (
                  <div key={ph.kind + i + ph.url.slice(-16)} className={"pdk-photo" + (ph.kind === "main" ? " pdk-main" : "") + (ph.kind === "new" ? " pdk-new" : "") + (on ? " pdk-picked" : "")}>
                    <button type="button" className="pdk-photo-view" onClick={() => setViewing(i)} aria-label={`View photograph ${i + 1}`}>
                      <img src={ph.url} alt="" />
                    </button>
                    <label className="pdk-photo-pick" title="Select">
                      <input type="checkbox" checked={on} onChange={() => togglePick(ph)} aria-label={`Select photograph ${i + 1}`} />
                    </label>
                    <button type="button" className="pdk-photo-x" onClick={() => dropPhoto(ph)} aria-label={`Remove photograph ${i + 1}`} title="Remove">
                      <Icon n="x" size={12} />
                    </button>
                    {ph.kind === "main" && <small>On the card</small>}
                    {ph.kind === "new" && <small>Not saved</small>}
                    {ph.kind === "demoted" && <small>Was on the card</small>}
                  </div>
                );
              })}
              <label className="pdk-photo pdk-photo-add" aria-label="Add photographs">
                <Icon n="plus" size={22} />
                <span>Add</span>
                <input type="file" accept="image/*" multiple hidden onChange={(e) => { addFiles(e.target.files || []); e.target.value = ""; }} />
              </label>
            </div>
            <p className="pdk-hint">Tap Add, or drop pictures here. The first is the picture on the card; the rest become the gallery shoppers swipe. Tap a picture to see it large, put it on the card, or remove it.</p>
          </section>

          {form.groups.map((g) => (
            <section key={g.title} className="ad-card pdk-sec">
              <header className="pdk-sec-head"><h3>{g.title}</h3></header>
              <div className="pdk-fields">{g.boxes.map(box)}</div>
            </section>
          ))}
        </div>

        <aside className="pdk-preview" aria-label="How it looks in the app">
          <div className="ad-card pdk-sec">
            <header className="pdk-sec-head"><h3>How shoppers see it</h3><small>Grey text is only a sample</small></header>
            <div className="pdk-mock-card">
              <div className={"pdk-mock-img" + lit("image")}>
                {form.photo ? <img src={form.photo} alt="" /> : <Icon n="layers" size={28} />}
                {show("mart_home_tag") && <span className={"pdk-mock-badge" + cls("mart_home_tag")}>{tag.text}</span>}
              </div>
              <b className={"pdk-mock-name" + cls("name")}>{pv("name").text}</b>
              {show("mart_unit_text") && <span className={"pdk-mock-line" + cls("mart_unit_text")}>{pv("mart_unit_text").text}</span>}
              {show("mart_note") && <span className={"pdk-mock-line" + cls("mart_note")}>({pv("mart_note").text})</span>}
              <div className="pdk-mock-price">
                <b className={cls("list_price")}>{money(Number(pv("list_price").text) || 0, cur)}</b>
                {show("compare_list_price") && <s className={cls("compare_list_price")}>{money(Number(pv("compare_list_price").text) || 0, cur)}</s>}
              </div>
              {show("mart_per_unit") && <span className={"pdk-mock-small" + cls("mart_per_unit")}>{pv("mart_per_unit").text}</span>}
              {focus === "mart_low_stock_at" && <span className={"pdk-mock-warn" + cls("mart_low_stock_at")}>Only {pv("mart_low_stock_at").text} left</span>}
              {show("mart_delivery_text") && <span className={"pdk-mock-small" + cls("mart_delivery_text")}><Icon n="truck" size={12} /> {pv("mart_delivery_text").text}</span>}
              <span className="pdk-mock-add">Add</span>
            </div>

            <div className="pdk-mock-page">
              <div className={"pdk-mock-block" + lit("mart_features")}>
                <h4>Key features</h4>
                <ul>{pv("mart_features").text.split("\n").filter(Boolean).map((f, i) => <li key={i} className={pv("mart_features").sample ? "pdk-sample" : ""}><Icon n="check" size={12} /> {f}</li>)}</ul>
              </div>
              <div className="pdk-mock-block">
                <h4>Product information</h4>
                <table><tbody>
                  {[["mart_in_the_box", "In the box"], ["mart_material", "Material"], ["mart_item_height", "Item height"], ["mart_item_length", "Item length"], ["mart_item_width", "Item width"], ["weight", "Net weight"]]
                    .filter(([k]) => form.boxes[k] && show(k))
                    .map(([k, label]) => <tr key={k} className={lit(k)}><th>{label}</th><td className={pv(k).sample ? "pdk-sample" : ""}>{pv(k).text}{k === "weight" ? " kg" : ""}</td></tr>)}
                </tbody></table>
              </div>
              {show("description_ecommerce") && (
                <div className={"pdk-mock-block" + lit("description_ecommerce")}>
                  <h4>Description</h4>
                  <p className={pv("description_ecommerce").sample ? "pdk-sample" : ""}>{pv("description_ecommerce").text}</p>
                </div>
              )}
            </div>
            <p className={"pdk-hint pdk-preview-note" + (note && beat === focus ? " pdk-beat" : "")}>
              {note ? <><b>{note.label}.</b> {note.text}</> : focus && form.boxes[focus] ? <>Outlined: <b>{form.boxes[focus].label}</b>.</> : "Click into a box to see where the app prints it."}
            </p>
          </div>
        </aside>
      </div>

      {viewing !== null && photoList[viewing] && (
        <PhotoViewer list={photoList} index={viewing} onIndex={setViewing} onClose={() => setViewing(null)} onUseOnCard={useOnCard} onRemove={dropPhoto} />
      )}
      {asking && (
        <Confirm title="Discard your changes?" text="What you typed on this product has not been saved." danger confirmLabel="Discard"
          onCancel={() => setAsking(false)} onConfirm={() => { setAsking(false); setDirty(false); onClose(); }} />
      )}
    </div>
  );
}
