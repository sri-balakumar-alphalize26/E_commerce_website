# 369 Mart Store — Node.js (Next.js 15 + React 19)

Home (Quick / Express), browsing (categories, search, offers, buy again), product page, cart, checkout and payment, account and sign in, as one runnable Node project.

## Run
```bash
npm install
npm run dev          # http://localhost:3000
```
Production:
```bash
npm run build
npm start            # PORT=8080 npm start to change the port
```
Needs Node 18.18 or newer (Node 20 LTS recommended).

## Features
- **Header** — logo, Quick / Express toggle (springing thumb), delivery location, search with
  rolling words, offers, reorder, cart badge, account.
- **Quick ↔ Express switch** — colour floods out of the tapped button, page swaps under it, the
  curtain lifts with a curved edge, new page rises in. Whole theme re-colours.
- **Location picker** — tap the location: popover springs from the button (bottom sheet on phones),
  map strip with dropping pin + radar rings, "Use my current location" (browser GPS, locating
  animation), pincode check, saved addresses with animated radio; header text rolls to the new address.
- **Search** — panel grows out of the search bar, sections and chips cascade; past searches
  (saved), trending, quick picks with Add; live results with highlight; Esc / backdrop shrink it back.
  Press `/` anywhere to open.
- **Product cards** — multi-image view: swipe, arrows (on hover / always on touch), animated dots
  showing how many images; heart, Add → − n + stepper, % OFF, veg mark, MRP, Quick / delivery days,
  Only N left, out of stock + Notify.
- **Add to cart** — tap Add: the product image lifts out of the card (card turns mint), arcs into the
  floating green cart pill while shrinking and spinning, the pill squashes and ripples, the item's
  thumbnail pops into the pill, the card image springs back and the button shows ✓ Added before turning
  into the − n + stepper. Works from cards, search results, My List, the product page and "Frequently
  bought together" (items fly one after another).
- **Floating cart pill + mini cart** — pill springs in with the first item (thumbnails, item count, total).
  Tap it and it grows into a "Your cart" panel (rows with steppers, free-delivery check with a driving
  scooter, subtotal, View cart / Proceed to checkout); close shrinks it back into the pill.
- **Banners** — 2-up carousel with autoplay (pauses on hover) and inline banner rows.
- **Cart** — delivery groups, minimum-order nudge, recommendations, coupons sheet, animated payment
  details, pay buttons, delivery instructions.
- **Product page** (`/product/<id>`) — tap any product card, search result, cart line or My List item.
  Image flies in from the tapped card; vertical thumbnail strip (scrolls, up/down arrows) + main image
  (swipe, arrows, dots, counter); desktop hover shows a lens and a magnified zoom pane on the right.
  Brand, name, rating, wishlist, share, price / MRP / % off, Add → stepper, "Show product details"
  (Key features, Product information, Item specifications, Description with view-full, Return policy),
  ratings & reviews with animated bars, delivery address, explore link, "Others you may also like".
- **Checkout** (`/checkout`) — from the cart's Pay buttons. Progress line (Cart ✓ Address Slot Payment);
  steps open and close like an accordion and finished steps collapse to a one-line summary with Change.
  Address: saved addresses with animated radios, add a new one inline (validated). Slot: Quick now or a
  scheduled slot, Express standard or priority (+₹49). Payment: 369 Wallet switch (payable counts down),
  UPI apps or UPI ID with Verify, saved card + new card with a live card preview that flips for CVV
  (brand detection, Luhn and expiry checks), net banking bank tiles, cash on delivery (up to ₹5,000).
  Order summary with bill, savings and a shining Pay button; sticky Pay bar on phones.
- **Payment screens** — UPI: phone with the request notification and a 5-minute countdown ring. Card:
  bank OTP sheet with 6 boxes (auto-advance, paste, shake on a wrong code, resend timer). Net banking:
  redirect steps. COD / wallet: placing-order bar. Success: ring + tick draw with a burst. Failure: red
  cross draws, sheet shakes, Retry or Change method. Demo rules: UPI ID with "fail" is declined, OTP
  000000 is wrong, card ending 0002 is declined.
- **Order success** (`/order/<id>`) — receipt printer: brass slot, the receipt feeds out in motor steps with
  a synthesised printer sound (mute button), then Re-print receipt (rolls back in and prints again) or
  Tear receipt (two tugs, rip sound, jagged top edge, paper drops free). Then Download receipt (prints
  only the receipt), Track order (Account → Orders, where the new order is listed) and Continue shopping.
  Orders, wallet balance and addresses are kept in localStorage.
