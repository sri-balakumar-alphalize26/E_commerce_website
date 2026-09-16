import type { Metadata } from 'next'
import StaticPage from '@/components/account/StaticPage'
import { CATALOG } from '@/lib/catalog-config'

export const metadata: Metadata = { title: 'Legal information' }

export default function LegalPage() {
  return (
    <StaticPage
      title="Legal information"
      intro="Terms covering the use of this storefront and the data it keeps."
      sections={[
        { heading: 'Product information', body: CATALOG.disclaimer },
        {
          heading: 'Data stored on your device',
          body: 'Your cart, saved list, delivery addresses and profile are held in this browser. Nothing is transmitted to a server, no cookies are set for tracking, and clearing site data removes all of it permanently.',
        },
        {
          heading: 'Pricing',
          body: 'Prices are shown in Indian rupees and include applicable taxes unless stated otherwise. Prices and availability in this build come from a demonstration catalogue.',
        },
      ]}
    />
  )
}
