'use client'

import ProductCard from '@/components/catalogue/ProductCard'
import SectionHeading from '@/components/home/SectionHeading'
import type { Product } from '@/lib/catalog'
import { useDeliveryMode } from '@/lib/use-prefs'

/**
 * A horizontal product rail.
 *
 * It used to be a server component on the grounds that it only maps products
 * to cards. That stopped being true once Quick had to filter it: the mode
 * lives in localStorage, the server cannot know it, and a rail showing items
 * the chosen mode excludes would contradict the listing pages one scroll
 * away. Mapping is cheap and the cards were already client, so the cost of
 * moving the boundary here is close to nothing.
 *
 * A rail that empties under Quick renders nothing rather than an empty
 * heading. A rail is a suggestion, not a destination -- unlike a category
 * page, where the customer asked for that specific view and is owed an
 * explanation.
 *
 * The track bleeds to the container edge via negative margins that exactly
 * cancel the Container gutter, so the first card starts flush with the
 * heading above it and the last runs off the edge -- which is what tells a
 * customer there is more to scroll.
 */
export default function ProductRail({
  title,
  subtitle,
  href,
  items,
  priority = false,
}: {
  title: string
  subtitle?: string
  href?: string
  items: Product[]
  priority?: boolean
}) {
  const mode = useDeliveryMode()
  const shown = mode === 'quick' ? items.filter((p) => p.quickDelivery) : items

  if (!shown.length) return null

  return (
    <section className="mt-6">
      <SectionHeading title={title} subtitle={subtitle} href={href} />
      {/*
        The list IS the scroller now, rather than sitting inside one.

        The motion engine needs a single element that is both the scroll
        container -- it reads scrollLeft to decide which edge to fade --
        and the direct parent of the cards, which it cascades one by one.
        With those split across a wrapper and a list, the engine saw one
        child and animated the whole row as a single block.

        Its scroll-aware [data-mm-edge] masks replace .edge-fade-x, which
        faded the right edge permanently, even once the track had been
        scrolled to the end and there was nothing left to show.

        Side effect worth knowing: snap-x was previously on the ul, which
        did not scroll, so it did nothing. On the real scroller it now
        takes effect, and rails snap gently (proximity, not mandatory).
      */}
      <ul
        data-mm="rail"
        className="-mx-4 flex snap-x items-stretch gap-3 overflow-x-auto px-4 pb-1 md:-mx-6 md:px-6 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {shown.map((p, i) => (
          <li
            key={p.id}
            /*
              Inside a rail the LIST ITEM is the card, not the article
              inside it. The engine cascades a group's direct children, so
              the role has to sit on the element the rail actually holds;
              the badge, ribbon and price rules all reach the article from
              here as descendants.

              Above the fold the item is skipped AND left untagged. Skip
              alone would stop it hiding but still leave it without
              data-mm-in, and the engine keeps a card's badge and ADD
              button at opacity 0 until that lands -- so a tagged-but-never
              -revealed card would lose them for good.
            */
            data-mm={priority ? undefined : 'card'}
            data-mm-skip={priority ? '' : undefined}
            className="w-[158px] shrink-0 snap-start md:w-[190px]"
          >
            {/* railSafe: two horizontal scrollers nested inside each other
                cannot both read the same drag, and the browser resolves it
                in favour of the inner one. See ProductCardMedia. */}
            <ProductCard product={p} priority={priority && i < 3} railSafe />
          </li>
        ))}
      </ul>
    </section>
  )
}
