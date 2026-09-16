import Image from 'next/image'
import { cn } from '@/lib/cn'
import { isVector } from '@/lib/image'

/**
 * Product artwork, with a branded fallback.
 *
 * The fixture catalogue carries no imagery, and a real catalogue will
 * always have some products whose image is missing or 404s. Rendering a
 * broken-image glyph in a grid of twenty cards is the single fastest way to
 * make a storefront look unfinished, so the absent case gets a deliberate
 * treatment instead: the product's initials on a soft brand tint.
 *
 * Because the fallback is keyed off the product id, the same product always
 * draws the same tint -- the grid reads as varied rather than as a column
 * of identical placeholders, and it does not flicker between renders.
 */

const TINTS = [
  'bg-brand-50 text-brand-600',
  'bg-brand-100 text-brand-700',
  'bg-accent-50 text-accent-600',
  'bg-surface-alt text-slate-muted',
  'bg-brand-50 text-brand-500',
  'bg-accent-100 text-accent-700',
]

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter((w) => /[a-z0-9]/i.test(w))
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
}

type Props = {
  id: number
  src: string
  alt: string
  /** Rendered width hint for the optimizer. */
  sizes?: string
  priority?: boolean
  /**
   * Forwarded to next/image.
   *
   * Worth setting to 'eager' for art that is mounted deliberately rather
   * than scrolled to: native lazy loading measures intersection with the
   * viewport, so an image parked off-axis inside a clipped scroller never
   * qualifies and never fetches until it is scrolled in -- which is one
   * frame too late for a carousel slide.
   */
  loading?: 'eager' | 'lazy'
  className?: string
}

export default function ProductImage({ id, src, alt, sizes, priority, loading, className }: Props) {
  if (!src) {
    return (
      <div
        className={cn(
          'flex aspect-square w-full items-center justify-center',
          TINTS[id % TINTS.length],
          className,
        )}
        // The alt text lives on the wrapper's aria-label because there is
        // no img element to carry it.
        role="img"
        aria-label={alt}
      >
        <span className="font-display text-2xl font-bold tracking-tight select-none">
          {initials(alt)}
        </span>
      </div>
    )
  }

  return (
    <div className={cn('bg-surface relative aspect-square w-full overflow-hidden', className)}>
      <Image
        src={src}
        alt={alt}
        fill
        sizes={sizes ?? '(min-width: 1360px) 240px, (min-width: 1100px) 260px, (min-width: 720px) 30vw, 45vw'}
        quality={70}
        priority={priority}
        loading={loading}
        unoptimized={isVector(src)}
        className="object-contain"
      />
    </div>
  )
}
