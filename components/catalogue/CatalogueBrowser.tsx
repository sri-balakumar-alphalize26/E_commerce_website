'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useMemo, useState } from 'react'
import { ArrowUpDown, SlidersHorizontal, X } from 'lucide-react'
import ProductGrid from '@/components/catalogue/ProductGrid'
import BottomSheet from '@/components/ui/BottomSheet'
import type { Product, SortKey } from '@/lib/catalog'
import { CATALOG } from '@/lib/catalog-config'
import { cn } from '@/lib/cn'
import { applyFacets, deriveFacets, priceBounds, type DerivedFacet } from '@/lib/facets'
import { SORT_OPTIONS, isSortKey, sortProducts } from '@/lib/sort'
import { setMode } from '@/lib/prefs-store'
import { useDeliveryMode } from '@/lib/use-prefs'

/**
 * Sort, facets and price filtering, all client-side over the items handed in.
 *
 * This is where the catalogue's limitations are absorbed AND declared. The
 * eventual backend exposes no sort parameter and no endpoint that enumerates
 * attribute values, so both are derived here from the fetched set -- and the
 * UI has to say so. A count that looks global but is not, or a "Price: low to
 * high" label over a single page, is a lie a customer catches on page two.
 *
 * SORT lives in the URL; FACETS do not, and the split is deliberate.
 *
 * Sort is a closed set of six known keys, so ?sort=price_asc always resolves
 * -- and losing the chosen order on every back/forward or product visit is
 * the one piece of state a customer actually notices going missing.
 *
 * Facets are derived from whatever result set was fetched, so ?brand=Foo
 * could name a value this page cannot resolve: a shareable link into a
 * filter that does not exist. They stay in component state until there is a
 * real facet endpoint to validate them against.
 */

type Props = {
  items: Product[]
  /** Facet keys worth offering, in display order. Others stay display-only. */
  emptyMessage?: string
}

