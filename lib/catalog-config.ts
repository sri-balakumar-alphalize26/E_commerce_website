import type { Product, SortKey, VerticalId } from '@/lib/catalog'

/**
 * THE SWITCHBOARD.
 *
 * Everything that knows what this shop SELLS lives in this file. No
 * component anywhere names a product category, a brand, or a piece of
 * marketing copy -- they read it from here.
 *
 * The product vertical is deliberately undecided for now. Re-pointing the
 * storefront at a real catalogue means editing this file and writing one
 * adapter; no route moves and no component changes. If changing what the
 * shop sells ever requires touching components/, the abstraction has
 * leaked and the fix belongs in the adapter rather than in the component.
 */

/**
 * Tile accents are named by role, not by hue, and every one of them
 * resolves to a pair drawn from the two logo ramps -- brand blue/cyan and
 * the orange arrow. Adding a seventh accent means adding a seventh ramp
 * position, not inventing a new colour.
 */
export type TileAccent = 'brand' | 'brand-deep' | 'cyan' | 'accent' | 'accent-deep' | 'neutral'

export type CategoryTile = {
  key: string
  label: string
  /** lucide-react icon name, resolved in components/home/CategoryTiles.tsx */
  icon: string
  accent: TileAccent
  href: string
}

export type PromoSlide = {
  key: string
  title: string
  subtitle: string
  cta: string
  href: string
  tone: 'brand' | 'deep' | 'accent'
}

export type HomeRail = {
  key: string
  title: string
  subtitle?: string
  href: string
  source: { vertical: VerticalId | null }
}

export type Collection = {
  key: string
  title: string
  subtitle: string
  /** Applied client-side. There is no "deals" concept in the data. */
  filter?: (p: Product) => boolean
  sort?: SortKey
}

export type VerticalMeta = {
  id: VerticalId
  label: string
  /** Plural noun for empty states: "No electronics match these filters." */
  noun: string
  icon: string
}

