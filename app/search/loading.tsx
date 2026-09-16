import ProductCardSkeleton from '@/components/catalogue/ProductCardSkeleton'
import Container from '@/components/ui/Container'
import Skeleton from '@/components/ui/Skeleton'

export default function Loading() {
  return (
    <>
      <div className="brand-gradient">
        <Container className="py-5 md:py-6">
          <Skeleton className="h-6 w-56 bg-white/25" />
          <Skeleton className="mt-2 h-3.5 w-40 bg-white/20" />
        </Container>
      </div>

      <main>
        <Container className="py-5">
          <div className="mb-3 flex items-center justify-between">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-9 w-40" />
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <ProductCardSkeleton key={i} />
            ))}
          </div>
        </Container>
      </main>
    </>
  )
}
