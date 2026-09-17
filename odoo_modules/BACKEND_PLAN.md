# 369 Mart — Odoo backend modules: plan and handover

One document covering all ten modules, the four that exist and the six that don't, with everything a
fresh session needs to pick up the work without re-deriving it.

**Split agreed:** `catalog` → `cart` → `order` in one session; `payment` → `account` → `support` in
the next. The order is forced by dependency, not preference.

---

## Part 1 — Where things stand

### The four built modules

| Module | Serves | Wired to the app? |
|---|---|---|
| `mart369_home` | home feed, `/369mart/home` | **no** |
| `mart369_product` | product detail, `/369mart/product/<id>` | **no** |
| `mart369_auth` | accounts + the Customers operator screen | **yes** |
| `mart369_address` | address book, `/369mart/addresses` | **no** |

All four are installed in `sparenix_test` and green (39 tests). Three of them are finished work the
storefront simply never calls — worth knowing before building more on the same assumption.

### The one fact that governs every module

**The app makes exactly four network calls, all auth:** `/api/auth/me`, `/api/auth/logout`
(`Home.jsx:303,544`) and `/api/auth/{login,signup,forgot}` (`app/login/page.jsx:10`). Everything else
— catalog, cart, orders, payments, wallet, reviews, chat — is static JS plus `localStorage`.

### The design rule — the UI is fixed, the backend adapts to it

**The existing UI does not change.** Not the storefront components, not the layouts, not the field
names they read. Every route returns the object the component already consumes, **field for field**,
so no component has to be rewritten. Where Odoo's natural shape differs, the **module** converts —
never the app.

This is proven, not aspirational. `mart369_home`'s payload is byte-for-byte `DEFAULT_MODES`
(`Home.jsx:265`); `mart369_product`'s is what `ProductDetail.jsx` already reads; `mart369_address`
joins `city` and `zip` into the single `"Dindigul 624003"` string the app uses and splits it back on
the way in, because that is how the app displays it.

Practical consequences, all of them real cases:

- `icon` values stay `home` / `brief` / `pin`, because `<Icon n={…}>` expects those names.
- `id` is serialized as a **string** (`str(product.id)`), because the app compares ids with `===`.
- Odoo fields with no UI counterpart (`state`, `area`, `alt`) are returned but not required, so a
  form that never collected them keeps working.
- A field the UI has no home for is not a reason to change the UI — it waits until there is one.

**The same rule applies to the operator screens.** Reuse `mart369_auth`'s existing stylesheet and
class vocabulary rather than designing a second look; a new module's screens should be
indistinguishable from the Customers screen already shipped.

Three corollaries that are easy to get wrong:

1. **`paid`, `txn`, `status` and refund amounts must reverse direction.** Today the client authors all
   four (`Checkout.jsx:617-631`, `OrderTrack.jsx:471,575`). They don't need a new data source; they
   need to become server-authored and client-displayed.
2. **`deliveryOtp` is `hash(order.id + "otp")`** (`orderState.js:82`) and is also printed in the help
   chat (`OrderTrack.jsx:418`). Anyone holding an order id can compute it offline. It must not
   survive in any form — the server issues a single-use token, the app only displays it.
3. **There is no tax line anywhere in the app.** GST has to enter at the cart, or no invoice the
   order module produces can be legal.

---

## Part 2 — Working conventions

Copy these; they are what the four existing modules do.

**Where code lives.** Source of truth is `C:\Projects\369Mart\odoo_modules\<module>\`, tracked by
git. Odoo's `addons_path` is only `…\server\odoo\addons`, so each module is **junctioned** in:

```powershell
New-Item -ItemType Junction -Path "C:\Program Files\Odoo 19.0.20260119\server\odoo\addons\<module>" `
         -Target "C:\Projects\369Mart\odoo_modules\<module>"
```

Never `rm -rf` a junction. Remove with `[System.IO.Directory]::Delete($p, $false)`.
Do not edit `odoo.conf` — its `addons_path` is shared with other projects on this server.

**Servers.** `8069` is the nssm service (`odoo-server-19.0` + `odoo-gevent-19.0`), serving several
databases — `369application`, `grocery_shop`, `sales_test`, `tool_managament` — so treat it as shared.
Dev work runs a separate process on `8097` against `sparenix_test`. Only one `-u` per database at a
time; parallel upgrades give "could not serialize access" and silently report "0 tests".

