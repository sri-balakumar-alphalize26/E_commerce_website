"use client";

/* HTML from the shop, made safe to draw: the product's eCommerce Description.

   Odoo already cleans it (mart369 `_mart369_description_html`, html_sanitize);
   this is the second lock on the door. Only an allow-list of formatting tags
   survives - paragraphs, bold, italics, lists, headings, tables, links and
   pictures - with no attributes but a link's address and a picture's source.
   Anything else keeps its text and loses its markup; scripts, styles, frames
   and forms are dropped whole.

   Needs the browser's DOMParser, so it runs on the client only: `toSafeHtml`
   answers null on the server and the caller shows the plain text instead. */

const KEEP = new Set(["P", "BR", "B", "STRONG", "I", "EM", "U", "S", "UL", "OL", "LI", "H2", "H3", "H4",
  "BLOCKQUOTE", "TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "A", "IMG", "HR", "SPAN", "DIV", "SUB", "SUP"]);
const RENAME = { H1: "H2", H5: "H4", H6: "H4" };
const DROP = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "BUTTON", "TEXTAREA",
  "SELECT", "LINK", "META", "SVG", "MATH", "TEMPLATE", "NOSCRIPT", "VIDEO", "AUDIO", "CANVAS"]);

const safeUrl = (url, { relative }) => {
  const u = String(url || "").trim();
  if (/^https?:\/\//i.test(u)) return u;
  if (relative && /^\/(?!\/)/.test(u)) return u;
  if (/^mailto:/i.test(u)) return u;
  return null;
};

function clean(node, doc) {
  const out = doc.createDocumentFragment();
  node.childNodes.forEach((child) => {
    if (child.nodeType === 3) { out.appendChild(doc.createTextNode(child.nodeValue)); return; }
    if (child.nodeType !== 1) return;
    const tag = RENAME[child.tagName] || child.tagName;
    if (DROP.has(tag)) return;
    const inner = clean(child, doc);
    if (!KEEP.has(tag)) { out.appendChild(inner); return; }
    const el = doc.createElement(tag);
    if (tag === "A") {
      const href = safeUrl(child.getAttribute("href"), { relative: true });
      if (!href) { out.appendChild(inner); return; }
      el.setAttribute("href", href);
      el.setAttribute("target", "_blank");
      el.setAttribute("rel", "noopener noreferrer nofollow");
    }
    if (tag === "IMG") {
      const src = safeUrl(child.getAttribute("src"), { relative: true });
      if (!src) return;
      el.setAttribute("src", src);
      el.setAttribute("alt", child.getAttribute("alt") || "");
      el.setAttribute("loading", "lazy");
    }
    if ((tag === "TD" || tag === "TH") && /^\d{1,2}$/.test(child.getAttribute("colspan") || "")) {
      el.setAttribute("colspan", child.getAttribute("colspan"));
    }
    el.appendChild(inner);
    out.appendChild(el);
  });
  return out;
}

export function toSafeHtml(html) {
  if (!html || typeof window === "undefined" || typeof DOMParser === "undefined") return null;
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const box = doc.createElement("div");
  box.appendChild(clean(doc.body, doc));
  const out = box.innerHTML.trim();
  return box.textContent.trim() || box.querySelector("img") ? out : null;
}
