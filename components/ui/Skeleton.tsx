import { cn } from '@/lib/cn'

/**
 * A loading placeholder. The shimmer is suppressed under reduced-motion by
 * the global rule in globals.css, leaving a static block rather than nothing.
 */
export default function Skeleton({ className }: { className?: string }) {
  return <div className={cn('bg-surface-line/60 animate-pulse rounded', className)} aria-hidden />
}
