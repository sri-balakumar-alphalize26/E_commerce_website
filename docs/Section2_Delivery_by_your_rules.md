# Section 2 is in: the website runs on your Quick / Express rules

*From the 369 Mart bridge. This replies to section 2 and section 5 of "Bridge hooks for 369 Mart", 7 Oct 2026.*

| | |
|---|---|
| Commit | `e8398b4` |
| Module | `mart369_whatsapp_bridge` **19.0.1.4.1** |
| Also touched | `mart369_cart` `cart.py` and `mart369_order` `order_place.py` (no version change; behaviour unchanged there) |

Wherever your `sales_automation_quick_express` runs, the website now reads and writes your records and calls your section 5 helpers, so the website and WhatsApp give the same answer. Where your module isn't installed, nothing changes; it's a soft dependency, with no new manifest dependency.

---

## Your question: what to do about the 1f99a9b data

**Please don't revert.** We already took 1f99a9b back (`c5e7f05`) and redid the work properly in `e8398b4`, which is this page. Reverting now would undo section 2.

1. Archive the **duplicate slots 7-12**.
2. Archive **areas 67/68/69** unless the shop really serves those pincodes. The website now reads your areas, so the areas you keep are the ones customers get.
3. Check that your quick / express **rules** and **delivery shops** weren't overwritten (table below).

1.4.1 only fills gaps, and it counts archived records as existing. Nothing you archive comes back.

---

## ⚠️ First, please check: an accidental push this afternoon

Another of our sessions pushed an **unfinished** version of this work inside `1f99a9b` and took it back 4 minutes later in `c5e7f05`. In between, your sync ran bridge **19.0.1.4.0** on DUBAI_TEST, including its migration. That migration copied the website's delivery settings into yours. It **may have**:

| What | What to look for |
|---|---|
| **Added slots** | `sa.qe.delivery.slot`: up to **6 extra slots** that duplicate yours with the website's wording (for example "Today, 6 - 8 PM" next to your "Today 6 - 8 PM"). Archive the duplicates. |
| **Added areas** | `sa.qe.service.area`: up to **3 areas** from the website's sample data (pincodes **67**, **68**, **69**; 67 was Express-only). Remove any you don't serve. |
| **Overwritten your fee rules** | `sa.qe.delivery.rule` quick / express: `label`, `eta`, `min_order`, `free_above` and `fee` were written with the website's values. These are probably the same 369 Mart defaults (30 / 499 / 99 and 49 / 999 / 0), but please check. |
| **Overwritten shop reach and pins** | `sa.delivery.shop`: `qe_quick`, `qe_quick_km`, `latitude` and `longitude` were written from our warehouse settings, for shops whose warehouse had Quick on or a pin. Please check your shops. |
| **Filled product texts** | `product.template.qe_delivery_text` was filled where empty, from our `mart_delivery_text`. This is harmless. |
| **Hid our old menus** | The website's four old Odoo delivery menus (`mart369_cart`) were hidden. This is intended. |

**From `e8398b4` on, this can't happen again.** The migration is now **19.0.1.4.1 and only fills gaps**. It never writes over a rule, a reach or a pin you already have, and it recognises a slot you already have by its **mode, kind, hours and day**, whatever it's called. On a database where 1.4.0 already ran, 1.4.1 changes nothing; we tested exactly that.

---

## What the website does now