export default function CatalogueBrowser({ items, emptyMessage }: Props) {
  const router = useRouter()
  const searchParams = useSearchParams()

  // Assigned first so the type guard narrows THIS binding. Inlining the
  // `?? undefined` would narrow the argument expression instead, leaving
  // sortParam as `string | null`.
  const sortParam = searchParams.get('sort') ?? undefined
  const sort: SortKey = isSortKey(sortParam) ? sortParam : 'default'

  function setSort(next: SortKey) {
    const params = new URLSearchParams(searchParams.toString())
    if (next === 'default') params.delete('sort')
    else params.set('sort', next)
    const qs = params.toString()
    // scroll:false so changing the order does not throw the customer back
    // to the top of a grid they had scrolled into.
    router.replace(qs ? `?${qs}` : '?', { scroll: false })
  }

  const [selected, setSelected] = useState<Record<string, string[]>>({})
  const [maxPrice, setMaxPrice] = useState<number | null>(null)
  const [sheet, setSheet] = useState<'none' | 'sort' | 'filter'>('none')

  // Quick narrows to what the local store actually stocks. The listing
  // routes are prerendered SSG and the mode lives in localStorage, so the
  // server cannot know it -- this has to be a client-side pass, and it
  // joins the one already running for facets.
  const mode = useDeliveryMode()
  const scoped = useMemo(
    () => (mode === 'quick' ? items.filter((p) => p.quickDelivery) : items),
    [items, mode],
  )

  const facets = useMemo(() => deriveFacets(scoped), [scoped])
  const bounds = useMemo(() => priceBounds(scoped), [scoped])

  const visible = useMemo(() => {
    let out = applyFacets(scoped, selected)
    if (maxPrice !== null) out = out.filter((p) => p.price <= maxPrice)
    return sortProducts(out, sort)
  }, [scoped, selected, maxPrice, sort])

  const activeChips = useMemo(
    () =>
      Object.entries(selected).flatMap(([key, values]) => values.map((value) => ({ key, value }))),
    [selected],
  )

  const filterCount = activeChips.length + (maxPrice !== null ? 1 : 0)

  function toggle(key: string, value: string) {
    setSelected((cur) => {
      const have = cur[key] ?? []
      const next = have.includes(value) ? have.filter((v) => v !== value) : [...have, value]
      const out = { ...cur, [key]: next }
      if (!next.length) delete out[key]
      return out
    })
  }

  function clearAll() {
    setSelected({})
    setMaxPrice(null)
  }

  const sortLabel = SORT_OPTIONS.find((o) => o.key === sort)?.label ?? 'Default order'

  return (
    <div className="lg:flex lg:items-start lg:gap-6">
      {/* Desktop facet rail. Sticky so filters stay reachable down a long
          grid, offset by the header's height. */}
      <aside className="hidden w-60 shrink-0 lg:block">
        <div className="sticky top-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-ink text-[13px] font-bold">Filters</h2>
            {filterCount > 0 ? (
              <button
                type="button"
                onClick={clearAll}
                className="text-brand-600 hover:text-brand-700 text-xs font-semibold"
              >
                Clear all
              </button>
            ) : null}
          </div>

          <FilterControls
            facets={facets}
            selected={selected}
            onToggle={toggle}
            bounds={bounds}
            maxPrice={maxPrice}
            onMaxPrice={setMaxPrice}
          />
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        {/* Toolbar. Desktop shows a native select; below lg it collapses to
            the two-button Sort | Filter bar the reference uses. */}
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-slate-muted text-[13px]">
            <span className="text-ink font-bold tabular-nums">{visible.length}</span>
            {visible.length === scoped.length ? ' products' : ` of ${scoped.length} products`}
          </p>

          <div className="hidden items-center gap-2 lg:flex">
            <label htmlFor="sort" className="text-slate-muted text-[13px]">
              Sort
            </label>
            <select
              id="sort"
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="border-field-line text-ink h-9 rounded-md border bg-transparent px-2.5 text-[13px] font-semibold"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2 lg:hidden">
            <ToolbarButton
              onClick={() => setSheet('sort')}
              icon={<ArrowUpDown className="size-4" />}
            >
              Sort
            </ToolbarButton>
            <ToolbarButton
              onClick={() => setSheet('filter')}
              icon={<SlidersHorizontal className="size-4" />}
              badge={filterCount || undefined}
            >
              Filter
            </ToolbarButton>
          </div>
        </div>

        {activeChips.length || maxPrice !== null ? (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {activeChips.map(({ key, value }) => (
              <Chip key={`${key}:${value}`} onRemove={() => toggle(key, value)}>
                {value}
              </Chip>
            ))}
            {maxPrice !== null ? (
              <Chip onRemove={() => setMaxPrice(null)}>Under {maxPrice}</Chip>
            ) : null}
            <button
              type="button"
              onClick={clearAll}
              className="text-brand-600 hover:text-brand-700 text-xs font-semibold"
            >
              Clear all
            </button>
          </div>
        ) : null}

        {visible.length ? (
          <>
            <ProductGrid items={visible} withRail priorityCount={4} />
            {/*
              The honest note about sort scope. One muted line, not an alert
              band: it is a fact about the ordering, not a problem to solve.
              It only appears when a non-default sort is active, because the
              default order is whatever the source returned and claims nothing.
            */}
            {sort !== 'default' ? (
              <p className="text-slate-muted mt-4 text-center text-xs">
                Sorted by {sortLabel.toLowerCase()} within these {visible.length} results.
              </p>
            ) : null}
          </>
        ) : (
          <div className="border-surface-line bg-surface rounded-card border p-10 text-center">
            <p className="text-ink text-sm font-bold">
              {mode === 'quick' && !filterCount
                ? 'Nothing here is stocked for quick delivery'
                : filterCount
                  ? 'Nothing matches these filters'
                  : (emptyMessage ?? 'Nothing here yet')}
            </p>
            {mode === 'quick' && !filterCount ? (
              <p className="text-slate-muted mx-auto mt-1.5 max-w-xs text-xs">
                Switch to {CATALOG.modes.all.label} to see the rest of the range.
              </p>
            ) : null}
            {mode === 'quick' && !filterCount ? (
              <button
                type="button"
                onClick={() => void setMode('all')}
                className="bg-brand-600 hover:bg-brand-700 mt-4 inline-flex h-10 items-center rounded-pill px-5 text-[13px] font-bold text-white transition-colors"
              >
                {CATALOG.modes.all.label}
              </button>
            ) : null}
            {filterCount ? (
              <button
                type="button"
                onClick={clearAll}
                className="bg-brand-600 hover:bg-brand-700 mt-4 inline-flex h-10 items-center rounded-pill px-5 text-[13px] font-bold text-white transition-colors"
              >
                Clear filters
              </button>
            ) : null}
          </div>
        )}
      </div>

      <BottomSheet open={sheet === 'sort'} onClose={() => setSheet('none')} title="Sort by">
        <ul className="space-y-1">
          {SORT_OPTIONS.map((o) => (
            <li key={o.key}>
              <button
                type="button"
                onClick={() => {
                  setSort(o.key)
                  setSheet('none')
                }}
                className={cn(
                  'flex w-full items-center justify-between rounded-md px-3 py-3 text-left text-sm',
                  sort === o.key ? 'bg-brand-50 text-brand-700 font-bold' : 'text-slate-body',
                )}
              >
                {o.label}
                {sort === o.key ? <span aria-hidden>&#10003;</span> : null}
              </button>
            </li>
          ))}
        </ul>
      </BottomSheet>

      <BottomSheet
        open={sheet === 'filter'}
        onClose={() => setSheet('none')}
        title="Filters"
        footer={
          <div className="flex gap-3">
            <button
              type="button"
              onClick={clearAll}
              className="border-field-line text-ink h-11 flex-1 rounded-pill border text-sm font-bold"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() => setSheet('none')}
              className="bg-brand-600 h-11 flex-1 rounded-pill text-sm font-bold text-white"
            >
              Show {visible.length}
            </button>
          </div>
        }
      >
        <FilterControls
          facets={facets}
          selected={selected}
          onToggle={toggle}
          bounds={bounds}
          maxPrice={maxPrice}
          onMaxPrice={setMaxPrice}
        />
      </BottomSheet>
    </div>
  )
}

