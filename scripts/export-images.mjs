/* Draws the catalogue's product images into /public/images/products.
   Run:  npm run images

   Adapted from the 369mart-store drop's script. Two changes: it reads this
   shop's catalogue through lib/fixtures.ts instead of the drop's sample
   data, and it writes only products -- the category icons it also produced
   have no home here, because the category tiles use lucide icons.

   Replace the generated files with real photographs whenever you have them:
   same names, any web format, and only the extension in lib/fixtures.ts
   changes. */
import { build } from 'esbuild'
import { mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const tmp = join(root, '.images-tmp.mjs')

/* The catalogue is TypeScript and uses the @/ alias, so it is bundled
   rather than imported: esbuild resolves both, Node would do neither. */
await build({
  stdin: {
    contents: `
      import React from "react";
      import { renderToStaticMarkup } from "react-dom/server";
      import ProductArt from "./components/home/vendor/art.jsx";
      export { imageSpecs } from "./lib/fixtures.ts";
      export const render = (props) => renderToStaticMarkup(React.createElement(ProductArt, props));
    `,
    resolveDir: root,
    loader: 'jsx',
  },
  bundle: true,
  platform: 'node',
  format: 'esm',
  jsx: 'automatic',
  packages: 'external',
  loader: { '.js': 'jsx' },
  alias: { '@': root },
  outfile: tmp,
  logLevel: 'error',
})

const { imageSpecs, render } = await import(pathToFileURL(tmp).href + '?t=' + Date.now())
rmSync(tmp)

const inner = (p) => render(p).replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '')

const hexA = (hex = '#0078a8', a = 0.14) => {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map((x) => x + x).join('') : h, 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

const svg = (viewBox, body) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" width="600" height="600" font-family="Inter, Arial, sans-serif">${body}</svg>\n`

/* 1 front · 2 close-up · 3 angled on a soft backdrop · 4 back (mirrored) */
const VIEWS = [
  (g) => svg('0 -10 120 120', g),
  (g) => svg('22 8 76 76', g),
  (g, c) =>
    svg(
      '0 -10 120 120',
      `<circle cx="60" cy="52" r="46" fill="${hexA(c, 0.13)}"/><circle cx="60" cy="52" r="34" fill="${hexA(c, 0.08)}"/><g transform="rotate(-9 60 55) translate(6 4) scale(.9)">${g}</g><path d="M96 20l2 5 5 2-5 2-2 5-2-5-5-2 5-2z" fill="${hexA(c, 0.45)}"/>`,
    ),
  (g) => svg('0 -10 120 120', `<g transform="translate(120 0) scale(-1 1)">${g}</g>`),
]

const out = (rel, text) => {
  const file = join(root, 'public', rel)
  mkdirSync(dirname(file), { recursive: true })
  writeFileSync(file, text)
}

let n = 0
for (const spec of imageSpecs()) {
  const g = inner({ art: spec.art, color: spec.color, label: spec.label })
  spec.images.forEach((src, k) => {
    out(src.replace(/^\//, ''), VIEWS[k % VIEWS.length](g, spec.color))
    n++
  })
}

console.log(`wrote ${n} images`)
