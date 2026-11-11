# Hubs on the website and WhatsApp: session notes (11 Nov 2026)

Everything done in this session, what was tested, and what is still open.
Committed on branch `hubs-whatsapp-11nov` (10 commits, not pushed). Times are local (UTC+4); Odoo stores them in UTC.

Plan page (artifact): https://claude.ai/artifact/6zQmMtRhB5Wfa5YoHEmhut

---

## 1. Summary

- **Website:** a basket from several hubs becomes one order per hub. It now stays that way even
  where the WhatsApp Quick/Express module is installed (step 5). Built and tested.
- **WhatsApp:** each hub has its own group. The group's **Company** is the hub, so every order
  raised in that group belongs to that hub. This already worked; no build was needed.
- **WhatsApp end-to-end test** on `WHATSAPP_TEST`: two orders (Customer test → My Company,
  Test 2 → br1). Each stayed in its own hub for the order, taxes, delivery, serials, invoice and
  payment. All 66 messages were sent; none failed.
- **Two bugs found in that test and fixed in code** (`sales_automation`): a name change didn't
  reach the delivery address, and an order placed from the group didn't know its group.
  The fix is in the repo and tested on a copy, but not yet installed on `WHATSAPP_TEST`.

---

## 2. How hubs work: website vs WhatsApp

| | Website | WhatsApp |
|---|---|---|
| Who picks the hub | The customer's address: the nearest hub that has the item, per item | The **group**: each group's Company is its hub |
| Items from 2 hubs | Split into one order per hub, paid once (cash on delivery or 369 Wallet) | Can't happen: one group is one hub |
| Hub out of stock | The next hub steps in | No other hub; the WhatsApp out-of-stock flow runs (sign link, vendor request) |
| Quick / Express | Hub rules table and each hub's distances, shown before paying | WhatsApp Quick/Express rules, decided at confirm |
| Cargo badge | Yes, on long trips | No |
| Order, warehouse, taxes, invoice, payment | In the hub's company | In the group's company |

**WhatsApp setup per hub:** one session (one number) serves every group.
1. Add the session's number to the hub's WhatsApp group.
2. In Odoo, open the session and click **Sync Groups**.
3. Open the group, set **Company** = the hub, and switch **On**.

Things to know:
- A group picks a **company**, not a warehouse. The order uses that company's default warehouse.
- A group with **no Company** falls back to the session's Order Company. Set it on every group.
- The finder's **Stock Company** only decides where the price and stock are read. It never moves the order.
- Each company needs its own **payment methods switched on**: the WhatsApp pay link offers the
  order company's methods.

---

## 3. Code changes

### 3a. Step 5: the website split stays on with WhatsApp Quick/Express

Module `mart369_whatsapp_bridge` → **19.0.1.7.0**

| File | Change |
|---|---|
| `storefront/mart369_whatsapp_bridge/models/qe_link.py` | New `hubs_on(env)`. With the hub rules on, the website's own rules win: hubs, fees, minimum, mode. The split is no longer switched off. Split parts and hub-rule orders keep the website's fee line, and `_qe_apply_fee` (at confirm and from the button) leaves them alone. A Quick hub part is sent from its hub's shop. Also: a WhatsApp delivery shop no longer makes another company's product Quick. |
| `storefront/mart369_whatsapp_bridge/tests/test_hub_split_qe.py` | **New**, 6 tests |
| `storefront/mart369_whatsapp_bridge/tests/test_qe_link.py` | setUp clears the hub table (those tests are about the WhatsApp rules) |
| `storefront/mart369_whatsapp_bridge/tests/__init__.py` | Imports the new test file |
| `storefront/mart369_whatsapp_bridge/__manifest__.py` | 19.0.1.6.3 → 19.0.1.7.0 |
| `storefront/mart369_cart/models/cart.py` | Docstring of `_mart369_split_allowed` only |
| `docs/STATUS_2026-11-11.md` | Two lines under §3 Hub testing |

**Where it runs:** copied into the local Odoo addons folder. `WHATSAPP_TEST` reports the bridge at 19.0.1.7.0.
The override of `_qe_apply_fee` works because the bridge loads after `sales_automation_quick_express`:
the bridge depends on `sales_automation_confirm`, which sits above `sales_automation_store`.

### 3b. WhatsApp fixes: name change and the order's group

Module `sales_automation` → **19.0.173.12.0**

