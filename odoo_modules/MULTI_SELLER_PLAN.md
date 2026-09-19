# 369 Mart — multi-seller: plan and handover

One document covering the move from a single-seller shop to several sellers on one 369 Mart app,
with everything a fresh session needs to pick up the work without re-deriving it.

**Decision agreed:** one database, one `res.company` per seller — Odoo's native multi-company.
Not a database per seller. The reasoning is in Part 1; do not reopen it without reading that first.

**Status:** nothing implemented. This is the plan only.

---

## Part 1 — Why one database, not one per seller

The first idea was: give each seller their own database, then show all their products on our
storefront. It was ruled out, and the reason matters, because it will come up again.

**Odoo databases cannot see each other.** There is no cross-database query, no shared session, no
shared user. So "just show their products" means building and owning, forever:

- a gateway that calls each database's `/369mart/...` endpoints and merges the answers
- sorting and paging by hand — "cheapest first" across 3 databases means fetching from all 3 and
  re-sorting; page 2 means re-fetching page 1
- id mapping, because product 42 exists in every database and is a different product in each. The
  app's basket is `{"42": 2}` — see [`mart369_cart/models/cart.py:42-64`](mart369_cart/models/cart.py) —
  which becomes ambiguous the moment two sellers are in it
- a separate signup per seller, since `login` is unique *per database* and the session cookie is
  per database — [`mart369_auth/controllers/auth_api.py:51`](mart369_auth/controllers/auth_api.py)
- no shared wallet: `mart369_payment.payment_provider_wallet` is one record in one database —
  [`mart369_payment/controllers/payment_api.py:358`](mart369_payment/controllers/payment_api.py)
- order push-back and stock pull-back, because the order is created in *our* database and the
  seller must fulfil it from *theirs*

That is a full systems integration, not a display feature. It never stays "only show".

**Native multi-company gives the same separation for a fraction of the work.** Separate products,
pricing, taxes, orders, invoices and payment providers per seller; a backend where seller A cannot
open seller B's records; and the storefront, cart, login and wallet stay exactly as they are.

A database per seller is only the right answer when the seller is an outside company running their
own Odoo that we do not control. That is not the case here.

---

## Part 2 — How it works, in plain terms

### The one idea underneath

Every record in Odoo can carry a **company**. Every user carries a list of companies they are
allowed into (`company_ids`). Odoo then enforces, at the query level, that a user only sees records
whose company is in their list. That is the whole mechanism.

**"Seller" is just a company with a name attached.**

### What the customer sees

- The app stays **369 Mart**. One brand, one look, one home page. No seller logo, no seller landing
  page, no seller branding anywhere.
- Search and browse show **every seller's products mixed together**, exactly as today.
- The only visible change: a small **"Sold by Green Farms"** line on the product card.
- **The cart belongs to one seller.** Adding an item from a second seller prompts
  "Start a new basket with Fresh Mart?" — the same behaviour as Blinkit and Instamart.
- Login, wallet, saved addresses and order history stay **one** across the whole marketplace.

### What the seller sees

Same Odoo URL as everyone, their own email and password. Their `company_ids` is ticked to exactly
one company, and that single tick is what does the work:

- Products — only theirs. A product they create gets their company automatically.
- Orders — only orders placed with them.
- Not in their menu at all: payments setup, categories, customers, trending searches, the home
  builder. Those stay marketplace-owned.
- If they guess a URL for another seller's record, Odoo raises `AccessError`. Refused, not filtered.

One seller can have several staff logins, all ticked to the same one company. A seller's backend
login and a shopper's app login are separate accounts, because `login` is unique per database.

### What we see

A company switcher at the top right to move between all sellers, or see them together.

### Where the money goes

The order is created under the seller's company, so the invoice, the tax, the stock move and the
payment transaction all land in that seller's books. Our accounts and theirs never mix. Commission,
if it is ever wanted, is a normal inter-company entry — not something bolted on.

---

## Part 3 — Decisions, and the one open assumption

| Decision | |
|---|---|
| One database, one `res.company` per seller | agreed |
| Storefront stays 369 Mart — no seller branding | agreed |
| "Sold by X" line on each product card | agreed |
| One seller per cart (no mixed basket) | agreed |
| Shopper account, wallet, addresses stay global | agreed |
| Sellers log into Odoo themselves | agreed |

