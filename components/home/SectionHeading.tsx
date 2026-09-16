import Link from 'next/link'
import { ChevronRight } from 'lucide-react'

/**
 * The ONE heading used by every home band -- tiles, rails, strips -- so the
 * page rhythm cannot drift as bands are added. Any band that hand-rolls its
 * own heading is how a dense page starts looking assembled rather than
 * designed.
 */
export default function SectionHeading({
  title,
  subtitle,
  href,
  id,
}: {
  title: string
  subtitle?: string
  /** Renders a "See all" affordance only when a real destination exists. */
  href?: string
  id?: string
}) {
  return (
    <div data-mm="sec-head" className="mb-2.5 flex items-baseline justify-between gap-4">
      <div className="min-w-0">
        <h2
          id={id}
          className="text-ink font-display truncate text-base font-extrabold tracking-tight md:text-lg"
        >
          {title}
        </h2>
        {subtitle ? <p className="text-slate-muted mt-0.5 truncate text-xs">{subtitle}</p> : null}
      </div>
      {href ? (
        <Link
          href={href}
          data-mm="see-all"
          className="text-brand-600 hover:text-brand-700 inline-flex shrink-0 items-center gap-0.5 text-[13px] font-semibold transition-colors"
        >
          See all
          <ChevronRight className="size-4" aria-hidden />
        </Link>
      ) : null}
    </div>
  )
}
