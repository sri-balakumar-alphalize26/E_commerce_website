import { NextResponse } from 'next/server'
import { getProduct } from '@/lib/fixtures'

/**
 * Current price and availability for a set of cart lines.
 *
 * The cart persists in localStorage, so every field on a line is a snapshot
 * taken whenever the item was added -- price, stock, availability, even the
 * name. Nothing refreshed them, which meant a cart opened a week later could
 * show a stale total and an "Only 3 left" warning for something now fully
 * stocked or withdrawn.
 *
 * A product that no longer resolves is returned as `gone`, so the client can
 * tell "unchanged" apart from "withdrawn" rather than silently dropping a
 * line the customer put there.
 */

export type RepricedLine =
  | {
      id: number
      gone?: false
      name: string
      subtitle: string
      image: string
      currency: string
      price: number
      originalPrice: number
      stock: number
      stockStatus: 'ok' | 'low' | 'out'
      inStock: boolean
      minQty: number
      qtyStep: number
      badge: string | null
    }
  | { id: number; gone: true }

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

  const lines: RepricedLine[] = ids
    .filter((id): id is number => Number.isInteger(id))
    .slice(0, 100)
    .map((id) => {
      const p = getProduct(id)
      if (!p) return { id, gone: true as const }
      return {
        id: p.id,
        name: p.name,
        subtitle: p.subtitle,
        image: p.image,
        currency: p.currency,
        price: p.price,
        originalPrice: p.originalPrice,
        stock: p.stock,
        stockStatus: p.stockStatus,
        inStock: p.inStock,
        minQty: p.minQty,
        qtyStep: p.qtyStep,
        badge: p.badge,
      }
    })

  return NextResponse.json({ lines }, { headers: { 'Cache-Control': 'no-store' } })
}
