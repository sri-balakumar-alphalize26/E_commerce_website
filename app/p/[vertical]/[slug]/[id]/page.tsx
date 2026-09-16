import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import AddToCartControl from '@/components/cart/AddToCartControl'
import Breadcrumbs from '@/components/product/Breadcrumbs'
import BuyToolbar from '@/components/product/BuyToolbar'
import {
  AttributeTable,
  Disclaimer,
  KeyFeatures,
  Showcase,
} from '@/components/product/DetailSections'
import PriceBlock from '@/components/product/PriceBlock'
import ProductGallery from '@/components/product/ProductGallery'
import SimilarItems from '@/components/product/SimilarItems'
import StockLine from '@/components/product/StockLine'
import Container from '@/components/ui/Container'
import { CATALOG, getVertical } from '@/lib/catalog-config'
import { PRODUCTS, getProductDetail, similarTo } from '@/lib/fixtures'
import { sanitizeDescription } from '@/lib/sanitize'

type Params = { params: Promise<{ vertical: string; slug: string; id: string }> }

/**
 * Every product is known at build time, so every product page prerenders
 * and an unknown one is refused before the page body ever runs.
 *
 * Without this the route was dynamic: 38 build-time-known pages rendered
 * per request, and an unknown id produced a SOFT 404 -- our 404 body under
 * an HTTP 200, which tells a crawler the page exists.
 */
export const dynamicParams = false

export function generateStaticParams() {
  return PRODUCTS.map((p) => ({
    vertical: p.vertical,
    slug: p.slug,
    id: String(p.id),
  }))
}

/**
 * The id is what resolves a product; the slug is cosmetic. That is
 * deliberate -- a shared link keeps working after a product is renamed,
 * instead of 404ing on a stale slug.
 */
function resolve(idParam: string) {
  const id = Number(idParam)
  if (!Number.isInteger(id)) return null
  return getProductDetail(id)
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params
  const product = resolve(id)
  if (!product) return { title: 'Not found' }
  return {
    title: product.name,
    description: product.shortDescription,
  }
}

export default async function ProductPage({ params }: Params) {
  // Next 16 hands params as a Promise.
  const { vertical, id } = await params
  const product = resolve(id)

  // A non-integer id, a missing product, or an id reached through the wrong
  // vertical segment all mean the same thing to a customer.
  if (!product || product.vertical !== vertical) notFound()

  const meta = getVertical(product.vertical)
  // Sanitised HERE, on the server. See lib/sanitize.ts.
  const description = sanitizeDescription(product.descriptionHtml)
  const similar = similarTo(product)
  const packBadge =
    product.attributes.find((a) => a.key === 'weight' || a.key === 'pack')?.value ?? null

  return (
    <>
      <main className="lg:pb-16">
        <Container className="py-4">
          <Breadcrumbs
            trail={[
              { label: 'Home', href: '/' },
              ...(meta ? [{ label: meta.label, href: `/c/${meta.id}` }] : []),
              { label: product.name },
            ]}
          />

          <div className="mt-4 lg:flex lg:items-start lg:gap-10">
            {/* The gallery column stays sticky on desktop so the images
                remain in view while the specification tables scroll. */}
            <div className="lg:sticky lg:top-40 lg:w-[46%] lg:shrink-0">
              <ProductGallery images={product.images} alt={product.name} badge={packBadge} />
            </div>

            <div className="mt-6 min-w-0 flex-1 lg:mt-0">
              {product.badge ? (
                <span className="bg-brand-50 text-brand-700 rounded-tag inline-block px-2 py-0.5 text-[11px] font-extrabold tracking-wide uppercase">
                  {product.badge}
                </span>
              ) : null}

              <h1 className="text-ink font-display mt-2 text-xl leading-snug font-extrabold tracking-tight md:text-2xl">
                {product.name}
              </h1>
              <p className="text-slate-muted mt-1 text-sm">{product.subtitle}</p>

              {/*
                No rating or review count here, though the reference page
                carries both. Nothing in this build can produce either, and a
                hardcoded "3.8 (1167)" is a fabricated social proof claim --
                the one kind of invented content that actually misleads a
                buyer rather than merely padding a page.
              */}

              <div className="border-surface-line mt-5 border-t pt-5">
                <PriceBlock product={product} />
              </div>

              <div className="mt-5">
                <StockLine product={product} />
              </div>

              {/* The in-flow control is desktop-only; below lg the sticky
                  BuyToolbar owns it. Rendering both would put two live ADD
                  buttons with the same accessible name on one screen. */}
              <div className="mt-6 hidden lg:block">
                <AddToCartControl product={product} />
              </div>

              <div className="mt-8 space-y-6">
                <KeyFeatures items={product.keyFeatures} />
                <AttributeTable title="Product Information" rows={product.productInfo} />
                <AttributeTable title="Item Specifications" rows={product.specifications} />
                <Showcase title={product.name} body={product.showcase} />

                <section className="border-surface-line border-t pt-5">
                  <h2 className="text-ink mb-3 text-sm font-extrabold">Description</h2>
                  <div
                    className="text-slate-body [&_a]:text-brand-600 space-y-3 text-[13px] leading-relaxed [&_a]:underline [&_li]:ml-4 [&_li]:list-disc [&_ul]:space-y-1"
                    dangerouslySetInnerHTML={{ __html: description }}
                  />
                </section>

                <Disclaimer text={CATALOG.disclaimer} />
              </div>
            </div>
          </div>

          <SimilarItems items={similar} />
        </Container>
      </main>

      <BuyToolbar product={product} />
    </>
  )
}
