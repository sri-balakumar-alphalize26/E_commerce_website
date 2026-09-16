import { cn } from '@/lib/cn'

/**
 * The page measure. One place to change the gutter, so the header card,
 * the grid and the footer can never drift out of alignment with each other.
 */
export default function Container({
  className,
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn('mx-auto w-full max-w-[1360px] px-4 md:px-6', className)}>{children}</div>
  )
}
