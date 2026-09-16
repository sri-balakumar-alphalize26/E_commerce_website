import Link from 'next/link'
import { ChevronRight } from 'lucide-react'

export type Crumb = { label: string; href?: string }

/**
 * The "where am I" trail. The last crumb is the current page and carries
 * aria-current rather than a link, so a screen reader announces position
 * instead of offering a link back to where the user already is.
 */
export default function Breadcrumbs({ trail }: { trail: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="text-slate-muted flex flex-wrap items-center gap-1 text-xs">
        {trail.map((c, i) => {
          const last = i === trail.length - 1
          return (
            <li key={`${c.label}-${i}`} className="flex items-center gap-1">
              {c.href && !last ? (
                <Link href={c.href} className="hover:text-brand-600 transition-colors">
                  {c.label}
                </Link>
              ) : (
                <span className="text-ink font-medium" aria-current={last ? 'page' : undefined}>
                  {c.label}
                </span>
              )}
              {!last ? <ChevronRight className="size-3 shrink-0" aria-hidden /> : null}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
