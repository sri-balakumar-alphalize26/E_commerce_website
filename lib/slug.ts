import type { Product } from '@/lib/catalog'

/**
 * Slugs are cosmetic: the id in the URL is what resolves a product, so a
 * stale or mis-encoded slug still reaches the right page rather than 404ing.
 * That keeps shared links working after a product is renamed.
 */
export function slugify(name: string) {
  return name
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'item'
}

export function productHref(p: Pick<Product, 'vertical' | 'slug' | 'id'>) {
  return `/p/${p.vertical}/${p.slug}/${p.id}`
}

