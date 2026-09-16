import type { Metadata } from 'next'
import CatalogueBrowser from '@/components/catalogue/CatalogueBrowser'
import Container from '@/components/ui/Container'
import PageHeader from '@/components/ui/PageHeader'
import { searchProducts } from '@/lib/fixtures'

type Props = { searchParams: Promise<{ q?: string }> }

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const { q } = await searchParams
  return { title: q ? `Search: ${q}` : 'Search' }
}

/**
 * Search fans across every vertical rather than staying inside one, because
 * a customer typing "coffee" does not know or care which aisle it lives in.
 */
export default async function SearchPage({ searchParams }: Props) {
  // Next 16 hands searchParams as a Promise.
  const { q } = await searchParams
  const term = (q ?? '').trim()
  const items = term ? searchProducts(term) : []

  return (
    <>
      <PageHeader
        title={term ? `Results for "${term}"` : 'Search'}
        subtitle={
          term
            ? `${items.length} ${items.length === 1 ? 'match' : 'matches'} across all categories`
            : 'Type in the search bar above'
        }
        backHref="/"
      />

      <main>
        <Container className="py-5">
          {term ? (
            <CatalogueBrowser
              items={items}
              emptyMessage={`Nothing matches "${term}"`}
            />
          ) : (
            <p className="text-slate-muted py-10 text-center text-sm">
              Enter a product name or brand to search.
            </p>
          )}
        </Container>
      </main>
    </>
  )
}
