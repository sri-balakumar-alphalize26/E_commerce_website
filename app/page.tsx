import HomeScreen from '@/components/home/HomeScreen'
import Container from '@/components/ui/Container'
import { CATALOG } from '@/lib/catalog-config'
import { homeBanners, homeCategories, homeRails } from '@/lib/home-adapter'
import '@/components/home/vendor/home.css'
import '@/components/home/vendor/home.brand.css'

/**
 * Home, rendering the vendored design.
 *
 * A server component: the catalogue is resolved here and handed down as
 * props, so the fixtures never reach a client bundle. HomeScreen is the
 * client boundary, and only because the cart and delivery mode are client
 * state.
 *
 * The design's stylesheet is imported on this route only, not globally --
 * it is 22KB scoped to .hm-*, and no other page renders that markup.
 * home.brand.css follows it and repoints its tokens at our palette.
 */
export default function Home() {
  return (
    <>
      <Container className="sr-only">
        <h1>{CATALOG.brand.name}</h1>
      </Container>
      <HomeScreen
        banners={homeBanners()}
        categories={homeCategories()}
        rails={homeRails()}
      />
    </>
  )
}
