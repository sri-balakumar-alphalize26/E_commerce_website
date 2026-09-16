import type { Product } from '@/lib/catalog'

/**
 * Which drawing stands in for a product, and in what colour.
 *
 * The vendored art.jsx can draw twenty-one shapes. Choosing between them is
 * catalogue knowledge -- it depends on what this shop sells -- so it lives
 * here in the adapter layer rather than in a component, for the same reason
 * lib/catalog-config.ts holds the copy.
 *
 * MATCHED BY KEYWORD, not by a hand-written list of ids. A list would be
 * correct exactly once: the next product added would silently fall through
 * to a blank pack, and nobody would notice until it was on the grid. Rules
 * degrade gracefully instead -- a new cooking oil gets the bottle without
 * anyone editing this file.
 *
 * The fallbacks are per-vertical and deliberately dull. Books, fashion and
 * stationery have no shape that suits them, and a box is an honest way of
 * saying "a product" where a wrong drawing would be worse than a plain one.
 */

export type ArtKind =
  | 'Pack'
  | 'Bottle'
  | 'Box'
  | 'Jar'
  | 'Bar'
  | 'Banana'
  | 'Apple'
  | 'Pomegranate'
  | 'Orange'
  | 'Grapes'
  | 'Headphones'
  | 'Speaker'
  | 'Charger'
  | 'Ssd'
  | 'Webcam'
  | 'Lamp'
  | 'Plates'
  | 'Flask'
  | 'Towels'
  | 'Board'
  | 'Basket'

export type ArtSpec = {
  art: ArtKind
  color: string
  /** Two to four characters; it is printed inside the drawing. */
  label: string
}

/**
 * First match wins, so the specific comes before the general.
 *
 * EVERY PATTERN IS WORD-ANCHORED, and that is not fussiness. The first
 * draft matched bare substrings and produced a charger for "Organic Whole
 * Wheat Atta" and for "Desk Organiser" -- both contain "gan", as in GaN --
 * and a desk lamp for "Highlighter". A drawing that is confidently wrong is
 * worse on a grid than a plain box, because a shopper reads it before the
 * name and has to correct themselves.
 */
const RULES: Array<[RegExp, ArtKind, string]> = [
  [/(headphones?|earbuds?|headsets?)/i, 'Headphones', '#04384f'],
  [/(speakers?|soundbar)/i, 'Speaker', '#006090'],
  [/(charger|adapter|power bank|gan)/i, 'Charger', '#0078a8'],
  [/(ssd|hard drive|pen ?drive)/i, 'Ssd', '#024a70'],
  [/(webcam|camera)/i, 'Webcam', '#1890c0'],
  [/(lamps?|lights?|lighting|bulbs?)/i, 'Lamp', '#b84f00'],
  [/(dinner set|plates?|crockery|bowls?)/i, 'Plates', '#b85a1c'],
  [/(flask|thermos|vacuum)/i, 'Flask', '#a8561f'],
  [/(towels?|linen|bedsheet)/i, 'Towels', '#c07a45'],
  [/(board|chopping|cutting)/i, 'Board', '#c38c49'],
  [/(basket|hamper|organiser|organizer)/i, 'Basket', '#c9a36b'],
  [/bananas?/i, 'Banana', '#e8b923'],
  [/apples?/i, 'Apple', '#d8262e'],
  [/pomegranates?/i, 'Pomegranate', '#b3122b'],
  [/(oranges?|citrus)/i, 'Orange', '#f28c1b'],
  [/grapes?/i, 'Grapes', '#88b62f'],
  [/(oil|sauce|syrup|vinegar|juice)/i, 'Bottle', '#d4a017'],
  [/(coffee|tea|honey|jam|pickle|spread)/i, 'Jar', '#7a4a1e'],
  [/(chocolate|bars?|biscuits?|cookies?)/i, 'Bar', '#5c3317'],
  [/(salt|sugar|atta|flour|rice|dal|masala|powder)/i, 'Pack', '#1f7a4c'],
  [/(dry fruits?|nuts?|gift box|assorted)/i, 'Box', '#8a5a2b'],
]

const FALLBACK: Record<string, [ArtKind, string]> = {
  grocery: ['Pack', '#1f7a4c'],
  electronics: ['Box', '#024a70'],
  home: ['Box', '#b85a1c'],
  fashion: ['Box', '#8a4a6a'],
  stationery: ['Box', '#3a6ea5'],
  books: ['Box', '#6a4a8a'],
}

/**
 * A short mark for the front of the drawing.
 *
 * The pack size is the best thing to print -- "1L" or "5kg" is information a
 * shopper actually uses -- and it is already short enough for the 40px panel
 * it sits in. Anything longer, or absent, falls back to initials, which is
 * the same treatment ProductImage gives a product with no artwork at all.
 */
function labelFor(product: Product) {
  const pack = product.attributes.find((a) => a.key === 'weight' || a.key === 'pack')?.value
  if (pack && pack.length <= 5) return pack

  return (
    product.name
      .split(/\s+/)
      .filter((w) => /[a-z0-9]/i.test(w))
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase() ?? '')
      .join('') || 'MT'
  )
}

export function artFor(product: Product): ArtSpec {
  const haystack = `${product.name} ${product.subtitle}`

  for (const [test, art, color] of RULES) {
    if (test.test(haystack)) return { art, color, label: labelFor(product) }
  }

  const [art, color] = FALLBACK[product.vertical] ?? ['Pack', '#1f7a4c']
  return { art, color, label: labelFor(product) }
}
