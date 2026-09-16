import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import CatalogueBrowser from '@/components/catalogue/CatalogueBrowser'
import Container from '@/components/ui/Container'
import PageHeader from '@/components/ui/PageHeader'
import { CATALOG, getCollection } from '@/lib/catalog-config'
import { PRODUCTS } from '@/lib/fixtures'

type Params = { params: Promise<{ key: string }> }

/**
 * Collections are config-declared slices, not a backend concept. Each one
 * carries its own predicate, so "Top offers" is literally "everything with a
 * discount" rather than a curated list nothing can produce.
 */
export const dynamicParams = false

export function generateStaticParams() {
  return CATALOG.collections.map((c) => ({ key: c.key }))
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { key } = await params
  const collection = getCollection(key)
  return collection ? { title: collection.title } : { title: 'Not found' }
}

export default async function CollectionPage({ params }: Params) {
  const { key } = await params
  const collection = getCollection(key)
  if (!collection) notFound()

  const items = collection.filter ? PRODUCTS.filter(collection.filter) : PRODUCTS

  return (
    <>
      <PageHeader
        title={collection.title}
        subtitle={`${items.length} ${items.length === 1 ? 'product' : 'products'}`}
        backHref="/"
      />

      <main>
        <Container className="py-5">
          <p className="text-slate-muted mb-4 text-sm">{collection.subtitle}</p>
          <CatalogueBrowser items={items} emptyMessage="Nothing here right now" />
        </Container>
      </main>
    </>
  )
}
