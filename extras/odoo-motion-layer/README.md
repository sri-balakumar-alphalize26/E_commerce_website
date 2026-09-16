# 369 Mart — home page motion layer

Two files: `mart-motion.css` + `mart-motion.js` (vanilla, no dependencies).
`_preview/preview.html` is a stand-in of the home page running the real engine.

## Hooks — add `data-mm="…"` to your markup

| Element | data-mm | Motion |
|---|---|---|
| Header bar | `header` | fades (no transform — keeps `position: sticky` working) |
| Logo / search / cart | `logo` `search` `cart` | logo from left, search drops, cart pops; search glows on focus |
| Cart count bubble | `cart-count` | bumps when an item lands |
| Pill row | `pills` | pills drop in 45ms apart, lift on hover, press-pop on click |
| Banner | `hero` | rises; light sweep + drifting glow behind content |
| Banner text wrapper | `hero-text` | title → subtitle → button cascade, replays on every slide change |
| Banner button | `hero-cta` | shine sweep on hover |
| Dots | `hero-dots` | active dot fills over `--mm-hero-interval` (set to your carousel speed) |
| Category grid / icon | `cats` / `cat-icon` | tiles zoom in 60ms apart, icon pops after; hover lift + icon tilt |
| Section head / See all | `sec-head` / `see-all` | head rises; arrow nudges on hover |
| Horizontal product row | `rail` | row observed as one unit, cards cascade from the right 55ms apart; edge fades |
| Card / image box | `card` / `card-img` | hover lift + image zoom (tag the `<img>` or `data-mm="thumb"`) |
| Discount/NEW badge | `badge` | pops after card lands |
| Add button | `add` | fly-to-cart arc + cart bump; sold-out (`disabled` / `aria-disabled` / card has `oos`) shakes |
| Qty stepper (your cart state) | `stepper`, number `qty` | stepper expands in; qty bumps |
| Out-of-stock strip | `oos` | slides up out of the image; image desaturates |
| MRP (struck price) | `old-price` | strike line draws across |
| "Only 2 left" | `low` | small pulsing dot |

Already have class names you don't want to touch? Edit `MAP` at the top of
`mart-motion.js` (e.g. `card: '.product-card'`) — the engine tags them at runtime.
Only opacity/transform are animated on cards; no layout, colour or size changes,
except the 6px dot added before `low` text.

## Search overlay (tap the search bar)

Page dims, a panel grows out of the bar itself (clip-path morph, text never
stretches), then its sections rise and chips/cards cascade 32ms apart. Esc,
backdrop tap or `data-mm="search-close"` shrinks it back into the bar and
returns focus. Under 600px it opens as a full-screen sheet. `/` opens it from
the keyboard. Scroll is locked while open, Tab is trapped inside.

```html
<button data-mm="search">Search for '<span data-mm="search-roll">
  <span>atta'</span><span>headphones'</span><span>green tea'</span></span></button>

<div data-mm="search-backdrop" hidden></div>
<div data-mm="search-panel" role="dialog" aria-modal="true" hidden>
  <input data-mm="search-input">  <button data-mm="search-close">Esc</button>
  <section data-mm="sp-block"> Past searches
    <div data-mm="sp-stagger"> …chips… </div></section>
  <section data-mm="sp-block"> Your quick picks
    <div data-mm="sp-stagger"> …cards… </div></section>
</div>
```

| Hook | Role |
|---|---|
| `search-roll` | words roll upward every 2.6s (all rolls share one clock — header and panel stay in sync) |
| `sp-block` | section rises, 70ms after the previous section |
| `sp-stagger` | its children cascade |
| `MartMotion.staggerIn(el)` | call after re-rendering live results — rows cascade again |
| `MartMotion.staggerOut(el, cb)` | "Clear" past searches — chips shrink out, then `cb` |
| `MartMotion.openSearch()` / `closeSearch()` | drive it from app state |
| `mm:search-open` / `mm:search-close` | events on `document` for React state sync |

Panel look (background, radius, padding) is your CSS; the layer only positions
and animates it. `--sp-max` on the panel sets desktop width (default 720px).

## Next.js (App Router)

```
public/mart-motion.js
app/mart-motion.css        → import "./mart-motion.css" in app/layout.jsx
```

```jsx
// app/layout.jsx
<html lang="en" suppressHydrationWarning>
  <head>
    <script dangerouslySetInnerHTML={{ __html:
      "document.documentElement.setAttribute('data-mm-js','');" +
      "setTimeout(function(){if(!window.MartMotion)document.documentElement.removeAttribute('data-mm-js')},2500)" }} />
  </head>
  <body>{children}<Script src="/mart-motion.js" strategy="afterInteractive" /></body>
</html>
```

The inline line hides content before first paint (no flash-then-hide); the
2.5s timeout is the safety net — if the engine never loads, the flag is dropped
and the page shows normally. After client-side route changes call
`window.MartMotion?.refresh()` in a `useEffect`.

In the Add handler you can also call `MartMotion.flyToCart(buttonEl)` manually;
the engine already does it on click for any `data-mm="add"`.

Don't combine with the older `o_rv` RevealEngine on the same elements.

## Odoo 18/19

Add both files to `web.assets_frontend` (last), put the `data-mm` attributes in
the QWeb template or via `xpath position="attributes"`. The JS carries
`/** @odoo-module ignore */` so it runs outside the module graph.

## Tuning (`:root` in the CSS)

`--mm-dur 640ms` · `--mm-travel 22px` · `--mm-hero-interval 5000ms` · `--mm-fly` dot colour.
Stagger per group: `STAGGER` in the JS. Fires too late → `ROOT_MARGIN` to `-2%`.

## Safeguards

`prefers-reduced-motion` → everything static. Odoo editor (`body.editor_enable`) →
forced visible. 3s failsafe reveals anything still hidden on screen.
MutationObserver animates cards injected later (ajax / React re-render).