**Tests.**
```bash
cd "/c/Program Files/Odoo 19.0.20260119/server"
MSYS_NO_PATHCONV=1 "/c/Program Files/Odoo 19.0.20260119/python/python.exe" odoo-bin \
  -c odoo.conf -d sparenix_test --http-port=8111 --gevent-port=8110 --max-cron-threads=0 \
  -u <module> --test-enable --test-tags=/<module> --stop-after-init \
  --log-level=info --logfile="C:/…/scratchpad/run.log"
```
`MSYS_NO_PATHCONV=1` stops Git Bash mangling Odoo's arguments — but it also mangles a `/c/…` logfile
path, so pass the logfile as `C:/…`.

**Controller shape.** `type='http'`, `auth='user'`, bare JSON via `request.make_json_response`, with
the `_json` / `_body` / `_fail(error, field, status)` helpers — copy
`mart369_address/controllers/address_api.py`. Failures are `{ok: false, error, field?}`; the Next BFF
passes Odoo's status through unchanged.

**Ownership is the security-critical part.** Every route that touches a customer's record resolves
the id through one helper requiring it belongs to `request.env.user.partner_id`, else **404 — not
403**, so ids cannot be probed. Give it its own test; it is the test most worth failing loudly.

**Operator screens.** `mart369_auth`'s `static/src/customers/customer_views.scss` holds the palette
(`$m369-*`) and the class vocabulary (`o_mart369_dash`, `o_mart369_kpi`, `o_mart369_tile`,
`o_mart369_nudge`, `o_mart369_addr`). Depend on `mart369_auth` and **reuse those classes — do not
add a second stylesheet**, or the screens drift apart. The KPI strip pattern is a `js_class` list/
kanban pair with an OWL component above; `customer_dashboard.js` is the template to copy.

### Five gotchas already paid for

- **Odoo forbids `@import` of a local file in bundled SCSS.** One such line fails the whole
  `web.assets_web` bundle and every backend page shows "Style error". The real message is in a
  trailing `css_error_message` rule inside the stored CSS, not the server log. Share variables by
  listing the partial first in the manifest instead.
- **A running Odoo caches each manifest for the life of the process.** Adding or deleting a file named
  in `assets` leaves any already-running server serving a stale manifest — a blank backend with "An
  error occurred while loading javascript modules". `-u` in another process does not fix it. Restart
  `odoo-server-19.0`.
- **An `act_window` on `res.partner` (or any model with stock views) silently uses Odoo's own
  kanban/list** unless you add `ir.actions.act_window.view` records binding yours.
- **A partner may have only one child with `type='delivery'`** — creating a second silently demotes
  the first to `other`. `mart369_address` stores every address as `other` and marks only the chosen
  one `delivery`.
- **`res.partner.mobile` does not exist in Odoo 19** — use `phone`. Groups on `res.users` are
  `group_ids`, not `groups_id`. Kanban pads rows with empty `.o_kanban_ghost` records, so filter them
  out before counting cards in a browser check.

### Verification, per module — not at the end

1. Module tests green **and** every previously passing test.
2. Live matrix over `curl` on 8097, including the ownership 404s.
3. Postgres inspection that what the API claims it stored actually landed. For anything with money,
   assert the Odoo total equals the payload total to the paisa.
4. **Drive the operator screens in a real browser.** Playwright with installed Edge
   (`channel: "msedge"`). Two defects in one day — Odoo's stock kanban being used instead of mine,
   and cards with no customer name — were invisible to DOM assertions and obvious in a screenshot.
5. Recompile `web.assets_web` in an `odoo-bin shell`: `css_errors == []` and no attachment containing
   `## CSS error message ##`.
6. Screenshots into `static/description/`, listed in the manifest `images`.
7. Restart the 8069 service if the manifest gained or lost a file.

---

## Part 3 — Session A: `catalog` → `cart` → `order`

### 1 · `mart369_catalog`
`depends: ['mart369_product']`. First because nothing downstream can name a real product until ids
resolve — today's ids are hand-typed strings like `"f3"` in `catalog.js`.

