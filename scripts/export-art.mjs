/* The app's built-in drawings (components/home/art.jsx), as SVG files Odoo
   can show.

   The storefront draws each one in React; Odoo's screens cannot, so the
   Catalogue desk's logo picker shows these files instead. Re-run whenever a
   drawing is added or changed in art.jsx:

     node scripts/export-art.mjs

   Writes odoo_modules/mart369/static/img/art/<Name>.svg, one per entry of
   the ART map, drawn in each drawing's own default colour. */
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const babel = require("next/dist/compiled/babel/core");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

const source = readFileSync(join(root, "components/home/art.jsx"), "utf8");
const { code } = babel.transformSync(source, {
  filename: "art.jsx",
  babelrc: false,
  configFile: false,
  presets: [[require.resolve("next/dist/compiled/babel/preset-react"), { runtime: "classic" }]],
  plugins: [require.resolve("next/dist/compiled/babel/plugin-transform-modules-commonjs")],
});
const mod = { exports: {} };
new Function("module", "exports", "require", "React", code)(mod, mod.exports, require, React);
const ProductArt = mod.exports.default;

const names = /const ART = \{([^}]*)\}/.exec(source)?.[1].split(",").map((s) => s.trim()).filter(Boolean);
if (!names?.length) throw new Error("No ART map found in art.jsx");

const out = join(root, "odoo_modules/mart369/static/img/art");
mkdirSync(out, { recursive: true });
for (const f of readdirSync(out)) if (f.endsWith(".svg")) rmSync(join(out, f));
for (const name of names) {
  const svg = renderToStaticMarkup(React.createElement(ProductArt, { art: name }))
    .replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ')
    .replace(/ role="img"| aria-hidden="true"| class="hm-art"/g, "");
  writeFileSync(join(out, `${name}.svg`), svg + "\n");
}
console.log(`${names.length} drawings -> ${out}`);