**One seller per cart is what keeps this project medium-sized.** It preserves
`one cart = one bill = one order = one payment`, which is welded into the code today: the unique
`mart369_ref` at [`mart369_order/models/sale_order.py:131-132`](mart369_order/models/sale_order.py),
the one-bill-equals-one-order check at
[`order_place.py:198-214`](mart369_order/models/order_place.py), and transaction-to-order as a
Many2one at [`payment_transaction.py:33-39`](mart369_order/models/payment_transaction.py). A mixed
basket would mean splitting the bill per seller, N orders under a parent reference, and one payment
fanned across them — roughly 3-4x the Phase 2 work below.

### ⚠ Open assumption — confirm before Phase 0

**Delivery fees, coupons, delivery slots and service areas stay marketplace-level.** One 369 Mart
fee, one 369 Mart coupon, because it is one brand and one delivery operation.

This assumption is worth a lot. It means `mart369.config`, the home-page modes,
[`delivery_rule.py:58-61`](mart369_cart/models/delivery_rule.py), the coupon `unique (code)`
constraint and the service-area `unique (pincode)` constraint **all stay exactly as they are** — no
migration, no per-company constraints, no per-seller storefront config.

If a seller must set their own delivery fee, that adds a phase back. Note that
`delivery_rule.py:58-61` currently allows **exactly two rows in the whole database** (`quick` and
`all`), so per-seller fees are not merely unimplemented — they are actively prevented.

---

## Part 4 — The two real problems

Everything else in this document is routine. These two are not.

### Problem 1 — `sudo()` bypasses the isolation

Multi-company in Odoo is implemented as `ir.rule` records on `company_id`. **`sudo()` skips record
rules.** The suite has **206 `sudo()` calls** and uses `with_company` **zero times**, so adding
companies alone changes nothing: `product.template.sudo().search(...)` still returns every seller's
products.

The good news: roughly **150 of those 206 are shopper-scoped and correct** — `res.partner`,
`res.users`, `payment.token`, `loyalty.card`, tickets, referrals, ratings. Those models stay global
by decision. Do **not** audit all 206. The set that leaks seller data is five functions, listed in
Part 5.

### Problem 2 — a mixed-seller list cannot be serialized in one company context

This is new, subtle, and the most likely bug in the project.

Because browse and search stay marketplace-wide, [`_cards()`](mart369_catalog/controllers/catalog_api.py)
receives templates from several companies at once. But `free_qty` is warehouse-dependent and the
pricelist is company-dependent, and it is read in three places:

- [`mart369/models/serializers.py:181-187`](mart369/models/serializers.py)
- [`mart369_home/models/home_section.py:129-130`](mart369_home/models/home_section.py)
- [`mart369_product/models/product_page.py:260-261`](mart369_product/models/product_page.py)

Serialize the whole mixed recordset in one context and **every card shows marketplace-wide stock**,
and possibly the wrong price. The fix is to group the recordset by company and serialize each group
under `.with_company(cid)`. Test 3 in Part 8 is what proves it works.

---

## Part 5 — The work

### 5.1 Seller identity — thin, and it lives in `mart369`

```
mart369.seller
  company_id  M2o res.company, required, unique, ondelete cascade
  name        Char, required      # "Green Farms" — the "Sold by" text
  slug        Char, unique        # stable API id, survives a rename
  state       Selection(draft / published / suspended)
```

No logo, no tagline, no storefront fields — there is no seller storefront. Three helpers are all the
rest of the code calls:

```python
_mart369_by_slug(slug)
_mart369_for_company(cid)
_mart369_published_company_ids()      # the read path uses this one
```

**Put the model in `mart369` itself, not in a new module.** It is as foundational as
`mart369.config` already is, and everything below depends on it. Splitting a model's fields from the
code that uses them across two modules makes the next person's life worse for no gain.

A new module **`mart369_seller`** holds only the genuinely new concern — security groups, `ir.rule`
records, and the seller-onboarding action — and is added to `mart369_all`'s `depends`.

### 5.2 Read path — filter by *published seller*, serialize *per company*

Browse and search stay marketplace-wide, so **there is no `?seller=` parameter on the read routes**
and their API contract does not change. Three edits:

