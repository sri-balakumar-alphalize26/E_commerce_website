import type { Attribute, Product, ProductDetail, VerticalId } from '@/lib/catalog'
import { artFor } from '@/lib/product-art'
import { productHref, slugify } from '@/lib/slug'

/**
 * The demo catalogue for the frontend-only phase.
 *
 * The product vertical is deliberately undecided, so this is a general
 * store: enough variety across price, discount, stock state and attribute
 * shape that every UI state has something real to render. When a backend
 * arrives, an adapter replaces this file and nothing in components/ moves.
 *
 * Deliberately included, because these are the states that get skipped and
 * then look broken in production: zero-discount items, out-of-stock items,
 * low-stock items, pack quantities above 1, names long enough to clamp,
 * and items with no badge.
 */

type Row = [
  vertical: VerticalId,
  name: string,
  subtitle: string,
  price: number,
  mrp: number,
  stock: number,
  badge: string | null,
  attrs: Record<string, string>,
]

const ROWS: Row[] = [
  // ---- electronics -------------------------------------------------------
  [
    'electronics',
    'Wireless Noise-Cancelling Headphones',
    'AudioCore',
    4499,
    7999,
    24,
    null,
    { brand: 'AudioCore', warranty: '1 year', colour: 'Charcoal' },
  ],
  [
    'electronics',
    'Bluetooth Speaker 20W',
    'AudioCore',
    1899,
    2999,
    8,
    null,
    { brand: 'AudioCore', warranty: '1 year', colour: 'Slate' },
  ],
  [
    'electronics',
    '65W GaN Fast Charger with Dual USB-C Ports and Foldable Pins',
    'VoltEdge',
    1299,
    1999,
    40,
    null,
    { brand: 'VoltEdge', warranty: '2 years', colour: 'White' },
  ],
  [
    'electronics',
    'Smart Fitness Band',
    'PulseFit',
    2199,
    2199,
    3,
    'New',
    { brand: 'PulseFit', warranty: '1 year', colour: 'Black' },
  ],
  [
    'electronics',
    'Mechanical Keyboard 87-Key',
    'KeyForge',
    3799,
    5499,
    0,
    null,
    { brand: 'KeyForge', warranty: '2 years', colour: 'Graphite' },
  ],
  [
    'electronics',
    '1080p Webcam with Privacy Shutter',
    'ClearView',
    2499,
    3299,
    15,
    null,
    { brand: 'ClearView', warranty: '1 year', colour: 'Black' },
  ],
  [
    'electronics',
    'Portable SSD 1TB',
    'DataVault',
    6499,
    8999,
    11,
    null,
    { brand: 'DataVault', warranty: '3 years', colour: 'Silver' },
  ],

  // ---- home --------------------------------------------------------------
  [
    'home',
    'Ceramic Dinner Set 18 Piece',
    'Terra Living',
    3299,
    4999,
    6,
    null,
    { brand: 'Terra Living', material: 'Stoneware', colour: 'Ivory' },
  ],
  [
    'home',
    'Cotton Bath Towel Pack of 4',
    'SoftWeave',
    1199,
    1799,
    30,
    null,
    { brand: 'SoftWeave', material: 'Cotton', colour: 'Sand' },
  ],
  [
    'home',
    'Stainless Steel Vacuum Flask 1L',
    'ThermaCore',
    899,
    1299,
    52,
    null,
    { brand: 'ThermaCore', material: 'Steel', colour: 'Steel' },
  ],
  [
    'home',
    'Bamboo Cutting Board Set',
    'Terra Living',
    749,
    1099,
    4,
    null,
    { brand: 'Terra Living', material: 'Bamboo', colour: 'Natural' },
  ],
  [
    'home',
    'LED Desk Lamp with Wireless Charging Base',
    'Lumen',
    2299,
    2299,
    18,
    'New',
    { brand: 'Lumen', material: 'Aluminium', colour: 'White' },
  ],
  [
    'home',
    'Storage Basket Woven Large',
    'SoftWeave',
    649,
    999,
    0,
    null,
    { brand: 'SoftWeave', material: 'Jute', colour: 'Beige' },
  ],

  // ---- grocery -----------------------------------------------------------
  [
    'grocery',
    'Cold Pressed Groundnut Oil 1L',
    'Harvest Lane',
    299,
    349,
    120,
    null,
    { brand: 'Harvest Lane', weight: '1 L', diet: 'Vegetarian' },
  ],
  [
    'grocery',
    'Organic Whole Wheat Atta 5kg',
    'Harvest Lane',
    359,
    449,
    64,
    null,
    { brand: 'Harvest Lane', weight: '5 kg', diet: 'Vegetarian' },
  ],
  [
    'grocery',
    'Arabica Coffee Beans 500g',
    'Roast House',
    649,
    899,
    22,
    null,
    { brand: 'Roast House', weight: '500 g', diet: 'Vegan' },
  ],
  [
    'grocery',
    'Assorted Dry Fruits Gift Box',
    'Nutty Co',
    1199,
    1699,
    9,
    'New',
    { brand: 'Nutty Co', weight: '750 g', diet: 'Vegetarian' },
  ],
  [
    'grocery',
    'Himalayan Pink Salt 1kg',
    'Harvest Lane',
    149,
    199,
    200,
    null,
    { brand: 'Harvest Lane', weight: '1 kg', diet: 'Vegan' },
  ],
  [
    'grocery',
    'Dark Chocolate 70% Cocoa',
    'Cacao Works',
    249,
    299,
    2,
    null,
    { brand: 'Cacao Works', weight: '100 g', diet: 'Vegetarian' },
  ],
  [
    'grocery',
    'Green Tea Bags Pack of 100',
    'Leaf and Co',
    429,
    599,
    47,
    null,
    { brand: 'Leaf and Co', weight: '200 g', diet: 'Vegan' },
  ],

  // ---- stationery --------------------------------------------------------
  [
    'stationery',
    'Gel Pen Box of 10',
    'InkLine',
    249,
    349,
    85,
    null,
    { brand: 'InkLine', pack: 'Box of 10', colour: 'Blue' },
  ],
  [
    'stationery',
    'A4 Copier Paper Ream 500 Sheets',
    'PaperMill',
    379,
    499,
    60,
    null,
    { brand: 'PaperMill', pack: 'Ream of 500', colour: 'White' },
  ],
  [
    'stationery',
    'Hardbound Ruled Notebook A5',
    'NoteCraft',
    199,
    279,
    44,
    null,
    { brand: 'NoteCraft', pack: 'Per piece', colour: 'Navy' },
  ],
  [
    'stationery',
    'Highlighter Set of 6 Pastel',
    'InkLine',
    329,
    449,
    27,
    null,
    { brand: 'InkLine', pack: 'Set of 6', colour: 'Assorted' },
  ],
  [
    'stationery',
    'Desk Organiser with Drawers',
    'DeskMate',
    899,
    1299,
    5,
    null,
    { brand: 'DeskMate', pack: 'Per piece', colour: 'Grey' },
  ],
  [
    'stationery',
    'Sticky Notes Pack of 12',
    'NoteCraft',
    299,
    399,
    0,
    null,
    { brand: 'NoteCraft', pack: 'Pack of 12', colour: 'Assorted' },
  ],

  // ---- books -------------------------------------------------------------
  [
    'books',
    'The Long Game: Strategy for Uncertain Times',
    'Priya Raghavan',
    499,
    699,
    17,
    null,
    { author: 'Priya Raghavan', language: 'English', pages: '384' },
  ],
  [
    'books',
    'Quiet Systems',
    'Daniel Okafor',
    399,
    550,
    9,
    null,
    { author: 'Daniel Okafor', language: 'English', pages: '272' },
  ],
  [
    'books',
    'Atlas of Small Cities',
    'Mira Sen',
    899,
    1299,
    3,
    'New',
    { author: 'Mira Sen', language: 'English', pages: '448' },
  ],
  [
    'books',
    'Cooking by Feel',
    'Anjali Nair',
    649,
    849,
    21,
    null,
    { author: 'Anjali Nair', language: 'English', pages: '320' },
  ],
  [
    'books',
    'The Debugging Mind',
    'Sam Whitaker',
    549,
    549,
    14,
    null,
    { author: 'Sam Whitaker', language: 'English', pages: '296' },
  ],
  [
    'books',
    'Letters from the Coast',
    'Rhea Fernandes',
    349,
    499,
    0,
    null,
    { author: 'Rhea Fernandes', language: 'English', pages: '208' },
  ],

  // ---- fashion -----------------------------------------------------------
  [
    'fashion',
    'Merino Wool Crew Socks Pack of 3',
    'Northbound',
    799,
    1199,
    38,
    null,
    { brand: 'Northbound', material: 'Merino wool', colour: 'Charcoal' },
  ],
  [
    'fashion',
    'Canvas Weekender Bag',
    'Northbound',
    2899,
    3999,
    7,
    null,
    { brand: 'Northbound', material: 'Canvas', colour: 'Olive' },
  ],
  [
    'fashion',
    'Leather Belt Reversible',
    'Craftsman',
    1499,
    2199,
    19,
    null,
    { brand: 'Craftsman', material: 'Leather', colour: 'Brown' },
  ],
  [
    'fashion',
    'Cotton Oxford Shirt',
    'Meridian',
    1799,
    2499,
    4,
    null,
    { brand: 'Meridian', material: 'Cotton', colour: 'Sky' },
  ],
  [
    'fashion',
    'Polarised Sunglasses',
    'Meridian',
    2199,
    2199,
    26,
    'New',
    { brand: 'Meridian', material: 'Acetate', colour: 'Tortoise' },
  ],
  [
    'fashion',
    'Packable Rain Jacket',
    'Northbound',
    3499,
    4999,
    0,
    null,
    { brand: 'Northbound', material: 'Nylon', colour: 'Slate' },
  ],
]