- **Taxonomy** — `CATALOG`'s id arrays (`catalog.js:115-168`) → `product.public.category`;
  `VARIANT_GROUPS` (`:82-112`) → real `product.product` variants; route slugs (`:171-187`) from the
  category records.
- **Routes** — `GET /369mart/catalog` (the tree), `/369mart/browse/<slug>` (cards + **server-side
  facets**: the brand counts and price min/max `Browse.jsx:139-148` builds today, plus the four
  sorts), `/369mart/search?q=`, `/369mart/search/suggest?q=` (**8** rows, `SearchOverlay.jsx:137`),
  `/369mart/search/trending`.
- Reuse `mart369_home`'s `_serialize_product` so cards stay identical to the home feed.
- **Kills the hash**: `rating` and `popularity` are `hash(product.id)` today (`catalog.js:221-228`)
  and drive both sorts, search ranking and every recommendation rail. Replace with `rating.rating`
  and real sales counts.
- Recent searches move to `res.partner` so they follow the account.

### 2 · `mart369_cart`
`depends: ['mart369_catalog', 'mart369_address', 'delivery']`. Returns `computeBill`'s exact output
(`mrp, items, sub, fees, feeFor, sums, couponValid, couponOff, total, saved, count, blocked` —
`Cart.jsx:25-48`) so `Cart.jsx` and `Checkout.jsx` render unchanged, computed on a **draft
`sale.order`** which becomes the authority.

| Today | Becomes |
|---|---|
| `CART_RULES`: ₹99 min, ₹499/₹999 free-above, ₹30/₹49 fees (`Cart.jsx:13`) | `delivery.carrier` per mode with `free_over` |
| `PRIORITY_FEE = 49` added client-side (`Checkout.jsx:26`) | a second carrier, arriving as a line |
| `COUPONS` with JS `calc()` closures (`Cart.jsx:18`) | `loyalty.program` with expiry and usage caps |
| no tax line | `account.tax` via fiscal position |
| `demoCheck`: `/^6[789]\d{4}$/`, ETA always "13 mins" (`LocationPicker.jsx:18`) | `mart369.service.area`: pincode → mode + ETA |
| `useSlots()`: browser clock, no capacity (`Checkout.jsx:29`) | slot model with capacity per window |

The delivery promise appears in four different wordings across the UI; all four come from the service
area afterwards.

### 3 · `mart369_order`
`depends: ['mart369_cart']`. Takes the Checkout payload (`Checkout.jsx:617-631`) → `sale.order` under
the customer's partner with their `mart369_address` as `partner_shipping_id`. **Idempotent on the
app's order ref**, which is client-generated and can collide (`payment.js:75`).