- **After the order** (`/track/<id>`) — from the receipt's Track order and Account → Orders. Status hero
  whose art changes per step (bag pulse → box flaps closing → scooter riding → tick burst / cancelled)
  with a live ETA. Quick: map with store and home pins, the rider moving along the route (travelled part
  fills, the rest marches), distance bubble, rider card (call / chat) and a 4-digit delivery OTP that flips
  in. Express: truck rolling along Seller → hub → hub → You with scan events. Timeline with times.
  Cancel order (before packing): reason sheet and refund to the original payment or instantly to 369 Wallet.
  Rate order after delivery: stars with moods, what went well / wrong, per-item like, rider tip, comment,
  thank-you burst. Return or replace (7 days): pick items and quantity → reason + photos → refund or
  replacement + pickup slot → return tracker. Help chat with quick topics and order-aware replies. View
  receipt, Reorder. Demo orders move on a fast clock; "Skip ahead (demo)" jumps a step. Changes are kept
  per order in localStorage (`369mart.orderPatches`) and Account → Orders shows the live status.
- **Account** (`/account`) — sidebar with profile card and a gliding highlight; My Profile (edit/save),
  My List (hearts from any product card, saved), Delivery Address (add / default / remove, shared with
  the location picker), Orders (tabs, live progress tracker, expandable detail, Reorder), Help (search +
  FAQ accordion), About us, Legal information, Sign out (confirm dialog). Sections slide in by menu
  order and the panel height eases between them.
- **Browsing** — category pages (`/category/<slug>/<sub>`) with a hero, subcategory tiles and a
  product grid; filters for brand (with brand search), price range, discount, rating, veg, in stock and
  delivery type; sort (relevance, popularity, price, discount, rating); active filter chips; infinite
  scroll with skeleton cards; phones get a floating Sort | Filter bar with bottom sheets. Header tabs,
  home category tiles and rail "View all" all open these pages, and the active tab follows the URL.
- **Search results** (`/search?q=`) — Enter or "See all results" in the search panel; the header keeps
  the term and reopens the panel with it selected. Results come in two blocks like JioMart:
  "Showing results for “neem” in Quick" (direct matches first, then related products from the same
  subcategories) and a tinted "… in Express" block below with 5 items and "See all N results in Express".
  A Quick | Express pill switches which block is the main one (sliding thumb). Chip bar: Sort by,
  Brands, Price (ranges + slider), Discount — each opens a popover (bottom sheet on phones) with a live
  count — and All filters opens a side drawer. "Show more results from Quick" loads 12 at a time.
  Typos get "Did you mean …?". Try "neem", "soap", "sandal", "coffee".
- **Offers** (`/offers`, header % icon) — deal countdown to midnight, coupon tickets with copy, top
  deals grid with discount pills. **Buy again** (`/buy-again`, header clock icon) — items from past
  orders with "Bought N×", Reorder all.
- **Product page extras** — pack-size picker (each size is its own product; price rolls, URL and cart
  are per size, ₹/kg shown), Frequently bought together (tick items, running total, add all),
  Similar products, Others you may also like, Recently viewed (also on home).
- **Footer and 404** — site footer with category links that reveals on scroll; animated 404 with search.
- **Sign in** — email sign in, create account with strength meter, forgot password.

## Product and category images
Sample images are in `public/images/products/<id>-<n>.svg` (1 front · 2 close-up · 3 angled ·
4 back) and `public/images/categories/`. Each product lists its images in `sampleData.js`:
```js
{ id: "t1", images: pics("t1", 4), name: "Wireless Noise-Cancelling Headphones", … }
```
To use real photos, drop your files in with the same names (jpg/png/webp work — just change the
extension in `pics`) or pass full URLs: `images: ["/api/image/123?view=1", "/api/image/123?view=2"]`.
Regenerate the sample SVGs after editing `art.jsx` with `npm run images`.

## Routes
| URL | Page |
|---|---|
| `/` | Home — Quick (groceries in minutes) and Express (2–5 days), animated switch |
| `/cart` | Cart — delivery groups, min-order nudge, coupons, payment details, instructions |
| `/product/<id>` | Product details — gallery with hover zoom, details, reviews, related |
| `/category/<slug>` · `/category/<slug>/<sub>` | Category — subcategory tiles, filters, sort, infinite scroll |
| `/search?q=<term>` | Search results — filters, sort, did you mean |
| `/offers` | Offers — countdown, coupons, top deals |
| `/buy-again` | Buy again — items from past orders |
| `/checkout` | Checkout — address, delivery slot, payment (UPI, card, net banking, wallet, COD) |
| `/order/<id>` | Payment success — printed receipt, re-print, tear, download, track |
| `/track/<id>` | After the order — live tracking, rider, OTP, cancel, rate, return / replace, help |
| `/account` | Account — profile, My List, addresses, orders, help, about, legal |
| `/login` | Sign in · Create account · Forgot password (email only) |
| anything else | 404 inside the store shell |

Header cart icon and the bottom "View Cart" bar open the cart in place and update the URL to
`/cart`; Back returns to `/`. The cart is kept in `localStorage` (`369mart.cart`) so it survives
reloads and direct visits to `/cart`.