export const CATALOG = {
  brand: {
    // One string, referenced everywhere. Change it here and it changes
    // across the header, footer, metadata, OG images and page titles.
    name: '369 Mart',
    short: '369',
    tagline: 'Beyond control. Beyond growth.',
    deliveryLabel: 'Deliver to',
  },

  /*
   * The two delivery modes, named in one place.
   *
   * These labels were hardcoded inline in five separate files, which is
   * the thing this module exists to prevent -- renaming one of them meant
   * finding all five and getting every aria-label and every sentence of
   * body copy to agree. They are copy, so they live here.
   *
   * The KEYS are the stored values and must not change: 'all' is what sits
   * in store.prefs.mode.v1 on every returning customer's device, and
   * renaming it would silently reset their choice. Only the label moved.
   *
   * `title` and `sub` are what the switch overlay announces mid-transition;
   * `label` is the button itself.
   */
  modes: {
    quick: {
      label: 'Quick',
      title: 'Quick',
      sub: 'Only what the local store has on the shelf',
    },
    all: {
      label: 'Express',
      title: 'Express',
      sub: 'The full range, delivered to your door',
    },
  },

  /** Order here is the order of the category strip and the vertical tabs. */
  verticals: [
    { id: 'grocery', label: 'Grocery', noun: 'grocery items', icon: 'ShoppingBasket' },
    { id: 'electronics', label: 'Electronics', noun: 'electronics', icon: 'Smartphone' },
    { id: 'home', label: 'Home & Kitchen', noun: 'home products', icon: 'Lamp' },
    { id: 'fashion', label: 'Fashion', noun: 'fashion items', icon: 'Shirt' },
    { id: 'stationery', label: 'Stationery', noun: 'stationery', icon: 'PenLine' },
    { id: 'books', label: 'Books', noun: 'books', icon: 'BookOpen' },
  ] satisfies VerticalMeta[],

  /*
   * There is deliberately no delivery fee, free-delivery threshold or
   * delivery-date estimate here.
   *
   * Nothing in this build -- and nothing in the backend that follows it --
   * can compute shipping or serviceability, so a "free delivery over 499"
   * meter would be a number that moves convincingly and means nothing, and
   * a "get it by Tuesday" line would be a promise with no fulfilment behind
   * it. A policy sentence stated once is honest; a calculated figure is not.
   */
  shippingNote: 'Dispatched within 24 hours of order confirmation',

  /** Statutory wording, identical for every product, so it lives here. */
  disclaimer:
    'Despite our attempts to provide the most accurate information possible, the actual packaging, material, ingredients and colour of the product may sometimes vary. Please read the label, directions and warnings carefully before use.',

  tiles: [
    {
      key: 'grocery',
      label: 'Grocery',
      icon: 'ShoppingBasket',
      accent: 'brand',
      href: '/c/grocery',
    },
    {
      key: 'electronics',
      label: 'Electronics',
      icon: 'Smartphone',
      accent: 'brand-deep',
      href: '/c/electronics',
    },
    { key: 'home', label: 'Home', icon: 'Lamp', accent: 'cyan', href: '/c/home' },
    { key: 'fashion', label: 'Fashion', icon: 'Shirt', accent: 'neutral', href: '/c/fashion' },
    {
      key: 'stationery',
      label: 'Stationery',
      icon: 'PenLine',
      accent: 'accent-deep',
      href: '/c/stationery',
    },
    { key: 'offers', label: 'Offers', icon: 'Tag', accent: 'accent', href: '/collection/deals' },
  ] satisfies CategoryTile[],

  slides: [
    {
      key: 'deals',
      title: 'Up to 45% off',
      subtitle: 'Across grocery, home and electronics',
      cta: 'Shop offers',
      href: '/collection/deals',
      tone: 'brand',
    },
    {
      key: 'essentials',
      title: 'Everyday essentials',
      subtitle: 'Restocked daily, delivered fast',
      cta: 'Browse grocery',
      href: '/c/grocery',
      tone: 'deep',
    },
    {
      key: 'new',
      title: 'Just arrived',
      subtitle: 'Fresh picks across every aisle',
      cta: 'See new',
      href: '/collection/new',
      tone: 'accent',
    },
  ] satisfies PromoSlide[],

  rails: [
    {
      key: 'deals',
      title: 'Top offers',
      subtitle: 'Biggest savings right now',
      href: '/collection/deals',
      source: { vertical: null },
    },
    {
      key: 'grocery',
      title: 'Daily essentials',
      href: '/c/grocery',
      source: { vertical: 'grocery' },
    },
    {
      key: 'electronics',
      title: 'Tech picks',
      href: '/c/electronics',
      source: { vertical: 'electronics' },
    },
    { key: 'home', title: 'For your home', href: '/c/home', source: { vertical: 'home' } },
  ] satisfies HomeRail[],

  collections: [
    {
      key: 'deals',
      title: 'Top offers',
      subtitle: 'Everything currently discounted',
      filter: (p) => p.discountPercent > 0,
      sort: 'discount_desc',
    },
    {
      key: 'new',
      title: 'New arrivals',
      subtitle: 'Recently added to the catalogue',
      filter: (p) => p.badge === 'New',
    },
  ] satisfies Collection[],
}

export const VERTICAL_IDS = CATALOG.verticals.map((v) => v.id)

export function getVertical(id: string): VerticalMeta | null {
  return CATALOG.verticals.find((v) => v.id === id) ?? null
}

export function getCollection(key: string): Collection | null {
  return CATALOG.collections.find((c) => c.key === key) ?? null
}

/**
 * True when the shop sells one thing. Vertical tabs, the category strip and
 * the /c index redirect all collapse in that case, so a single-vertical
 * catalogue needs no dead code removed.
 */
export const IS_SINGLE_VERTICAL = CATALOG.verticals.length === 1
