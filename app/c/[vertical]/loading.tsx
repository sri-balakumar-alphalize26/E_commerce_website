import ProductCardSkeleton from '@/components/catalogue/ProductCardSkeleton'
import Container from '@/components/ui/Container'
import Skeleton from '@/components/ui/Skeleton'

/**
 * Mirrors the real listing layout -- gradient band, toolbar row, rail and
 * grid -- so nothing jumps when the content arrives.
 */
export default function Loading() {
  return (
    <>
      <div className="brand-gradient">
        <Container className="py-5 md:py-6">
          <Skeleton className="h-6 w-40 bg-white/25" />
          <Skeleton className="mt-2 h-3.5 w-24 bg-white/20" />
        </Container>
      </div>

      <main>
        <Container className="py-5">
          <div className="lg:flex lg:items-start lg:gap-6">
            <aside className="hidden w-60 shrink-0 space-y-5 lg:block">
              {[0, 1, 2].map((i) => (
                <div key={i}>
                  <Skeleton className="h-3 w-20" />
                  <div className="mt-2 space-y-2">
                    <Skeleton className="h-3.5 w-full" />
                    <Skeleton className="h-3.5 w-5/6" />
                    <Skeleton className="h-3.5 w-4/6" />
                  </div>
                </div>
              ))}
            </aside>

            <div className="min-w-0 flex-1">
              <div className="mb-3 flex items-center justify-between">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-9 w-40" />
              </div>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
                {Array.from({ length: 8 }).map((_, i) => (
                  <ProductCardSkeleton key={i} />
                ))}
              </div>
            </div>
          </div>
        </Container>
      </main>
    </>
  )
}