**(a) A published-seller term**, so a draft or suspended seller's products never appear. Add to the
`mart369.serializable` mixin in [`mart369/models/serializers.py`](mart369/models/serializers.py) —
already inherited by home mode/section, cart, catalog, order and product page:

```python
def _mart369_visible_domain(self):
    """Products a shopper may see: shared, or a published seller's."""
    cids = self.env['mart369.seller']._mart369_published_company_ids()
    return Domain(['|', ('company_id', '=', False), ('company_id', 'in', cids)])
```

Apply at five chokepoints — one edit each, and the whole read path is covered:

| # | Where | Why it is the chokepoint |
|---|---|---|
| 1 | `home_section.py` `_base_domain()` :124-131 | highest leverage in the repo — all six source resolvers AND this domain |
| 2 | `product_public_category.py` `_mart369_product_domain()` :122-128 | covers catalog browse and `mart_product_count` together |
| 3 | `catalog_api.py` `_search_domain()` :120-129 | search |
| 4 | `cart.py` `_mart369_resolve()` :61-63 | **most security-relevant** — decides what gets priced and ordered |
| 5 | `product_api.py` :23 | after `.exists()`, 404 if the company's seller is not published |

What does **not** need changing: `_guess()` recommendations at
[`product_page.py:250-256`](mart369_product/models/product_page.py) may cross sellers. For a
single-brand marketplace that is desirable, not a leak.

**(b) Group by company before serializing.** In `_price_context_for`
([`serializers.py:192-223`](mart369/models/serializers.py)), split the recordset by `company_id`,
call each group with `.with_company(cid)` before reading price and `free_qty`, then merge back into
the original order. One function, and Problem 2 is solved.

**(c) The seller on the card.** [`serializers.py:144-152`](mart369/models/serializers.py) gains:

```python
'seller': {'slug': ..., 'name': ...},
```

**Always present, never optional** — unlike the optional keys below it, the frontend must never have
to handle it missing. The app renders it as a small "Sold by ..." line.

### 5.3 Cart, order, payment

**The cart derives its own seller.** [`cart.py:61-63`](mart369_cart/models/cart.py) already resolves
the templates; take `company_id` from them. No new request parameter is needed — the basket already
says who it belongs to. If the items span more than one company, `/369mart/cart/bill` answers:

```json
400 {"error": "mixed_sellers", "sellers": ["green-farms", "fresh-mart"]}
```

so the app can prompt for a new basket. Do not rely on silently dropping the odd-seller items: that
charges less than the shopper was shown.

**Order placement** — [`order_place.py:96`](mart369_order/models/order_place.py):

```python
order = self.sudo().with_company(company).create({
    ...,
    'company_id': company.id,
})
```

`warehouse_id` computes from `company_id` in Odoo 17+, so setting the company is enough — but assert
it in a test rather than trusting it. `with_company` also makes pricelist, sales team and fiscal
position defaults resolve in the right company.

**Tax** — [`order_place.py:314-327`](mart369_order/models/order_place.py) reads
`self.env.company.mart369_tax_id`. Change to `self.company_id.mart369_tax_id`. The field on
[`res_company.py:20-24`](mart369_order/models/res_company.py) is already per-company; no field change
needed.

**The two service products** at [`order_place.py:187-188`](mart369_order/models/order_place.py) need
**no change**. Their `company_id` is `False`, which in Odoo means shared across all companies — which
is already the correct multi-company answer.

**Payment** is the fiddliest area:

- `_mart369_provider_for()` ([`payment_provider.py:68-94`](mart369_payment/models/payment_provider.py))
  takes a company argument instead of `env.company`. The caller resolves it from the order. Note it
  already calls `_get_compatible_providers(company_id, ...)`, so this is the most multi-company-ready
  code in the suite.
- **COD must stop using `env.ref('delivery.payment_provider_cod')`**
  ([`payment_provider.py:61`](mart369_payment/models/payment_provider.py)).
  `payment.provider.company_id` is required in Odoo and the `delivery` module creates a COD provider
  *per company*. Replace with a search by code + company, and apply the ₹5000 limit per company at
  onboarding. [`payment_api.py:171`](mart369_payment/controllers/payment_api.py), which builds the
  "cash on delivery up to X" message from the same ref, must read the same search — otherwise every
  seller quotes our limit.