/** Shared by the desktop rail and the mobile sheet so they cannot drift. */
function FilterControls({
  facets,
  selected,
  onToggle,
  bounds,
  maxPrice,
  onMaxPrice,
}: {
  facets: DerivedFacet[]
  selected: Record<string, string[]>
  onToggle: (key: string, value: string) => void
  bounds: { min: number; max: number }
  maxPrice: number | null
  onMaxPrice: (v: number | null) => void
}) {
  return (
    <div className="space-y-5">
      {bounds.max > bounds.min ? (
        <section>
          <h3 className="text-ink mb-2 text-xs font-bold tracking-[0.04em] uppercase">Max price</h3>
          <input
            type="range"
            min={bounds.min}
            max={bounds.max}
            step={Math.max(1, Math.round((bounds.max - bounds.min) / 50))}
            value={maxPrice ?? bounds.max}
            onChange={(e) => {
              const v = Number(e.target.value)
              onMaxPrice(v >= bounds.max ? null : v)
            }}
            aria-label="Maximum price"
            className="accent-brand-600 w-full"
          />
          <p className="text-slate-muted mt-1 text-xs tabular-nums">
            Up to {maxPrice ?? bounds.max}
          </p>
        </section>
      ) : null}

      {facets.map((facet) => (
        <section key={facet.key}>
          <h3 className="text-ink mb-2 text-xs font-bold tracking-[0.04em] uppercase">
            {facet.label}
          </h3>
          <ul className="space-y-1.5">
            {facet.values.map((v) => {
              const checked = (selected[facet.key] ?? []).includes(v.value)
              return (
                <li key={v.value}>
                  <label className="flex cursor-pointer items-center gap-2.5 text-[13px]">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggle(facet.key, v.value)}
                      className="accent-brand-600 size-4 shrink-0"
                    />
                    <span className="text-slate-body min-w-0 flex-1 truncate">{v.value}</span>
                    {/* "in these results" is stated once per rail rather than
                        per row -- see the header note in the rail. */}
                    <span className="text-slate-faint tabular-nums">{v.count}</span>
                  </label>
                </li>
              )
            })}
          </ul>
        </section>
      ))}

      <p className="text-slate-faint text-[11px]">Counts reflect the products shown here.</p>
    </div>
  )
}

function ToolbarButton({
  onClick,
  icon,
  badge,
  children,
}: {
  onClick: () => void
  icon: React.ReactNode
  badge?: number
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="border-field-line text-ink inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-[13px] font-semibold"
    >
      {icon}
      {children}
      {badge ? (
        <span className="bg-brand-600 inline-flex min-w-4 items-center justify-center rounded-pill px-1 text-[10px] leading-4 font-bold text-white tabular-nums">
          {badge}
        </span>
      ) : null}
    </button>
  )
}

function Chip({ onRemove, children }: { onRemove: () => void; children: React.ReactNode }) {
  return (
    <span className="border-surface-line bg-brand-50 text-brand-700 inline-flex h-7 items-center gap-1 rounded-pill border px-2.5 text-xs font-semibold">
      {children}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove filter ${String(children)}`}
        className="hover:text-brand-900 -mr-1 inline-flex size-5 items-center justify-center"
      >
        <X className="size-3" aria-hidden />
      </button>
    </span>
  )
}
