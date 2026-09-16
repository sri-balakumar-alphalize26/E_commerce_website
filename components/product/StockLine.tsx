import { PackageX, Truck } from 'lucide-react'
import type { Product } from '@/lib/catalog'
import { CATALOG } from '@/lib/catalog-config'

/**
 * One line, three exclusive states.
 *
 * The shipping copy is a POLICY sentence from config, not a computed date.
 * Nothing in this build knows a customer's address, a courier or a cut-off,
 * so "Get it by Tuesday" would be a promise with nothing behind it -- the
 * same fabrication as a fake review, just harder to spot.
 */
export default function StockLine({ product }: { product: Product }) {
  if (!product.inStock) {
    return (
      <p className="bg-danger-soft text-danger flex items-center gap-2 rounded-md px-3 py-2 text-[13px] font-bold">
        <PackageX className="size-4 shrink-0" aria-hidden />
        Out of stock
      </p>
    )
  }

  return (
    <div className="space-y-2">
      {product.stockStatus === 'low' ? (
        <p className="text-ink text-[13px] font-bold">Only {product.stock} left</p>
      ) : null}
      <p className="bg-brand-50 text-brand-700 flex items-center gap-2 rounded-md px-3 py-2 text-[13px] font-semibold">
        <Truck className="size-4 shrink-0" aria-hidden />
        {CATALOG.shippingNote}
      </p>
    </div>
  )
}
