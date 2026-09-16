'use client'

import Link from 'next/link'
import { ShoppingCart } from 'lucide-react'
import { useCart } from '@/components/cart/CartProvider'
import CartLineRow from '@/components/cart/CartLineRow'
import Container from '@/components/ui/Container'
import PageHeader from '@/components/ui/PageHeader'
import { formatMoney } from '@/lib/money'

/**
 * The cart page.
 *
 * Entirely client-rendered, deliberately. The cart is client state, and
 * server-rendering the lines would paint a stale total for the frame between
 * hydration and the store being read -- on the one screen where a customer is
 * checking the arithmetic.
 *
 * The bill shows an item count, a savings line and a total, and nothing else.
 * There is no delivery fee, no tax row and no free-delivery meter: nothing in
 * this build can compute any of them, and a number that moves convincingly
 * while meaning nothing is worse than an absent row.
 */
export default function CartPage() {
  const { cart, ready, clear } = useCart()

  if (!ready) {
    return (
      <>
        <PageHeader title="Cart" backHref="/" />
        <main>
          <Container className="py-10">
            <p className="text-slate-muted text-sm">Loading your cart...</p>
          </Container>
        </main>
      </>
    )
  }

  if (!cart.lines.length) {
    return (
      <>
        <PageHeader title="Cart" backHref="/" />
        <main>
          <Container className="py-12">
            <div className="border-surface-line bg-surface shadow-card rounded-card mx-auto max-w-md border p-10 text-center">
              <span className="bg-brand-50 text-brand-600 mx-auto inline-flex size-14 items-center justify-center rounded-2xl">
                <ShoppingCart className="size-6" aria-hidden />
              </span>
              <h2 className="text-ink mt-4 text-lg font-bold">Your cart is empty</h2>
              <p className="text-slate-muted mt-1.5 text-sm">
                Browse a category and add something you like.
              </p>
              <Link
                href="/"
                className="bg-brand-600 hover:bg-brand-700 mt-5 inline-flex h-11 items-center rounded-pill px-6 text-sm font-bold text-white transition-colors"
              >
                Start shopping
              </Link>
            </div>
          </Container>
        </main>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Cart"
        subtitle={`${cart.itemCount} ${cart.itemCount === 1 ? 'item' : 'items'}`}
        backHref="/"
      />

      <main className="lg:pb-10">
        <Container className="py-5">
          <div className="lg:flex lg:items-start lg:gap-6">
            <div className="min-w-0 flex-1">
              <div className="border-surface-line bg-surface rounded-card border px-4">
                <ul>
                  {cart.lines.map((line) => (
                    <CartLineRow key={line.productId} line={line} />
                  ))}
                </ul>
              </div>

              <button
                type="button"
                onClick={() => clear()}
                className="text-slate-muted hover:text-danger mt-3 text-xs font-semibold transition-colors"
              >
                Clear cart
              </button>
            </div>

            {/* Sticky so the total stays visible down a long cart. */}
            <aside className="mt-6 lg:mt-0 lg:w-80 lg:shrink-0">
              <div className="border-surface-line bg-surface shadow-card rounded-card sticky top-4 border p-4">
                <h2 className="text-ink text-sm font-bold">Bill details</h2>

                <dl className="mt-3 space-y-2 text-[13px]">
                  <div className="flex justify-between">
                    <dt className="text-slate-muted">
                      Items ({cart.itemCount})
                    </dt>
                    <dd className="tnum text-ink font-semibold">
                      {formatMoney(cart.subtotal + cart.savings, cart.currency)}
                    </dd>
                  </div>

                  {cart.savings > 0 ? (
                    <div className="flex justify-between">
                      <dt className="text-save">Discount</dt>
                      <dd className="tnum text-save font-semibold">
                        &minus; {formatMoney(cart.savings, cart.currency)}
                      </dd>
                    </div>
                  ) : null}
                </dl>

                <div className="border-surface-line mt-3 flex items-baseline justify-between border-t pt-3">
                  <span className="text-ink text-sm font-bold">Total</span>
                  <span className="tnum text-ink text-lg font-bold">
                    {formatMoney(cart.subtotal, cart.currency)}
                  </span>
                </div>

                {cart.savings > 0 ? (
                  <p className="bg-save-soft text-save rounded-md mt-3 px-3 py-2 text-center text-[13px] font-bold">
                    You save {formatMoney(cart.savings, cart.currency)}
                  </p>
                ) : null}

                {/*
                  The one orange control on the page. Ink on orange, not white
                  (6.90:1 vs 2.65:1), with an accent-700 rim so the button's
                  own silhouette is perceivable against the white panel.

                  DESKTOP ONLY. Below 1100px CartCheckoutBar pins the same
                  action to the bottom edge, and both rendering at once put
                  two saturated orange fills on one screen -- which is the
                  one thing the accent budget exists to prevent. The bar is
                  the better of the two on a phone because it stays in
                  reach without scrolling past every line.
                */}
                <button
                  type="button"
                  className="cta-accent mt-4 hidden h-12 w-full items-center justify-center rounded-pill text-sm font-bold lg:inline-flex"
                >
                  Proceed to checkout
                </button>
                <p className="text-slate-faint mt-2 text-center text-[11px]">
                  Checkout arrives with the backend
                </p>
              </div>
            </aside>
          </div>
        </Container>
      </main>

    </>
  )
}
