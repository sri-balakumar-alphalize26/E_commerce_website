import { NextResponse } from 'next/server'
import { searchProducts } from '@/lib/fixtures'
import { productHref } from '@/lib/slug'

/**
 * Search suggestions, computed on the server.
 *
 * SearchBar used to import `searchProducts` directly. Because it is a client
 * component mounted in the root layout, that dragged the entire catalogue
 * into the browser: a measured 28,446-byte chunk referenced by 11 of 12
 * prerendered pages, including /cart and the 404. Every stock level was
 * public in the JS bundle, and the scan ran unmemoised during render on
 * every keystroke.
 *
 * Moving it behind a route handler fixes the payload, keeps stock out of the
 * bundle, and -- the reason that matters most -- is the shape the real
 * backend needs. When the catalogue is remote, the client cannot hold it.
 *
 * The response is deliberately narrower than Product: a suggestion row needs
 * a label and a destination, not price or stock.
 */

export type Suggestion = {
  id: number
  name: string
  subtitle: string
  href: string
}

const MAX = 7
const MIN_TERM = 2

export async function GET(request: Request) {
  const term = (new URL(request.url).searchParams.get('q') ?? '').trim()

  if (term.length < MIN_TERM) {
    return NextResponse.json({ items: [] as Suggestion[] })
  }

  const items: Suggestion[] = searchProducts(term)
    .slice(0, MAX)
    .map((p) => ({
      id: p.id,
      name: p.name,
      subtitle: p.subtitle,
      href: productHref(p),
    }))

  return NextResponse.json(
    { items },
    {
      // Suggestions are public and identical for everyone, so a short shared
      // cache absorbs the repeated prefixes a typing session produces.
      headers: { 'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=300' },
    },
  )
}
