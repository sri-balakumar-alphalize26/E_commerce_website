'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Home, LayoutGrid, ShoppingCart, UserRound } from 'lucide-react'
import { useCart } from '@/components/cart/CartProvider'
import { cn } from '@/lib/cn'

/**
 * The mobile bottom bar.
 *
 * It exists because the header alone was not enough: before this, three rows
 * down a category page at 390px there was no cart, no search and no category
 * access on screen at all. The header is sticky now, and this is the other
 * half of the fix.
 *
 * FOUR items, matching the reference. It shipped with three while there
 * was no account route -- an Account tab that 404s from permanent chrome is
 * worse than an absent one. Orders and Wallet stay out: nothing completes a
 * checkout yet, and there is no wallet at all.
 *
 * Hidden on checkout-like surfaces and at >=1100px, where the sticky header
 * already carries everything.
 */
const ITEMS = [
  { href: '/', label: 'Home', icon: Home, match: (p: string) => p === '/' },
  { href: '/c/grocery', label: 'Categories', icon: LayoutGrid, match: (p: string) => p.startsWith('/c/') },
  { href: '/cart', label: 'Cart', icon: ShoppingCart, match: (p: string) => p === '/cart' },
  {
    href: '/account',
    label: 'Account',
    icon: UserRound,
    match: (p: string) => p.startsWith('/account') || p === '/login',
  },
]

export default function MobileTabBar() {
  const pathname = usePathname()
  const { cart, ready } = useCart()

  return (
    <nav
      aria-label="Primary"
      className="border-surface-line bg-surface shadow-bar fixed inset-x-0 bottom-0 z-40 border-t lg:hidden"
      // max(), not addition: adding the inset to a fixed padding double-counts
      // it on devices that report zero, which is how these bars end up
      // floating above a dead grey band.
      style={{ paddingBottom: 'max(0.375rem, env(safe-area-inset-bottom))' }}
    >
      <ul className="mx-auto flex max-w-lg items-stretch">
        {ITEMS.map((item) => {
          const active = item.match(pathname)
          const Icon = item.icon
          const count = item.href === '/cart' && ready ? cart.itemCount : 0

          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'relative flex h-14 flex-col items-center justify-center gap-0.5 transition-colors',
                  active ? 'text-brand-600' : 'text-slate-muted',
                )}
              >
                <span className="relative">
                  <Icon className="size-[22px]" aria-hidden />
                  {count > 0 ? (
                    <span className="bg-accent-500 text-ink ring-surface absolute -top-1.5 -right-2.5 inline-flex min-w-[18px] items-center justify-center rounded-pill px-1 text-[10px] leading-[18px] font-extrabold tabular-nums ring-2">
                      {count > 99 ? '99+' : count}
                    </span>
                  ) : null}
                </span>
                <span className="text-[11px] font-bold">{item.label}</span>
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
