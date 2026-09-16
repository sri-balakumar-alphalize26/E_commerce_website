<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Project rules

## What this is

A storefront web app. The layout and interaction model are modelled on **JioMart** (Indian grocery marketplace): gradient header card, pill search, category strip, dense tile grids, discount badges, out-of-stock ribbons, an ADD button that morphs into a `− qty +` stepper, mobile bottom tab bar, sticky cart bar.

The **skin is 369ai.Biz**, not JioMart. Colours come from the company logo only — brand blue→cyan and the orange growth arrow. See `app/globals.css`.

## Current phase: FRONTEND ONLY

Every screen renders from typed fixtures in `lib/fixtures.ts`. There is **no backend, no auth, no payments** in this phase. An Odoo backend lands later.

Client state lives in `localStorage` behind `useSyncExternalStore`, one store per concern: `lib/cart-store.ts`, `lib/prefs-store.ts` (addresses + delivery mode), `lib/wishlist-store.ts`, `lib/session-store.ts`. Each exposes the interface its server-backed replacement will expose, so swapping one is one file.

Two rules those stores share. Snapshots are CACHED -- returning a freshly parsed array from `getSnapshot` makes React believe the store changed on every render and loop. And components subscribe per-item (`use-cart-line.ts`, `use-wishlist.ts`) rather than through context, because context has no selector and one `+` press would otherwise re-render every card on the page.

**Do not** add API routes, database code, or payment code in this phase.

## Hard rules

- **No component may import a vertical-specific type.** Components speak `Product` / `ProductDetail` from `lib/catalog.ts` and nothing else. Anything that knows what the shop _sells_ lives in `lib/catalog-config.ts`. If a change to the product vertical would require editing anything in `components/`, the abstraction has leaked — fix the adapter, not the component.
- **No dead UI.** If a control cannot act, it does not ship. Do not build a heart icon that does nothing.

  The line is DEVICE-local vs SERVER-backed, not frontend vs backend. A wishlist, an address book, a delivery-mode toggle and a profile are all just persisted state, so they are real here and live in `localStorage` alongside the cart. Ratings, reviews, order history, payments, wallets and coupons need a server, so they are omitted -- not stubbed, not seeded with samples.

  An earlier revision of this file listed wishlists and saved addresses as unsupportable. That was wrong: it confused "the server cannot hold this yet" with "this cannot work".

- **Never fabricate social proof or money.** No invented star ratings, review counts, order history, wallet balances or delivery dates. These are the inventions that actually mislead a buyer rather than merely padding a page. A PAN or other identity field in a build with no backend is refused outright.
- **No variant pickers.** Products are single-variant.
- **Tell the truth about sorting.** Sorting is client-side over the fetched page. Never label a page-local sort as if it were global.
- Quantities respect `minQty` and `qtyStep`.

## Conventions

- Next 16 App Router, React 19, TypeScript `strict`
- **Tailwind v4 — CSS-first. There is NO `tailwind.config.js`.** The design system is the `@theme` block in `app/globals.css`.
- Path alias `@/*` → `./*`
- `components/<feature>/` — ui, layout, home, catalogue, product, cart, checkout, account, auth
- `lib/` is **flat**, kebab-case files, hooks as `use-*.ts`
- Single quotes, **no semicolons**, `export default function Name()`
- `lucide-react` for icons; no animation library. Motion is the **vendored mart-motion layer** (`public/mart-motion.js` + `app/mart-motion.css`), driven entirely by `data-mm="role"` attributes. New motion belongs in that layer, not in component CSS or in a React animation library.
  - Both files are copied VERBATIM from the 369mart_motion drop, so a new version is a straight file swap. The JS carries one local change, marked `369mart: LOCAL EDIT` — re-apply it after every update.
  - The engine can always be absent: it loads `afterInteractive` and drops its own flag after 2.5s. Nothing may depend on it having arrived — reach it through `lib/mart-motion.ts`, which returns null when it has not.
  - Anything above the fold carries `data-mm-skip`, because the reveal engine hides what it animates and the fold must not wait on a script.
  - Motion the layer does not cover — a transition belonging to one component, like the delivery-mode curtain — goes in `app/globals.css` under `@layer components`, using the `@theme` easings (`--ease-out-soft`, `--ease-spring`) and palette tokens. Never hardcode a colour a ramp already names.
- Multi-paragraph _why_ comments on non-obvious decisions; no comments restating what the code says

## Next 16 specifics that bite

- `params` and `searchParams` are **Promises** — `const { vertical } = await params`
- `cookies()` and `headers()` are **async**
- `middleware.ts` is now **`proxy.ts`** at the project root
- Every non-default `next/image` quality must be declared in `images.qualities`
- `use cache` requires `cacheComponents: true` — deliberately off for now
