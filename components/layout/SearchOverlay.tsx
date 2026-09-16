'use client'

import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Clock, Search, TrendingUp, X } from 'lucide-react'
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react'
import { createPortal } from 'react-dom'
import type { Suggestion } from '@/app/api/suggest/route'
import { motion } from '@/lib/mart-motion'
import { clearSearches, readSearches, rememberSearch } from '@/lib/recent-searches'
import { useDebouncedValue } from '@/lib/use-debounced-value'

/**
 * The full-screen search panel.
 *
 * THE ENGINE OWNS VISIBILITY, not React. mart-motion opens and closes this
 * by setting `hidden` on the panel and the backdrop itself, so that it can
 * grow the panel out of the header bar with a clip-path and shrink it back
 * on the way out. React must therefore never render `hidden` as a prop:
 * the close event fires at the START of the exit animation, a quarter of a
 * second before the panel is actually hidden, so a React-controlled
 * attribute would snap it away mid-flight. The initial hide is applied once
 * through a ref instead, and the attribute is left alone afterwards.
 *
 * Everything inside is still ordinary React. The engine animates the shell
 * and cascades the sections; what they contain, and what a keystroke does,
 * belongs here.
 *
 * Focus trapping, the scroll lock and the "/" shortcut are all the engine's
 * too -- which is why this component deliberately does NOT reach for
 * useLockBodyScroll or the BottomSheet trap. Two implementations of a
 * scroll lock fighting over the same body is a scroll position lost.
 */

type Props = {
  /** A handful of products to offer before anything is typed. */
  picks: Suggestion[]
  /** Suggested terms. Chosen by the adapter, never by this component. */
  trending: string[]
}

