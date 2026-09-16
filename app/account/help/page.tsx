import type { Metadata } from 'next'
import StaticPage from '@/components/account/StaticPage'
import { CATALOG } from '@/lib/catalog-config'

export const metadata: Metadata = { title: 'Help' }

export default function HelpPage() {
  return (
    <StaticPage
      title="Help"
      intro={`Answers to the things customers ask ${CATALOG.brand.name} most often.`}
      sections={[
        {
          heading: 'How do I place an order?',
          body: 'Add items with the ADD button on any product, then open the cart. Checkout is not connected to a payment provider yet, so nothing is charged and no order is created.',
        },
        {
          heading: 'When will my order arrive?',
          body:
            CATALOG.shippingNote +
            '. Delivery timing depends on your address, and a per-address estimate arrives with the fulfilment backend.',
        },
        {
          heading: 'What does Quick mean?',
          body: 'Quick shows only products stocked in your local store, which are the ones eligible for fast delivery. Express shows the full catalogue.',
        },
        {
          heading: 'Is my information stored anywhere?',
          body: 'Your cart, list, addresses and profile are kept in this browser only. They are not sent to a server, and clearing site data removes them.',
        },
      ]}
    />
  )
}
