'use client'

import { usePathname } from 'next/navigation'
import { useEffect } from 'react'
import { motion } from '@/lib/mart-motion'

/**
 * Re-tags the page for the motion engine after a client-side navigation.
 *
 * The engine walks the DOM once, when it boots. An App Router navigation
 * swaps the whole tree without a document load, so every rail and card
 * that arrives afterwards would never be tagged -- and since the reveal
 * engine's hiding rule is keyed off `html[data-mm-js]`, which stays set,
 * anything it did manage to tag on the way out would be left at opacity 0.
 *
 * `refresh()` only adds attributes to elements that do not already carry
 * them, so running it on every route change costs a single querySelectorAll
 * pass and cannot double-animate what is already on screen.
 */
export default function MotionRefresh() {
  const pathname = usePathname()

  useEffect(() => {
    motion()?.refresh()
  }, [pathname])

  return null
}
