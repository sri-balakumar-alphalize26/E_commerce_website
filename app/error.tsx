'use client'

import { useEffect } from 'react'
import { RotateCcw, TriangleAlert } from 'lucide-react'
import Container from '@/components/ui/Container'

/**
 * The recoverable error boundary.
 *
 * Like not-found.tsx, this exists partly so Next's built-in error page --
 * and its unlayered dark-mode body background -- is never reached.
 *
 * `error.message` is deliberately not rendered. In production Next replaces
 * it with a digest, and in development it is a stack-shaped string that tells
 * a shopper nothing. The digest is logged instead, so a report can be
 * correlated without putting internals on screen.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('[storefront]', error.digest ?? error.message)
  }, [error])

  return (
    <main>
      <Container className="py-16">
        <div className="border-surface-line bg-surface shadow-card rounded-card mx-auto max-w-xl border p-8 text-center">
          <span className="bg-danger-soft text-danger mx-auto inline-flex size-14 items-center justify-center rounded-2xl">
            <TriangleAlert className="size-6" aria-hidden />
          </span>
          <h1 className="text-ink mt-4 text-lg font-bold">Something went wrong</h1>
          <p className="text-slate-muted mx-auto mt-1.5 max-w-sm text-sm">
            The page did not load. Trying again usually clears it.
          </p>
          <button
            type="button"
            onClick={reset}
            className="bg-brand-600 hover:bg-brand-700 mt-5 inline-flex h-11 items-center gap-2 rounded-pill px-6 text-sm font-bold text-white transition-colors"
          >
            <RotateCcw className="size-4" aria-hidden />
            Try again
          </button>
          {error.digest ? (
            <p className="text-slate-faint mt-4 font-mono text-[11px]">ref {error.digest}</p>
          ) : null}
        </div>
      </Container>
    </main>
  )
}
