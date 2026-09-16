'use client'

import Image from 'next/image'
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from 'lucide-react'
import { useRef, useState } from 'react'
import Dots from '@/components/ui/Dots'
import { cn } from '@/lib/cn'
import { isVector } from '@/lib/image'

/**
 * The product gallery: thumbnail rail, main frame, arrows, and a hover zoom.
 *
 * ZOOM. The magnifier is the Amazon/Flipkart pattern: hovering the main
 * frame opens a panel beside it showing a magnified crop that tracks the
 * cursor. It is built with a background-image rather than a scaled <img>
 * because background-position takes percentages directly, so the crop maps
 * to the cursor with no transform maths and no layout cost -- moving the
 * mouse only ever changes one CSS property.
 *
 * The panel is rendered OUTSIDE the frame, absolutely positioned to its
 * right, so it can overhang the info column without the frame needing
 * overflow:visible (which would let the zoom clip through the sticky
 * header).
 *
 * Deliberately pointer-gated. Zoom is opened by onMouseEnter, which touch
 * devices do not fire reliably, and a magnifier is meaningless on a screen
 * the size of the image anyway -- on mobile the same images are swipeable at
 * full width instead.
 */

const ZOOM = 2.6

export default function ProductGallery({
  images,
  alt,
  badge,
}: {
  images: string[]
  alt: string
  /** Pack size chip, drawn bottom-right over the frame. */
  badge?: string | null
}) {
  const [index, setIndex] = useState(0)
  const [zooming, setZooming] = useState(false)
  const [pos, setPos] = useState({ x: 50, y: 50 })
  const frameRef = useRef<HTMLDivElement>(null)

  const safe = images.length ? images : ['']
  const current = safe[Math.min(index, safe.length - 1)]
  const multiple = safe.length > 1

  function go(delta: number) {
    setIndex((i) => (i + delta + safe.length) % safe.length)
  }

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    const box = frameRef.current?.getBoundingClientRect()
    if (!box) return
    // Clamped so the panel never shows past the edge of the source image.
    const x = Math.min(100, Math.max(0, ((e.clientX - box.left) / box.width) * 100))
    const y = Math.min(100, Math.max(0, ((e.clientY - box.top) / box.height) * 100))
    setPos({ x, y })
  }

  return (
    <div className="flex gap-3">
      {/* Thumbnail rail: a column beside the frame from md up, a row beneath
          it below that, where vertical space is the scarce axis. */}
      {multiple ? (
        <div className="hidden w-[68px] shrink-0 flex-col gap-2 md:flex">
          <RailButton onClick={() => go(-1)} label="Previous image">
            <ChevronUp className="size-4" aria-hidden />
          </RailButton>

          <ul className="flex flex-col gap-2">
            {safe.map((src, i) => (
              <li key={src}>
                <Thumb
                  src={src}
                  alt={`${alt} view ${i + 1}`}
                  active={i === index}
                  onSelect={() => setIndex(i)}
                />
              </li>
            ))}
          </ul>

          <RailButton onClick={() => go(1)} label="Next image">
            <ChevronDown className="size-4" aria-hidden />
          </RailButton>
        </div>
      ) : null}

      <div className="relative min-w-0 flex-1">
        <div
          ref={frameRef}
          onMouseEnter={() => setZooming(true)}
          onMouseLeave={() => setZooming(false)}
          onMouseMove={onMove}
          className="border-surface-line bg-surface relative aspect-square w-full overflow-hidden rounded-[14px] border"
        >
          {current ? (
            <Image
              key={current}
              src={current}
              alt={alt}
              fill
              sizes="(min-width: 1100px) 46vw, 100vw"
              priority
              unoptimized={isVector(current)}
              className="object-contain p-2"
            />
          ) : null}

          {badge ? (
            <span className="bg-ink absolute right-3 bottom-3 rounded-lg px-2.5 py-1.5 text-[13px] font-extrabold text-white">
              {badge}
            </span>
          ) : null}

          {/* Arrows over the frame, for reaching the set without the rail. */}
          {multiple ? (
            <div className="absolute right-3 bottom-3 flex gap-1.5 md:bottom-auto md:top-1/2 md:right-0 md:left-0 md:-translate-y-1/2 md:justify-between md:px-2">
              <FrameArrow onClick={() => go(-1)} label="Previous image">
                <ChevronLeft className="size-5" aria-hidden />
              </FrameArrow>
              <FrameArrow onClick={() => go(1)} label="Next image">
                <ChevronRight className="size-5" aria-hidden />
              </FrameArrow>
            </div>
          ) : null}
        </div>

        {/* Mobile dots: the rail is hidden below md, so this is the only
            indication that there is more than one image. */}
        <Dots count={safe.length} index={index} onSelect={setIndex} className="mt-2.5 md:hidden" />

        {/* The magnifier. Desktop only, and only while the cursor is inside
            the frame. */}
        {zooming && current ? (
          <div
            aria-hidden
            className="border-surface-line bg-surface shadow-float pointer-events-none absolute top-0 left-[calc(100%+16px)] z-30 hidden aspect-square w-[420px] overflow-hidden rounded-[14px] border lg:block"
            style={{
              backgroundImage: `url(${current})`,
              backgroundRepeat: 'no-repeat',
              backgroundSize: `${ZOOM * 100}%`,
              backgroundPosition: `${pos.x}% ${pos.y}%`,
            }}
          />
        ) : null}
      </div>
    </div>
  )
}

function Thumb({
  src,
  alt,
  active,
  onSelect,
}: {
  src: string
  alt: string
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      // Hovering a thumbnail selects it, which is what both reference sites
      // do -- requiring a click to preview an image a customer is already
      // pointing at is a wasted interaction.
      onMouseEnter={onSelect}
      onFocus={onSelect}
      onClick={onSelect}
      aria-label={alt}
      aria-current={active ? 'true' : undefined}
      className={cn(
        'bg-surface relative block aspect-square w-full overflow-hidden rounded-lg border-2 transition-colors',
        active ? 'border-brand-600' : 'border-surface-line hover:border-brand-300',
      )}
    >
      <Image src={src} alt="" fill sizes="68px" unoptimized={isVector(src)} className="object-contain p-1" />
    </button>
  )
}

function RailButton({
  onClick,
  label,
  children,
}: {
  onClick: () => void
  label: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="border-surface-line text-slate-body hover:border-brand-300 hover:text-brand-600 bg-surface inline-flex h-8 w-full items-center justify-center rounded-lg border transition-colors"
    >
      {children}
    </button>
  )
}

function FrameArrow({
  onClick,
  label,
  children,
}: {
  onClick: () => void
  label: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="border-surface-line bg-surface/95 text-slate-body hover:text-brand-600 shadow-card pointer-events-auto inline-flex size-9 items-center justify-center rounded-full border transition-colors"
    >
      {children}
    </button>
  )
}
