/* Generates the sample product + category images in /public/images from
   components/home/art.jsx, reading names and counts from sampleData.js and catalog.js (browse-only products).
   Run:  npm run images
   Replace the generated files with real photos (same file names) whenever you have them. */
import { build } from "esbuild";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const tmp = join(root, ".images-tmp.mjs");

await build({
  stdin: {
    contents: `
      import React from "react";
      import { renderToStaticMarkup } from "react-dom/server";
      import ProductArt from "./components/home/art.jsx";
      export * as data from "./components/home/sampleData.js";
      export * as catalog from "./components/home/catalog.js";
      export const render = (props) => renderToStaticMarkup(React.createElement(ProductArt, props));
    `,
    resolveDir: root,
    loader: "jsx",
  },
  bundle: true, platform: "node", format: "esm", jsx: "automatic", packages: "external",
  loader: { ".js": "jsx" }, outfile: tmp, logLevel: "error",
});

const { data, catalog, render } = await import(pathToFileURL(tmp).href + "?t=" + Date.now());
rmSync(tmp);

const inner = (p) => render(p).replace(/^<svg[^>]*>/, "").replace(/<\/svg>$/, "");
const hexA = (hex = "#0a78ab", a = 0.14) => {
  const h = hex.replace("#", ""); const n = parseInt(h.length === 3 ? h.split("").map((x) => x + x).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};
const svg = (viewBox, body) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" width="600" height="600" font-family="Inter, Arial, sans-serif">${body}</svg>\n`;

/* image 1 front · 2 close-up · 3 angled on a soft backdrop · 4 back (mirrored) */
const VIEWS = [
  (g) => svg("0 -10 120 120", g),
  (g) => svg("22 8 76 76", g),
  (g, c) => svg("0 -10 120 120", `<circle cx="60" cy="52" r="46" fill="${hexA(c, 0.13)}"/><circle cx="60" cy="52" r="34" fill="${hexA(c, 0.08)}"/><g transform="rotate(-9 60 55) translate(6 4) scale(.9)">${g}</g><path d="M96 20l2 5 5 2-5 2-2 5-2-5-5-2 5-2z" fill="${hexA(c, 0.45)}"/>`),
  (g) => svg("0 -10 120 120", `<g transform="translate(120 0) scale(-1 1)">${g}</g>`),
];

const DEFAULT_COLOR = { Banana: "#e8b923", Apple: "#d8262e", Pomegranate: "#b3122b", Orange: "#f28c1b", Grapes: "#88b62f", Headphones: "#1b3a55", Speaker: "#0f6a9c", Charger: "#1a7f9a", Ssd: "#155c86", Webcam: "#2a86b8", Lamp: "#b3561a", Plates: "#b85a1c", Flask: "#a8561f", Towels: "#c07a45", Board: "#c38c49", Basket: "#c9a36b", Soap: "#2e7d4f", SoapBar: "#d99a5b", Tomato: "#d8312a", Onion: "#9c4a6b", Leafy: "#2f8a3a" };

const out = (rel, text) => { const f = join(root, "public", rel); mkdirSync(dirname(f), { recursive: true }); writeFileSync(f, text); };
let n = 0;

for (const list of [data.SECTIONS, data.ALL_SECTIONS, [{ items: catalog.EXTRA_ITEMS }]]) {
  for (const s of list) {
    for (const p of s.items || []) {
      const g = inner({ art: p.art, color: p.color, label: p.label });
      (p.images || []).forEach((src, k) => { out(src.replace(/^\//, ""), VIEWS[k % VIEWS.length](g, p.color || DEFAULT_COLOR[p.art])); n++; });
    }
  }
}
for (const c of [...data.CATEGORIES, ...data.ALL_CATEGORIES]) {
  if (!c.image) continue;
  out(c.image.replace(/^\//, ""), svg("0 -10 120 120", inner({ art: c.art, color: c.color, label: c.t })));
  n++;
}
console.log(`Wrote ${n} images to public/images`);
