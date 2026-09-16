'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import Dots from '@/components/ui/Dots'
import { CATALOG } from '@/lib/catalog-config'
import { cn } from '@/lib/cn'
import { useMediaQuery } from '@/lib/use-media-query'

/**
 * The promo carousel.
 *
 * A native scroll-snap track rather than a JS slider: swipe, momentum and
 * keyboard scrolling all come free and correct, and there is no transform
 * animation to fight with reduced-motion.
 *
 * Autoplay stops on hover, on focus anywhere inside, and entirely under
 * prefers-reduced-motion -- an auto-advancing banner that moves while
 * someone is reading it is the most common accessibility complaint about
 * this pattern.
 *
 * Slides carry the deep end of the gradient only. White text on the logo's
 * bright cyan measures 2.09:1; --brand-gradient stops short of it.
 */
const TONES: Record<string, string> = {
  brand: 'brand-gradient',
  deep: 'bg-brand-900',
  accent: 'bg-brand-800',
}

const INTERVAL = 5000

export default function HeroCarousel() {
  const slides = CATALOG.slides
  const trackRef = useRef<HTMLDivElement>(null)
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')

  useEffect(() => {
    if (paused || reduced || slides.length < 2) return
    const t = setInterval(() => {
      const track = trackRef.current
      if (!track) return
      const next = (Math.round(track.scrollLeft / track.clientWidth) + 1) % slides.length
      track.scrollTo({ left: next * track.clientWidth, behavior: 'smooth' })
    }, INTERVAL)
    return () => clearInterval(t)
  }, [paused, reduced, slides.length])

  function onScroll() {
    const track = trackRef.current
    if (!track) return
    setIndex(Math.round(track.scrollLeft / track.clientWidth))
  }

  function goTo(i: number) {
    const track = trackRef.current
    if (!track) return
    track.scrollTo({ left: i * track.clientWidth, behavior: reduced ? 'auto' : 'smooth' })
  }

  return (
    <section
      aria-roledescription="carousel"
      aria-label="Promotions"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div
        ref={trackRef}
        onScroll={onScroll}
        className="flex snap-x snap-mandatory overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {slides.map((slide, i) => (
          <div
            key={slide.key}
            className="w-full shrink-0 snap-start pr-3 last:pr-0"
            role="group"
            aria-roledescription="slide"
            aria-label={`${i + 1} of ${slides.length}`}
          >
            {/*
              data-mm-skip, but still data-mm="hero": skip keeps the banner
              itself out of the reveal engine, so the card paints without
              waiting for a script, while the role still lets the engine
              run the light sweep, the drifting glow and the text cascade.

              The cascade is the one piece here that DOES hide first --
              hero-text's children start at opacity 0 under html[data-mm-js]
              -- so the headline waits for the engine. That is accepted
              deliberately for the effect, and bounded by the 2.5s failsafe
              in app/layout.tsx, which drops the flag and reveals the text
              if the engine never arrives.

              Title, subtitle and CTA are DIRECT children of hero-text
              because the cascade is driven by :nth-child -- the CTA is the
              third child, which is the one that gets the pop rather than a
              rise. mt-auto on it reproduces what justify-between did on
              the link before the three were grouped.
            */}
            <Link
              href={slide.href}
              data-mm="hero"
              data-mm-skip
              className={cn(
                'on-dark flex min-h-[150px] flex-col rounded-2xl p-5 text-white md:min-h-[180px] md:p-6',
                TONES[slide.tone] ?? TONES.brand,
              )}
            >
              <div data-mm="hero-text" className="flex flex-1 flex-col items-start">
                <p className="font-display text-xl leading-tight font-bold tracking-tight md:text-2xl">
                  {slide.title}
                </p>
                <p className="mt-1.5 text-[13px] text-white/85">{slide.subtitle}</p>
                <span
                  data-mm="hero-cta"
                  className="chip-on-brand mt-auto inline-flex h-8 w-fit items-center rounded-pill px-3.5 text-xs font-extrabold tracking-[0.3px]"
                >
                  {slide.cta}
                </span>
              </div>
            </Link>
          </div>
        ))}
      </div>

      <Dots
        count={slides.length}
        index={index}
        onSelect={goTo}
        noun="slide"
        dataMm="hero-dots"
        className="mt-2.5"
      />
    </section>
  )
}
