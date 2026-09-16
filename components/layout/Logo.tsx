import Image from 'next/image'
import Link from 'next/link'
import { CATALOG } from '@/lib/catalog-config'
import { cn } from '@/lib/cn'

/**
 * Two lockups, because the logo artwork cannot go everywhere.
 *
 * The mark is a blue-to-cyan "369" with a silver wordmark on a transparent
 * ground. On a light surface it is the real brand asset and should be used.
 * On the gradient header it would be blue artwork on a blue field -- the
 * numerals measure barely 1.5:1 against brand-700 -- so the header gets a
 * white wordmark set in the display face instead. That is the ordinary
 * resolution for a coloured logo on a dark bar, and it keeps the header
 * legible without commissioning a knockout asset.
 *
 * The orange arrow is what makes the mark recognisable, so the wordmark
 * keeps it as a rising glyph. It is identity rather than signal, so it does
 * not count against the accent budget.
 */

export default function Logo({
  onDark = false,
  className,
}: {
  onDark?: boolean
  className?: string
}) {
  return (
    <Link
      href="/"
      aria-label={`${CATALOG.brand.name} home`}
      data-mm="logo"
      data-mm-skip
      className={cn('inline-flex shrink-0 items-center gap-2', className)}
    >
      {onDark ? (
        <span className="inline-flex items-baseline gap-[3px]">
          <span className="font-display text-xl leading-none font-bold tracking-tight text-white md:text-[1.375rem]">
            {CATALOG.brand.short}
          </span>
          {/* The arrow, scaled to sit on the wordmark's cap height. */}
          <svg
            viewBox="0 0 12 14"
            className="h-[0.9em] w-auto translate-y-[0.06em]"
            aria-hidden
            fill="none"
          >
            <path
              d="M1 13C3.2 8.6 6.2 4.8 10.4 1.8"
              stroke="var(--color-accent-400)"
              strokeWidth="2.4"
              strokeLinecap="round"
            />
            <path
              d="M6.4 1.2h5v5"
              stroke="var(--color-accent-400)"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="font-display text-xl leading-none font-bold tracking-tight text-white/90 md:text-[1.375rem]">
            Mart
          </span>
        </span>
      ) : (
        <>
          <Image
            src="/logo.png"
            alt=""
            width={36}
            height={36}
            priority
            className="h-9 w-9 object-contain"
          />
          <span className="font-display text-ink text-lg leading-none font-bold tracking-tight">
            {CATALOG.brand.name}
          </span>
        </>
      )}
    </Link>
  )
}
