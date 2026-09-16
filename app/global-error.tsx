'use client'

import { useEffect } from 'react'

/**
 * The last-resort error boundary.
 *
 * This is the one place app/error.tsx cannot cover: a throw in the ROOT
 * layout, which is exactly where CartProvider and SiteHeader live. Without
 * this file that case falls through to Next's built-in error page, and that
 * page injects
 *
 *   @media (prefers-color-scheme:dark) { body { background:#000 } }
 *
 * unlayered -- the precise mechanism that turned every category page black
 * before. The defence in app/globals.css has a hole here, and this closes it.
 *
 * EVERY STYLE BELOW IS INLINE, DELIBERATELY. global-error replaces the root
 * layout wholesale, so it renders its own <html> and <body> and NOTHING from
 * globals.css applies -- no Tailwind, no design tokens, no @layer. Reaching
 * for a class here would produce an unstyled page in the one situation where
 * the page is already broken. The colours are the literal token values
 * because `var(--color-*)` would resolve to nothing too.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('[storefront:fatal]', error.digest ?? error.message)
  }, [error])

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: '100dvh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          // Explicit, and never conditional on prefers-color-scheme.
          background: '#f4f9fc',
          color: '#334155',
          fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif',
        }}
      >
        <div
          style={{
            maxWidth: '28rem',
            width: '100%',
            textAlign: 'center',
            background: '#ffffff',
            border: '1px solid #dce8ef',
            borderRadius: '12px',
            padding: '32px 24px',
          }}
        >
          <h1
            style={{
              margin: 0,
              fontSize: '1.125rem',
              fontWeight: 800,
              color: '#0b1620',
              letterSpacing: '-0.02em',
            }}
          >
            Something went wrong
          </h1>
          <p style={{ margin: '8px 0 0', fontSize: '0.875rem', color: '#5b7183' }}>
            The page could not be loaded. Trying again usually clears it.
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: '20px',
              height: '44px',
              padding: '0 24px',
              border: 0,
              borderRadius: '50px',
              background: '#0078a8',
              color: '#ffffff',
              fontSize: '0.875rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
          {error.digest ? (
            <p
              style={{
                margin: '16px 0 0',
                fontSize: '11px',
                color: '#94a3b8',
                fontFamily: 'ui-monospace, monospace',
              }}
            >
              ref {error.digest}
            </p>
          ) : null}
        </div>
      </body>
    </html>
  )
}