- `mart369_state`: Selection over the app's own six keys — `placed · packed · shipped · out ·
  delivered · cancelled` (`orderState.js:9-22`) — plus stamps, so the timeline survives a reload.
  `DEMO_MS` (placed → delivered in 100 seconds) and "Skip ahead (demo)" disappear.
- Cancel while `placed`; returns → `stock.return.picking` + credit note; return photos, a counter
  today (`OrderTrack.jsx:361`), become real `ir.attachment` uploads.
- Invoice → `account.move` + QWeb PDF, so `Receipt.jsx`'s Download button (today `window.print()`)
  fetches a real document.
- Delivery OTP server-issued and single-use — see corollary 2 above.
- **Operator dashboard, 369 Mart ▸ Orders**: KPI strip, list, board by state with an Advance button,
  per-customer drill-down on the profile's existing Orders tab. Also makes the Customers screen's
  "Ordered in 30 days" tile, which reads 0 for everyone, tell the truth.

---

## Part 4 — Session B: `payment` → `account` → `support`

All three depend on `mart369_order` existing. Lighter than session A: two are mostly configuring
Odoo's own apps rather than new logic.

### 4 · `mart369_payment`
`depends: ['mart369_order', 'payment']`.

`components/home/payment.js` is a demo gateway whose own header says to replace it. Today
`netbanking()` and `wallet()` **succeed unconditionally without reading their input**; card "OTP" is
any six digits except `000000`; `newTxnId()` is a timestamp slice.

- `payment.provider` + `payment.transaction`, created server-side. **Paid is set by the webhook after
  server-side signature verification**, never by the client.
- Saved methods keep their UI shape — `{cards: [{id, brand, last4, name, exp, bank, default}], upis:
  [{id, vpa, name, app, default}]}` (`accountStore.js:64-72`, read by `Checkout.jsx:560` and
  `AccountExtras.jsx:296`) — but backed by `payment.token`. **No PAN in browser storage**; today the
  full card number passes through app state (`Checkout.jsx:600`).
- **Wallet**: balance (`369mart.wallet`) and ledger (`369mart.walletLog`) are two unlinked keys today,
  which will desync the moment either becomes real. One `loyalty.card` with `loyalty.history`.
  Add-money is a `setTimeout` today (`AccountExtras.jsx:144`) and needs a real transaction.
- `COD_LIMIT = 5000` enforced server-side, not just at `Checkout.jsx:574`.

### 5 · `mart369_account`
`depends: ['mart369_order']`. Small CRUD, several independent pieces.

- **Profile save** — smallest and most obviously broken: `onSave` is literally `setUser`
  (`Account.jsx:399`), so edits are discarded on reload after the UI has said "Saved". Needs a write
  endpoint on `res.partner`; `/369mart/auth/me` already reads.
- **Reviews** → `rating.rating` on `product.template`, with a real "Verified purchase" check against
  `sale.order.line`. Note there are **two disconnected rating systems** today — the order/rider
  rating in `369mart.orderPatches` (`OrderTrack.jsx:504`) and the product review in `369mart.reviews`
  (`AccountExtras.jsx:652`). In Odoo both are `rating.rating`, on different `res_model`s; link them.
  The PDP currently shows three hardcoded reviewers ("Anjali R.", "Faisal K.", "Meera S.") identical
  on all 108 products — `mart369_product` already does the honest thing and returns `[]` when there
  are none.
- **Notifications** → `mail.message`; prefs → `res.partner`. Nothing consumes the prefs today.
- **Referrals** → a real unique code on the partner. Today it is derived from the user's name
  client-side (`AccountExtras.jsx:843`), so it is neither unique nor stable.
- **Wishlist** → `product.wishlist` (`369mart.list` today).
- **Scratch cards / rewards** → `loyalty.program`. The "your coupons" list is currently the global
  `COUPONS` array — identical for every user.

### 6 · `mart369_support`
`depends: ['mart369_order']`, plus `im_livechat` and a helpdesk app.

- One endpoint returning the bot's existing `{text, actions?, chips?, agent?}` shape, so
  `SupportBot.jsx` does not change — its header already prescribes exactly this contract.
- **Consolidate the two bots first.** There are two divergent scripts for one persona: `botReplies.js`
  and a second inline one in `HelpSheet` (`OrderTrack.jsx:410-449`).
- The "human agent" is a `setTimeout` (`SupportBot.jsx:149`) and creates no ticket, while telling the
  customer "I've noted this and will update you within 30 minutes". → `im_livechat` for the operator,
  `helpdesk.ticket` for the record, `mail.message` for the transcript (today `sessionStorage`, gone
  when the tab closes).
- The bot recites hardcoded fees, coupons and SLAs that duplicate `Cart.jsx` constants and go stale
  the moment `mart369_cart` is real — retrieve them instead.
- **WhatsApp**: four independent fakes, none wired (`Cart.jsx:263`, `Checkout.jsx:630`,
  `AccountExtras.jsx:767`, `accountStore.js:99`). The cart's opt-in is stored on the order and read by
  nothing. → `whatsapp.template` / `whatsapp.message` triggered by order state changes.

---

## Part 5 — Carried over

- **Nothing from 2026-09-17 is committed**: the `mart369_auth` UI drop, the `mart369_address` console
  removal, the screenshots. `odoo_modules/mart369_product` also has modified and untracked files that
  are the user's, not mine — keep them out of any commit unless asked.
- **Storefront wiring** is a separate job and now blocks four finished modules. The seams are named in
  the repo's own README: `onPlaced(order)` in `Home.jsx` for orders, `onLocate(coords)` in
  `LocationPicker.jsx` for reverse geocoding, and the `modes` prop for the home feed.
- One old test customer has two addresses both flagged Default — stale rows from a pre-fix version,
  not a live bug.
- `sparenix_test` holds ~14 test customers from today's API matrices ("Addr A/B", "Playwright Person",
  "Matrix Tester", "Button Test"). Worth clearing before anything real.
