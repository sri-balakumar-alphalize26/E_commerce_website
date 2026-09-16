import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import Script from 'next/script'
import CartCheckoutBar from '@/components/cart/CartCheckoutBar'
import CartProvider from '@/components/cart/CartProvider'
import CategoryStrip from '@/components/layout/CategoryStrip'
import MobileTabBar from '@/components/layout/MobileTabBar'
import MotionRefresh from '@/components/layout/MotionRefresh'
import SiteFooter from '@/components/layout/SiteFooter'
import SiteHeader from '@/components/layout/SiteHeader'
import { CATALOG } from '@/lib/catalog-config'
import './globals.css'
import './mart-motion.css'

/*
 * Inter, for everything.
 *
 * This replaces a deliberate two-face split -- Plus Jakarta Sans for UI
 * text, Space Grotesk for large display headings. That split bought a
 * contrast between heading and body that a single family cannot, and it is
 * being given up on purpose: both vendored designs are drawn in Inter and
 * retuned around its metrics, so keeping our own faces would leave the home
 * page reading in one voice and the rest of the storefront in another.
 *
 * The old face was chosen for a weight ceiling -- every dense element on a
 * card sits at 800, which Instrument Sans and Space Grotesk could not
 * reach. Inter's variable range is 100-900, so nothing is lost there.
 *
 * ITALIC IS NOT DECORATION. The mode switch sets the Quick wordmark in
 * italic 800; without the italic style loaded the browser would synthesise
 * it by shearing the upright, which at that weight looks like a rendering
 * fault. latin-ext comes along for the same reason -- the catalogue carries
 * accented brand names.
 */
const inter = Inter({
  subsets: ['latin', 'latin-ext'],
  style: ['normal', 'italic'],
  variable: '--font-inter',
  display: 'swap',
})

export const metadata: Metadata = {
  title: {
    default: `${CATALOG.brand.name} — online shopping`,
    template: `%s | ${CATALOG.brand.name}`,
  },
  description: `Shop groceries, electronics, home, fashion and more at ${CATALOG.brand.name}.`,
}

export const viewport: Viewport = {
  // The header gradient runs under the status bar on mobile; matching the
  // theme colour to its darkest stop stops the bar looking detached.
  themeColor: '#006090',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        {/*
          Sets the motion engine's flag BEFORE first paint.

          mart-motion.css hides anything it is going to reveal, but only
          under html[data-mm-js] -- so the flag has to land before the
          browser paints, or the page shows its content and then snatches
          it away. That is why this is an inline blocking script and not
          the engine itself.

          The timeout is the safety net that makes the whole arrangement
          safe: if the engine has not announced itself within 2.5s, the
          flag is dropped and every hidden element becomes visible. A
          blocked or failed script therefore costs a plain page, never a
          blank one. suppressHydrationWarning on <html> is required because
          this runs before React reaches the attribute.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "document.documentElement.setAttribute('data-mm-js','');" +
              'setTimeout(function(){if(!window.MartMotion)' +
              "document.documentElement.removeAttribute('data-mm-js')},2500)",
          }}
        />
      </head>
      <body className="min-h-dvh antialiased">
        <CartProvider>
          {/*
            Header and category strip stick as ONE unit rather than
            separately. Sticking the strip on its own needs the header
            height as a magic number, and that height changes with the
            breakpoint and with whether the tagline line is showing.
          */}
          <div className="sticky top-0 z-40">
            <SiteHeader />
            <CategoryStrip />
          </div>

          {/* Clears the fixed bottom chrome so the last row of any page is
              reachable. The View Cart bar only appears with items in the
              cart, so the reserve covers both and simply goes unused when
              the cart is empty -- cheaper than measuring it at runtime. */}
          <div className="pb-[calc(var(--tabbar-h)+var(--buybar-h))] lg:pb-0">
            {children}
            <SiteFooter />
          </div>

          {/* Both pin to the bottom edge; the bar stacks above the tabs. */}
          <CartCheckoutBar />
          <MobileTabBar />
        </CartProvider>

        {/* afterInteractive: the engine is decoration, so it must never
            compete with hydration for the main thread. */}
        <Script src="/mart-motion.js" strategy="afterInteractive" />
        <MotionRefresh />
      </body>
    </html>
  )
}
