import type { Attribute, Product } from '@/lib/catalog'

/**
 * Facet values derived from the items already fetched.
 *
 * There is no backend endpoint that enumerates attribute values, so counts
 * describe the current result set and nothing more. Every label rendered
 * from this must say "in these results" — a count that looks global but is
 * not is worse than no count.
 */

export type FacetValue = {
  value: string
  count: number
}

export type DerivedFacet = {
  key: string
  label: string
  values: FacetValue[]
}

export function deriveFacets(items: Product[], maxPerFacet = 8): DerivedFacet[] {
  const byKey = new Map<string, { label: string; counts: Map<string, number> }>()

  for (const item of items) {
    for (const attr of item.attributes) {
      if (attr.facetId === null || attr.facetId === undefined) continue
      let bucket = byKey.get(attr.key)
      if (!bucket) {
        bucket = { label: attr.label, counts: new Map() }
        byKey.set(attr.key, bucket)
      }
      for (const v of valuesOf(attr)) {
        bucket.counts.set(v, (bucket.counts.get(v) ?? 0) + 1)
      }
    }
  }

  return [...byKey.entries()]
    .map(([key, { label, counts }]) => ({
      key,
      label,
      values: [...counts.entries()]
        .map(([value, count]) => ({ value, count }))
        .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
        .slice(0, maxPerFacet),
    }))
    // A facet where every item shares the same value filters nothing.
    .filter((f) => f.values.length > 1)
    .sort((a, b) => a.label.localeCompare(b.label))
}

function valuesOf(attr: Attribute) {
  return attr.values && attr.values.length ? attr.values : [attr.value]
}

export function applyFacets(items: Product[], selected: Record<string, string[]>) {
  const active = Object.entries(selected).filter(([, vs]) => vs.length > 0)
  if (!active.length) return items
  return items.filter((item) =>
    active.every(([key, wanted]) => {
      const attr = item.attributes.find((a) => a.key === key)
      if (!attr) return false
      const vals = valuesOf(attr)
      return wanted.some((w) => vals.includes(w))
    }),
  )
}

export function priceBounds(items: Product[]) {
  if (!items.length) return { min: 0, max: 0 }
  let min = Infinity
  let max = 0
  for (const p of items) {
    if (p.price < min) min = p.price
    if (p.price > max) max = p.price
  }
  return { min: Math.floor(min), max: Math.ceil(max) }
}
