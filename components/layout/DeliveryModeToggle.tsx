'use client'

import { Grid2x2, Zap } from 'lucide-react'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import ModeSwitchOverlay from '@/components/layout/ModeSwitchOverlay'
import { CATALOG } from '@/lib/catalog-config'
import { cn } from '@/lib/cn'
import type { DeliveryMode } from '@/lib/prefs'
import { setMode } from '@/lib/prefs-store'
import { useModeSwitch } from '@/lib/use-mode-switch'
import { useDeliveryMode } from '@/lib/use-prefs'

/**
 * Quick / Express.
 *
 * This genuinely filters -- Quick narrows the catalogue to products flagged
 * as stocked in the local dark store, and the choice persists. A segmented
 * control that switches state without changing what a customer sees would be
 * the exact dead UI this build has refused everywhere else.
 *
 * Rendered as a radiogroup rather than two buttons, because that is what it
 * is: one choice with two mutually exclusive options. A screen reader then
 * announces the selected state instead of two unrelated pressable things.
 *
 * THE CURTAIN ONLY PLAYS WHERE THE MODE CHANGES SOMETHING. The control sits
 * in the header on every route, but only the listing surfaces re-filter on
 * it. Covering the screen for a second and a half on the cart page, to
 * reveal the identical cart page, would be an animation telling the
 * customer something happened when nothing did.
 */

/** The routes whose contents are filtered by the delivery mode. */
function modeChangesThisPage(pathname: string) {
  return (
    pathname === '/' ||
    pathname.startsWith('/c/') ||
    pathname.startsWith('/search') ||
    pathname.startsWith('/collection/')
  )
}

export default function DeliveryModeToggle({ className }: { className?: string }) {
  const mode = useDeliveryMode()
  const pathname = usePathname()
  const [state, runSwitch] = useModeSwitch()

  /*
   * The thumb is measured, not calculated.
   *
   * Both segments are sized by their own text, and "Quick" carries an icon
   * the other does not -- so the travel distance is whatever the browser
   * laid out, and re-measuring on resize is what keeps the thumb under the
   * label when the header reflows at a breakpoint. Rendering it only once
   * a measurement exists avoids a frame of it sitting at zero width.
   */
  const wrap = useRef<HTMLDivElement>(null)
  const [thumb, setThumb] = useState<{ x: number; w: number } | null>(null)

  useEffect(() => {
    function place() {
      const el = wrap.current?.querySelector<HTMLElement>(`[data-mode="${mode}"]`)
      if (el) setThumb({ x: el.offsetLeft, w: el.offsetWidth })
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [mode])

  function select(next: DeliveryMode, origin: HTMLElement) {
    if (next === mode) return
    const swap = () => void setMode(next)
    if (modeChangesThisPage(pathname)) {
      void runSwitch(next, origin, swap)
      return
    }
    swap()
  }

  return (
    <>
      <div
        ref={wrap}
        role="radiogroup"
        aria-label="Delivery mode"
        className={cn(
          'chip-on-brand relative inline-flex h-9 shrink-0 items-center rounded-pill p-0.5',
          className,
        )}
      >
        {thumb ? (
          <span
            aria-hidden
            className="bg-surface pointer-events-none absolute top-0.5 bottom-0.5 left-0 rounded-pill shadow-sm transition-[transform,width] duration-500"
            style={{
              transform: `translateX(${thumb.x}px)`,
              width: thumb.w,
              transitionTimingFunction: 'var(--ease-spring)',
            }}
          />
        ) : null}

        <Segment
          mode="quick"
          active={mode === 'quick'}
          onSelect={select}
          label={CATALOG.modes.quick.label}
        >
          <Zap className="size-3.5 fill-current" aria-hidden />
          <i className="font-extrabold">{CATALOG.modes.quick.label}</i>
        </Segment>

        <Segment
          mode="all"
          active={mode === 'all'}
          onSelect={select}
          label={CATALOG.modes.all.label}
        >
          <Grid2x2 className="size-3.5" aria-hidden />
          {CATALOG.modes.all.label}
        </Segment>
      </div>

      <ModeSwitchOverlay state={state} />
    </>
  )
}

function Segment({
  mode,
  active,
  onSelect,
  label,
  children,
}: {
  mode: DeliveryMode
  active: boolean
  onSelect: (mode: DeliveryMode, origin: HTMLElement) => void
  label: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      role="radio"
      data-mode={mode}
      aria-checked={active}
      aria-label={label}
      onClick={(e) => onSelect(mode, e.currentTarget)}
      className={cn(
        // Sits above the thumb, which is painted behind it.
        'relative inline-flex h-8 items-center gap-1 rounded-pill px-3 text-[13px] font-extrabold whitespace-nowrap transition-colors',
        // The filled segment is the white thumb with ink on it. White text
        // on a translucent chip over the gradient measures 3.62:1 and
        // fails; ink on white is 16:1 and cannot.
        active ? 'text-ink' : 'text-white/85 hover:text-white',
      )}
    >
      {children}
    </button>
  )
}
