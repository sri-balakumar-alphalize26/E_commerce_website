/**
 * Currency formatting.
 *
 * The locale is PINNED rather than taken from the browser. The same amount
 * must format identically during server render and after hydration, and
 * `navigator.language` differs between the two — React reports that as a
 * hydration mismatch. INR gets en-IN so grouping follows the lakh/crore
 * convention (1,24,500 rather than 124,500); everything else gets en-US.
 *
 * An unrecognised currency code falls through to "CODE 1234.00" instead of
 * throwing, because a bad code from upstream should degrade a price label,
 * not take down the render.
 */

const LOCALES: Record<string, string> = {
  INR: 'en-IN',
}

const cache = new Map<string, Intl.NumberFormat>()

function formatter(currency: string) {
  const key = currency.toUpperCase()
  const hit = cache.get(key)
  if (hit) return hit
  try {
    const fmt = new Intl.NumberFormat(LOCALES[key] ?? 'en-US', {
      style: 'currency',
      currency: key,
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
    })
    cache.set(key, fmt)
    return fmt
  } catch {
    return null
  }
}

export function formatMoney(amount: number, currency = 'USD') {
  const fmt = formatter(currency)
  if (!fmt) return `${currency.toUpperCase()} ${amount.toFixed(2)}`
  return fmt.format(amount)
}

/**
 * Whole-rupee form for dense surfaces — cards, rails, the sticky cart bar —
 * where two decimal places are noise. Detail, cart and checkout always use
 * `formatMoney`, because that is where a customer checks the arithmetic.
 */
export function formatMoneyCompact(amount: number, currency = 'USD') {
  const key = currency.toUpperCase()
  try {
    return new Intl.NumberFormat(LOCALES[key] ?? 'en-US', {
      style: 'currency',
      currency: key,
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    return `${key} ${Math.round(amount)}`
  }
}
