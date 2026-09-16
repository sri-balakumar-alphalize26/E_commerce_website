import fs from 'node:fs'
import path from 'node:path'

/**
 * Generates pack-shot SVGs for the fixture catalogue.
 *
 * Four variants per product, mirroring what a real grocery listing carries:
 * a front pack, a reverse with a barcode, a nutrition panel and a statutory
 * label block. The last two are deliberately full of small text -- the
 * gallery has a hover-zoom, and a zoom over a flat colour proves nothing.
 */

const OUT = process.argv[2]
const SRC = process.argv[3]

const PALETTE = {
  grocery: ['#0e7a58', '#e8f6f0', '#0a5c43'],
  electronics: ['#0078a8', '#eaf6fb', '#024a70'],
  home: ['#b84f00', '#fff4e8', '#8a3c00'],
  fashion: ['#5b7183', '#f1f5f9', '#334155'],
  stationery: ['#1890c0', '#d0ecf6', '#006090'],
  books: ['#04384f', '#eaf6fb', '#052637'],
}

const esc = (s) =>
  String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')

function barcode(x, y, w, h, seed) {
  let bars = ''
  let cursor = x
  let s = seed
  while (cursor < x + w) {
    s = (s * 1103515245 + 12345) & 0x7fffffff
    const bw = 1 + (s % 4)
    if ((s >> 3) % 2 === 0) {
      bars += '<rect x="' + cursor + '" y="' + y + '" width="' + bw + '" height="' + h + '" fill="#0b1620"/>'
    }
    cursor += bw + 1 + ((s >> 5) % 2)
  }
  return bars
}

function front(o) {
  return [
    '<rect x="150" y="120" width="500" height="560" rx="18" fill="' + o.tint + '"/>',
    '<rect x="150" y="120" width="500" height="150" rx="18" fill="' + o.ink + '"/>',
    '<rect x="150" y="240" width="500" height="30" fill="' + o.ink + '"/>',
    '<text x="400" y="200" text-anchor="middle" font-family="sans-serif" font-size="46" font-weight="800" fill="#ffffff">' + esc(o.brand) + '</text>',
    '<text x="400" y="360" text-anchor="middle" font-family="sans-serif" font-size="96" font-weight="800" fill="' + o.deep + '" opacity="0.18">' + esc(o.initials) + '</text>',
    '<text x="400" y="452" text-anchor="middle" font-family="sans-serif" font-size="28" font-weight="700" fill="' + o.deep + '">' + esc(o.name.slice(0, 26)) + '</text>',
    '<rect x="300" y="492" width="200" height="4" fill="' + o.ink + '" opacity="0.35"/>',
    '<text x="400" y="546" text-anchor="middle" font-family="sans-serif" font-size="20" fill="' + o.deep + '" opacity="0.75">Quality assured</text>',
    '<rect x="556" y="576" width="84" height="84" rx="10" fill="#ffffff" stroke="' + o.ink + '" stroke-width="3"/>',
    '<text x="598" y="626" text-anchor="middle" font-family="sans-serif" font-size="21" font-weight="800" fill="' + o.ink + '">' + esc(o.pack) + '</text>',
    '<rect x="176" y="600" width="34" height="34" rx="4" fill="#ffffff" stroke="#0e7a58" stroke-width="3"/>',
    '<circle cx="193" cy="617" r="9" fill="#0e7a58"/>',
  ].join('')
}

