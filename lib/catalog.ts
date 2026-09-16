/**
 * The vertical-agnostic product model.
 *
 * Every component in components/catalogue, components/product and
 * components/cart is written against THIS type and nothing else. What the
 * shop actually sells is declared in lib/catalog-config.ts; the shape of
 * whatever backend eventually feeds it is absorbed by an adapter.
 *
 * That is the whole point of the indirection, and it is why `subtitle`,
 * `badge` and `attributes` exist as generic slots rather than as
 * `author`, `language` and `packLabel`. A component that reaches for a
 * domain-specific field has broken the seam, and the fix belongs in the
 * adapter rather than in the component.
 */

export type VerticalId = string

export type StockStatus = 'ok' | 'low' | 'out'

/**
 * One displayable fact about a product.
 *
 * `facetId` carries the backend's own id when that attribute can be
 * filtered server-side. When it is null the value can still be faceted,
 * but only across the items already fetched — which the UI must say out
 * loud rather than implying the count is global.
 */
export type Attribute = {
  /** Stable machine key, e.g. 'brand'. Never shown to a user. */
  key: string
  label: string
  value: string
  /** Set instead of `value` when the attribute is multi-valued. */
  values?: string[]
  facetId?: number | string | null
  kind?: 'text' | 'chips' | 'html' | 'number' | 'date'
}

export type Product = {
  vertical: VerticalId
  /** Doubles as the cart key and the detail-route key. */
  id: number
  slug: string
  name: string
  /** The single line under the card title. */
  subtitle: string
  /** Corner chip on the card. Null renders nothing. */
  badge: string | null
  currency: string
  price: number
  /** List price / MRP. Struck through when it exceeds `price`. */
  originalPrice: number
  discountPercent: number
  stock: number
  stockStatus: StockStatus
  inStock: boolean
  /**
   * The card thumbnail, and always `images[0]`.
   *
   * Kept as its own field because the cart snapshots it onto a line at the
   * moment of adding: a line has one picture, not a gallery, and it must
   * survive the product's gallery being re-ordered later.
   */
  image: string
  /**
   * The full gallery, largest first usable size.
   *
   * The listing payload carries the whole set, not just the thumbnail,
   * because the product CARD is itself a carousel -- a customer pages
   * through the pack-shots without leaving the grid.
   */
  images: string[]
  /** Smallest quantity that may be added. Usually 1. */
  minQty: number
  /** Quantity increment. Usually 1; packs may step by more. */
  qtyStep: number
  /**
   * Stocked in the local dark store, so it can go out on the fast
   * delivery promise. The Quick / Express toggle filters on this.
   */
  quickDelivery: boolean
  attributes: Attribute[]
}

export type ProductDetail = Product & {
  shortDescription: string
  /** Pre-sanitised on the server. Never sanitise in a client component. */
  descriptionHtml: string

  /* ---- the detail sections a grocery listing carries ---------------
     Kept as separate typed slots rather than one blob so the page can
     omit a section entirely when a product has nothing for it, instead
     of rendering an empty heading. */

  /** Short scannable claims, shown as bullets above the tables. */
  keyFeatures: string[]
  /** Brand, seller, origin, manufacturer, dimensions, article id. */
  productInfo: Attribute[]
  /** Net quantity, product type -- the narrower table beneath. */
  specifications: Attribute[]
  /** Marketing prose. Plain text; the page decides the typography. */
  showcase: string
}

export type SortKey =
  'default' | 'price_asc' | 'price_desc' | 'name_asc' | 'name_desc' | 'discount_desc'

export function savings(p: Pick<Product, 'price' | 'originalPrice'>) {
  return Math.max(0, p.originalPrice - p.price)
}

/**
 * Clamp a requested quantity onto the product's pack rules and its stock.
 *
 * Steps are measured from `minQty`, not from zero: a product with
 * minQty 2 and qtyStep 3 sells 2, 5, 8 — not 3, 6, 9.
 *
 * The stock ceiling lives here rather than in the control that renders the
 * plus button. A disabled button is a courtesy, not an invariant: it can be
 * bypassed by a stale cart, a restored session or any future caller, and a
 * domain that will happily hold twelve of a product with three in stock is
 * one that eventually sends that quantity to a checkout.
 */
export function clampQty(p: Pick<Product, 'minQty' | 'qtyStep'> & { stock?: number }, qty: number) {
  const min = p.minQty > 0 ? p.minQty : 1
  const step = p.qtyStep > 0 ? p.qtyStep : 1
  const wanted = qty <= min ? min : min + Math.ceil((qty - min) / step) * step

  if (p.stock === undefined) return wanted
  if (p.stock < min) return min
  // Step back down to a legal multiple that still fits the stock on hand.
  return wanted <= p.stock ? wanted : min + Math.floor((p.stock - min) / step) * step
}
