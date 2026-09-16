'use client'

import Link from 'next/link'
import { Heart } from 'lucide-react'
import { useEffect, useState } from 'react'
import ProductCard from '@/components/catalogue/ProductCard'
import type { Product } from '@/lib/catalog'
import { useWishlist } from '@/lib/use-wishlist'

/**
 * My List.
 *
 * Products are fetched by id rather than imported. Importing the catalogue
 * into this client component put all 38 products -- names, prices and stock
 * levels -- into an 18.3 KB browser chunk, which is the same mistake
 * SearchBar made before it moved behind a route handler.
 *
 * Only ids are persisted, so everything else is re-resolved on every visit:
 * a list opened weeks later cannot show a stale price, and a withdrawn
 * product falls out of the response rather than rendering from a snapshot.
 */
export default function ListPage() {
  const ids = useWishlist()
  /*
   * Results are stored WITH the id list they belong to, and the visible
   * items are derived by comparing that key to the current one.
   *
   * A bare Product[] plus an empty-case setState in the effect body is a
   * synchronous setState inside an effect, which costs a render pass. It
   * also fixes a staleness window: items fetched for a previous list can
   * never be shown under a newer one.
   */
  const key = ids.join(',')
  const [data, setData] = useState<{ key: string; items: Product[] }>({ key: '', items: [] })
  const items = ids.length === 0 ? [] : data.key === key ? data.items : null

  useEffect(() => {
    if (!ids.length) return
    const controller = new AbortController()
    fetch('/api/products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : { items: [] }))
      .then((payload: { items: Product[] }) => {
        // Kept in the order the customer saved them, not the order the
        // route happened to return.
        const byId = new Map(payload.items.map((p) => [p.id, p]))
        setData({
          key,
          items: ids.map((id) => byId.get(id)).filter((p): p is Product => Boolean(p)),
        })
      })
      .catch(() => {})
    return () => controller.abort()
  }, [ids, key])

  return (
    <section>
      <h2 className="text-ink font-display mb-4 text-lg font-extrabold tracking-tight">My List</h2>

      {items === null ? (
        <p className="text-slate-muted text-sm">Loading your list…</p>
      ) : items.length ? (
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
          {items.map((p) => (
            <li key={p.id} className="contents">
              <ProductCard product={p} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="border-surface-line bg-surface rounded-card border p-10 text-center">
          <span className="bg-brand-50 text-brand-600 mx-auto inline-flex size-14 items-center justify-center rounded-2xl">
            <Heart className="size-6" aria-hidden />
          </span>
          <h3 className="text-ink mt-4 text-base font-extrabold">Your list is empty</h3>
          <p className="text-slate-muted mx-auto mt-1.5 max-w-sm text-sm">
            Tap the heart on any product to save it here.
          </p>
          <Link
            href="/"
            className="bg-brand-600 hover:bg-brand-700 mt-5 inline-flex h-11 items-center rounded-pill px-6 text-sm font-bold text-white transition-colors"
          >
            Browse products
          </Link>
        </div>
      )}
    </section>
  )
}