| Question | Answered by |
|---|---|
| Is this pincode served? | `sa.qe.service.area._qe_match(pin)` (quick, express, eta) |
| Quick or Express for each item | The product's delivery text (ours **or** your `qe_delivery_text`) is Express. Otherwise your shops that are `qe_quick` and `_qe_ready()`, via `_qe_in_reach(lat, lng)`, then `shop._qe_has_stock(variant, qty)`. Without a pin, your area decides. Your order of rules. |
| What delivery costs | Your two rules (`_qe_for`). **One fee per order, your formula.** The order is Quick only when every line is Quick. The fee is the rule's fee while the goods are under `free_above`, plus the slot's fee. A Quick order under `min_order` is refused. |
| Checkout slots | Your slots where `_qe_is_open()`, as chips keyed `qe:<id>`. A closed or full slot is refused when the order is placed. |
| The placed order | It gets `qe_decided`, `qe_mode`, `qe_slot_id`, then **your `_qe_apply_fee()`**, so there is exactly one fee line (`qe_kind = 'fee'`). We also set our own `mart369_kind = 'fee'` on that line, so our bill, receipt and points read it as delivery. **We add no fee line of our own.** |
| The promise | With a slot: `slot._qe_due(slot._qe_day())`. Without one: our default until the job exists; after that your `sa_promised_on`, which we already copy into `mart369_due_at`. |
| Staff console, Delivery screen | Same screen for the shop's staff; it lists and saves **your** rules, slots, areas and shops (Quick on, reach, pin) with plain create and write. The console's own access check decides who may edit, and the write runs with sudo, because your ACL allows only your delivery managers. |

**One visible change for customers:** a basket mixing Quick and Express items now pays **one** Express fee instead of two, and counts as Express, as WhatsApp already does.

---

## Tests

| Where | Result |
|---|---|
| A private copy of our test database running **your ten modules at DUBAI_TEST versions** (crons and WhatsApp switched off) | **12 / 12** new `TestQeLink` tests pass: pincodes, reach, distance and stock, product text, one fee for mixed baskets, free-above and minimum, slot fee, open slots only, the placed order's single fee line and slot, a full slot refused, the console list, and the gap-filling copy run twice. |
| Our normal test database (without your module) | **642** tests run. Only 8 old failures, which fail the same way without this commit (6 in the bridge, 2 in `mart369_order` caused by a fixed demo door code and a crowded order list). |

---

## Three questions

1. **`qe_auto_fee` on DUBAI_TEST:** is it on? Website orders already carry your fee line when they're placed. If auto-fee is on, your confirm re-applies it, which is fine, because it keeps one line. But your goods total then **includes** our coupon and points lines (they are negative lines), so the free-above check can come out differently from what the customer was shown. Could `_qe_goods_total` leave out negative-price lines? If not, we'd prefer auto-fee off for orders that already have a fee line.
2. **Your `action_confirm` and `_qe_decide`:** when a website order is placed, we set `qe_decided = True` along with `qe_mode` and `qe_slot_id`. Does your confirm skip `_qe_decide` when `qe_decided` is already set? If not, it could change `qe_mode` after the website has charged. Please make it skip, or tell us which field to set. Our tests place orders but don't confirm one through your `action_confirm`, so this is not proven yet.
3. **Step 2:** once you've checked this on DUBAI_TEST, we'll delete the website's old models (`mart369.service.area`, `mart369.delivery.rule`, `mart369.delivery.slot`) and the warehouse fields (`mart369_quick`, `mart369_quick_km`, `mart369_lat`, `mart369_lng`). Tell us when.

---

## Checks to run on DUBAI_TEST

```
# version
mart369_whatsapp_bridge.latest_version == '19.0.1.4.1'

# pincode (an area 68 quick)
env['mart369.service.area']._mart369_check('682016') -> {'ok': True, 'quick': True, 'eta': ...}

# rules the website shows = yours
env['mart369.delivery.rule']._mart369_rules()['quick']._mart369_serialize()
    == your sa.qe.delivery.rule quick (fee, freeAbove, minOrder)

# checkout slots = your open slots
env['mart369.delivery.slot']._mart369_slots() -> keys 'qe:<id>' only

# a website order placed with a slot
order.order_line.filtered(lambda l: l.qe_kind == 'fee')  -> exactly 1 line
order.qe_slot_id set ; order.mart369_slot_key == 'qe:<id>'

# mixed basket (Quick item + Express item, goods under free_above)
env['mart369.cart']._mart369_bill(items, address=addr)['fees'] == express rule fee (one fee)

# console
GET /369mart/admin/delivery -> rules / slots / areas / branches are your records
```

---

*Earlier, all checked by you: `26134da` removals, `ef0a957` mirrors, `76ecc40` hooks, `7e7cad2` links and wallet booking, `a8d893e` variant form.*
