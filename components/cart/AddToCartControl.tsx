'use client'

import { Minus, Plus } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { addProduct, setProductQty } from '@/lib/cart-store'
import type { Product } from '@/lib/catalog'
import { cn } from '@/lib/cn'
import { flyToCart } from '@/lib/fly-to-cart'
import { useCartLine, useCartReady } from '@/lib/use-cart-line'

/**
 * The ADD-to-stepper morph.
 *
 * Before the product is in the cart this is an outlined ADD button. Once a
 * line exists it becomes a "minus / qty / plus" stepper IN THE SAME BOX --
 * which is only true because both states share a fixed width. An intrinsic
 * ADD is about 62px and a stepper about 104px, so without that the card
 * reflowed on every add, and again after hydration on every load with a
 * non-empty cart.
 *
 * `overlay` is the card variant, and it is where the real site puts it: a
 * compact white chip in the TOP-RIGHT CORNER OF THE IMAGE, not a bar at the
 * foot of the card. That position is most of what makes a grid read as a
 * grocery marketplace -- the control sits on the product, the text block
 * below stays uninterrupted, and the swap to a stepper never moves a single
 * pixel of layout.
 *
 * COLOUR: white ground with a brand-blue rim and blue glyphs in both states.
 * A saturated fill would put twenty solid blue rectangles across a grid and
 * compete with the one orange CTA the accent budget exists to protect.
 * Orange never appears here; it belongs to View Cart and Place Order alone.
 */

type Props = {
  product: Product
  /** Card variant: a compact chip meant to sit over the product image. */
  overlay?: boolean
  className?: string
}

export default function AddToCartControl({ product, overlay = false, className }: Props) {
  // Subscribed to THIS product only. Reading the cart through context here
  // re-rendered every control on the page on every quantity change, because
  // context has no selector -- see lib/use-cart-line.ts.
  const line = useCartLine(product.id)
  const ready = useCartReady()

  // One width for both states, so the morph cannot shift anything.
  const box = overlay ? 'h-9 w-[74px] text-[13px]' : 'h-11 w-[116px] text-sm'

  // Until the stored cart has been read every control would render as ADD and
  // then half of them would snap to a stepper. Showing the resting state
  // without the flip is the lesser of the two, and the shared width keeps the
  // swap from moving anything when it does happen.
  const qty = ready ? (line?.qty ?? 0) : 0

  /*
   * EVERY HOOK SITS ABOVE THE EARLY RETURNS.
   *
   * This block used to be further down, below the out-of-stock branch, which
   * meant an in-stock product called three hooks and an out-of-stock one
   * called none. That is not a style rule being satisfied: a product whose
   * stock flips between renders -- which cart reconciliation does on load --
   * changes the hook count for the same component instance, and React throws
   * rather than re-rendering.
   *
   * Re-triggers the count bump whenever the quantity changes. The motion
   * layer animates off a data-mm-bump attribute rather than a class, and a
   * CSS animation only replays if the attribute is removed, layout is
   * flushed, and it is set again -- so the offsetWidth read is load-bearing
   * and not a stray statement.
   *
   * It deliberately does nothing on the first pass: `ready` flips false to
   * true once storage has been read, and without that guard every load with
   * a non-empty cart would open with the number bouncing.
   */
  const qtyRef = useRef<HTMLSpanElement>(null)
  const seen = useRef(false)
  useEffect(() => {
    const el = qtyRef.current
    if (!el || !ready) return
    if (!seen.current) {
      seen.current = true
      return
    }
    el.removeAttribute('data-mm-bump')
    void el.offsetWidth
    el.setAttribute('data-mm-bump', '')
  }, [qty, ready])

  if (!product.inStock) {
    return (
      <span
        className={cn(
          'border-surface-line bg-surface/95 text-slate-faint inline-flex items-center justify-center rounded-lg border font-bold select-none',
          overlay ? 'h-9 px-2 text-[10px]' : 'h-11 px-4 text-xs',
          className,
        )}
      >
        Sold out
      </span>
    )
  }

  if (qty === 0) {
    return (
      <button
        type="button"
        /* data-mm-fly opts this button out of the engine's own dot flight;
           lib/fly-to-cart.ts sends the product image instead. The flight is
           started before the store write so the feedback is immediate. */
        data-mm="add"
        data-mm-fly
        onClick={(e) => {
          flyToCart(e.currentTarget)
          addProduct(product)
        }}
        aria-label={`Add ${product.name} to cart`}
        className={cn(
          'border-brand-600 text-brand-600 bg-surface hover:bg-brand-50 active:bg-brand-100 inline-flex items-center justify-center rounded-lg border font-bold shadow-sm transition-colors',
          box,
          className,
        )}
      >
        Add
      </button>
    )
  }

  const step = product.qtyStep > 0 ? product.qtyStep : 1
  const atCap = qty + step > product.stock

  return (
    <span
      data-mm="stepper"
      className={cn(
        'border-brand-600 bg-surface inline-flex items-center justify-between rounded-lg border shadow-sm',
        box,
        className,
      )}
    >
      <StepButton
        label={
          qty <= product.minQty ? `Remove ${product.name} from cart` : `Decrease ${product.name}`
        }
        onClick={() => setProductQty(product.id, qty - step)}
        overlay={overlay}
      >
        <Minus className={overlay ? 'size-3.5' : 'size-4'} aria-hidden />
      </StepButton>

      {/* aria-live so a screen reader announces the new quantity without the
          control losing focus on every press. */}
      <span
        ref={qtyRef}
        data-mm="qty"
        className="tnum text-ink flex-1 text-center font-bold"
        aria-live="polite"
      >
        {qty}
      </span>

      <StepButton
        label={`Increase ${product.name}`}
        onClick={() => setProductQty(product.id, qty + step)}
        disabled={atCap}
        overlay={overlay}
      >
        <Plus className={overlay ? 'size-3.5' : 'size-4'} aria-hidden />
      </StepButton>
    </span>
  )
}

function StepButton({
  label,
  onClick,
  disabled,
  overlay,
  children,
}: {
  label: string
  onClick: () => void
  disabled?: boolean
  overlay: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={cn(
        // The hit area is grown on the BUTTON via a pseudo-element that
        // overflows the box without affecting layout. Padding a wrapper --
        // which this file used to do -- widens the box without making either
        // glyph easier to hit, which is how you get a 32px target under a
        // comment claiming 44px.
        'text-brand-600 hover:bg-brand-50 active:bg-brand-100 relative inline-flex items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:bg-transparent',
        "before:absolute before:top-1/2 before:left-1/2 before:size-11 before:-translate-x-1/2 before:-translate-y-1/2 before:content-['']",
        overlay ? 'h-8 w-7' : 'h-10 w-10',
      )}
    >
      {children}
    </button>
  )
}