/** Attributes the UI may filter on. The rest are display-only specs. */
const FACETABLE = new Set(['brand', 'author', 'material', 'colour', 'diet', 'pack', 'language'])

const LABELS: Record<string, string> = {
  brand: 'Brand',
  author: 'Author',
  warranty: 'Warranty',
  colour: 'Colour',
  material: 'Material',
  weight: 'Net weight',
  diet: 'Dietary',
  pack: 'Pack size',
  language: 'Language',
  pages: 'Pages',
}

function stockStatus(stock: number) {
  if (stock <= 0) return 'out' as const
  if (stock <= 5) return 'low' as const
  return 'ok' as const
}

/**
 * Pack rules exist on the type because the eventual backend carries them
 * per product. Nothing in this demo set steps by more than 1, but the
 * stepper is written against these fields rather than against a hardcoded
 * 1 so that a pack-priced catalogue needs no component change.
 */
function packRules(): { minQty: number; qtyStep: number } {
  return { minQty: 1, qtyStep: 1 }
}

/**
 * How many views each product has, and where they live.
 *
 * The files are produced by scripts/export-images.mjs, which draws them from
 * components/home/vendor/art.jsx: 1 front, 2 close-up, 3 angled, 4 back. The
 * numbering is the script's contract, so it is spelled as a count here
 * rather than as names -- renaming a view would mean regenerating anyway.
 */
