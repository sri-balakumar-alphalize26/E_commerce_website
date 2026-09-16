import ProductCard from '@/components/catalogue/ProductCard'
import type { Product } from '@/lib/catalog'
import { cn } from '@/lib/cn'

/**
 * The column ladder, in one place.
 *
 * 2 / 2 / 3 / 4 / 5 at base / sm / md / lg / xl, dropping to 3 / 4 when a
 * facet rail takes 240px off the width. The reference stylesheet jumps
 * straight from 3 to 5 at 1100px, which leaves cards under 200px wide once
 * the rail is present -- so the ladder gains a step the original did not
 * have.
 */
export default function ProductGrid({
  items,
  withRail = false,
  priorityCount = 0,
  className,
}: {
  items: Product[]
  withRail?: boolean
  /** Eagerly load this many leading images -- the ones above the fold. */
  priorityCount?: number
  className?: string
}) {
  return (
    <ul
      className={cn(
        'grid grid-cols-2 gap-3',
        withRail ? 'md:grid-cols-3 xl:grid-cols-4' : 'md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5',
        className,
      )}
    >
      {items.map((p, i) => (
        <li key={p.id} className="contents">
          <ProductCard product={p} priority={i < priorityCount} />
        </li>
      ))}
    </ul>
  )
}
