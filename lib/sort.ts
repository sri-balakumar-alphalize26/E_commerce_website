import type { Product, SortKey } from '@/lib/catalog'

/**
 * Client-side sorting.
 *
 * The eventual backend exposes no sort parameter, so sorting happens over
 * whatever page has been fetched. That is a real limitation and the UI is
 * required to say so rather than label a page-local sort as if it were
 * global — see ResultsHeader. Sorting a single page and calling it
 * "Price: low to high" is a lie a customer catches on page two.
 */

export const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'default', label: 'Default order' },
  { key: 'price_asc', label: 'Price: low to high' },
  { key: 'price_desc', label: 'Price: high to low' },
  { key: 'discount_desc', label: 'Discount' },
  { key: 'name_asc', label: 'Name: A to Z' },
  { key: 'name_desc', label: 'Name: Z to A' },
]

const COMPARATORS: Record<SortKey, ((a: Product, b: Product) => number) | null> = {
  default: null,
  price_asc: (a, b) => a.price - b.price,
  price_desc: (a, b) => b.price - a.price,
  discount_desc: (a, b) => b.discountPercent - a.discountPercent,
  name_asc: (a, b) => a.name.localeCompare(b.name),
  name_desc: (a, b) => b.name.localeCompare(a.name),
}

export function sortProducts(items: Product[], key: SortKey) {
  const cmp = COMPARATORS[key]
  if (!cmp) return items
  // Out-of-stock items sink to the bottom under every ordering. A shopper
  // sorting by price does not want the cheapest thing they cannot buy.
  return [...items].sort((a, b) => {
    if (a.inStock !== b.inStock) return a.inStock ? -1 : 1
    return cmp(a, b)
  })
}

export function isSortKey(v: string | undefined): v is SortKey {
  return !!v && SORT_OPTIONS.some((o) => o.key === v)
}
