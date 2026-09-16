'use client'

import { Grid2x2, Zap } from 'lucide-react'
import { createPortal } from 'react-dom'
import { CATALOG } from '@/lib/catalog-config'
import { cn } from '@/lib/cn'
import type { ModeSwitchState } from '@/lib/use-mode-switch'

/**
 * The cover that hides the mode swap.
 *
 * Portalled to the body. The toggle that opens it lives inside a sticky,
 * z-indexed header, and an element cannot escape the stacking context of
 * an ancestor that has one -- rendered in place it would be clipped to the
 * header bar instead of covering the page.
 *
 * The flood starts at the tapped control rather than at the centre of the
 * screen, which is what ties the colour to the thing that caused it. Its
 * origin arrives as --x / --y and drives a clip-path circle.
 *
 * role="status" and aria-live="polite" because this is a state change a
 * screen reader should hear, announced once when the phase begins. It is
 * not a dialog: nothing in it can be acted on, and it takes no focus.
 */
export default function ModeSwitchOverlay({ state }: { state: ModeSwitchState | null }) {
  if (!state || typeof document === 'undefined') return null

  const copy = CATALOG.modes[state.to]
  const Icon = state.to === 'quick' ? Zap : Grid2x2

  return createPortal(
    <div
      role="status"
      aria-live="polite"
      data-to={state.to}
      className={cn('mode-curtain', `mode-curtain-${state.phase}`)}
      style={{ '--x': `${state.x}px`, '--y': `${state.y}px` } as React.CSSProperties}
    >
      <div className="mode-curtain-card">
        <span className="mode-curtain-icon">
          <Icon className="size-8" aria-hidden />
        </span>
        <strong>{copy.title}</strong>
        <span>{copy.sub}</span>
        <i className="mode-curtain-bar" aria-hidden />
      </div>
    </div>,
    document.body,
  )
}
