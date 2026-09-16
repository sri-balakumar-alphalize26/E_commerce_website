import ProductCard from '@/components/catalogue/ProductCard'
import type { Product } from '@/lib/catalog'

/**
 * Returns null on an empty list rather than rendering a "nothing to show"
 * block -- an empty section header is worse than no section.
 */
export default function SimilarItems({ items }: { items: Product[] }) {
  if (!items.length) return null

  return (
    <section className="mt-10">
      <h2 className="text-ink font-display mb-3 text-base font-bold tracking-tight md:text-lg">
        Similar products
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {items.map((p) => (
          <ProductCard key={p.id} product={p} />
        ))}
      </div>
    </section>
  )
}
