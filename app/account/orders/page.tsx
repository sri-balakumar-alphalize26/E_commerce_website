import type { Metadata } from 'next'
import Link from 'next/link'
import { Package } from 'lucide-react'

export const metadata: Metadata = { title: 'Orders' }

/**
 * An honest empty state.
 *
 * No checkout completes in this phase, so there is no such thing as a past
 * order. Seeding sample orders would be the most convincing lie on the site
 * -- a customer would reasonably believe they had bought something.
 */
export default function OrdersPage() {
  return (
    <section className="border-surface-line bg-surface rounded-card border p-10 text-center">
      <span className="bg-brand-50 text-brand-600 mx-auto inline-flex size-14 items-center justify-center rounded-2xl">
        <Package className="size-6" aria-hidden />
      </span>
      <h2 className="text-ink mt-4 text-base font-extrabold">No orders yet</h2>
      <p className="text-slate-muted mx-auto mt-1.5 max-w-sm text-sm">
        Orders will appear here once checkout is connected to the store backend. Nothing you add
        to the cart is charged today.
      </p>
      <Link
        href="/"
        className="bg-brand-600 hover:bg-brand-700 mt-5 inline-flex h-11 items-center rounded-pill px-6 text-sm font-bold text-white transition-colors"
      >
        Start shopping
      </Link>
    </section>
  )
}
