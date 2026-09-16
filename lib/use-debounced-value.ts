'use client'

import { useEffect, useState } from 'react'

/**
 * Trails `value` by `delay` ms. Used by search-as-you-type so a query fires
 * once the customer stops typing rather than once per keystroke.
 */
export function useDebouncedValue<T>(value: T, delay = 250) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])

  return debounced
}
