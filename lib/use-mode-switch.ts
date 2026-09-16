'use client'

import { useCallback, useRef, useState } from 'react'
import type { DeliveryMode } from '@/lib/prefs'

/**
 * The three-beat transition between delivery modes.
 *
 *   in    colour floods out of the button that was tapped
 *   hold  the page swaps underneath the cover and scrolls to the top
 *   out   the cover lifts away and the new page rises in behind it
 *
 * The point of the middle beat is that the swap is never seen. Switching
 * modes re-filters every rail and grid on the page, which without a cover
 * is a hard cut -- rows vanishing and re-flowing while the eye is still on
 * them. Hiding it costs a second and buys a change that reads as deliberate.
 *
 * REDUCED MOTION SKIPS THE WHOLE THING, rather than shortening it. A cover
 * that flashes over the viewport is precisely the kind of full-screen
 * movement the preference is set to avoid, and the swap underneath is
 * instant either way.
 *
 * The busy ref is not politeness. Each beat is a timer, so a second tap
 * partway through would interleave two sequences and leave the cover
 * stranded on screen with no run left to remove it.
 */

export type SwitchPhase = 'in' | 'hold' | 'out'

export type ModeSwitchState = {
  to: DeliveryMode
  /** Viewport coordinates of the tapped control: the flood's origin. */
  x: number
  y: number
  phase: SwitchPhase
}

const FLOOD_MS = 520
const HOLD_MS = 380
const LIFT_MS = 560

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

export function useModeSwitch() {
  const [state, setState] = useState<ModeSwitchState | null>(null)
  const busy = useRef(false)

  const run = useCallback(
    async (to: DeliveryMode, origin: HTMLElement | null, swap: () => void) => {
      if (busy.current) return

      const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      if (reduced || !origin) {
        swap()
        window.scrollTo(0, 0)
        return
      }

      busy.current = true
      const box = origin.getBoundingClientRect()
      setState({ to, x: box.left + box.width / 2, y: box.top + box.height / 2, phase: 'in' })
      await wait(FLOOD_MS)

      setState((s) => (s ? { ...s, phase: 'hold' } : s))
      swap()
      window.scrollTo(0, 0)
      await wait(HOLD_MS)

      setState((s) => (s ? { ...s, phase: 'out' } : s))
      await wait(LIFT_MS)

      setState(null)
      busy.current = false
    },
    [],
  )

  return [state, run] as const
}
