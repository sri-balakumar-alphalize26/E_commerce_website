import Skeleton from '@/components/ui/Skeleton'

/**
 * Mirrors ProductCard's box exactly -- square image, two title lines, a
 * subtitle, a price row and a control row -- so the swap from loading to
 * loaded shifts nothing.
 */
export default function ProductCardSkeleton() {
  return (
    <div className="border-surface-line bg-surface shadow-card rounded-card overflow-hidden border">
      <Skeleton className="aspect-square w-full rounded-none" />
      <div className="p-3">
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="mt-1.5 h-3.5 w-4/5" />
        <Skeleton className="mt-2 h-3 w-1/2" />
        <div className="mt-4 flex items-center justify-between">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-8 w-[104px] rounded-md" />
        </div>
      </div>
    </div>
  )
}