| File | Change |
|---|---|
| `sales_automation/sales_automation/models/sa_group_request.py` | New `_sa_rename_own_addresses()`. When the customer changes their name, their **own** delivery addresses (the ones carrying the old name) follow. An address for someone else keeps its name. |
| `sales_automation/sales_automation/models/sale_order_link.py` | `sa_group_id` is now computed from the forward link **or** the enquiry pointing at the order (new `sa_enquiry_ids`). This fixes the order form, the console card, and the rider job's sending number. The chat flow is unchanged: `sa_group_request_id` is **not** written, because writing it would switch private chats onto the group's question ladder. |
| `sales_automation/sales_automation/migrations/19.0.173.12.0/post-migrate.py` | **New**: fills `sa_group_id` on existing orders |
| `sales_automation/sales_automation/tests/test_details_name_and_group.py` | **New**, 6 tests |
| `sales_automation/sales_automation/tests/__init__.py` | Imports it |
| `sales_automation/sales_automation/__manifest__.py` | 19.0.173.11.0 → 19.0.173.12.0 |

**Where it runs:** repo only. It was tested on a copy, and the local Odoo was put back to the original files afterwards.

---

## 4. Test results

### Step 5 (on `qe_hub_test`, a copy of `WHATSAPP_TEST_HUB` with Quick/Express installed)

| | Old code | New code |
|---|---|---|
| Failed + errors | 108 of 404 | 85 of 410 |
| New tests (`TestHubSplitQe`) | — | 6 of 6 pass |

- 26 tests that failed before now pass, mostly the hub split and hub rules tests.
- None of the remaining failures come from the change; they fail with the old code too.
  - They are website tests that assume the website's own delivery stack, while the WhatsApp
    Quick/Express module takes over when the hub table is empty.
  - Some are test data: the copy has 6 real hub rules, and `product_tracker` needs serials before confirming.
- `TestBranchQuick.test_a_branch_with_quick_off_reaches_nobody` fails because the copy's hub rules
  apply. The test doesn't clear the hub table.

### WhatsApp fixes (on `wa_fix_test`, a copy of `WHATSAPP_TEST` with every session, group and scheduled job switched off)

- All `sales_automation` tests pass, including the 6 new ones.
- 3 bridge tests fail: `TestStoreChannel` ×2 and `TestWhatsappOrders.test_deliver_needs_the_stacks_code`.
  These are the same 3 that failed with the old code.
- After the migration, S00023 → Customer test (sri) and S00024 → Test 2 (sri).

---

## 5. Setup changes made in `WHATSAPP_TEST` (data, not code)

