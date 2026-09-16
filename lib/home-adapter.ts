import type { Product } from '@/lib/catalog'
import { productHref } from '@/lib/slug'
import { CATALOG } from '@/lib/catalog-config'
import { PRODUCTS, listProducts } from '@/lib/fixtures'

/**
 * Maps this app's catalogue onto the vendored home design's prop shape.
 *
 * The whole point of this module is that nothing in components/home/vendor
 * ever learns what a `Product` is. The design was written against its own
 * item shape; rather than editing it to match ours -- which would make it
 * undiffable against the upstream zip -- the translation happens here, once.
 *
 * It runs on the SERVER. The wrapper is a client component because the cart
 * and delivery mode are client state, but the catalogue itself is resolved
 * here and handed down as serialised props, so no fixture data reaches the
 * browser bundle.
 */

export type HomeItem = {
  id: number
  name: string
  unit: string
  price: number
  mrp?: number
  image?: string
  /** The full pack-shot set, so the card can page through it. */
  images?: string[]
  veg?: boolean
  stock?: number
  /** Units remaining, shown only when stock is low. */
  low?: number
  perUnit?: string
  tag?: string
  /** Stocked locally, so eligible for the fast promise. */
  quick?: boolean
  /**
   * Where the card goes when tapped.
   *
   * The design ships its cards with nothing to click -- it was drawn for a
   * shop whose product page did not exist yet -- so this is supplied here
   * rather than built in the component, which is not allowed to know how
   * this app routes.
   */
  href: string
}

export type HomeBanner = {
  id: string
  /** Where the banner goes when tapped. */
  href: string
  kicker: string
  title: string
  note: string
  tone: string
  /**
   * Names resolved by vendor/art.jsx, which draws each as an inline SVG.
   * Required, not optional: the design maps over it unconditionally, so
   * omitting it is a prerender crash rather than a missing illustration.
   */
  art: string[]
}

export type HomeCategory = {
  key: string
  label: string
  href: string
}

/**
 * A rail carries PRODUCTS, not display items.
 *
 * The wrapper needs the full Product to write to the cart -- addProduct
 * builds a CartLine from it, carrying price, image, minQty, qtyStep and
 * stock. Handing the client only the display shape would mean fetching
 * the product back again on the first tap of ADD.
 *
 * This is not the catalogue leak that SearchBar and My List both hit:
 * those imported the whole fixture module into a client CHUNK loaded on
 * every route. These are page props for the products this page already
 * renders, so nothing travels that the HTML does not already contain.
 */
export type HomeRail = {
  key: string
  title: string
  /** The rail's "View all" destination. */
  href?: string
  subtitle?: string
  products: Product[]
  /** Banner ids to place after this rail. */
  bannerAfter?: string[]
}

/** The pack or weight attribute, which the design shows under the name. */
function unitOf(p: Product) {
  return p.attributes.find((a) => a.key === 'weight' || a.key === 'pack')?.value ?? ''
}

export function toHomeItem(p: Product): HomeItem {
  return {
    id: p.id,
    href: productHref(p),
    name: p.name,
    unit: unitOf(p),
    price: p.price,
    // Only when it is genuinely higher -- the design strikes through whatever
    // it is given, and a struck price equal to the asking price is a lie the
    // customer can spot.
    mrp: p.originalPrice > p.price ? p.originalPrice : undefined,
    // art.jsx draws a placeholder illustration only when `image` is absent.
    // Every product here has a generated pack-shot, so the illustrations are
    // skipped entirely.
    image: p.image,
    images: p.images,
    veg: p.vertical === 'grocery',
    stock: p.stock,
    // The design renders `Only {low} left`, so this is the COUNT, not a
    // flag. Passing a boolean printed "Only  left" with a hole in it.
    low: p.stockStatus === 'low' ? p.stock : undefined,
    // Quick is NOT a corner tag. The card already shows a Quick chip
    // under the price, and the corner slot shares its position with the
    // discount badge -- a product that is both discounted and quick had
    // the two stacked on top of each other. The corner is for something
    // a product can only be one of.
    // The corner slot holds ONE thing. The design positions the discount
    // badge and the tag identically, so a product that is both New and
    // discounted stacks them -- which is the bug this started as. The
    // discount is the one a shopper acts on, so it wins.
    tag: p.badge === 'New' && p.discountPercent < 10 ? 'New' : undefined,
    quick: p.quickDelivery,
  }
}

/**
 * Illustrations per slide, keyed by the slide it belongs to.
 *
 * art.jsx ships 21 drawings and the design expects two or three per
 * banner. These are chosen to match the copy rather than picked at
 * random -- the offers slide shows things that are actually discounted.
 */
const SLIDE_ART: Record<string, string[]> = {
  deals: ['Headphones', 'Speaker', 'Box'],
  essentials: ['Pack', 'Bottle', 'Jar'],
  new: ['Lamp', 'Flask', 'Plates'],
}

export function homeBanners(): HomeBanner[] {
  return CATALOG.slides.map((s) => ({
    id: s.key,
    href: s.href,
    kicker: s.subtitle,
    title: s.title,
    note: s.cta,
    tone: s.tone,
    art: SLIDE_ART[s.key] ?? ['Pack', 'Box'],
  }))
}

export function homeCategories(): HomeCategory[] {
  return CATALOG.tiles.map((t) => ({ key: t.key, label: t.label, href: t.href }))
}

/**
 * The rails, with a banner row interleaved.
 *
 * The design supports a `{ banner: [ids] }` entry between rails, which is
 * what keeps a long home page from reading as an undifferentiated stack of
 * carousels. One break, after the second rail.
 */
export function homeRails(): HomeRail[] {
  return CATALOG.rails.map((rail, i) => {
    const source = rail.source.vertical
    const products = source ? listProducts(source) : PRODUCTS.filter((p) => p.discountPercent > 0)

    return {
      key: rail.key,
      title: rail.title,
      href: rail.href,
      subtitle: rail.subtitle,
      products: products.slice(0, 12),
      // One banner break, after the second rail. Without it a long home
      // page reads as an undifferentiated stack of carousels.
      bannerAfter: i === 1 ? CATALOG.slides.slice(0, 2).map((s) => s.key) : undefined,
    }
  })
}
