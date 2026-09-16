import Container from '@/components/ui/Container'
import Skeleton from '@/components/ui/Skeleton'

/**
 * Replaces the bare "Loading your cart..." string the page used to render
 * while the stored cart was unreadable, which is the one frame every visitor
 * sees on a hard load.
 */
export default function Loading() {
  return (
    <>
      <div className="brand-gradient">
        <Container className="py-5 md:py-6">
          <Skeleton className="h-6 w-24 bg-white/25" />
          <Skeleton className="mt-2 h-3.5 w-20 bg-white/20" />
        </Container>
      </div>

      <main>
        <Container className="py-5">
          <div className="lg:flex lg:items-start lg:gap-6">
            <div className="border-surface-line bg-surface rounded-card min-w-0 flex-1 border px-4">
              {[0, 1, 2].map((i) => (
                <div key={i} className="border-surface-line flex gap-3 border-b py-4 last:border-b-0">
                  <Skeleton className="size-20 shrink-0 rounded-md" />
                  <div className="min-w-0 flex-1">
                    <Skeleton className="h-3.5 w-3/4" />
                    <Skeleton className="mt-1.5 h-3 w-1/3" />
                    <div className="mt-3 flex items-center justify-between">
                      <Skeleton className="h-9 w-28 rounded-md" />
                      <Skeleton className="h-4 w-16" />
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <aside className="mt-6 lg:mt-0 lg:w-80 lg:shrink-0">
              <div className="border-surface-line bg-surface shadow-card rounded-card border p-4">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="mt-4 h-3.5 w-full" />
                <Skeleton className="mt-2 h-3.5 w-2/3" />
                <Skeleton className="mt-4 h-12 w-full rounded-pill" />
              </div>
            </aside>
          </div>
        </Container>
      </main>
    </>
  )
}