const VIEWS = 4
const imagesFor = (id: number) =>
  Array.from({ length: VIEWS }, (_, n) => `/images/products/${id}-${n + 1}.svg`)

export const PRODUCTS: Product[] = ROWS.map(
  ([vertical, name, subtitle, price, mrp, stock, badge, attrs], i) => {
    const discount = mrp > price ? Math.round(((mrp - price) / mrp) * 100) : 0
    const images = imagesFor(1000 + i)
    return {
      vertical,
      id: 1000 + i,
      slug: slugify(name),
      name,
      subtitle,
      badge,
      currency: 'INR',
      price,
      originalPrice: mrp,
      discountPercent: discount,
      stock,
      stockStatus: stockStatus(stock),
      inStock: stock > 0,
      // A real catalogue carries dark-store availability per product.
      // Deriving it from stock keeps it deterministic, so the same item
      // is Quick-eligible on every render and in every tab.
      quickDelivery: stock >= 20,
      // Generated pack-shots in public/products. The card pages through the
      // whole set, so the listing payload carries it; `image` stays the
      // front shot because that is what a cart line snapshots.
      image: images[0],
      images,
      ...packRules(),
      attributes: Object.entries(attrs).map(([key, value]) => ({
        key,
        label: LABELS[key] ?? key,
        value,
        facetId: FACETABLE.has(key) ? value : null,
      })),
    }
  },
)

