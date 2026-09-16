'use client'

import { useCallback, useSyncExternalStore } from 'react'

/**
 * Reach for CSS first -- this is for behaviour a media query cannot express,
 * such as rendering a bottom sheet on mobile and a sidebar on desktop from
 * genuinely different markup.
 *
 * Returns false during the server render and the first client paint, because
 * the match is unknowable until the client mounts. Anything that would look
 * wrong in that frame needs a CSS solution instead.
 */
export function useMediaQuery(query: string) {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const mql = window.matchMedia(query)
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    },
    [query],
  )

  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  )
}
