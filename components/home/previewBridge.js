"use client";
/* The product page inside Odoo's 369 Mart editor ("How shoppers see it").

   Only there - the page is in a frame and its address carries `preview` - a
   section under the pointer is outlined, and tapping it tells the editor which
   one it is (postMessage to the frame's parent). The editor then scrolls to
   the box that fills that section and makes it pulse
   (mart369_product/static/src/products/product_editor.js `onPreviewPick`).
   The tap still does what it does on the shop - picking a colour still picks
   it. For shoppers, outside a frame, none of this runs. */

/* The page's sections, by the classes it already draws them with, most
   specific first: [selector, what the editor calls it]. */
const SECTIONS = [
  [".pd-trust", "trust"],
  [".pd-keys", "details"],
  [".pd-about", "about"],
  [".pd-show", "showcase"],
  [".pd-compare", "details"],
  ['[data-sec="specs"]', "variants"],
  ['[data-sec="info"]', "info"],
  ['[data-sec="description"]', "description"],
  [".pd-vars, .pd-sizes", "variants"],
  [".pd-price", "price"],
  [".pd-low", "lowstock"],
  [".pd-unit-tag", "unit"],
  [".pd-name", "name"],
  [".pd-gallery", "photos"],
  [".pd-reviews", "reviews"],
];

export const inEditorPreview = () => {
  try {
    return typeof window !== "undefined" && window.parent !== window
      && new URLSearchParams(window.location.search).has("preview");
  } catch (e) {
    return false;
  }
};

function sectionOf(node) {
  for (const [sel, key] of SECTIONS) {
    const el = node?.closest?.(sel);
    if (el) return { el, key };
  }
  return null;
}

/* Start listening; returns the function that stops it. */
export function startPreviewBridge() {
  if (!inEditorPreview()) return () => {};
  let lit = null;
  const light = (el) => {
    if (lit === el) return;
    lit?.classList.remove("pv-pick-on");
    lit = el;
    lit?.classList.add("pv-pick-on");
  };
  const over = (e) => light(sectionOf(e.target)?.el || null);
  const leave = () => light(null);
  const click = (e) => {
    const hit = sectionOf(e.target);
    if (!hit) return;
    hit.el.classList.remove("pv-pick-tap");
    void hit.el.offsetWidth; /* restart the flash */
    hit.el.classList.add("pv-pick-tap");
    window.parent.postMessage({ type: "mart369:preview-pick", target: hit.key }, "*");
  };
  document.addEventListener("mouseover", over, true);
  document.addEventListener("mouseleave", leave);
  document.addEventListener("click", click, true);
  document.documentElement.classList.add("pv-editing");
  return () => {
    document.removeEventListener("mouseover", over, true);
    document.removeEventListener("mouseleave", leave);
    document.removeEventListener("click", click, true);
    document.documentElement.classList.remove("pv-editing");
    light(null);
  };
}