const BY_ID = new Map(PRODUCTS.map((p) => [p.id, p]))

export function getProduct(id: number): Product | null {
  return BY_ID.get(id) ?? null
}

/**
 * Deterministic pseudo-values for the fields a real catalogue carries and a
 * fixture cannot know -- article ids, dimensions, manufacturer addresses.
 *
 * Derived from the product id rather than randomised, so the same product
 * shows the same article number on every render and between server and
 * client. Math.random() here would be a hydration mismatch waiting to
 * happen, and a moving article number in a screenshot is a bug report.
 */
function stable(id: number, salt: number, min: number, max: number) {
  const n = (id * 9301 + salt * 49297) % 233280
  return min + (n % (max - min + 1))
}

const ORIGIN = 'India'
const SELLER = '369 Mart Retail Limited'

function keyFeaturesFor(p: Product): string[] {
  const out: string[] = []
  const brandAttr = p.attributes.find((a) => a.key === 'brand' || a.key === 'author')
  if (brandAttr) out.push(`Genuine ${brandAttr.value} product, sourced directly`)
  if (p.discountPercent > 0) out.push(`Currently ${p.discountPercent}% below list price`)
  const material = p.attributes.find((a) => a.key === 'material')
  if (material) out.push(`Made from ${String(material.value).toLowerCase()}`)
  const diet = p.attributes.find((a) => a.key === 'diet')
  if (diet) out.push(`Suitable for ${String(diet.value).toLowerCase()} diets`)
  const warranty = p.attributes.find((a) => a.key === 'warranty')
  if (warranty) out.push(`Covered by a ${warranty.value} manufacturer warranty`)
  out.push('Inspected before dispatch and eligible for return on arrival')
  return out
}

