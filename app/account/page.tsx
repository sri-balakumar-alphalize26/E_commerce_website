import type { Metadata } from 'next'
import Link from 'next/link'
import { Heart, LifeBuoy, MapPin, Package, UserRound } from 'lucide-react'

export const metadata: Metadata = { title: 'My Account' }

/**
 * The card grid from the reference, minus Wallet and Coupons -- neither has
 * anything behind it, and a card promising a balance is worse than an absent
 * card.
 */
const CARDS = [
  { href: '/account/orders', label: 'Orders', hint: 'Track and reorder', icon: Package },
  { href: '/account/list', label: 'My List', hint: 'Saved for later', icon: Heart },
  { href: '/account/profile', label: 'Personal Info', hint: 'Name and contact', icon: UserRound },
  { href: '/account/addresses', label: 'Delivery Address', hint: 'Where we deliver', icon: MapPin },
  { href: '/account/help', label: 'Help', hint: 'Contact support', icon: LifeBuoy },
]

export default function AccountHome() {
  return (
    <>
      <h2 className="text-ink font-display mb-4 text-lg font-extrabold tracking-tight">
        My Profile
      </h2>

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {CARDS.map(({ href, label, hint, icon: Icon }) => (
          <li key={href}>
            <Link
              href={href}
              className="border-surface-line bg-surface shadow-card rounded-card lift flex h-full flex-col gap-2 border p-4"
            >
              <span className="bg-brand-50 text-brand-600 inline-flex size-10 items-center justify-center rounded-xl">
                <Icon className="size-5" aria-hidden />
              </span>
              <span className="text-ink text-sm font-extrabold">{label}</span>
              <span className="text-slate-muted text-xs">{hint}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  )
}
