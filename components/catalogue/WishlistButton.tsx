'use client'

import { Heart } from 'lucide-react'
import { toggle } from '@/lib/wishlist-store'
import { cn } from '@/lib/cn'
import { useWishlisted } from '@/lib/use-wishlist'

/**
 * The heart on a product card.
 *
 * Subscribed to THIS product's membership only. Reading the list through
 * context would re-render every card on the page each time any heart is
 * pressed, because context has no selector -- the same trap
 * lib/use-cart-line.ts exists to avoid.
 *
 * aria-pressed rather than a label that changes: a toggle button should
 * announce its state, not describe the action it is about to perform.
 */
export default function WishlistButton({
  productId,
  name,
  className,
}: {
  productId: number
  name: string
  className?: string
}) {
  const listed = useWishlisted(productId)

  return (
    <button
      type="button"
      onClick={() => void toggle(productId)}
      aria-pressed={listed}
      aria-label={`Save ${name} to My List`}
      className={cn(
        'bg-surface/90 inline-flex size-8 items-center justify-center rounded-full shadow-sm backdrop-blur-[2px] transition-colors',
        listed ? 'text-danger' : 'text-slate-faint hover:text-slate-muted',
        className,
      )}
    >
      <Heart className={cn('size-[18px]', listed && 'fill-current')} aria-hidden />
    </button>
  )
}
