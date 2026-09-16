'use client'

import { Zap } from 'lucide-react'
import { CATALOG } from '@/lib/catalog-config'
import { setMode } from '@/lib/prefs-store'
import { useDeliveryMode } from '@/lib/use-prefs'

/**
 * Says so when Quick is narrowing the page.
 *
 * NOT CURRENTLY RENDERED. The home page moved to the vendored design and
 * this was left behind; it is kept because the need it answers is real and
 * has not gone away, but it is dead code until something mounts it.
 *
 * Rails that empty under Quick simply disappear, which without this would
 * leave a home page that looks arbitrarily short with nothing explaining
 * why. One line, and a way back -- the same courtesy the listing pages
 * extend when a filter empties a grid.
 */
export default function QuickNotice() {
  const mode = useDeliveryMode()
  if (mode !== 'quick') return null

  return (
    <p className="border-brand-100 bg-brand-50 text-brand-700 mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border px-3 py-2 text-[13px] font-semibold">
      <Zap className="size-4 shrink-0 fill-current" aria-hidden />
      Showing only items stocked for quick delivery.
      <button
        type="button"
        onClick={() => void setMode('all')}
        className="text-brand-700 font-extrabold underline underline-offset-2"
      >
        {CATALOG.modes.all.label} instead
      </button>
    </p>
  )
}
