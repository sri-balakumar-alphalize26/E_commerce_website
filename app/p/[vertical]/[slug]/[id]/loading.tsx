import Container from '@/components/ui/Container'
import Skeleton from '@/components/ui/Skeleton'

/**
 * Mirrors the real product layout -- breadcrumb, gallery beside the info
 * column at >=1100px, stacked below -- so the swap to content shifts nothing.
 */
export default function Loading() {
  return (
    <main className="lg:pb-16">
      <Container className="py-4">
        <Skeleton className="h-3 w-56" />

        <div className="mt-4 lg:flex lg:items-start lg:gap-10">
          <div className="lg:w-[46%] lg:shrink-0">
            <Skeleton className="aspect-square w-full rounded-[14px]" />
          </div>

          <div className="mt-6 min-w-0 flex-1 lg:mt-0">
            <Skeleton className="h-6 w-4/5" />
            <Skeleton className="mt-2 h-6 w-3/5" />
            <Skeleton className="mt-3 h-3.5 w-32" />

            <div className="border-surface-line mt-5 border-t pt-5">
              <Skeleton className="h-8 w-40" />
              <Skeleton className="mt-2 h-3.5 w-28" />
            </div>

            <Skeleton className="mt-5 h-10 w-full rounded-md" />

            <div className="border-surface-line mt-8 space-y-3 border-t pt-5">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-3.5 w-full" />
              ))}
            </div>
          </div>
        </div>
      </Container>
    </main>
  )
}
