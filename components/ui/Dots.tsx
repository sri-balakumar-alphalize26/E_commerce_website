import { cn } from '@/lib/cn'

/**
 * The carousel position indicator: one dot per slide, the current one drawn
 * as a short bar rather than a larger circle so the row's height never
 * changes as it moves.
 *
 * INTERACTIVE OR NOT. Passing `onSelect` makes every dot a button with a
 * 44x44 tap target supplied by a pseudo-element -- the target overflows the
 * 6px dot without occupying layout, so a comfortable touch target costs no
 * space. Omitting `onSelect` renders the same row as inert spans, hidden
 * from assistive technology.
 *
 * That second mode exists for the product card. Four 44px targets need
 * 176px and a card is ~160px wide, so tappable dots there would overlap one
 * another and the arrows sitting beside them. On a surface that narrow the
 * dots earn their place as an ANSWER to "how many pictures are there", and
 * the pictures themselves are reached by swiping or by the arrows.
 */
export default function Dots({
  count,
  index,
  onSelect,
  noun = 'image',
  onMedia,
  align = 'center',
  dataMm,
  className,
}: {
  count: number
  index: number
  /** Omit to render an inert indicator instead of buttons. */
  onSelect?: (i: number) => void
  /** What each dot selects, for the button's accessible name. */
  noun?: string
  /**
   * Darkens the idle dot for a row drawn over product art.
   *
   * The default idle dot is --surface-line, which reads correctly against
   * the tinted panels these dots normally sit under but all but vanishes
   * on the white of an object-contain pack-shot.
   */
  onMedia?: boolean
  /** cn() is a plain joiner, so the row's alignment cannot be overridden
      from a caller's className -- it has to be chosen here. */
  align?: 'center' | 'end'
  /** data-mm role, for the motion engine. The row must carry it itself:
      the engine reads the dots as this element's direct children. */
  dataMm?: string
  className?: string
}) {
  if (count < 2) return null

  const dots = Array.from({ length: count }, (_, i) => i)
  const idle = onMedia ? 'bg-ink/25' : 'bg-surface-line'
  const justify = align === 'end' ? 'justify-end' : 'justify-center'

  if (!onSelect) {
    return (
      <div aria-hidden data-mm={dataMm} className={cn('flex gap-1', justify, className)}>
        {dots.map((i) => (
          <span
            key={i}
            className={cn(
              'block h-1.5 rounded-pill transition-all',
              i === index ? 'bg-brand-600 w-[18px]' : cn('w-1.5', idle),
            )}
          />
        ))}
      </div>
    )
  }

  return (
    <div data-mm={dataMm} className={cn('flex gap-1.5', justify, className)}>
      {dots.map((i) => (
        <button
          key={i}
          type="button"
          onClick={() => onSelect(i)}
          aria-label={`Show ${noun} ${i + 1}`}
          aria-current={i === index ? 'true' : undefined}
          className="relative inline-flex h-6 items-center px-1.5 before:absolute before:top-1/2 before:left-1/2 before:size-11 before:-translate-x-1/2 before:-translate-y-1/2 before:content-['']"
        >
          <span
            className={cn(
              'block h-1.5 rounded-pill transition-all',
              i === index ? 'bg-brand-600 w-[18px]' : cn('w-1.5', idle),
            )}
          />
        </button>
      ))}
    </div>
  )
}
