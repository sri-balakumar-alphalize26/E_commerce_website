'use client'

import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useLockBodyScroll } from '@/lib/use-lock-body-scroll'

/**
 * The mobile bottom sheet, with the grab handle from the reference
 * FilterSortBar.
 *
 * Portalled to <body> so it escapes any ancestor with `overflow: hidden` or
 * a transform -- a sheet rendered in place inside a scrolling grid gets
 * clipped, and a transformed ancestor would make `position: fixed` resolve
 * against the wrong containing block.
 *
 * Focus is moved in on open and returned on close, and Escape closes. Body
 * scroll is frozen through the shared hook, which restores the scroll
 * position afterwards -- without that, closing a filter sheet drops the
 * customer back at the top of a long grid.
 */
export default function BottomSheet({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreRef = useRef<HTMLElement | null>(null)

  useLockBodyScroll(open)

  useEffect(() => {
    if (!open) return
    restoreRef.current = document.activeElement as HTMLElement | null
    panelRef.current?.focus()

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      restoreRef.current?.focus?.()
    }
  }, [open, onClose])

  if (!open || typeof document === 'undefined') return null

  return createPortal(
    <div className="fixed inset-0 z-[70] flex flex-col justify-end">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 cursor-default"
        style={{ background: 'var(--scrim)' }}
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="bg-surface relative max-h-[82dvh] w-full overflow-hidden rounded-t-panel shadow-[0_-12px_28px_-12px_rgb(4_56_79/0.28)] outline-none"
      >
        <div className="flex justify-center pt-2.5 pb-1">
          <span className="bg-surface-line h-1 w-10 rounded-pill" aria-hidden />
        </div>

        <div className="border-surface-line border-b px-4 pb-3">
          <h2 className="text-ink text-[15px] font-bold">{title}</h2>
        </div>

        <div className="max-h-[56dvh] overflow-y-auto px-4 py-3">{children}</div>

        {footer ? (
          <div className="border-surface-line bg-surface border-t px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  )
}
