import type { Metadata } from 'next'
import CartScreen from '@/components/cart/CartScreen'
import { PRODUCTS } from '@/lib/fixtures'
import { toHomeItem } from '@/lib/home-adapter'
import '@/components/home/vendor/home.css'
import '@/components/home/vendor/home.brand.css'
import '@/components/cart/vendor/cart.css'
import '@/components/cart/vendor/cart.brand.css'

export const metadata: Metadata = { title: 'Cart' }

/**
 * Cart, rendering the vendored design.
 *
 * A server component, for the same reason the home route is one: the two
 * suggestion rails are drawn from the catalogue, and resolving them here
 * keeps the fixtures -- and every stock level in them -- out of the client
 * bundle. CartScreen is the client boundary, and only because the cart
 * itself is client state.
 *
 * home.css comes first and is not optional: cart.css declares only four
 * tokens of its own and reads sixty-one --hm-* values that live on .hm-page,
 * so without it the cart renders unstyled in places and unreadable in
 * others. extras.css is not listed with them because the root layout
 * already carries it. All four here are scoped and imported on this route
 * alone.
 *
 * The suggestions are deliberately dumb -- the best discounts, and the
 * newest arrivals. There is no recommendation engine here, and dressing an
 * arbitrary slice as "picked for you" would be a claim about personalisation
 * that nothing in this build could stand behind.
 */
export default function CartRoute() {
  const discounted = [...PRODUCTS]
    .filter((p) => p.inStock && p.discountPercent > 0)
    .sort((a, b) => b.discountPercent - a.discountPercent)
    .slice(0, 8)
    .map(toHomeItem)

  const fresh = PRODUCTS.filter((p) => p.inStock && p.badge)
    .slice(0, 8)
    .map(toHomeItem)

  return <CartScreen recommended={discounted} alsoLike={fresh} />
}