- **Wallet** — [`payment_api.py:358`](mart369_payment/controllers/payment_api.py). One wallet
  *provider* per seller company, created at onboarding, so settlement lands in the right books. The
  shopper's wallet *balance* (`loyalty.card`) stays global. Put that in a comment: it reads like a
  contradiction otherwise.
- **Token lookup** — [`payment_api.py:133-135`](mart369_payment/controllers/payment_api.py) picks a
  provider with no company filter at all. Add `('company_id', 'in', (cid, False))`.

### 5.4 Backend isolation — the `mart369_seller` module

**Groups:** `group_seller`, and `group_marketplace_manager` implying it plus
`base.group_multi_company`.

**A seller user gets `company_ids` of exactly one company.** That single line is where most of the
isolation comes from — Odoo's own rules on `sale.order`, `stock.*`, `account.move`, `payment.*` and
`product.pricelist` all key off `company_ids` and need nothing from us.

**Needs `company_id` + the standard rule** `['|',('company_id','=',False),('company_id','in',company_ids)]`:
`product.template` (native field with a native rule — free), `mart369.order.return`,
`mart369.order.stamp`, `mart369.ticket`.

**Marketplace-owned, read-only to sellers:** `product.public.category`, `mart369.config`, home
modes/sections/banners/tiles/tabs, delivery rules, coupons, service areas, slots,
`mart369.search.term`, the `mart369.product.page` layout registry, `mart369.bot.rule`. These are our
brand and our storefront — sellers do not touch them.

**Guard against orphan products:** add an `@api.constrains` on `product.template` refusing a
published product with no company once more than one seller exists. Otherwise a product silently
belongs to everybody.

**The menu does not need forking.** [`mart369/views/menus.xml`](mart369/views/menus.xml) renders
narrower automatically, because `ir.ui.menu` hides entries whose action model the user cannot read.
Put `groups="mart369_seller.group_seller"` on the root and keep the home builder, pricing, payments,
categories, customers and trending terms manager-only. The order and support menus already gate on
`sales_team.group_sale_salesman` and are correct as-is.

### ⚠ 5.5 The one genuine hole — `res.partner`

**Odoo ships no `ir.rule` restricting `res.partner` for a salesman.** A seller's staff would see
every shopper in the marketplace, including people who only ever bought from another seller. This
collides head-on with "sellers must never see another seller's data", and a company term cannot fix
it, because shoppers are deliberately global.

**Recommended fix:** a stored `mart369_seller_ids` M2M on `res.partner`, written at
[`order_place.py:96`](mart369_order/models/order_place.py), with the rule
`['|', ('mart369_seller_ids','in',company_ids), ('id','=',user.partner_id.id)]`. Needs a backfill,
but it is fast.

**Rejected alternative:** a rule with a correlated subquery on `sale.order`. No backfill, but it puts
a slow domain on the most-searched model in Odoo. Expect complaints.

### 5.6 Onboarding a seller

One action in `mart369_seller`, creating in this order:

1. `res.company`
2. a warehouse
3. the `mart369.seller` record
4. a COD provider, with its limit applied
5. a wallet provider
6. the seller's manager user, `company_ids` set to exactly that one company

---

## Part 6 — Phases

Each phase leaves the system working and shippable.

**Phase 0 — ~1-2 days, nothing visible changes.**
`mart369.seller` model + helpers; the `seller` key on every product card; the group-by-company
serialization fix (5.2b). Still one seller, so nothing moves — but the frontend can build "Sold by"
straight away, and the fix for Problem 2 is in place before it is needed.

**Phase 1 — read isolation.**
Backfill `product.template.company_id`; add `_mart369_visible_domain()` at the five chokepoints; add
the `@api.constrains`. Two sellers can now coexist and browse correctly. Test on staging with a
throwaway second company.

**Phase 2 — transact.**
Cart seller derivation and the `mixed_sellers` 400; order under the seller's company and warehouse;
per-order tax; per-company COD, wallet and provider lookup. **Money moves here — do not bundle this
with Phase 3.**

**Phase 3 — backend isolation.**
The `mart369_seller` module: groups, rules, menu groups, the `res.partner` fix, the onboarding
action. **Independent of Phases 1-2** — a second person can build this in parallel from Phase 1
onward.

---

## Part 7 — Migrating the existing data