function back(o) {
  let lines = ''
  for (let i = 0; i < 11; i++) {
    lines +=
      '<rect x="200" y="' + (300 + i * 22) + '" width="' + (400 - ((i * 53) % 180)) +
      '" height="7" rx="3" fill="' + o.deep + '" opacity="0.28"/>'
  }
  return [
    '<rect x="150" y="120" width="500" height="560" rx="18" fill="#ffffff" stroke="' + o.tint + '" stroke-width="10"/>',
    '<text x="200" y="215" font-family="sans-serif" font-size="24" font-weight="800" fill="' + o.ink + '">PRODUCT INFORMATION</text>',
    '<rect x="200" y="235" width="400" height="3" fill="' + o.ink + '" opacity="0.4"/>',
    '<text x="200" y="278" font-family="sans-serif" font-size="14" font-weight="700" fill="' + o.deep + '">Storage, usage and manufacturer details</text>',
    lines,
    barcode(232, 566, 336, 72, o.id),
    '<text x="400" y="662" text-anchor="middle" font-family="monospace" font-size="17" fill="#0b1620">8 90' + o.id + ' 0' + o.id + ' 4</text>',
  ].join('')
}

function nutrition(o) {
  const rows = [
    ['Energy', '482 kcal'], ['Protein', '6.8 g'], ['Carbohydrate', '62.1 g'],
    ['of which sugars', '21.4 g'], ['Total Fat', '22.3 g'], ['Saturated fat', '11.2 g'],
    ['Trans fat', '0.0 g'], ['Dietary fibre', '1.9 g'], ['Sodium', '312 mg'],
    ['Calcium', '118 mg'], ['Iron', '2.4 mg'],
  ]
  let body = ''
  rows.forEach((r, i) => {
    body +=
      '<rect x="200" y="' + (300 + i * 30) + '" width="400" height="30" fill="' + (i % 2 ? o.tint : '#ffffff') + '" opacity="0.65"/>' +
      '<text x="212" y="' + (320 + i * 30) + '" font-family="sans-serif" font-size="15" fill="#0b1620">' + esc(r[0]) + '</text>' +
      '<text x="588" y="' + (320 + i * 30) + '" text-anchor="end" font-family="sans-serif" font-size="15" font-weight="700" fill="#0b1620">' + esc(r[1]) + '</text>'
  })
  return [
    '<rect x="150" y="120" width="500" height="560" rx="18" fill="#ffffff" stroke="' + o.tint + '" stroke-width="10"/>',
    '<text x="200" y="212" font-family="sans-serif" font-size="24" font-weight="800" fill="' + o.ink + '">NUTRITION FACTS</text>',
    '<text x="200" y="240" font-family="sans-serif" font-size="14" fill="' + o.deep + '">Approximate values per 100 g</text>',
    '<rect x="200" y="258" width="400" height="3" fill="' + o.ink + '"/>',
    '<rect x="200" y="272" width="400" height="24" fill="' + o.ink + '" opacity="0.12"/>',
    '<text x="212" y="289" font-family="sans-serif" font-size="13" font-weight="800" fill="' + o.deep + '">NUTRIENT</text>',
    '<text x="588" y="289" text-anchor="end" font-family="sans-serif" font-size="13" font-weight="800" fill="' + o.deep + '">PER 100 G</text>',
    body,
    '<rect x="200" y="630" width="400" height="3" fill="' + o.ink + '"/>',
    '<text x="200" y="656" font-family="sans-serif" font-size="12" fill="' + o.deep + '">Percentage daily values based on a 2000 kcal diet.</text>',
  ].join('')
}

