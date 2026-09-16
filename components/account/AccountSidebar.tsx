'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  BookOpen,
  Heart,
  Info,
  LifeBuoy,
  LogOut,
  MapPin,
  Package,
  ScrollText,
  UserRound,
} from 'lucide-react'
import { signOut } from '@/lib/session-store'
import { initialsOf } from '@/lib/session'
import { cn } from '@/lib/cn'
import { useSession } from '@/lib/use-session'

/**
 * The account sidebar.
 *
 * Grouped the way the reference groups it -- account, then help, then
 * information, then sign out -- but with Wallet, PAN Card and Coupons left
 * out entirely. There are no payments, no KYC and no coupon engine behind
 * them, and a PAN field collecting real identity numbers in a build with no
 * backend is worth refusing on its own merits, not just on the no-dead-UI
 * rule.
 *
 * Every remaining item resolves to a route that exists and does something.
 */

const ACCOUNT = [
  { href: '/account/profile', label: 'My Profile', icon: UserRound },
  { href: '/account/list', label: 'My List', icon: Heart },
  { href: '/account/addresses', label: 'Delivery Address', icon: MapPin },
  { href: '/account/orders', label: 'Orders', icon: Package },
]

const SUPPORT = [
  { href: '/account/help', label: 'Help', icon: LifeBuoy },
  { href: '/account/about', label: 'About us', icon: Info },
  { href: '/account/legal', label: 'Legal information', icon: ScrollText },
]

export default function AccountSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const { profile, signedIn } = useSession()

  return (
    <nav
      aria-label="Account"
      className="border-surface-line bg-surface rounded-card h-max border p-4 lg:sticky lg:top-40"
    >
      <div className="flex items-center gap-3 pb-4">
        <span className="bg-brand-50 text-brand-700 inline-flex size-12 shrink-0 items-center justify-center rounded-full text-sm font-extrabold">
          {signedIn && profile ? initialsOf(profile.name) : <UserRound className="size-5" aria-hidden />}
        </span>
        <div className="min-w-0">
          <p className="text-ink truncate text-sm font-extrabold">
            {signedIn && profile ? profile.name : 'Guest'}
          </p>
          <p className="text-slate-muted truncate text-xs">
            {signedIn && profile ? profile.email : 'Not signed in'}
          </p>
        </div>
      </div>

      <Group items={ACCOUNT} pathname={pathname} />

      <p className="text-slate-muted mt-5 mb-1.5 px-2 text-[11px] font-bold tracking-[0.04em] uppercase">
        Help &amp; information
      </p>
      <Group items={SUPPORT} pathname={pathname} />

      <div className="border-surface-line mt-5 border-t pt-3">
        {signedIn ? (
          <button
            type="button"
            onClick={async () => {
              await signOut()
              router.push('/')
            }}
            className="text-slate-body hover:bg-surface-alt flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-[13px] font-semibold transition-colors"
          >
            <LogOut className="size-[18px] shrink-0" aria-hidden />
            Sign out
          </button>
        ) : (
          <Link
            href="/login"
            className="text-brand-600 hover:bg-brand-50 flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-[13px] font-bold transition-colors"
          >
            <BookOpen className="size-[18px] shrink-0" aria-hidden />
            Sign in
          </Link>
        )}
      </div>
    </nav>
  )
}

function Group({
  items,
  pathname,
}: {
  items: { href: string; label: string; icon: typeof UserRound }[]
  pathname: string
}) {
  return (
    <ul className="space-y-0.5">
      {items.map(({ href, label, icon: Icon }) => {
        const active = pathname === href
        return (
          <li key={href}>
            <Link
              href={href}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'flex items-center gap-3 rounded-lg px-2 py-2.5 text-[13px] transition-colors',
                active
                  ? 'bg-brand-50 text-brand-700 font-extrabold'
                  : 'text-slate-body hover:bg-surface-alt font-semibold',
              )}
            >
              <Icon className="size-[18px] shrink-0" aria-hidden />
              {label}
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
