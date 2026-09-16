import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import CatalogueBrowser from '@/components/catalogue/CatalogueBrowser'
import Container from '@/components/ui/Container'
import PageHeader from '@/components/ui/PageHeader'
import { CATALOG, VERTICAL_IDS, getVertical } from '@/lib/catalog-config'
import { listProducts } from '@/lib/fixtures'

type Params = { params: Promise<{ vertical: string }> }

/**
 * The complete set of verticals is known from config at build time, so
 * anything else is not a slow path -- it is not a route at all.
 *
 * With the default dynamicParams:true, an unknown vertical renders on
 * demand and calling notFound() paints our 404 body but still answers
 * HTTP 200 -- a soft 404, which tells a crawler the page exists. Closing
 * the param set makes Next answer a real 404 before the page ever runs.
 */
export const dynamicParams = false

/** The six verticals are known at build time, so the shells prerender. */
export function generateStaticParams() {
  return VERTICAL_IDS.map((vertical) => ({ vertical }))
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  // Next 16 hands params as a Promise.
  const { vertical } = await params
  const meta = getVertical(vertical)
  if (!meta) return { title: 'Not found' }
  return {
    title: meta.label,
    description: `Shop ${meta.noun} at ${CATALOG.brand.name}.`,
  }
}

export default async function CategoryPage({ params }: Params) {
  const { vertical } = await params
  const meta = getVertical(vertical)

  // An unknown vertical is a 404, not an empty grid. An empty grid would
  // imply the category exists and happens to be out of stock.
  if (!meta) notFound()

  const items = listProducts(meta.id)

  return (
    <>
      <PageHeader
        title={meta.label}
        subtitle={`${items.length} ${items.length === 1 ? 'product' : 'products'}`}
        backHref="/"
      />

      <main>
        <Container className="py-5">
          <CatalogueBrowser items={items} emptyMessage={`No ${meta.noun} yet`} />
        </Container>
      </main>
    </>
  )
}
