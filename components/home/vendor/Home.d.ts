import type { HomeBanner, HomeCategory, HomeItem } from '@/lib/home-adapter'

/**
 * The type boundary around the vendored design.
 *
 * Home.jsx stays untyped JavaScript -- it is vendored, and rewriting it in
 * TypeScript is the "port fully" option that was not taken. Declaring its
 * props here seals the untyped region: everything crossing into it is
 * checked, and TypeScript stops inferring `never[]` from the `= []` defaults
 * in the JS.
 *
 * Keep this in step with the props Home.jsx actually destructures.
 */

export type HomeSection =
  | { key: string; title: string; subtitle?: string; items: HomeItem[] }
  | { banner: string[] }

declare function Home(props: {
  banners?: HomeBanner[]
  categories?: HomeCategory[]
  sections?: HomeSection[]
  /** Product id to quantity. Controlled -- see HomeScreen. */
  cart?: Record<number, number>
  onQtyChange?: (id: number, qty: number) => void
}): JSX.Element

export default Home