Additive and reversible. There are no unique constraints to rewrite, because config, home modes,
delivery rules and coupons all stay marketplace-level under the Part 3 assumption.

1. Install the new module versions. No behaviour change — every new `company_id` defaults to the
   existing company.
2. Create one `mart369.seller` for the existing company, `state = 'published'`.
3. Backfill `product.template.company_id` for every template with `is_published` or any `mart_*`
   field set. **Exclude `mart369_order.product_delivery_fee` and `product_coupon`** — they must stay
   NULL, because NULL means shared and that is correct.
4. `sale.order` and `payment.provider` need nothing — `company_id` is required on both and is already
   right. Do run the COD limit per company.
5. If the `res.partner` fix is taken, backfill `mart369_seller_ids` from existing `sale.order` rows.
6. Seller #2 is then an onboarding click, not a migration.

---

## Part 8 — Verification

Shared fixture in `mart369/tests/common.py` — two companies, a published seller each, a product each,
a seller user each with exactly one `company_ids` — reused the way
[`mart369_order/tests/common.py:15`](mart369_order/tests/common.py) already reuses
`mart369_payment`'s.

1. **Both sellers appear.** `/369mart/search` and `/369mart/browse/<slug>` return both companies'
   products, each card carrying the right `seller.name`. Here mixing is the *correct* result — this
   is not an isolation case.
2. **A suspended seller vanishes** from home, catalog, browse and search, and their product id
   returns 404 from `/369mart/product/<id>`.
3. **The stock trap.** Give both companies the same product name with different warehouse
   quantities. Assert each card's `stock` / `low` reflects its own seller's warehouse — not the sum,
   not the other's. **This is the test that catches a missing `with_company` in 5.2b, and it is the
   most likely bug in the whole project.**
4. **Mixed basket** → `/369mart/cart/bill` returns 400 `mixed_sellers`, and `total` is never computed
   across sellers.
5. **Order placement** → `order.company_id`, `warehouse_id.company_id`, the line taxes and
   `provider_id.company_id` all resolve to the right seller.
6. **Backend, not sudo'd** — via `with_user(seller_a)`: `product.template` and `sale.order` searches
   exclude B; reading B's order raises `AccessError`; `res.partner` search excludes a shopper who
   only ever bought from B.
7. **Menu** — seller A sees the 369 Mart root plus their products and orders, and does not see
   payments, categories or the home builder.
8. **Every existing suite passes unchanged** on a single-company database. Free, and it is the proof
   that nothing regressed for today's shop.

A source-grep test is also worth it: `product.template.sudo().search` must not appear outside
`serializers.py` and the five chokepoint files. Ugly, but it is the thing that survives the next
contributor.

---

## Part 9 — Known limits, before anything is promised

- **Per-seller pricelists are out of reach without rework.**
  [`serializers.py:192-223`](mart369/models/serializers.py) prices through `get_current_website()`,
  and there is one marketplace website, so one pricelist for everybody. Per-product `list_price` is
  already per-seller, since products belong to sellers — so this is fine now. But a seller wanting
  their own pricelist means reworking `_price_context_for`.

- **[`serializers.py:205-210`](mart369/models/serializers.py) swallows every pricing exception** into
  `prices = {}` and silently falls back to `list_price`. Under multi-company a `with_company` mistake
  lands here invisibly and charges a wrong-but-plausible price. **Add a `_logger.exception` in Phase
  0** — cheap, and it will save a day during Phase 1.

- **One delivery fee for all sellers** is the Part 3 assumption. If it turns out wrong,
  [`delivery_rule.py:58-61`](mart369_cart/models/delivery_rule.py)'s `unique (mode)` allows exactly
  two rows in the whole database and would need a migration to `unique (company_id, mode)`, plus the
  same treatment for coupons, slots and service areas.

- **Mixing sellers in one basket stays blocked.** If customers push back, the behind-the-scenes split
  is a separate project of roughly 3-4x the Phase 2 work — see Part 3.

- **One website per seller is a dead end**, for the record. A website request is bound to one
  website, so it could never produce the cross-seller home and search that are the whole point, and
  it would need a hostname per seller. `website=True` in
  [`mart369/controllers/public.py:23`](mart369/controllers/public.py) is there for the pricelist and
  fiscal position only — not for multi-tenancy.
