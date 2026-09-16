'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import Container from '@/components/ui/Container'
import { CATALOG, IS_SINGLE_VERTICAL } from '@/lib/catalog-config'
import { cn } from '@/lib/cn'

/**
 * The category band under the header.
 *
 * Pills, not tabs with an underline. The filled-pill active state is what
 * makes this read as a marketplace rather than as a Material app, and it
 * survives a horizontally scrolled row far better: an underline on a
 * partially scrolled tab is ambiguous, a filled pill is not.
 *
 * "All" is always first. Without it there is no one-tap route from a
 * category back to the whole catalogue, and the strip has no neutral active
 * state on the home route.
 *
 * Derived from usePathname ALONE. This used to also read useSearchParams to
 * decide whether "All" was active, which opted the whole root layout into
 * client rendering and forced a Suspense boundary -- so every route painted
 * a blank 53px band before the pills arrived. `/search` is the only route
 * that carries `q`, and pathname already tells us that.
 */
export default function CategoryStrip() {
  const pathname = usePathname()

  // Hidden entirely when the shop sells one thing -- a single-item filter
  // strip is chrome that cannot do anything.
  if (IS_SINGLE_VERTICAL) return null

  const activeVertical = pathname.startsWith('/c/') ? pathname.split('/')[2] : null
  const isAll = pathname === '/'

  return (
    <nav aria-label="Product categories" className="bg-surface border-surface-line border-b">
      <Container>
        {/* The fade tells a customer there is more to scroll; without it a
            row clipped mid-pill just looks broken. */}
        <div className="edge-fade-x -mx-4 overflow-x-auto px-4 md:mx-0 md:px-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {/* data-mm-skip on each item, not on the ul: the engine hides a
              group's CHILDREN, so skipping only the parent would still
              leave every pill invisible until the script boots. */}
          <ul data-mm="pills" className="flex items-center gap-2 py-2">
            <li data-mm-skip>
              <Pill href="/" active={isAll}>
                All
              </Pill>
            </li>
            {CATALOG.verticals.map((v) => (
              <li key={v.id} data-mm-skip>
                <Pill href={`/c/${v.id}`} active={activeVertical === v.id}>
                  {v.label}
                </Pill>
              </li>
            ))}
          </ul>
        </div>
      </Container>
    </nav>
  )
}

function Pill({
  href,
  active,
  children,
}: {
  href: string
  active: boolean
  children: React.ReactNode
}) {
  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      // h-9 rather than the reference's 28px pill: the reference sits inside
      // a 44px ScrollView row that supplies the touch target, and there is
      // no such row here.
      className={cn(
        'inline-flex h-9 items-center rounded-pill px-3.5 text-[13px] font-bold whitespace-nowrap transition-colors',
        active
          ? 'bg-brand-600 text-white'
          : 'border-surface-line text-slate-body hover:border-brand-300 hover:text-brand-700 border bg-transparent',
      )}
    >
      {children}
    </Link>
  )
}