export function getProductDetail(id: number): ProductDetail | null {
  const p = BY_ID.get(id)
  if (!p) return null

  const brand =
    p.attributes.find((a) => a.key === 'brand' || a.key === 'author')?.value ?? p.subtitle
  const netQty = p.attributes.find((a) => a.key === 'weight' || a.key === 'pack')?.value ?? '1 unit'
  const vertical = p.vertical

  const productInfo: Attribute[] = [
    { key: 'brand', label: 'Brand', value: String(brand).toUpperCase() },
    { key: 'seller', label: 'Sold By', value: SELLER },
    { key: 'origin', label: 'Country of Origin', value: ORIGIN },
    { key: 'manufacturer', label: 'Manufacturer Name', value: String(brand) },
    {
      key: 'address',
      label: 'Manufacturer Address',
      value: `Plot ${stable(p.id, 3, 10, 99)}, Phase ${stable(p.id, 7, 1, 4)} Industrial Estate, Pune, Maharashtra 4${stable(p.id, 11, 10000, 99999)}`,
    },
    {
      key: 'articleId',
      label: 'Article ID',
      value: String(400000000 + p.id * 12347),
    },
    {
      key: 'veg',
      label: 'Veg / Non-Veg',
      value: vertical === 'grocery' ? 'Vegetarian' : 'Not applicable',
    },
    {
      key: 'height',
      label: 'Item Height',
      value: `${stable(p.id, 13, 2, 30)} cm`,
    },
    {
      key: 'length',
      label: 'Item Length',
      value: `${stable(p.id, 17, 2, 30)} cm`,
    },
    {
      key: 'width',
      label: 'Item Width',
      value: `${stable(p.id, 19, 2, 30)} cm`,
    },
    { key: 'netWeight', label: 'Net Weight', value: netQty },
  ]

  const specifications: Attribute[] = [
    { key: 'netQuantity', label: 'Net Quantity', value: netQty },
    {
      key: 'productType',
      label: 'Product Type',
      value:
        p.attributes.find((a) => a.key === 'pack' || a.key === 'material')?.value ?? p.subtitle,
    },
  ]

  const specLine = p.attributes.map((a) => `${a.label}: ${a.value}`).join(' · ')

  return {
    ...p,
    shortDescription: `${p.name} from ${p.subtitle}. ${specLine}.`,
    descriptionHtml:
      `<p>${p.name} is built for everyday use and backed by a straightforward returns policy.</p>` +
      `<ul>${p.attributes.map((a) => `<li><strong>${a.label}:</strong> ${a.value}</li>`).join('')}</ul>`,
    keyFeatures: keyFeaturesFor(p),
    productInfo,
    specifications,
    showcase:
      `${p.name} from ${brand} is chosen for everyday use and checked before it leaves our warehouse. ` +
      `Order it online today and have it dispatched within 24 hours of confirmation.`,
  }
}

export function listProducts(vertical: VerticalId | null) {
  return vertical ? PRODUCTS.filter((p) => p.vertical === vertical) : PRODUCTS
}

export function searchProducts(term: string) {
  const q = term.trim().toLowerCase()
  if (!q) return []
  return PRODUCTS.filter(
    (p) =>
      p.name.toLowerCase().includes(q) ||
      p.subtitle.toLowerCase().includes(q) ||
      p.attributes.some((a) => a.value.toLowerCase().includes(q)),
  )
}

export function similarTo(p: Product, limit = 6) {
  return PRODUCTS.filter((x) => x.vertical === p.vertical && x.id !== p.id).slice(0, limit)
}

/**
 * What the search panel shows before anything has been typed.
 *
 * Lives here, in the adapter, rather than in the panel: the component is
 * not allowed to know what this shop sells, and "trending" is exactly the
 * kind of thing a real backend will one day compute and hand over. Swapping
 * fixtures for that backend must not mean editing a component.
 *
 * Both lists are derived, never hand-written, so a change of vertical
 * cannot leave a hardcoded grocery term behind on an electronics store.
 * Trending leans on the brand line, which is the shortest human-sounding
 * label a product carries; picks lead on the deepest discounts, which is
 * the most defensible stand-in for popularity a fixture can offer.
 */
export function getSearchSeeds(trendingLimit = 5, pickLimit = 6) {
  const trending = Array.from(new Set(PRODUCTS.map((p) => p.subtitle)))
    .filter(Boolean)
    .slice(0, trendingLimit)

  const picks = [...PRODUCTS]
    .filter((p) => p.inStock)
    .sort((a, b) => b.discountPercent - a.discountPercent)
    .slice(0, pickLimit)
    .map((p) => ({
      id: p.id,
      name: p.name,
      subtitle: p.subtitle,
      href: productHref(p),
    }))

  return { trending, picks }
}

/**
 * What scripts/export-images.mjs needs to draw the catalogue.
 *
 * Exported from the adapter rather than assembled in the script, so the
 * filenames the fixtures point at and the filenames written to disk come
 * from one place and cannot drift apart. The script is the only caller.
 */
export function imageSpecs() {
  return PRODUCTS.map((p) => ({ images: p.images, ...artFor(p) }))
}
