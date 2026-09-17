# 369 Mart Catalog (`mart369_catalog`)

The app's category pages and its search box.

Odoo already knows the products. This module decides how they are grouped for
the app — which categories exist, what colour sits behind each one, and which
products are in them — and it answers the search box.

## Three values the app used to make up

`enrich()` in `components/home/catalog.js` fills in a product's rating,
popularity and brand whenever the card does not carry them, and it fills them
from a hash of the product id:

```js
p.rating = p.rating ?? Math.round((3.8 + (h % 12) / 10) * 10) / 10;
p.popularity = p.popularity ?? h % 1000;
p.brand = p.brand || (p.veg ? "369 Mart Select" : p.unit || "369 Mart");
```

So "sort by customer rating" sorted by a hash, "most popular" was a hash, and a
laptop's brand was whatever sat in its pack-size column. Those two hashes also
rank search results and choose every *similar* and *bought together* rail.

| Card field | Now comes from |
|---|---|
| `rating`, `ratingCount` | `rating.rating` — real reviews, internal notes excluded |
| `popularity` | units actually sold on confirmed orders |
| `brand` | the Brand field on the product |

No change was needed in the app: `??` and `||` mean a card that carries the
value wins. A product with no reviews **omits** `rating` rather than sending 0,
because `0 ?? x` keeps the 0 and the app would draw an empty five stars.

This is done by extending `_price_context_for` on the shared serializer, so the
home feed and the product page get the same values without either module being
touched — and a 40-product page costs two extra queries in total, not eighty.

## For staff

**369 Mart → Catalog** is the category list: name, app address, storefront,
product count, and the two colours the app paints the page with. The board view
shows each category in its own colours, so you see what the shopper will see.

**369 Mart → Searches** is what people typed. Read from the top it is a demand
list; filtered to *Found nothing* — which is how it opens — it is a list of
things customers wanted and you do not stock.

Everything else stays on Odoo's own screens: a product's category is set on the
product, and the category tree is Odoo's `product.public.category`.

## What the app reads

| Route | Answers |
|---|---|
| `GET /369mart/catalog` | the category tree, each with `slug, name, mode, tone, accent, blurb, subs` |
| `GET /369mart/browse/<category>` | that category's product cards |
| `GET /369mart/browse/<category>/<sub>` | one sub-category |
| `GET /369mart/search?q=` | search results, and counts the term |
| `GET /369mart/search/suggest?q=` | the 8 rows under the search box |
| `GET /369mart/search/trending` | the real trending terms |
| `GET/POST/DELETE /369mart/search/recent` | one customer's own recent searches |

**No facets are returned**, deliberately. `useProductFilters` in
`components/home/Browse.jsx` already builds the brand counts and the price range
from the list it is handed, and runs every filter and all five sorts in the
browser. Sending facets would mean rewriting that hook.

`suggest` does not count what it is asked, or every keystroke would make "coff"
as trending as "coffee". `trending` only offers terms that found something —
suggesting a search that returns an empty page is worse than suggesting nothing.

Recent searches live on the customer's partner record, so they follow the
account rather than the browser, and they are strictly private: a signed-out
visitor is sent to the login page, and one customer never sees another's.

## Notes

- **Every category needs an app address** (`fresh-fruits`), because that is what
  the customer's URL contains. It is filled in from the name, kept unique in
  Postgres, and never changed by a rename — a customer may have the link. The
  install hook backfills categories that existed before this module.
- A child category takes its parent's storefront (Quick or Express).
- A category with nothing in it answers `200` with an empty list. "Launching
  soon" is a real state, not an error.

## Tests

`odoo-bin -d <db> --test-enable --test-tags /mart369_catalog --stop-after-init`

The two worth keeping an eye on: `test_card_carries_rating_popularity_and_brand`,
because if a card stops carrying them the app falls back to the hash and nobody
notices — a hash looks exactly like a plausible rating; and
`test_recent_searches_are_private`.
