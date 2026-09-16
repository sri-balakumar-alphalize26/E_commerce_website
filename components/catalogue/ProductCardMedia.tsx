'use client'

import Link from 'next/link'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useRef, useState } from 'react'
import ProductImage from '@/components/catalogue/ProductImage'
import Dots from '@/components/ui/Dots'
import type { Product } from '@/lib/catalog'
import { cn } from '@/lib/cn'
import { productHref } from '@/lib/slug'
import { useMediaQuery } from '@/lib/use-media-query'

/**
 * The card's image area: every pack-shot a product has, on a scroll-snap
 * track, with arrows and a dot count.
 *
 * A NATIVE SCROLLER, not a slider. The track is the same construction as
 * HeroCarousel -- snap points and an index read back off scrollLeft -- so
 * swipe, momentum, rubber-banding and reduced-motion all come from the
 * browser. There is no transform to animate and no library to ship, which
 * matters more here than on the hero because this component is mounted
 * twenty times on a grid.
 *
 * SLIDES ARE LINKS, CONTROLS ARE NOT. Each slide wraps its image in the
 * product link, so a tap anywhere on the art still opens the product AND
 * the swipe gesture begins on an element inside the scroller. That second
 * half is the load-bearing one: a browser picks the scroller for a touch
 * by walking the ANCESTORS of whatever the finger landed on, so the
 * tempting alternative -- one link stretched across the whole frame with
 * the track behind it -- would make every swipe scroll the page instead,
 * on mobile only, where it is least likely to be noticed.
 *
 * The arrows are siblings of the track rather than children of a slide: a
 * button nested in an anchor is invalid HTML and turns every tap into a
 * coin-flip between advancing the image and navigating away from it.
 *
 * NO CAROUSEL ARIA. HeroCarousel announces itself with
 * aria-roledescription="carousel" and labels each slide, which is right for
 * one banner and wrong thirty times over on a grid -- it would put the word
 * "carousel" in front of every product name on the page. Everything after
 * the first slide is hidden from assistive technology instead, and the
 * whole gallery is one link away on the product page, where ProductGallery
 * already exposes it properly.
 */

type Props = {
  product: Product
  priority?: boolean
  /**
   * Set when the card sits inside a horizontally-scrolling rail.
   *
   * Two horizontal scrollers nested one inside the other cannot both read
   * the same drag, and the browser resolves it in favour of the INNER one:
   * a customer dragging the homescreen rail would flip a card's picture
   * and leave the rail where it was. `overflow-x: hidden` keeps the track
   * programmatically scrollable -- scrollTo, snapping and scrollLeft all
   * still work, so the arrows are unaffected -- while taking it out of the
   * touch scroll chain entirely, which hands the drag back to the rail.
   *
   * `touch-action: pan-y` is the obvious-looking alternative and is a trap:
   * it is resolved up the ancestor chain and forbids the gesture outright,
   * so a horizontal swipe on the art would scroll neither the card nor the
   * rail.
   *
   * With the swipe gone, the chrome would be unoperable on a touch screen
   * -- there is no hover to reveal the arrows -- so below `md` a railed
   * card shows no dots and no arrows at all. A control that cannot be
   * worked is worse than no control.
   */
  railSafe?: boolean
  className?: string
}

