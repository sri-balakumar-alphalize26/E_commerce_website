'use client'

import Image from 'next/image'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useCart } from '@/components/cart/CartProvider'
import { cn } from '@/lib/cn'
import { isVector } from '@/lib/image'
import { formatMoney } from '@/lib/money'

/**
 * The View Cart bar.
 *
 * Mounted once in the root layout, so the moment anything is added ANYWHERE
 * a persistent bar appears carrying thumbnails of what is in the bag, the
 * count, any saving, and the way through. That is the other half of the ADD
 * control: adding something has to visibly go somewhere, or a customer taps
 * ADD twice because nothing acknowledged the first press.
 *
 * COLOUR. View Cart is BRAND BLUE, not the orange accent, and that is the
 * doctrine rather than an exception to it: blue is the system speaking --
 * navigate, filter, select -- while orange marks the one thing on screen
 * that commits. View Cart navigates. Spending the single orange control on
 * a link is what leaves nothing to mark Checkout, which is why that button,
 * on /cart, is the one place the accent appears.
 *
 * It stacks above MobileTabBar using the same shared --tabbar-h the product
 * page's buy bar uses, so the two can never drift apart.
 */

/** Beyond three the count already says how many; more would just smear. */
const MAX_THUMBS = 3

export default function CartCheckoutBar() {
  const { cart, ready } = useCart()
  const pathname = usePathname()

  // Suppressed on product detail, which pins its own buy bar in exactly this
  // slot. Two stacked bars would eat a third of a 390px viewport, and the
  // tab bar right below already carries a live cart badge.
  if (pathname.startsWith('/p/')) return null

  /*
   * And suppressed on the cart itself.
   *
   * This bar used to switch its View Cart link for an orange Checkout
   * button here -- a button with no onClick, inert by design, waiting for a
   * backend. The cart page now says that in words, in its own to-pay card,
   * and a button that cannot act is the thing AGENTS.md rules out most
   * plainly. Repeating the total under a page that already shows it was the
   * lesser half of what this bar was doing anyway.
   */
  if (pathname === '/cart') return null

  if (!ready || !cart.lines.length) return null

  const thumbs = cart.lines.slice(0, MAX_THUMBS)
  const overflow = cart.lines.length - thumbs.length

  return (
    <div
      className="border-surface-line bg-surface shadow-bar fixed inset-x-0 z-30 border-t lg:hidden"
      style={{
        bottom: 'calc(var(--tabbar-h) + max(0.375rem, env(safe-area-inset-bottom)))',
        paddingBottom: '0.75rem',
      }}
    >
      <div className="mx-auto flex max-w-[1360px] items-center gap-3 px-4 pt-3">
        {/*
          Overlapping by a third with a ring in the page colour, so the stack
          reads as separate items rather than as one smeared image. Rendered
          in reverse via flex-row-reverse so EARLIER items sit on top -- with
          natural order the last item added would cover the first, which is
          the opposite of what a customer expects to recognise.
        */}
        <ul className="flex shrink-0 flex-row-reverse items-center ps-0">
          {overflow > 0 ? (
            <li className="border-surface-line bg-surface-alt text-slate-muted ring-surface -ms-3 inline-flex size-10 items-center justify-center rounded-lg border text-[11px] font-extrabold tabular-nums ring-2">
              +{overflow}
            </li>
          ) : null}
          {[...thumbs].reverse().map((line, i) => (
            <li
              key={line.productId}
              className={cn(
                'border-surface-line bg-surface ring-surface relative size-10 overflow-hidden rounded-lg border ring-2',
                // The last rendered (visually leftmost) keeps its full width.
                i === thumbs.length - 1 ? '' : '-ms-3',
              )}
            >
              <Image
                src={line.image}
                alt=""
                fill
                sizes="40px"
                unoptimized={isVector(line.image)}
                className="object-contain p-0.5"
              />
            </li>
          ))}
        </ul>

        <div className="min-w-0 flex-1">
          <p className="text-ink text-sm leading-none font-extrabold">
            {cart.itemCount} {cart.itemCount === 1 ? 'item' : 'items'}
          </p>
          {cart.savings > 0 ? (
            <p className="text-save mt-1.5 text-[12px] leading-none font-bold">
              You save {formatMoney(cart.savings, cart.currency)}
            </p>
          ) : (
            <p className="tnum text-slate-muted mt-1.5 text-[12px] leading-none font-semibold">
              {formatMoney(cart.subtotal, cart.currency)}
            </p>
          )}
        </div>

        <Link
          href="/cart"
          className="bg-brand-600 hover:bg-brand-700 inline-flex h-11 shrink-0 items-center rounded-pill px-6 text-sm font-extrabold text-white transition-colors"
        >
          View Cart
        </Link>
      </div>
    </div>
  )
}
