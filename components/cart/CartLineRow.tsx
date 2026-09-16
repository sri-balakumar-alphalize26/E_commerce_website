'use client'

import Link from 'next/link'
import { Minus, Plus, Trash2 } from 'lucide-react'
import { useCart } from '@/components/cart/CartProvider'
import ProductImage from '@/components/catalogue/ProductImage'
import type { CartLine } from '@/lib/cart'
import { formatMoney } from '@/lib/money'
import { productHref } from '@/lib/slug'

/**
 * One cart line.
 *
 * The stepper here is a full-size sibling of the card's compact one rather
 * than a reuse of it: this control operates on a CartLine, which may refer to
 * a product no longer in the catalogue, so it must not need a Product to
 * render. At the minimum quantity the minus becomes a bin -- pressing minus
 * at qty 1 means "take it out", and hiding that behind a separate X is how
 * customers end up with items they thought they had removed.
 *
 * badge and stockStatus travel on the line specifically so the micro-labels
 * a customer used to choose the item are still there while they review it.
 */
export default function CartLineRow({ line }: { line: CartLine }) {
  const { setQty, remove } = useCart()
  const step = line.qtyStep > 0 ? line.qtyStep : 1
  const atMin = line.qty <= line.minQty
  const atCap = line.qty + step > line.stock

  return (
    <li className="border-surface-line flex gap-3 border-b py-4 last:border-b-0">
      <Link
        href={productHref({ vertical: line.vertical, slug: line.slug, id: line.productId })}
        className="border-surface-line size-20 shrink-0 overflow-hidden rounded-md border"
      >
        <ProductImage id={line.productId} src={line.image} alt={line.name} sizes="80px" />
      </Link>

      <div className="min-w-0 flex-1">
        <Link href={productHref({ vertical: line.vertical, slug: line.slug, id: line.productId })} className="hover:text-brand-600 transition-colors">
          <p className="text-ink line-clamp-2 text-[13px] font-semibold">{line.name}</p>
        </Link>
        <p className="text-slate-muted mt-0.5 truncate text-xs">{line.subtitle}</p>

        {line.stockStatus === 'low' ? (
          <p className="text-ink mt-1 text-[11px] font-bold">Only {line.stock} left</p>
        ) : null}
        {!line.inStock ? (
          <p className="text-danger mt-1 text-[11px] font-bold">No longer available</p>
        ) : null}

        <div className="mt-2 flex items-center justify-between gap-3">
          <div className="border-field-line inline-flex h-9 items-center rounded-md border">
            <button
              type="button"
              onClick={() => (atMin ? remove(line.productId) : setQty(line.productId, line.qty - step))}
              aria-label={atMin ? `Remove ${line.name} from cart` : `Decrease ${line.name}`}
              className="text-brand-600 hover:bg-brand-50 inline-flex h-9 w-9 items-center justify-center rounded-l-md transition-colors"
            >
              {atMin ? <Trash2 className="size-4" aria-hidden /> : <Minus className="size-4" aria-hidden />}
            </button>
            <span className="tnum text-ink min-w-8 text-center text-sm font-bold" aria-live="polite">
              {line.qty}
            </span>
            <button
              type="button"
              onClick={() => setQty(line.productId, line.qty + step)}
              disabled={atCap}
              aria-label={`Increase ${line.name}`}
              className="text-brand-600 hover:bg-brand-50 inline-flex h-9 w-9 items-center justify-center rounded-r-md transition-colors disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <Plus className="size-4" aria-hidden />
            </button>
          </div>

          <div className="text-right">
            <p className="tnum text-ink text-sm font-bold">
              {formatMoney(line.price * line.qty, line.currency)}
            </p>
            {line.originalPrice > line.price ? (
              <p className="tnum text-slate-faint text-[11px] line-through">
                {formatMoney(line.originalPrice * line.qty, line.currency)}
              </p>
            ) : null}
          </div>
        </div>

        {atCap ? (
          <p className="text-slate-muted mt-1.5 text-[11px] font-bold">
            Max {line.stock} in stock
          </p>
        ) : null}
      </div>
    </li>
  )
}
