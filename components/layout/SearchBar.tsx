import { Search } from 'lucide-react'
import { cn } from '@/lib/cn'

/**
 * The header search control.
 *
 * A BUTTON, not a text field. The real input lives in the overlay panel
 * (see SearchOverlay), which the motion engine opens from this element and
 * grows out of its exact rectangle. Leaving a real input here would be a
 * decoy: the engine cancels the click and moves focus into the panel, so
 * the field in the header could never be typed into, and a text box that
 * refuses text is worse than an honest button.
 *
 * That also retires the inline typeahead this component used to own. Two
 * search surfaces -- one dropping down from the bar, one growing out of it
 * -- would both have opened on the same tap.
 *
 * The rolling hints come from the adapter rather than being written here,
 * because a component is not allowed to know what this shop sells. Only the
 * first is visible until the engine starts advancing them, so the control
 * still reads correctly with no JavaScript at all.
 *
 * Server component: there is no state left once the panel owns the search.
 */
export default function SearchBar({ hints, className }: { hints: string[]; className?: string }) {
  const words = hints.length ? hints : ['products']

  return (
    <button
      type="button"
      data-mm="search"
      data-mm-skip
      aria-haspopup="dialog"
      aria-label="Search products"
      className={cn(
        'bg-surface shadow-card text-slate-muted flex h-10 cursor-text items-center gap-2 rounded-pill px-4 text-left md:h-11',
        className,
      )}
    >
      <Search className="size-[18px] shrink-0" aria-hidden />

      <span className="min-w-0 flex-1 truncate text-sm">
        Search for{' '}
        <span data-mm="search-roll" className="inline-grid h-[1.4em] overflow-hidden align-bottom">
          {words.map((word) => (
            <span key={word} className="col-start-1 row-start-1 whitespace-nowrap">
              {word}
            </span>
          ))}
        </span>
      </span>

      {/* The engine binds "/" globally; the hint is desktop-only because a
          phone keyboard has no always-available slash key to advertise. */}
      <kbd className="border-surface-line text-slate-muted hidden shrink-0 rounded border px-1.5 py-0.5 text-[11px] font-semibold lg:inline">
        /
      </kbd>
    </button>
  )
}
