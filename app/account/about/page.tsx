import type { Metadata } from 'next'
import StaticPage from '@/components/account/StaticPage'
import { CATALOG } from '@/lib/catalog-config'

export const metadata: Metadata = { title: 'About us' }

export default function AboutPage() {
  return (
    <StaticPage
      title={`About ${CATALOG.brand.name}`}
      intro={`${CATALOG.brand.name} is an online store carrying groceries, electronics, home, fashion, stationery and books.`}
      sections={[
        {
          heading: 'What this is',
          body: 'A storefront built on a catalogue of demonstration products. Browsing, search, filtering, the cart and your saved list all work exactly as they would in production.',
        },
        {
          heading: 'What is not connected yet',
          body: 'Payments, order history and accounts run against a server that is not wired up in this build. Anywhere that would need one says so plainly rather than showing a placeholder.',
        },
      ]}
    />
  )
}
