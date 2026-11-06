# 369 Mart Payments & Wallet (`mart369_payment`)

Real payments for the storefront, saved cards and UPI IDs that hold no card number,
and a **369 Wallet** whose balance and history cannot drift apart.

The screen this replaces is a demo, and its own header says so. `demoGateway`'s
`netbanking()` and `wallet()` take no arguments at all and return success without
reading anything; `newTxnId()` is a slice of the clock; and the order the app writes
carries `paid`, `txn` and `status` that nothing ever checked.

## What changes, and what does not

**The storefront does not change.** Every route answers the object the component
already reads, field for field — the saved-methods document, the wallet balance and
ledger, and the gateway's own `{ok, txn}` / `{ok:false, error}` /
`{ok:false, retry:true, error}` shapes, so the pay sheet keeps working by polling a
route instead of awaiting a promise.

What reverses direction is who authors the truth:

| | Before | After |
|---|---|---|
| `txn` | `"TXN" + Date.now()` in the browser | the provider's reference |
| `paid` | written before any gateway confirms | set when the provider's webhook confirms |
| cash on delivery | marked paid the moment the order is placed | **not paid until the cash is collected** |
| the card number | held in React state, sent through app state | never reaches us; there is no field for it |

## The 369 Wallet

One `loyalty.card` per customer holds the balance; every movement is a
`loyalty.history` row. The app keeps these as two unrelated `localStorage` keys, so
a failure writing either one leaves them disagreeing for ever. Three things stop
that happening here:

* a **partial unique index**, so a customer cannot end up with two wallets;
* a **`write()` guard**, so `points` cannot change outside the movement helper —
  not from a later module, not from an operator, not from a stray `sudo().write()`;
* an **advisory lock** in the helper, so two tabs paying at once serialise.

A debit larger than the balance **raises**. The app clamps it with
`Math.max(0, …)`, which silently absorbs an overdraft in the shop's favour.

Ledger rows carry a real `order_id` reference. The subtitle still reads
`Order #369M-…` because the app digs the order out of it with a regular expression —
but that string is no longer the only copy.

## For staff

**369 Mart → Payments** — a numbers strip (collected today, how many went through
with a 14-day chart, waiting, cash still to collect, and the wallet float), a list,
and a board grouped by status. A cash payment has a **Cash collected** button; that
is the only thing that makes it paid.

**369 Mart → Wallets** — every wallet with its balance, what its movements add up
to, and a flag when the two disagree. Open one to see the full ledger.

Both screens use `mart369_auth`'s stylesheet, so they and the Customers screen are
one design.

**369 Mart → Settings** draws every group the shop's settings hand it: Store,
Payments (this module), Alerts, and **Customers** when `mart369_auth` is
installed - how many days a customer is New, and when a quiet one turns Dormant.
See `mart369_auth`'s README.

## The API

Called by the storefront's own server, not the browser. All `auth='user'`.

| Route | Does |
|---|---|
| `GET /369mart/payment/methods` | saved cards and UPI IDs |
| `POST /369mart/payment/methods/upi` | save a UPI ID |
| `POST /369mart/payment/methods/card` | start saving a card — **no number in the body** |
| `PATCH /369mart/payment/methods/<id>` | choose the default |
| `DELETE /369mart/payment/methods/<id>` | archive one |
| `GET /369mart/wallet` | balance, limits and the ledger |
| `POST /369mart/wallet/topup` | start adding money — credits nothing yet |
| `GET /369mart/wallet/topup/<ref>` | did it land? |
| `POST /369mart/payment/pay` | take a payment |
| `GET /369mart/payment/status/<ref>` | poll it |
| `POST /369mart/payment/<ref>/cancel` | give up on it |

A customer can only ever reach their own saved method, wallet and payment: every
route resolves the id through one helper that requires it to be theirs, and answers
**404 otherwise — not 403**, so ids cannot be probed.

## The cash limit

`COD_LIMIT` is not a constant in this module. It is `maximum_amount` on Odoo's own
cash-on-delivery provider, which `_get_compatible_providers` already applies — so an
operator changes it without a deployment, and it is measured against the cash
actually to be collected rather than a number the browser sent.

Cash on delivery itself is entirely Odoo's: `delivery` ships the method, the
provider and the rule that refuses cash unless the carrier allows it.

## Choosing a provider

Nothing here names a gateway. A payment resolves through
`_get_compatible_providers`, so enabling `payment_razorpay` — present in this
installation — makes it take UPI, cards and net banking with no code change. Fill in
the key and secret, set it to enabled, and register its webhook URL.

`paid` is set in exactly one place, `payment.transaction._post_process()`, which
Odoo reaches from the provider's own webhook **after** its signature check.

## For `mart369_order`, when it exists

Three methods on `payment.transaction`, and nothing else moves:

* `_mart369_on_paid()` — the money is in and verified. Must stay idempotent.
* `_mart369_on_failed()` — give back the wallet leg; call `super()`.
* `_mart369_amount_for()` — read the total off the `sale.order` and ignore what the
  browser claimed.

Until then, every transaction priced by the browser is flagged
`mart369_amount_client`, and the operator list can filter for them. It is a real
hole, so it is recorded on the record rather than left implicit.

## Tests

`odoo-bin -d <db> --test-enable --test-tags=/mart369_payment --stop-after-init`
