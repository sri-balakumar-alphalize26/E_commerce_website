import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import Container from '@/components/ui/Container'
import { cn } from '@/lib/cn'

/**
 * The gradient page header card.
 *
 * Every surface except home leads with one: listing, product, cart, search,
 * the 404. It is the element that stops a storefront reading as a grey admin
 * panel, and repeating it is what makes the pages feel like one shop rather
 * than a set of unrelated screens.
 *
 * `.on-dark` swaps the focus ring to the two-tone white-over-ink one, because
 * a brand-blue ring on a brand-blue field computes to 1.00:1 -- the ring
 * would be its own background.
 */
export default function PageHeader({
  title,
  subtitle,
  backHref,
  children,
  className,
}: {
  title: string
  subtitle?: string
  /** Renders the circular back affordance when set. */
  backHref?: string
  children?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('on-dark brand-gradient', className)}>
      <Container className="py-5 md:py-6">
        <div className="flex items-start gap-3">
          {backHref ? (
            <Link
              href={backHref}
              aria-label="Go back"
              className="chip-on-brand mt-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-pill text-white transition-colors"
            >
              <ArrowLeft className="size-[18px]" aria-hidden />
            </Link>
          ) : null}

          <div className="min-w-0 flex-1">
            <h1 className="font-display truncate text-xl leading-tight font-bold tracking-tight text-white md:text-[1.375rem]">
              {title}
            </h1>
            {subtitle ? (
              <p className="mt-1 text-[13px] text-white/85">{subtitle}</p>
            ) : null}
          </div>

          {children}
        </div>
      </Container>
    </div>
  )
}
