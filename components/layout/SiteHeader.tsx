import AccountButton from '@/components/layout/AccountButton'
import AddressPill from '@/components/layout/AddressPill'
import CartButton from '@/components/layout/CartButton'
import DeliveryModeToggle from '@/components/layout/DeliveryModeToggle'
import Logo from '@/components/layout/Logo'
import SearchBar from '@/components/layout/SearchBar'
import SearchOverlay from '@/components/layout/SearchOverlay'
import Container from '@/components/ui/Container'
import { getSearchSeeds } from '@/lib/fixtures'

/**
 * The gradient header card.
 *
 * This is the single element that decides whether the storefront reads as a
 * branded shop or as a competent grey admin panel, so it gets the page's
 * only large saturated surface.
 *
 * Load-bearing details, each of which has already been got wrong once:
 *
 * 1. STICKY -- applied by the wrapper in app/layout.tsx, which sticks this
 *    and the category strip as one unit. Without it, three rows down a
 *    category page at 390px there was no cart, no search and no category
 *    access on screen at all.
 *
 * 2. The gradient stops short of the logo's bright cyan. White text on the
 *    logo ramp runs 6.83 / 3.63 / 2.80 / 2.09:1 across its four stops, so a
 *    header using it verbatim would be legible on the left and unreadable
 *    on the right. See --brand-gradient.
 *
 * 3. Chips on it DARKEN rather than lighten. The frosted `bg-white/18`
 *    instinct drops white text from 4.94:1 to 3.62:1 -- the pill meant to
 *    lift the label is what makes it fail AA. `.chip-on-brand` darkens to
 *    6.02:1 and does the lifting with a hairline ring instead.
 *
 * 4. ONE SearchBar, not two. Rendering a desktop copy and a mobile copy
 *    mounts two components, two debounce timers and two request paths on
 *    every page, of which one is always display:none. Flex `order` moves the
 *    single instance between rows instead.
 *
 * Every control here now resolves somewhere real: the mode toggle filters
 * the catalogue, the address pill opens a working address book, and the
 * account button has a route behind it. An earlier pass removed two of these
 * for being dead, and that judgement stands -- they are back because they do
 * something now, not because the layout wanted them.
 */
export default function SiteHeader() {
  /*
   * Read on the SERVER and handed down as plain props.
   *
   * Letting the search panel import the catalogue itself would undo the
   * reason app/api/suggest exists: this header is mounted in the root
   * layout, so anything it pulls in client-side lands in the bundle of
   * every page, stock levels included.
   */
  const { trending, picks } = getSearchSeeds()

  return (
    <header className="bg-surface-alt lg:py-2.5">
      <Container className="max-lg:px-0">
        {/*
          Inset rounded card at >=1100px, edge-to-edge below it. The reference
          is a card floating on the grey page, and that is most of why it
          reads as a shop -- but at 390px an inset card spends 32px of a
          390px viewport on margin, so the phone gets the full width.
        */}
        {/* data-mm-skip: the header is above the fold on every route, and
            the reveal engine hides what it is going to animate. Letting it
            fade in would gate the first paint of the whole chrome on a
            script that loads afterInteractive. */}
        <div
          data-mm="header"
          data-mm-skip
          className="on-dark brand-gradient shadow-header px-4 py-2.5 max-lg:pb-3 md:px-5 lg:rounded-2xl lg:py-3"
        >
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2.5">
            <Logo onDark />

            <DeliveryModeToggle className="max-lg:order-3" />

            <AddressPill className="max-lg:order-4 max-lg:flex-1" />

            <SearchBar
              hints={trending}
              className="order-last w-full lg:order-none lg:mx-2 lg:w-auto lg:max-w-[520px] lg:flex-1"
            />

            <div className="ml-auto flex shrink-0 items-center gap-2 lg:ml-0">
              <CartButton />
              <AccountButton />
            </div>
          </div>
        </div>
      </Container>
      {/* Portals to the body, so it is not clipped by the sticky header
          it grows out of. */}
      <SearchOverlay picks={picks} trending={trending} />
    </header>
  )
}
