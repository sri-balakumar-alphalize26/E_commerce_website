# 369 Mart — Home (quick-commerce layout)

`Home.jsx` (Next.js client component, React only) · `art.jsx` (placeholder product drawings) ·
`sampleData.js` (tabs, banners, categories, rails) · `home.css` (scoped `.hm-*`).
`_preview/preview.html` runs it with the sample catalogue.

## What's on the page
- White sticky header: logo, Quick / Shop all switch, delivery location, search with rolling
  "Search for '…'" words, offers, reorder, cart badge, account.
- Category tabs with a sliding highlight.
- Promo banner carousel (2-up desktop, swipe on mobile, autoplay pauses on hover) + inline banners between rails.
- Category tiles.
- Product rails: wishlist heart, Add → − 1 + stepper, % OFF, veg mark, unit, MRP strike,
  per-unit price, "Quick" tag, "Only N left", out-of-stock with Notify. Arrows hide at the ends.
- Add flies a dot to the cart; free-delivery pill fills toward the threshold; sticky bottom
  bar with item thumbnails, count, total and View Cart.

## Install
```
components/home/Home.jsx
components/home/art.jsx
components/home/sampleData.js
components/home/home.css
app/page.jsx
```
```jsx
import Home from "@/components/home/Home";
import "@/components/home/home.css";

export default async function Page() {
  const sections = await getSections(); // from your /api/products
  return <Home sections={sections} freeDeliveryAt={499}
    onCartChange={(cart) => saveCart(cart)} onViewCart={() => router.push("/cart")} />;
}
```

## Item shape
```js
{ id, name, unit, price, mrp?, image?, veg?, stock?, low?, perUnit?, note?, tag? }
```
`image` = product photo URL (e.g. `/api/image/<id>`). Without it, `art` / `color` / `label`
pick a drawn placeholder. `stock: 0` → out of stock. A section `{ banner: ["b3","b4"] }`
places banners between rails.

## Props
`tabs` `banners` `categories` `sections` `freeDeliveryAt` (default 499 — set your real rule)
`initialCart` `onCartChange(cart)` `onViewCart()` `onSearch()` (hook the search overlay here).

The free-delivery threshold, banner copy and offer percentages are sample content.
