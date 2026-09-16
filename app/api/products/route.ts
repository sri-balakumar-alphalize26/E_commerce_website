import { NextResponse } from 'next/server'
import type { Product } from '@/lib/catalog'
import { getProduct } from '@/lib/fixtures'

/**
 * Full products for a set of ids.
 *
 * My List holds ids in localStorage, so the page that renders it is a client
 * component -- and importing the catalogue there drags every product into
 * the browser bundle. That is not hypothetical: it is exactly what happened,
 * an 18.3 KB chunk, and it is the same mistake SearchBar made before it was
 * moved behind /api/suggest.
 *
 * Ids that no longer resolve are simply absent from the response, so a list
 * naturally sheds withdrawn products rather than rendering from a stale
 * snapshot.
 */
export async function POST(request: Request) {
  let ids: unknown
  try {
    ids = (await request.json())?.ids
  } catch {
    return NextResponse.json({ error: 'Invalid body' }, { status: 400 })
  }

  if (!Array.isArray(ids)) {
    return NextResponse.json({ error: 'ids must be an array' }, { status: 400 })
  }

  const items = ids
    .filter((id): id is number => Number.isInteger(id))
    .slice(0, 100)
    .map((id) => getProduct(id))
    .filter((p): p is Product => p !== null)

  return NextResponse.json({ items }, { headers: { 'Cache-Control': 'no-store' } })
}