export default function ProductCardMedia({ product, priority, railSafe, className }: Props) {
  const images = product.images.length ? product.images : [product.image]
  const multiple = images.length > 1

  const trackRef = useRef<HTMLDivElement>(null)
  const [index, setIndex] = useState(0)
  /**
   * Gates every image after the first.
   *
   * A grid shows twenty cards, so mounting four pack-shots apiece would
   * quadruple the requests behind the fold for pictures most customers
   * never ask to see. The slide BOXES are always rendered, so the track is
   * the right width and the dots tell the truth before anything is
   * fetched; only the image inside them waits. The flag flips on the first
   * sign of interest -- a pointer entering, a finger landing, focus
   * arriving, or the track being scrolled by any other means -- and
   * touchstart in particular fires as the finger lands, well before the
   * swipe resolves, so the next slide is painted by the time it snaps in.
   */
  const [activated, setActivated] = useState(false)
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')

  function activate() {
    setActivated(true)
  }

  function onScroll() {
    const track = trackRef.current
    if (!track) return
    setActivated(true)
    setIndex(Math.round(track.scrollLeft / track.clientWidth))
  }

  function go(delta: number) {
    const track = trackRef.current
    if (!track) return
    setActivated(true)
    // Wraps, like the hero. Hiding an arrow at the end of the set makes it
    // vanish from under the cursor on the very click that got you there.
    const next = (index + delta + images.length) % images.length
    track.scrollTo({ left: next * track.clientWidth, behavior: reduced ? 'auto' : 'smooth' })
  }

  return (
    <div
      className={cn('relative', className)}
      onPointerEnter={activate}
      onTouchStart={activate}
      onFocusCapture={activate}
    >
      <div
        ref={trackRef}
        onScroll={multiple ? onScroll : undefined}
        className={cn(
          'flex [scrollbar-width:none] [&::-webkit-scrollbar]:hidden',
          multiple && 'snap-x snap-mandatory',
          railSafe ? 'overflow-x-hidden' : 'overflow-x-auto',
        )}
      >
        {images.map((src, i) => (
          <div
            key={src}
            /*
              card-img goes on the SLIDE, never on the track.

              The engine's rule for this role is `overflow: hidden` -- the
              shorthand -- so putting it on the scroller would reset
              overflow-x from auto and kill the swipe outright. On a slide
              it is exactly what the hover zoom needs: 1.05 scale clipped to
              its own frame, with no bleed into the neighbouring image and
              no cross-axis scrollbar on the track.
            */
            data-mm="card-img"
            className="w-full shrink-0 snap-start"
            // Four near-identical pack-shots per card would otherwise be
            // read out on every tile in the grid.
            aria-hidden={i === 0 ? undefined : true}
          >
            <Link
              href={productHref(product)}
              tabIndex={i === 0 ? undefined : -1}
              className="focus-visible:outline-brand-500 block"
            >
              {i === 0 || activated ? (
                <ProductImage
                  id={product.id}
                  src={src}
                  alt={product.name}
                  priority={priority && i === 0}
                  // The mount gate above IS the laziness; the attribute
                  // would only stop the fetch from ever happening.
                  loading={i === 0 ? undefined : 'eager'}
                />
              ) : (
                <div className="bg-surface aspect-square w-full" />
              )}
            </Link>
          </div>
        ))}
      </div>

      {multiple ? (
        <>
          <Arrow
            side="left"
            railSafe={railSafe}
            onClick={() => go(-1)}
            label={`Previous image of ${product.name}`}
          />
          <Arrow
            side="right"
            railSafe={railSafe}
            onClick={() => go(1)}
            label={`Next image of ${product.name}`}
          />

          {/* Over the art, not under it. A row between the image and the
              pack-size band would add its height to every card in every
              grid, and the skeleton would have to grow to match.

              CENTRED, AND CLEAR OF THE BOTTOM ROW. These were bottom-right
              for a while, tucked beside the discount badge, and they read as
              misaligned because they were: a 6px dot and an 18px chip share
              a bottom edge and nothing else, so the eye lines them up and
              finds them 2px apart.

              36px up is the vendored design's own answer to the same
              problem, and it is worth copying exactly -- it clears both the
              badge and the out-of-stock ribbon, which lets the position stop
              depending on stock. The translucent pill is what keeps six grey
              pixels legible over a photograph. */}
          <Dots
            count={images.length}
            index={index}
            onMedia
            className={cn(
              'rounded-pill bg-surface/75 pointer-events-none absolute bottom-9 left-1/2 -translate-x-1/2 items-center px-1.5 py-1 backdrop-blur-[4px]',
              railSafe && 'hidden md:flex',
            )}
          />
        </>
      ) : null}
    </div>
  )
}

function Arrow({
  side,
  railSafe,
  onClick,
  label,
}: {
  side: 'left' | 'right'
  railSafe?: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      // Pointer-only chrome, and a duplicate of what the product page
      // offers properly: taking it out of the tab order keeps a 30-card
      // grid from growing sixty stops that all lead somewhere the keyboard
      // user can already reach.
      tabIndex={-1}
      aria-hidden
      className={cn(
        'border-surface-line bg-surface/90 text-slate-body shadow-card absolute top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-full border opacity-0 transition-opacity group-hover:opacity-100',
        // The visible button stays 28px; the TARGET is 44px via a
        // pseudo-element that overflows it without affecting layout.
        "before:absolute before:top-1/2 before:left-1/2 before:size-11 before:-translate-x-1/2 before:-translate-y-1/2 before:content-['']",
        side === 'left' ? 'left-1.5' : 'right-1.5',
        // group-hover is already gated behind (hover: hover) by Tailwind,
        // so these never appear on a touch screen; in a rail that leaves
        // nothing to operate below md, so they are dropped there outright.
        railSafe && 'hidden md:inline-flex',
      )}
    >
      {side === 'left' ? (
        <ChevronLeft className="size-4" aria-hidden />
      ) : (
        <ChevronRight className="size-4" aria-hidden />
      )}
    </button>
  )
}
