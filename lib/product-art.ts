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
  [/\b(headphones?|earbuds?|headsets?)\b/i, 'Headphones', '#04384f'],
  [/\b(speakers?|soundbar)\b/i, 'Speaker', '#006090'],
  [/\b(charger|adapter|power bank|gan)\b/i, 'Charger', '#0078a8'],
  [/\b(ssd|hard drive|pen ?drive)\b/i, 'Ssd', '#024a70'],
  [/\b(webcam|camera)\b/i, 'Webcam', '#1890c0'],
  [/\b(lamps?|lights?|lighting|bulbs?)\b/i, 'Lamp', '#b84f00'],
  [/\b(dinner set|plates?|crockery|bowls?)\b/i, 'Plates', '#b85a1c'],
  [/\b(flask|thermos|vacuum)\b/i, 'Flask', '#a8561f'],
  [/\b(towels?|linen|bedsheet)\b/i, 'Towels', '#c07a45'],
  [/\b(board|chopping|cutting)\b/i, 'Board', '#c38c49'],
  [/\b(basket|hamper|organiser|organizer)\b/i, 'Basket', '#c9a36b'],
  [/\bbananas?\b/i, 'Banana', '#e8b923'],
  [/\bapples?\b/i, 'Apple', '#d8262e'],
  [/\bpomegranates?\b/i, 'Pomegranate', '#b3122b'],
  [/\b(oranges?|citrus)\b/i, 'Orange', '#f28c1b'],
  [/\bgrapes?\b/i, 'Grapes', '#88b62f'],
  [/\b(oil|sauce|syrup|vinegar|juice)\b/i, 'Bottle', '#d4a017'],
  [/\b(coffee|tea|honey|jam|pickle|spread)\b/i, 'Jar', '#7a4a1e'],
  [/\b(chocolate|bars?|biscuits?|cookies?)\b/i, 'Bar', '#5c3317'],
  [/\b(salt|sugar|atta|flour|rice|dal|masala|powder)\b/i, 'Pack', '#1f7a4c'],
  [/\b(dry fruits?|nuts?|gift box|assorted)\b/i, 'Box', '#8a5a2b'],
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
