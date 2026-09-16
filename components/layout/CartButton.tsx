'use client'

import Link from 'next/link'
import { ShoppingCart } from 'lucide-react'
import { useCart } from '@/components/cart/CartProvider'
import { cn } from '@/lib/cn'

/**
 * The header cart entry point.
 *
 * The count badge is the one place orange is allowed in the header. It is
 * the smallest possible mark carrying the most consequential state, and it
 * is never simultaneously visible with another saturated orange fill, so it
 * stays inside the accent budget.
 *
 * It carries ink on orange rather than white: #ff7800 against white is
 * 2.65:1, which fails as text and as a text background, while ink on the
 * same orange is 6.90:1.
 */
export default function CartButton({ className }: { className?: string }) {
  const { cart, ready } = useCart()
  const count = cart.itemCount

  return (
    <Link
      href="/cart"
      data-mm="cart"
      data-mm-skip
      className={cn(
        'chip-on-brand relative inline-flex h-10 items-center gap-2 rounded-pill px-3 text-sm font-semibold text-white transition-colors',
        className,
      )}
    >
      <ShoppingCart className="size-[18px]" aria-hidden />
      <span className="hidden md:inline">Cart</span>

      {/* suppressHydrationWarning is not enough on its own -- the count is
          gated on `ready` so the server and the first client paint agree on
          an empty cart, and the badge appears once storage has been read. */}
      {ready && count > 0 ? (
        <span
          data-mm="cart-count"
          className="bg-accent-500 text-ink absolute -top-1 -right-1 inline-flex min-w-5 items-center justify-center rounded-pill px-1 text-[11px] leading-5 font-bold tabular-nums ring-1 ring-accent-700"
          aria-hidden
        >
          {count > 99 ? '99+' : count}
        </span>
      ) : null}

      <span className="sr-only">
        {ready && count > 0 ? `${count} item${count === 1 ? '' : 's'} in cart` : 'Cart is empty'}
      </span>
    </Link>
  )
}