| What | Now |
|---|---|
| Group **Customer test** #245 (session sri) | **On**, Company My Company |
| Group **Test 2** #223 (session sri) | **On**, Company **br1** |
| Group Customer test #130 (session angitha) | **Off**, so the bot doesn't answer twice (same WhatsApp group as #245) |
| Group Name Later #120 | Back to off, Company My Company (turned on by mistake, then reverted) |
| Employee **sri** + employee session #9 | New: session sri, number 917092090133, Order Company My Company, settings copied from angitha (auto-reply off) |
| Payment methods, **ho** | Cash on Delivery (#26) on; Demo (#33) test mode |
| Payment methods, **br1** | Cash on Delivery (#28) on; Demo (#32) test mode |
| Stock, **BR1/Stock** | 5 × Demo laptop 8 GB / 512 GB SSD, serials **BR1-TEST-001 … 005** (inventory adjustment) |

---

## 6. WhatsApp end-to-end test (11 Nov, 14:14–14:51)

| | Customer test → My Company | Test 2 → br1 |
|---|---|---|
| Order | **S00023**, confirmed | **S00024**, confirmed |
| Items | 1 × Demo laptop 8 GB / 512 GB | 2 × Demo laptop 8 GB / 512 GB |
| Warehouse | My Company | **br1 Warehouse** |
| Taxes | My Company's (5%) | **br1's** (5%) |
| Total | 630.000 | 1,260.000 |
| Delivery | MC/OUT/00006 from MC/Stock, serial LAPT000000002 | **BR1/OUT/00001 from BR1/Stock**, serials BR1-TEST-001 and 002 |
| Invoice | INV/2026/00005, My Company, paid | **INV/2026/00001, br1** (its own numbering), paid |
| Payment | Demo card, My Company, done | Demo card, **br1**, done |
| WhatsApp | 28 sent, 0 failed; picture, order PDF and invoice PDF sent | 38 sent, 0 failed; picture, order PDF and invoice PDF sent |

- **Stock:** each order reserved only from its own hub. BR1 has 5 on hand, 2 reserved, 3 free.
  MC/Stock has 100 on hand, 2 reserved (S00023 and the older S00010), 98 free.
  No negative stock in any warehouse.
- Stock is **reserved**, not yet taken out. It leaves when the delivery is validated.

---

## 7. WhatsApp sessions on this machine

| Database | Session | Status |
|---|---|---|
| **WHATSAPP_TEST** | #6 angitha | error (it was connected earlier today; angitha and sri share one number) |
| **WHATSAPP_TEST** | #25 sri | connected |
| WHATSAPP_TEST_HUB | #6 angitha, #25 sri | error 403: "token belongs to database WHATSAPP_TEST" |
| qe_hub_test (test copy) | #6 angitha | disconnected |
| wa_fix_test (test copy) | angitha, sri | switched off, dead gateway address, dummy key |
| alpha_reset_test, trading_test_1706 | admin, Nisha | waiting for QR |

The gateway (`localhost:8086`) accepts a key only from the database it was issued to.
`WHATSAPP_TEST_HUB` is a copy of `WHATSAPP_TEST`, so it carries the same key and is refused.

**No messages were sent by any test or check in this session.** The bridge tests fake the gateway,
scheduled jobs were off during test runs, and the test copies can't use the real key.

---

## 8. Still to fix / to do

### Do next
1. **Install the WhatsApp fixes on `WHATSAPP_TEST`.** Copy `sales_automation` into the Odoo addons
   folder, upgrade the module (19.0.173.12.0), then repeat NO → NAME in **Test 2** and check the
   read-back shows only the new name.
2. **Test 1 → ho.** Click Sync Groups on the sri session, set Test 1's Company to **ho**, and switch it on.
   ho has **no stock**: add test serials like BR1, or the order takes the out-of-stock path.
3. **Delivery not tested yet.** Both orders are "waiting for the shop". Test shop Accept, the rider,
   and Delivered, then check the stock leaves (BR1 5 → 3, MC 100 → 99).
4. **No delivery shops exist in `WHATSAPP_TEST`** (`sa.delivery.shop` is empty). Check how Accept and
   rider dispatch behave, and add a shop per hub warehouse if needed.

### Watch out
5. **angitha and sri are the same WhatsApp number** in `WHATSAPP_TEST`. Keep each group switched on
   under only one of them, or every answer goes out twice. angitha now shows **error**.
6. **`WHATSAPP_TEST_HUB` can't use WhatsApp** (403). In the gateway panel, register that database for
   the key or issue it a new key. Never link the same number in both databases.
7. **A group picks a company, not a warehouse.** A hub with two warehouses always uses the first one.

### Smaller fixes
8. **Confusing message:** after tapping an old poll button, a typed name was read as the answer to the
   current address question ("Sorry, I can't use *Sri*"). The logic is right; the wording could say what it expected.
9. **Test data in older tests:**
   - `TestBranchQuick.test_a_branch_with_quick_off_reaches_nobody` should clear the hub table.
   - `TestQeLink.test_a_pincode_is_served_by_his_areas` expects no `needPin` key in the answer.
   - Website tests that call `action_confirm` fail where `product_tracker` requires serials.
10. **Known bridge test failures** (STATUS §4, 8 of 189), including the 3 seen here. They are not from this session.

### Before going live
11. **Merge and push.** Everything is committed on branch `hubs-whatsapp-11nov`, not pushed: this
    session's work plus the other changes that were in the working tree (shop card placeholders, hub
    stock on the product page, Find from the address for branches). Fast-forward `main` to it and
    push when ready. `odoo_modules/storefront.zip` was left out on purpose.
12. **Live server:** upgrade `mart369_whatsapp_bridge` (19.0.1.7.0) and `sales_automation`
    (19.0.173.12.0) with the other modules in STATUS §5.
13. **Each hub company on live** needs payment methods on, accounting (journals, taxes), stock in its
    warehouse, and a delivery shop.
14. **Later (from STATUS):** online card payment and loyalty points for baskets from several hubs.

### Clean-up
15. Test databases still on this machine: **`qe_hub_test`** and **`wa_fix_test`**. Drop them when
    no longer needed. `qe_hub_base` was already dropped.
16. Database dumps in the session scratchpad (`hub.dump`, `wa.dump`) can be deleted.

### Side note
17. "**My Company has no street, town or pincode**" (Find from the address on a branch) means the
    branch's contact has no address. Add it in Contacts or use **Pick on map**. The repo has newer
    wording, so the server may need a module update.
