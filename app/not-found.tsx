import Link from 'next/link'
import { SearchX } from 'lucide-react'
import PageHeader from '@/components/ui/PageHeader'
import Container from '@/components/ui/Container'
import { CATALOG } from '@/lib/catalog-config'

/**
 * Our own 404.
 *
 * Its existence is functional, not cosmetic: without it Next serves a
 * built-in not-found page that injects an unlayered
 * `@media (prefers-color-scheme:dark) { body { background:#000 } }`, which
 * outranks a layered body rule and turns the page black on any machine in
 * dark mode. See the note above `html body` in app/globals.css.
 *
 * It also has to do the job a 404 is for: offer a way onward. Every category
 * is one tap away rather than a dead end with a back button.
 */
export default function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" subtitle="That link did not lead anywhere" backHref="/" />

      <main>
        <Container className="py-10">
          <div className="border-surface-line bg-surface shadow-card rounded-card mx-auto max-w-xl border p-8 text-center">
            <span className="bg-brand-50 text-brand-600 mx-auto inline-flex size-14 items-center justify-center rounded-2xl">
              <SearchX className="size-6" aria-hidden />
            </span>
            <h2 className="text-ink mt-4 text-lg font-bold">We could not find that page</h2>
            <p className="text-slate-muted mx-auto mt-1.5 max-w-sm text-sm">
              It may have been moved, or the address may be slightly off.
            </p>
            <Link
              href="/"
              className="bg-brand-600 hover:bg-brand-700 mt-5 inline-flex h-11 items-center rounded-pill px-6 text-sm font-bold text-white transition-colors"
            >
              Back to home
            </Link>
          </div>

          <h3 className="text-slate-muted mt-10 mb-3 text-center text-[11px] font-bold tracking-[0.08em] uppercase">
            Browse a category
          </h3>
          <ul className="mx-auto grid max-w-3xl grid-cols-2 gap-3 md:grid-cols-3">
            {CATALOG.verticals.map((v) => (
              <li key={v.id}>
                <Link
                  href={`/c/${v.id}`}
                  className="border-surface-line bg-surface shadow-card rounded-card lift text-ink hover:text-brand-700 flex h-full items-center justify-center border px-4 py-4 text-center text-sm font-semibold"
                >
                  {v.label}
                </Link>
              </li>
            ))}
          </ul>
        </Container>
      </main>
    </>
  )
}
