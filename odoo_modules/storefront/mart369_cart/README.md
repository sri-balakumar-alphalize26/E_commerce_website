# 369 Mart Delivery & Pricing (`mart369_cart`)

The bill.

Until now the app added up its own basket. Prices came from the browser's
bundle, the delivery fee was a constant sitting next to them, and a coupon's
discount was a JavaScript closure:

```js
{ code: "QUICK20", group: "quick", min: 199,
  calc: (s) => Math.min(60, Math.round(s.quick * 0.2)) }
```

So the customer's own machine decided what it would be charged. Anyone could
open the console and give themselves any discount they liked.

This module moves the arithmetic to Odoo — **deliberately the same arithmetic**,
step for step, `Math.round` included. A bill that disagreed with the one the app
used to draw would look like a mistake to everyone who saw it, and "the server
is right" is not a thing a shopper wants to read.

No screen changes. `POST /369mart/cart/bill` answers with what the cart page
already prints.

## What moved

| Was | Is now |
|---|---|
| `CART_RULES` — ₹99 minimum, ₹499/₹999 free-above, ₹30/₹49 fees (`Cart.jsx:13`) | **Delivery & fees**, one row per storefront |
| `COUPONS` — three codes with `calc()` closures (`Cart.jsx:18`) | **Coupons**, with expiry and usage limits |
| `demoCheck` — `/^6[789]\d{4}$/`, ETA always "13 mins" (`LocationPicker.jsx:18`) | **Service areas**, a row per pincode or prefix |
| `useSlots()` — windows off the browser clock (`Checkout.jsx:29`) | **Delivery slots**, with a capacity |
| `PRIORITY_FEE = 49` added client-side (`Checkout.jsx:26`) | the fee on the Priority slot |

Everything ships holding the numbers the app has been using, so **nothing a
shopper sees changes on the day it is installed** — only who decides them. The
seed data is `noupdate`, so an upgrade never overwrites a fee you have changed.

## For staff

**369 Mart → Delivery & Pricing**, four screens:

- **Delivery & fees** — per storefront: the promise shown on the basket, the
  smallest order you accept, the amount above which delivery is free, and the
  fee. A mixed basket pays both fees, which is what the app already did.
- **Coupons** — the discount is worked out on the server now. A percentage can
  be capped, a code can be limited to Quick or Express items only, and it can
  expire or run out of uses. A discount can never exceed the bill: no code ever
  hands money back.
- **Service areas** — a row is a pincode, or the start of one: `68` covers
  everything beginning 68. **The most specific row wins**, so a city can have
  its own promise inside a region that already has one.
- **Delivery slots** — the windows the checkout offers. *Order before* is what
  the app expressed as `if (now.getHours() < 17)`. Give a window a capacity and
  it stops being offered once that many orders have taken it — impossible
  before, when the list came from the browser's clock.

## What the app reads

| Route | Answers |
|---|---|
| `POST /369mart/cart/bill` | `{items, mrp, sub{quick,all}, fees, couponValid, couponOff, total, saved, count, blocked, unknown}` |
| `GET /369mart/cart/rules` | `CART_RULES` and the live coupons |
| `GET /369mart/serviceability?pin=` | `{ok, quick, eta}` — or `{ok:false, error}` |
| `GET /369mart/slots` | `{quick:[chip…], all:[chip…]}` |

Three deliberate omissions from the bill:

- **`groups` and `lines`** are the whole product objects, which the app already
  holds. It keeps building those itself.
- **`feeFor`** is a function. There is no JSON for a function.
- **tax.** The app has no tax line anywhere, and Odoo's prices here are what the
  customer pays — which is how Indian retail quotes a price. The GST split
  belongs on the invoice, and that is `mart369_order`'s job.

One addition: **`unknown`** lists basket ids that no longer exist or have been
unpublished. A basket that has sat in a browser for a week still checks out with
what is left in it, but the app can now say which line vanished instead of
quietly charging less than the basket showed.

## Why not `delivery.carrier` and `loyalty.program`

Both were considered and neither fits the screens as they are.

A **carrier** knows `free_over` and a price, but has no idea of a *minimum
order*, and the app needs all four numbers together, per storefront, on the cart
page — where there is no order for a carrier to attach to. The app-facing
numbers therefore live here, and a rule can point at a carrier for when an order
really ships.

**Loyalty** computes its discount *on a sale.order*, and the app shows coupons on
the cart page and the offers page, before any order exists. It also has nowhere
to keep the two lines the app prints — the `title` and the `note` — and no
notion of "Quick items only". Bending the app around the engine would have meant
rewriting the cart page, which is exactly what this work is meant to avoid. The
coupon is applied to the real order in `mart369_order`.

## Tests

`odoo-bin -d <db> --test-enable --test-tags /mart369_cart --stop-after-init`

The arithmetic ones assert exact figures worked out by hand from the same rules
— 100 + 50 = 150, under 499, so 30 delivery, total 180 — rather than "roughly".
If the server ever disagrees with what the app drew, a customer sees the total
move under them.