## Folders
```
app/
  layout.jsx          root layout, metadata
  globals.css         imports fonts + component CSS
  fonts/              Inter (self-hosted, OFL) — latin + latin-ext so ₹ renders
  page.jsx            /
  cart/page.jsx       /cart
  category/[...slug]/ /category/<slug>/<sub>
  search/page.jsx     /search?q=
  checkout/page.jsx   /checkout
  order/[id]/page.jsx /order/<id>
  track/[id]/page.jsx /track/<id>
  offers/page.jsx     /offers
  buy-again/page.jsx  /buy-again
  not-found.jsx       404
  login/page.jsx      /login
components/
  home/Home.jsx       header, mode switch, tabs, banners, categories, rails, cart bar
  home/SearchOverlay.jsx   search panel
  home/LocationPicker.jsx  delivery location popover / sheet
  home/extras.css     gallery, search, location styles
  home/Browse.jsx     category page, listing + filters, search results, offers, buy again, footer, 404
  home/browse.css     browsing styles and animations
  home/catalog.js     categories → subcategories, extra products, pack-size variants, route maps
  home/nav.js         in-app navigation (NavContext) and URL ↔ view mapping
  home/MiniCart.jsx   floating cart pill and mini cart panel
  home/cartfx.css     add-to-cart flight, Added button, pill and panel styles
  home/OrderTrack.jsx order tracking page, cancel / rate / return / help sheets
  home/orderState.js  order steps, demo clock, rider, OTP, return window — replace with Odoo data
  home/track.css      tracking styles and animations
  home/Checkout.jsx   checkout steps, payment methods, pay sheet (UPI wait, OTP, redirect, result)
  home/Receipt.jsx    receipt printer animation + printer sounds
  home/payment.js     card/UPI helpers, banks, UPI apps, demo gateway — swap for your real gateway
  home/checkout.css   checkout, payment and receipt styles
  home/ProductDetail.jsx  product page
  home/productDetails.js  sample detail content (features, info table, specs, reviews)
  home/product.css    product page styles
  home/Account.jsx    account page and sections
  home/account.css    account styles
  home/Cart.jsx       cart page, coupon sheet, payment details
  home/shared.jsx     icons, product card, rail, fly-to-cart, hooks
  home/art.jsx        drawn product placeholders (used when an item has no image)
  home/sampleData.js  sample catalogue for both modes — replace with your API data
  signin/SignIn.jsx   sign-in flow
public/images/        sample product (multi-view) and category images
scripts/export-images.mjs  regenerates the sample images (npm run images)
```

## Connecting real data (Odoo)
- Location: `<LocationPicker onLocate={async (coords) => ({ id, label, line, city })}` for reverse
  geocoding and `onCheckPincode={async (pin) => ({ ok, quick, eta })}` for serviceability.
- Products: pass `modes={{ quick: {...}, all: {...} }}` to `<Home>` with items shaped like
  `sampleData.js`. Add `image: "/api/image/<id>"` and the placeholder drawing is skipped.
- Categories: replace `CATALOG` in `catalog.js` with Odoo `product.public.category` (slug, name, subs
  with product ids). Pack sizes: `VARIANT_GROUPS` ↔ `product.product` variants of one template.
  `enrich()` fills `brand`, `off`, `rating`, `popularity` for products that don't send them.
- Buy again: `<BuyAgainPage orders={…} />` takes the same order shape as the account page.
- Checkout: the built-in `/checkout` runs by default. To use Odoo's own checkout instead pass
  `<Home onCheckout={({ how, total, coupon, instructions }) => …} />` and hand the cart to `/cart/handoff`.
- Payments: replace `demoGateway` in `payment.js`. Create the payment order in Odoo (payment.provider,
  e.g. Razorpay / PayU / Cashfree), open the provider's checkout for UPI / card / net banking, and mark
  the order paid only after Odoo verifies the signature server-side. `onPlaced(order)` in `Home.jsx` is
  where the confirmed order is saved — post it to Odoo there. Never store card numbers in the app.
- Sign in: `components/signin/SignIn.jsx` props `onEmailSignIn`, `onCreateAccount`,
  `onForgotPassword` — each returns `{ ok: true }` or `{ ok: false, error }`.

## Sample rules to replace
Quick: minimum order ₹99, delivery ₹30, free above ₹499. Express: delivery ₹49, free above ₹999
(`CART_RULES` in `Cart.jsx`). Coupons QUICK20 / WELCOME50 / FREEDEL (`COUPONS` in `Cart.jsx`).

## What else is in this zip
- `previews/` — standalone HTML previews of home, browsing, product, cart, checkout, account and sign-in (open directly in a browser).
- `extras/odoo-motion-layer/` — the vanilla CSS/JS scroll + search animation layer for the Odoo website
  theme (not used by the Next.js app).
- `package-lock.json` — exact dependency versions, so `npm install` reproduces this build.