export default function SearchOverlay({ picks, trending }: Props) {
  const router = useRouter()

  /*
   * The panel is created client-side only: rendering it on the server would
   * put a full-screen dialog into the HTML with nothing yet able to hide it.
   *
   * useSyncExternalStore rather than the usual setState-in-an-effect, which
   * costs a second render pass of the whole panel for a value that is
   * constant per environment. The store never changes, so subscribe is a
   * no-op; only the two snapshots differ.
   */
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  )

  const panelRef = useRef<HTMLDivElement>(null)
  const backdropRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    if (panelRef.current) panelRef.current.hidden = true
    if (backdropRef.current) backdropRef.current.hidden = true
  }, [mounted])

  const [open, setOpen] = useState(false)
  const [term, setTerm] = useState('')
  const [recent, setRecent] = useState<string[]>([])
  const [results, setResults] = useState<Suggestion[]>([])
  const debounced = useDebouncedValue(term, 200)
  const resultsRef = useRef<HTMLDivElement>(null)
  const chipsRef = useRef<HTMLDivElement>(null)

  // Mirrors the engine rather than driving it: the header bar is the
  // trigger, and the engine opens on that click by itself.
  useEffect(() => {
    function onOpen() {
      setRecent(readSearches())
      setOpen(true)
    }
    function onClose() {
      setOpen(false)
      setTerm('')
    }
    document.addEventListener('mm:search-open', onOpen)
    document.addEventListener('mm:search-close', onClose)
    return () => {
      document.removeEventListener('mm:search-open', onOpen)
      document.removeEventListener('mm:search-close', onClose)
    }
  }, [])

  const query = debounced.trim()
  const searching = query.length >= 2

  /*
   * Results are never cleared here, only replaced when a fetch resolves.
   *
   * Blanking them on every keystroke below the minimum length would be a
   * synchronous setState inside an effect -- a second render pass for a
   * list the render already knows to hide, since anything under two
   * characters shows the idle sections instead. Keeping the previous rows
   * until the new ones arrive also stops the list flashing empty between
   * one query and the next.
   */
  useEffect(() => {
    if (!open || !searching) return
    const ac = new AbortController()
    fetch(`/api/suggest?q=${encodeURIComponent(query)}`, { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : { items: [] }))
      .then((d: { items?: Suggestion[] }) => setResults(d.items ?? []))
      .catch(() => {
        // An aborted or failed suggestion is not worth a message; the
        // customer can still submit the term they have typed.
      })
    return () => ac.abort()
  }, [open, searching, query])

  // Re-cascade the rows after each render of a new result set, which is
  // what makes typing feel like the list is answering rather than blinking.
  useEffect(() => {
    if (results.length && resultsRef.current) motion()?.staggerIn(resultsRef.current)
  }, [results])

  const submit = useCallback(
    (value: string) => {
      const clean = value.trim()
      if (!clean) return
      setRecent(rememberSearch(clean))
      motion()?.closeSearch()
      router.push(`/search?q=${encodeURIComponent(clean)}`)
    },
    [router],
  )

  function onClear() {
    const el = chipsRef.current
    const mm = motion()
    if (el && mm) {
      mm.staggerOut(el, () => setRecent(clearSearches()))
      return
    }
    setRecent(clearSearches())
  }

  if (!mounted) return null

  return createPortal(
    <>
      <div ref={backdropRef} data-mm="search-backdrop" />

      <div
        ref={panelRef}
        data-mm="search-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Search products"
        className="bg-surface-alt shadow-float rounded-panel [--sp-max:720px] data-[mm-sheet]:rounded-none"
      >
        <div className="bg-surface-alt sticky top-0 z-2 flex items-center gap-2 px-3 py-2.5">
          <label className="border-brand-600 bg-surface flex h-11 flex-1 items-center gap-2 rounded-pill border-[1.5px] px-4 shadow-[0_0_0_4px_rgb(0_120_168/0.12)]">
            <Search className="text-brand-600 size-[18px] shrink-0" aria-hidden />
            <input
              data-mm="search-input"
              type="search"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submit(term)
              }}
              placeholder="Search for products"
              aria-label="Search products"
              className="text-ink placeholder:text-slate-muted h-full min-w-0 flex-1 bg-transparent text-[15px] outline-none focus-visible:shadow-none [&::-webkit-search-cancel-button]:hidden"
            />
            {term ? (
              <button
                type="button"
                onClick={() => setTerm('')}
                aria-label="Clear text"
                className="bg-surface-alt text-ink inline-flex size-6 shrink-0 items-center justify-center rounded-pill"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            ) : null}
          </label>

          <button
            type="button"
            data-mm="search-close"
            aria-label="Close search"
            className="border-surface-line bg-surface text-slate-muted hover:text-ink shrink-0 rounded-lg border px-2.5 py-2 text-xs font-semibold transition-colors"
          >
            Esc
          </button>
        </div>

        <div className="flex flex-col gap-4 px-4 pb-5">
          {searching ? (
            <section>
              <p className="text-slate-muted pb-2 text-xs">
                {results.length
                  ? `${results.length} ${results.length === 1 ? 'product' : 'products'} for “${query}”`
                  : `Nothing matches “${query}”`}
              </p>

              <div
                ref={resultsRef}
                className="border-surface-line bg-surface rounded-card divide-surface-line flex flex-col divide-y overflow-hidden border"
              >
                {results.map((item) => (
                  <Link
                    key={item.id}
                    href={item.href}
                    onClick={() => {
                      setRecent(rememberSearch(query))
                      motion()?.closeSearch()
                    }}
                    className="hover:bg-brand-50 flex items-center gap-3 px-3 py-2.5 transition-colors"
                  >
                    <Search className="text-slate-faint size-4 shrink-0" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="text-ink block truncate text-sm font-semibold">
                        {item.name}
                      </span>
                      <span className="text-slate-muted block truncate text-[11.5px]">
                        {item.subtitle}
                      </span>
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          ) : (
            <>
              {recent.length ? (
                <section data-mm="sp-block">
                  <div className="flex items-center justify-between pb-2">
                    <h2 className="text-ink text-sm font-extrabold">Past searches</h2>
                    <button
                      type="button"
                      onClick={onClear}
                      className="text-brand-600 hover:text-brand-700 text-[13px] font-bold transition-colors"
                    >
                      Clear
                    </button>
                  </div>
                  <div ref={chipsRef} data-mm="sp-stagger" className="flex flex-wrap gap-2">
                    {recent.map((t) => (
                      <Chip
                        key={t}
                        icon={<Clock className="size-3.5" aria-hidden />}
                        onClick={() => submit(t)}
                      >
                        {t}
                      </Chip>
                    ))}
                  </div>
                </section>
              ) : null}

              {trending.length ? (
                <section data-mm="sp-block">
                  <h2 className="text-ink pb-2 text-sm font-extrabold">Trending</h2>
                  <div data-mm="sp-stagger" className="flex flex-wrap gap-2">
                    {trending.map((t) => (
                      <Chip
                        key={t}
                        icon={<TrendingUp className="text-accent-600 size-3.5" aria-hidden />}
                        onClick={() => submit(t)}
                      >
                        {t}
                      </Chip>
                    ))}
                  </div>
                </section>
              ) : null}

              {picks.length ? (
                <section data-mm="sp-block">
                  <h2 className="text-ink pb-2 text-sm font-extrabold">Quick picks</h2>
                  <div data-mm="sp-stagger" className="grid grid-cols-2 gap-2 md:grid-cols-3">
                    {picks.map((p) => (
                      <Link
                        key={p.id}
                        href={p.href}
                        onClick={() => motion()?.closeSearch()}
                        className="border-surface-line bg-surface hover:border-brand-300 rounded-card border px-3 py-2.5 transition-colors"
                      >
                        <span className="text-ink line-clamp-2 block text-[12.5px] leading-tight font-bold">
                          {p.name}
                        </span>
                        <span className="text-slate-muted mt-1 block truncate text-[11px]">
                          {p.subtitle}
                        </span>
                      </Link>
                    ))}
                  </div>
                </section>
              ) : null}
            </>
          )}
        </div>
      </div>
    </>,
    document.body,
  )
}

function Chip({
  icon,
  onClick,
  children,
}: {
  icon: React.ReactNode
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="border-surface-line bg-surface text-ink hover:border-brand-600 hover:text-brand-600 inline-flex items-center gap-1.5 rounded-pill border px-3 py-1.5 text-[13px] transition-colors"
    >
      {icon}
      {children}
    </button>
  )
}
