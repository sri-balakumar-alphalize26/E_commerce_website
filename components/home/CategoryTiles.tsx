import Link from 'next/link'
import {
  BookOpen,
  Lamp,
  PenLine,
  Shirt,
  ShoppingBasket,
  Smartphone,
  Tag,
  type LucideIcon,
} from 'lucide-react'
import SectionHeading from '@/components/home/SectionHeading'
import { CATALOG, type TileAccent } from '@/lib/catalog-config'

/**
 * The category tile grid -- the reference's signature shape.
 *
 * 3-across at base, 6 from md.
 *
 * 4-across matches the real app and was the first choice, but with six
 * tiles it leaves a ragged 4+2 half-row at 390px -- two empty cells
 * hanging under the grid. Three gives two full rows of three. If the tile
 * count ever becomes a multiple of four, 4-across is the better density.
 *
 * Icons are imported by name rather than looked up dynamically, so the
 * bundler can tree-shake lucide down to the seven glyphs actually used
 * instead of shipping the whole set.
 */
const ICONS: Record<string, LucideIcon> = {
  ShoppingBasket,
  Smartphone,
  Lamp,
  Shirt,
  PenLine,
  BookOpen,
  Tag,
}

/**
 * Every pair was measured against the 3:1 non-text floor: the glyph sits on
 * its tint at 4.14:1 or better. The obvious brighter cyan pairings
 * (brand-400 on brand-50) come in at 2.47:1 and are not used.
 */
const ACCENTS: Record<TileAccent, string> = {
  brand: 'bg-brand-50 text-brand-600',
  'brand-deep': 'bg-brand-100 text-brand-800',
  cyan: 'bg-brand-100 text-brand-700',
  accent: 'bg-accent-50 text-accent-700',
  'accent-deep': 'bg-accent-100 text-accent-700',
  neutral: 'bg-surface-alt text-slate-body',
}

export default function CategoryTiles() {
  return (
    <section aria-labelledby="shop-by-category">
      <SectionHeading title="Shop by category" id="shop-by-category" />
      <ul data-mm="cats" className="grid grid-cols-3 gap-2.5 md:grid-cols-6 md:gap-3">
        {CATALOG.tiles.map((tile) => {
          const Icon = ICONS[tile.icon] ?? Tag
          return (
            <li key={tile.key}>
              <Link
                href={tile.href}
                className="border-surface-line bg-surface shadow-card rounded-[14px] flex h-full flex-col items-center gap-2.5 border px-2.5 py-[18px] text-center md:px-3"
              >
                <span
                  data-mm="cat-icon"
                  className={`inline-flex size-[54px] items-center justify-center rounded-2xl ${ACCENTS[tile.accent]}`}
                >
                  <Icon className="size-[22px]" aria-hidden />
                </span>
                {/* break-words, or a long single-word label overflows the
                    tile at 390px instead of wrapping. */}
                <span className="text-ink line-clamp-2 text-[12.5px] leading-tight font-bold break-words">
                  {tile.label}
                </span>
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
