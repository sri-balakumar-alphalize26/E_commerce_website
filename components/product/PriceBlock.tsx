import type { Product } from '@/lib/catalog'
import { savings } from '@/lib/catalog'
import { cn } from '@/lib/cn'
import { formatMoney } from '@/lib/money'

/**
 * The price treatment.
 *
 * Emphasis comes from size and weight, never from hue: the price is a
 * statement of fact, and colouring it brand blue or accent orange would
 * either compete with the CTA or imply the number is a link. The only
 * coloured element is the savings line, which is genuinely about money the
 * customer keeps.
 *
 * Tabular figures throughout, so a column of prices lines up on the decimal.
 */
export default function PriceBlock({
  product,
  size = 'lg',
  className,
}: {
  product: Product
  size?: 'lg' | 'sm'
  className?: string
}) {
  const discounted = product.originalPrice > product.price
  const saved = savings(product)

  return (
    <div className={className}>
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span
          className={cn(
            'tnum text-brand-600 font-extrabold',
            size === 'lg' ? 'text-[1.75rem] leading-none' : 'text-lg leading-none',
          )}
        >
          {formatMoney(product.price, product.currency)}
        </span>

        {discounted ? (
          <>
            <span className="tnum text-slate-faint text-sm line-through">
              {formatMoney(product.originalPrice, product.currency)}
            </span>
            <span className="bg-save-soft text-save rounded-tag px-1.5 py-0.5 text-[11px] font-bold tabular-nums">
              {product.discountPercent}% off
            </span>
          </>
        ) : null}
      </div>

      {discounted ? (
        <p className="text-save mt-1.5 text-[13px] font-bold">
          You save {formatMoney(saved, product.currency)}
        </p>
      ) : null}
    </div>
  )
}