function label(o) {
  return [
    '<rect x="150" y="120" width="500" height="560" rx="18" fill="' + o.tint + '"/>',
    '<rect x="215" y="200" width="370" height="150" rx="10" fill="#ffffff" stroke="' + o.ink + '" stroke-width="3"/>',
    '<text x="400" y="252" text-anchor="middle" font-family="sans-serif" font-size="30" font-weight="800" fill="' + o.ink + '">FSSAI</text>',
    '<text x="400" y="288" text-anchor="middle" font-family="sans-serif" font-size="16" fill="' + o.deep + '">Lic. No.</text>',
    '<text x="400" y="322" text-anchor="middle" font-family="monospace" font-size="24" font-weight="700" fill="#0b1620">100' + o.id + '430' + o.id + '</text>',
    '<rect x="215" y="386" width="370" height="130" rx="10" fill="#ffffff" stroke="' + o.ink + '" stroke-width="3"/>',
    '<text x="400" y="430" text-anchor="middle" font-family="sans-serif" font-size="15" font-weight="700" fill="' + o.deep + '">BEST BEFORE</text>',
    '<text x="400" y="466" text-anchor="middle" font-family="sans-serif" font-size="22" font-weight="800" fill="#0b1620">9 MONTHS FROM</text>',
    '<text x="400" y="496" text-anchor="middle" font-family="sans-serif" font-size="22" font-weight="800" fill="#0b1620">PACKAGING DATE</text>',
    '<text x="400" y="566" text-anchor="middle" font-family="sans-serif" font-size="13" fill="' + o.deep + '">Marketed by 369 Mart Retail Pvt Ltd</text>',
    '<text x="400" y="590" text-anchor="middle" font-family="sans-serif" font-size="13" fill="' + o.deep + '">Customer care: care@369mart.example</text>',
    '<text x="400" y="614" text-anchor="middle" font-family="sans-serif" font-size="13" fill="' + o.deep + '">Batch ' + o.id + '-A7 - keep in a cool dry place</text>',
  ].join('')
}

const VARIANTS = { front, back, nutrition, label }

const src = fs.readFileSync(SRC, 'utf8')

/*
 * Whitespace-tolerant on purpose.
 *
 * The first version anchored to a single-line row shape. A formatter later
 * reflowed ROWS across multiple lines and this pattern silently matched
 * nothing: the script reported success, wrote no files, and would have
 * shipped 152 images nobody could regenerate. Matching across newlines makes
 * it survive reformatting, and the guard below makes any future mismatch
 * loud rather than silent.
 */
const re = /\[\s*'([a-z]+)',\s*'((?:[^'\\]|\\.)*)',\s*'((?:[^'\\]|\\.)*)'/g

/*
 * Scoped to the ROWS array, not the whole file.
 *
 * Loosening the pattern to survive reformatting also made it match two
 * unrelated literals further down -- the FACETABLE set and GALLERY_VARIANTS
 * -- which produced art for two products that do not exist. They happened to
 * sit after the real rows, so ids stayed aligned and the damage was eight
 * orphan files; had they sat before, every product's artwork would have been
 * attached to the wrong product. Bounding the search removes that class of
 * failure rather than the one instance of it.
 */
const START = src.indexOf('const ROWS: Row[] = [')
const END = src.indexOf('\n]', START)
if (START === -1 || END === -1) {
  console.error(`Could not locate the ROWS array in ${SRC}.`)
  process.exit(1)
}

const rows = [...src.slice(START, END).matchAll(re)]

if (!rows.length) {
  console.error(
    [
      `No product rows matched in ${SRC}.`,
      'The ROWS literal has changed shape. Fix the pattern rather than',
      'accepting an empty run: writing nothing looks like success while',
      'leaving the existing art in place, silently unregenerated.',
    ].join('\n'),
  )
  process.exit(1)
}

fs.mkdirSync(OUT, { recursive: true })
let n = 0
rows.forEach((m, i) => {
  const vertical = m[1]
  const name = m[2]
  const brand = m[3]
  const id = 1000 + i
  const pal = PALETTE[vertical] || PALETTE.grocery
  const packMatch = name.match(/(\d+\s?(?:g|kg|ml|L))\b/i)
  const initials = name
    .split(/\s+/)
    .filter((w) => /[a-z0-9]/i.test(w))
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')

  const o = {
    id,
    name,
    brand,
    pack: packMatch ? packMatch[1] : 'PACK',
    ink: pal[0],
    tint: pal[1],
    deep: pal[2],
    initials,
  }

  for (const key of Object.keys(VARIANTS)) {
    const inner = VARIANTS[key](o)
    const svg =
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="800" height="800" role="img">' +
      '<rect width="800" height="800" fill="#ffffff"/>' +
      inner +
      '</svg>'
    fs.writeFileSync(path.join(OUT, id + '-' + key + '.svg'), svg)
    n++
  }
})
console.log('generated ' + n + ' images for ' + rows.length + ' products')
