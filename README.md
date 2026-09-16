# 369 Mart Store — Node.js (Next.js 15 + React 19)

Home (Quick / Shop all), Cart and Sign in, as one runnable Node project.

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
- **Header** — logo, Quick / Shop all toggle (springing thumb), delivery location, search with
  rolling words, offers, reorder, cart badge, account.
- **Quick ↔ Shop all switch** — colour floods out of the tapped button, page swaps under it, the
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
- **Banners** — 2-up carousel with autoplay (pauses on hover) and inline banner rows.
- **Cart** — delivery groups, minimum-order nudge, recommendations, coupons sheet, animated payment
  details, pay buttons, delivery instructions.
- **Account** (`/account`) — sidebar with profile card and a gliding highlight; My Profile (edit/save),
  My List (hearts from any product card, saved), Delivery Address (add / default / remove, shared with
  the location picker), Orders (tabs, live progress tracker, expandable detail, Reorder), Help (search +
  FAQ accordion), About us, Legal information, Sign out (confirm dialog). Sections slide in by menu
  order and the panel height eases between them.
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
| `/` | Home — Quick (groceries in minutes) and Shop all (2–5 days), animated switch |
| `/cart` | Cart — delivery groups, min-order nudge, coupons, payment details, instructions |
| `/account` | Account — profile, My List, addresses, orders, help, about, legal |
| `/login` | Sign in · Create account · Forgot password (email only) |

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
  login/page.jsx      /login
components/
  home/Home.jsx       header, mode switch, tabs, banners, categories, rails, cart bar
  home/SearchOverlay.jsx   search panel
  home/LocationPicker.jsx  delivery location popover / sheet
  home/extras.css     gallery, search, location styles
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
- Checkout: `<Home onCheckout={({ how, total, coupon, instructions }) => …} />` — hand the cart
  to Odoo's `/cart/handoff` route (see the headless storefront notes).
- Sign in: `components/signin/SignIn.jsx` props `onEmailSignIn`, `onCreateAccount`,
  `onForgotPassword` — each returns `{ ok: true }` or `{ ok: false, error }`.

## Sample rules to replace
Quick: minimum order ₹99, delivery ₹30, free above ₹499. Shop all: delivery ₹49, free above ₹999
(`CART_RULES` in `Cart.jsx`). Coupons QUICK20 / WELCOME50 / FREEDEL (`COUPONS` in `Cart.jsx`).

## What else is in this zip
- `previews/` — standalone HTML previews of home, cart, account and sign-in (open directly in a browser).
- `extras/odoo-motion-layer/` — the vanilla CSS/JS scroll + search animation layer for the Odoo website
  theme (not used by the Next.js app).
- `package-lock.json` — exact dependency versions, so `npm install` reproduces this build.
