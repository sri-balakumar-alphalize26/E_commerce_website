# WhatsApp Sales Automation for Odoo 19 - full flow, module by module

Package of 26 September 2026. Companion to `User_Manual.pdf` and `README.md`.
This file walks the **complete flow** from the first WhatsApp message to the delivered order and shows,
for every step, **which module does it**, what the customer / vendor / shop sees, and where it is configured.

Modules in this package (all in `Odoo_Modules.zip`):

| # | Module | Version | Role in the flow |
|---|---|---|---|
| 1 | `whatsapp_gateway` | 19.0.3.1.1 | Talks to the WhatsApp server (Evolution API + control panel). Sends text, pictures, polls, documents. Receives every incoming message on the webhook. Shows the authorized number and sender e-mail the panel fixed for this database. |
| 2 | `whatsapp_employee_tracker` | 19.0.1.2.1 | Employee sessions, conversations, the auto-reply engine that turns a closed deal into an order, quality scores. |
| 3 | `sales_automation` | 19.0.173.4.3 | The brain: reads group messages, classifies them, finds the product, asks vendors, quotes, bargains, takes the quantity, creates the order, sends sign / pay links, menus, address, human takeover. |
| 4 | `sales_automation_confirm` | 19.0.2.4.3 | Catalogue tap-menu (NEW ORDER), attribute questions (brand / capacity / …), exact variant, product picture search, the confirmation page with ACCEPT / REJECT, click log. |
| 5 | `sales_automation_wechat` | 19.0.1.7.4 | Vendors on WeChat through the bridge PC: numbered steps, bilingual texts, vendor answer page, relay by hand. |
| 6 | `sales_automation_store` | 19.0.6.1.0 | The shop counter: alarm screen, accept + pack orders, pickup code, enquiry desk (pick vendors), WeChat relay rows. |
| 7 | `sales_automation_delivery` | 19.0.16.3.1 | Delivery jobs, rider link / app, OTP delivery code, live tracking page with map, delivery queues and analysis. |
| 8 | `pos_loyalty_card` + `sale_loyalty_card` | 19.0.1.78.0 / 19.0.1.3.0 | One loyalty ledger for POS and sales, cards, rules, redeem wizard. |
| 9 | `sales_automation_loyalty` | 19.0.1.4.0 | USE POINTS / PAY FULL on WhatsApp before the payment link, points line after payment. |
| 10 | `sales_automation_insights` | 19.0.3.2.1 | Customer and vendor 1-5 star ratings, dashboards, profiles, compare, chat log, conduct filter. |
| 11 | `sales_automation_manual` | 19.0.1.2.0 | The user manual inside Odoo: "📖 User Manual" menu under Sales Automation, Store, Delivery, Insights. Installing this one installs 1-7; loyalty (8-10) is optional and separate. |

Outside Odoo: the **WhatsApp server** (`WhatsApp_Server.zip`: Evolution API on port 8085 + control panel on 8086)
and the optional **WeChat bridge PC** (`WeChat_Bridge_DubaiPC.zip`, WeChat 3.9 for Windows).

---

## 0. The picture in one screen

```
Customer in the shop's WhatsApp group
        │  "hi"  /  "laptop battery"  /  taps a poll
        ▼
WhatsApp ──► Evolution API (:8085) ──► Control panel (:8086) ──► Odoo  /whatsapp/webhook   [whatsapp_gateway]
                                                                        │
                                                                        ▼
                                                   sa.group.request  (one row per enquiry)   [sales_automation]
                                                                        │
      ┌──────────────── menus / catalogue / attributes / picture / confirmation page ────────┐   [sales_automation_confirm]
      │                                                                                        │
      ▼                                                                                        ▼
  in stock ──► price ──► bargain ──► quantity ──► order summary ──► sale.order            not in stock ──► vendors
                                                                        │                       │  WhatsApp poll + page   [sales_automation]
                                                                        │                       │  WeChat 1/2 + page      [sales_automation_wechat]
                                                                        │                       │  shop picks vendors     [sales_automation_store]
                                                                        │                       └──► cheapest quote + margin ──► price
                                                                        ▼
              name ──► address ──► details read-back (phone) YES ──► sign link ──► signed ──► payment link (in stock)
                                   [sales_automation, in the group]                         │  or: shop accepts (counter) ──► payment link (sourced)
                                                                       loyalty USE POINTS? ─┘ [sales_automation_store] [sales_automation_loyalty] ──► paid
                                                                        │
                                                                        ▼
                                   delivery job ──► rider offered ──► picked up ──► delivered with OTP ──► tracking page
                                                                 [sales_automation_delivery]
                                                                        │
                                                                        ▼
                                   ratings, dashboards, remarks, click log                                  [sales_automation_insights]
```

---

## 1. Message arrives (whatsapp_gateway → sales_automation)

| Step | What happens | Module | Where to look |
|---|---|---|---|
| 1.1 | The customer's phone sends a message in the shop's WhatsApp group. | WhatsApp | - |
| 1.2 | Evolution API receives it and posts it to the control panel; the panel checks the key + server + database and forwards it to Odoo's webhook. | WhatsApp server | Panel ▸ Servers / Databases |
| 1.3 | `whatsapp_gateway` stores the message (`whatsapp.message`) with sender, group, poll vote, media. Group messages are only kept when the group is configured. | whatsapp_gateway | WhatsApp ▸ Messages |
| 1.4 | `sales_automation` picks it up in `_on_group_message`: is this group a **customer group**? which **employee session** answers here? is the sender opted out? is there an open enquiry for this person? | sales_automation | Sales Automation ▸ Configuration ▸ WhatsApp Groups |
| 1.5 | Conduct filter: abusive words → the message is deleted in WhatsApp (number must be group admin), the sender is warned, a remark lowers their rating. | sales_automation_insights | AI Settings ▸ word lists; Insights ▸ Remarks |
| 1.6 | Typed-answer hooks run first: a typed attribute value (after "TYPE IT"), a typed part model, a typed NOT LISTED product. | sales_automation_confirm | - |
| 1.7 | Otherwise the message is routed: poll tap → `_sa_answer_poll`; text → greeting / cancel / chatter / **enquiry** through the AI classifier. | sales_automation | AI Settings (Gemini key) |

**Enquiry states** (`sa.group.request.state`): `new` → `finding` (guided finder) → `awaiting_confirm` (page out) → `sourcing` (vendors asked) / `awaiting_vendor_pick` (desk) → `quoted` → `negotiating` → `awaiting_qty` → `awaiting_order_confirm` (summary) → `order_created` → `answered`. Side exits: `handed_off` (human takeover), `dropped` (cancelled / stale), `not_product` (chatter).

---

## 2. Greeting and the main menu (sales_automation)

| Step | Customer sees | Module |
|---|---|---|
| 2.1 | `hi` / `hello` / `menu` → **"Hi 👋 welcome back! What would you like to do?"** poll: 📦 MY ORDERS · 🆕 NEW ORDER · ➕ MORE | sales_automation |
| 2.2 | MY ORDERS → Pending orders (sign / pay / cancel each) and Delivery orders (track). | sales_automation + sales_automation_delivery |
| 2.3 | MORE → 🎁 My loyalty points · 👤 My details · 📍 Change address · BACK. | sales_automation (+ loyalty) |
| 2.4 | Every list ends with BACK and 🏠 MAIN MENU; after a finished order also 🙏 THAT'S ALL, THANK YOU. A second tap on the same poll is refused politely. | sales_automation |

The menu is stored per enquiry in `sa_menu_json` (items with kind / level / target), so a tap is always read against the poll it belongs to.

---

## 3. NEW ORDER: the catalogue as tap lists (sales_automation_confirm)

| Step | Customer sees | Where configured |
|---|---|---|
| 3.1 | 🆕 NEW ORDER → **categories** poll: Mobile · Laptop · Computer · Computer Spare Parts · Laptop Parts · Mobile Parts · Printers · Printer Spare Parts · ✏️ NOT LISTED · 🏠 MAIN MENU | Product category form: "WhatsApp menu order", "Hide from the WhatsApp menu" |
| 3.2 | A category → its sub-categories, or its **products** six at a time (➡️ MORE, BACK, MAIN MENU). | Products ▸ Products (active, sale OK, in that category) |
| 3.3 | A product tap → `_sa_menu_start_enquiry(product)` → straight into the attribute questions (section 5) or the confirmation (section 6). | - |
| 3.4 | ✏️ NOT LISTED → "Type what you need" → the typed text goes through the normal understanding (section 4). | - |

WhatsApp polls take at most 10 options, so lists are paged.

---

## 4. A typed request (sales_automation + sales_automation_confirm)

| Step | What happens | Module |
|---|---|---|
| 4.1 | The AI classifier (Gemini) says: enquiry or not, product words, quantity, specificity. Generic words ("computer parts") are not price-checked; the customer is asked to be specific. | sales_automation |
| 4.2 | Catalogue match by name / synonyms / brand words → **one product** → section 5 / 6. | sales_automation |
| 4.3 | No clear match → the **guided finder**: type → brand → model as polls, each with "Not listed" to type. | sales_automation (Guided Finder settings) |
| 4.4 | **Parts flow**: "laptop battery", "charger", "screen", "ink" … → the brand is asked; a typed brand without a model gets one more question "Which model is it for?" → item = "Dell Inspiron 15 3520 Laptop Battery". | sales_automation_confirm (`sa_finder_confirm`) |
| 4.5 | Unlisted items (no product in Odoo) are still confirmed on the page (section 6) with the customer's own words, then sourced from vendors of the closest category. | sales_automation_confirm + sales_automation |

---

## 5. Attributes: the exact item (sales_automation_confirm)

| Step | Customer sees | Notes |
|---|---|---|
| 5.1 | For each attribute of the product with more than one value, one poll: **"📦 Hard Disk 3.5 inch - which brand?"** WD Blue · Seagate BarraCuda · Toshiba P300 · ✏️ TYPE IT / OTHER | Order of values = attribute value sequence |
| 5.2 | Next attribute: **which capacity?** 1TB · 2TB · 4TB · ✏️ TYPE IT / OTHER | Only attributes still open are asked |
| 5.3 | ✏️ TYPE IT / OTHER → "Type the capacity you need (for example: 1TB, 2TB, 4TB) - or reply ANY". The typed text is read against **all** open attributes at once: "seagate 2 tb" answers brand + capacity; "512 navy" → 512GB + Navy; "2k" → 2K; a bare number matches the value with that number. | `_sa_attr_typed` |
| 5.4 | A value not in the list but with a unit ("64gb", "1000w") is kept in the customer's own words as a note; that attribute is closed and the note becomes part of the item name. "any / skip / not sure" skips the question. | `sa_attr_notes` |
| 5.5 | All answered → the matching **variant** (`product.product`) is stored on the enquiry (`sa_variant_id`); its exact name ("Seagate BarraCuda 2TB Hard Disk 3.5 inch") is used everywhere after this: picture search, page, vendor ask, order line. | `_sa_attr_done` |

Configured on the product form ▸ Attributes & Variants. Products without attributes skip this section.

---

## 6. The confirmation: picture + page (sales_automation_confirm)

| Step | What happens | Who sees it |
|---|---|---|
| 6.1 | `_sa_confirm_picture`: the product / variant picture in Odoo → else automatic search by the exact name in a headless Chromium (Google Images, then Bing when Google shows its robot check), results ranked (chosen values +, sibling values / collages −), verified as real JPEG/PNG, saved on the product; 2 extra shots kept → else Google Custom Search (key optional) → Openverse → Wikipedia → Wikimedia → Gemini-found page picture → Gemini drawing → "No photo yet". | server |
| 6.2 | A **`sa.confirm.link`** row is created for this enquiry + this person (deterministic token = HMAC of enquiry, kind, channel, phone). | Sales Automation ▸ Enquiries ▸ Confirmation Links |
| 6.3 | ONE message: the picture with caption **"📦 Seagate BarraCuda 2TB Hard Disk 3.5 inch / Please check the photo and details, then press ACCEPT: / https://…/scoped_app/c?db=…&t=… / Ref K7"**. State `awaiting_confirm`. Nothing is priced, no vendor is asked yet. | customer |
| 6.4 | The link opens the **page**: main picture, strip of up to 3 pictures (tap to switch, tap to zoom), details table (product, reference, quantity, chosen brand / capacity / colour, code, barcode, category, price when known, weight, description), then **ACCEPT** / **REJECT**. A page opened before the server finished shows "Loading…" and retries by itself. | customer's phone browser |
| 6.5 | **ACCEPT** (first press) → `decided='accept'`, click row with IP + browser, chat gets "✅ Confirmed - getting your price", flow continues to section 7. **REJECT** → "Noted - checking what you asked for instead" → back to the finder / a new match. Later presses are refused and logged (`again`). | customer + click log |
| 6.6 | A typed "yes" while the link is out → "please press ACCEPT on the page" (once). After `confirm_remind_minutes` (10) one reminder. The stale timer closes it after that. | customer |
| 6.7 | Every open / accept / reject / again is a **`sa.link.click`** row: who (identity the link was sent to), account, time, IP, browser. Shown on the enquiry form, the counter's enquiry detail ("Confirmation page" block), Insights profiles, and Sales Automation ▸ Enquiries ▸ Link Clicks. | shop |

Settings: Sales Automation ▸ Configuration ▸ **Product Confirmation** (customers on/off, vendors on/off, picture fetching, browser search paths, Google CSE key, reminder minutes, "Try it" search box).

---

## 7. Price (sales_automation)

| Case | What happens | Customer sees |
|---|---|---|
| 7.1 In stock | Stock rule (26 Sep): a product not tracked in stock is never short; a tracked one is measured on free stock (on hand minus reserved) in the order's company, on the exact variant when one was picked. The shop price is quoted at once. State `quoted`. | **"💰 X: 30.00 each"** poll ACCEPT · BETTER PRICE · CANCEL |
| 7.2 Not in stock | If the product's "Sell when Out-of-Stock" is off (website_sale_stock), the customer is told "out of stock" / "only N left" and the enquiry drops as `unavailable`; such products are also left out of NEW ORDER and typed search. Otherwise state `sourcing` (or `awaiting_vendor_pick`), "Let me check that for you ⏳", vendors are asked (section 8), cheapest quote + `margin_percent` becomes the price. Stock is read again, fresh, right before the order is created. | same poll after the window |
| 7.3 No vendor answered | The enquiry parks for the shop: counter screen card "needs a price" + tokened price link; the shop types a price. | "Still checking - a moment" |
| 7.4 Vendor price ≠ product page price | Product already has a sale price and vendor cost + margin differs from it (tolerance in AI Settings): the enquiry parks on the counter screen only - card "Two prices - approve one" (page price / vendor price / type another), each confirmed once more; then the customer is quoted that price and the order + invoice carry it. The product page is never changed. | "Still checking on … ⏳" |
| 7.4 Shop picks vendors (optional) | With "shop picks vendors" on, out-of-stock enquiries wait in Store ▸ Enquiries for a person to tick the vendors; the timeout auto-sends. | - |

---

## 8. Vendors (sales_automation, sales_automation_confirm, sales_automation_wechat, sales_automation_store)

Vendors come from the **category** (Vendors tab) and the product's Purchase tab. Each vendor card has two ticks, WhatsApp and WeChat, and a "WeChat contact remark".

### 8a. WhatsApp vendor

| Step | Vendor sees | Module |
|---|---|---|
| 8a.1 | Picture + caption **"🔎 Price check #K7 / Seagate BarraCuda 2TB Hard Disk 3.5 inch x 2 / See the details and press ACCEPT if you have this exact product: / https://…"** (bilingual page, never the customer's price or name). | sales_automation_confirm (`_sa_ask_vendor_confirm`) |
| 8a.2 | ACCEPT on the page = "I have it" → **"👍 Good - what is your best price?"**; REJECT = no stock. Typed YES / NO / "have it" / "no stock" still work. | sales_automation_confirm → sales_automation |
| 8a.3 | Vendor types **"450"** or **"450 3 days"** (with `#K7` when several checks are open) → `sa.vendor.quote` row. | sales_automation |
| 8a.4 | Window closes → cheapest wins → winner thanked, others told. | sales_automation |
| 8a.5 | Vendor WhatsApp **groups** per category get the same price check as one post. | sales_automation |

### 8b. WeChat vendor (through the bridge PC)

| Step | Vendor sees | Module |
|---|---|---|
| 8b.1 | An outbox row (`sa.wechat.message`, with `image_url` + `wx_confirm_link_id`) is pulled by the bridge (`/sa/wechat/outbox`, headers X-SA-Key + X-Odoo-Database). The bridge sends the picture, then the text. | sales_automation_wechat + bridge |
| 8b.2 | **"Price check #K7 / Seagate BarraCuda 2TB … / Qty: 2 / Do you have it? / 1 = In stock / 2 = No stock / 询价 #K7 … 1 = 有货 / 2 = 没有 / 👉 Confirm / 确认: https://…"** | sales_automation_wechat (+ confirm) |
| 8b.3 | Vendor taps the page or replies **1 / 2** (or "I have it", "没有") → step **price**: "45" or "45 3" → step **days**: 1 = ready, 2 = 1-3 days, 3 = 4-7 days, 4 = more than 7 days. | `_sa_answer_step`, `_sa_answer_days` |
| 8b.4 | Thanks ends with **"Our store manager will contact you soon. Thank you! / 我们的店长会尽快联系您。谢谢！"** | sales_automation_wechat |
| 8b.5 | Bridge down longer than `wechat_stale_minutes` → counter screen shows **"WeChat - relay by hand"**: Copy, Sent by hand, type the vendor's price. | sales_automation_store + wechat |

Bridge status: Sales Automation ▸ Configuration ▸ Connections. Key: Configuration ▸ WeChat Bridge ▸ New key → `config.json` on the bridge PC.

---

## 9. Bargaining, quantity, order (sales_automation)

| Step | Customer sees | Rules |
|---|---|---|
| 9.1 | BETTER PRICE → the price steps down by `bargain_step_percent`, at most `bargain_max_steps` times, never below `min_margin_percent`. State `negotiating`. | Configuration ▸ Bargaining |
| 9.2 | Products with **quantity ranges** (product form ▸ WhatsApp Bargaining, e.g. 5-9 pcs 2 %, 10-20 pcs 5 %) ask the quantity first; BETTER PRICE appears only inside a range; the range discount is applied once. | product form |
| 9.3 | ACCEPT → **"How many?"** (poll 1 · 2 · 3 · 5 · 10 · TYPE) or the typed number. State `awaiting_qty`. | - |
| 9.4 | **"📋 Order summary / Seagate BarraCuda 2TB … / 2 x 30.00 / Total: 60.00"** poll CONFIRM · CHANGE. CHANGE → CHANGE QUANTITY · BETTER PRICE · KEEP · CANCEL. | state `awaiting_order_confirm` |
| 9.5 | CONFIRM → **sale.order** in the employee session's company, the **exact variant** on the line, the WhatsApp customer as partner (created from the phone if new), delivery address from the last confirmed address or asked now. "✅ Order S00123 created". State `order_created`. | Sales ▸ Orders |

---

## 10. Sign, accept, pay (sales_automation, sales_automation_store, sales_automation_loyalty)

| Step | What happens | Module |
|---|---|---|
| 10.0 | **Every order, in the group (19.0.173.4.7):** "👤 What name should the quotation be in?" → "🏠 What is your full address?" → pincode (only where the country issues one) → **"📋 Please check your details"** read-back with name, address, postcode and 📱 phone → **YES** (NO restarts, CANCEL stops). The customer contact is written with these details, so the quotation is never in the name of a phone number. | sales_automation |
| 10.1 | Details confirmed → **"✍️ Please sign your order"** with the portal sign link (`/my/orders/<id>?access_token=…` through the doorway). The signature confirms the order. | sales_automation |
| 10.2 | Signed: goods **in stock** → the payment link is posted at once (10.4). Goods **to be sourced** → "we are arranging the goods"; the payment link follows when the shop accepts them (10.3). | sales_automation |
| 10.3 | The order appears on the **counter screen** (Store ▸ New Orders / Shop Queue) with an alarm. **Accept** → customer gets "approved" and, for unpaid orders, the payment link. **Ready** (packed, pickup code shown) → the rider is paged. | sales_automation_store |
| 10.4 | Before the payment link: **"🎁 You have N points (worth X). Use them on order #S00123?"** USE POINTS · PAY FULL (only when the customer has points). | sales_automation_loyalty |
| 10.5 | **Payment link**: quotation → portal page Pay; confirmed order → Odoo's payment link wizard URL (`/my/orders/<id>?…&payment_amount=…`). Providers: whatever is enabled (Demo in test). | sales_automation |
| 10.6 | Paid → "✅ Payment received" + **"🎁 You earned N points · balance B"** + poll TRACK THIS ORDER · MY ORDERS · MAIN MENU · THAT'S ALL. | sales_automation + loyalty |

---

## 11. Delivery (sales_automation_delivery)

| Step | Who | What |
|---|---|---|
| 11.1 | system | A paid (or accepted cash-on-delivery) order's **stock.picking** becomes a delivery job (Delivery ▸ To Dispatch). Same Day / Express are separate queues. |
| 11.0 | shop | **Delivery optional (1 Oct):** Delivery ▸ Configuration ▸ Delivery Settings ▸ *WhatsApp order flow ends at* = Order confirmed / Invoice sent / Payment received / Delivered. Before *Delivered* no job is raised (the picking is validated by hand), the pay link goes out at the signature, the paid text has no delivery line and the paid menu has no TRACK. Cards show the sale order number and a live Paid / Unpaid badge; newest day first; times follow the browser's clock (the user's tz is set to the browser's zone on login). |
| 11.0b | shop | **Call a Rider (3 Oct):** Packed leaves the job at Ready; **Call a Rider** (job form / Shop Queue / `POST /api/sa/jobs/{id}/call_rider`) = the rider the counter picks, else the nearest free on-duty rider to the shop's map pin (Haversine, 5 km radius, longest idle on a near tie, `random.choice` on an exact tie). One rider at a time with a 60 s offer; timeout or decline calls the next (max 5). Riders go on duty from the app with GPS (`/api/delivery/duty`), reverse-geocoded to an area name; fleet kanban free / busy / off; FCM push to the one chosen rider. `models/sa_dispatch.py`. Mode in Delivery Settings (`call_rider_mode`): ask / auto / auto_radius (never outside the km radius) / manual (the counter ticks riders in a table, multi-select; called one at a time, nobody else). |
| 11.2 | rider | Offered by a **tokened link** (`/wa/delivery/<id>?token=…`) or the rider app (phone-code login, Delivery ▸ App Sessions). Accept → Picked up → Out for delivery. |
| 11.3 | customer | **"🚚 Your order is on the way"** + tracking link (`/wa/track/<id>?token=…`): timeline + live map from the rider's position pings + the **delivery code** (OTP, private chat). |
| 11.4 | rider | **Delivered** only with the customer's code. Cash collected is recorded on the job. Failed attempts go to Delivery ▸ Failed with the reason. |
| 11.5 | shop | Delivery ▸ Delivered / All, Riders & Couriers, Shops, Delivery Codes, Delivery Analysis, Delivery Settings. |

---

## 12. After the sale (sales_automation_insights)

| What | Where |
|---|---|
| Automatic **1-5 ★ ratings** nightly from behaviour only: customers (reply speed, conversion, completion, cancellations, bargaining, payment), vendors (reply rate and speed, win rate, promise kept, price, conduct). Tiers Best / Better / Normal / Poor / New. | Insights ▸ Customer Dashboard / Vendor Dashboard |
| **Profile**: orders with progress, enquiries with the full thread, timeline, heatmap, logs incl. confirmation-page clicks, WhatsApp chat log by day. Tick 2-4 rows to **compare**. | click a row |
| **Remarks** from the conduct filter (FLAGGED, deleted message, warning). | Insights ▸ Configuration ▸ Remarks |

---

## 13. Human takeover and the counter (sales_automation, sales_automation_store)

| Situation | What to do |
|---|---|
| A customer needs a person | Sales Automation ▸ Configuration ▸ Human Takeover: staff take the conversation (bot silent), hand it back when done. |
| An enquiry is stuck | Store ▸ Shop Queue: stalled cards show the clocks; open the detail (vendors table, customer thread, supplier thread, confirmation page block). |
| No vendor answered | Type the price on the card or through the tokened price link. |
| Vendor price differs from the product page | Store ▸ Enquiries: Use page price / Use vendor price / Type another, then confirm. |
| Alarm sound | On by default from the first tap on the screen (browser rule); the "Turn on the alarm" button appears only if the browser blocked audio. |
| Out-of-stock and "shop picks vendors" on | Store ▸ Enquiries: tick vendors, Send (auto-sends after the timeout). |
| Order to hand over | Store ▸ New Orders: Accept → Ready (pickup code) → rider paged. |

---

## 14. Setup checklist (install order)

1. Copy all 12 folders from `Odoo_Modules.zip/odoo_addons/` into the Odoo addons directory, restart Odoo, Update Apps List, install **`sales_automation_manual`** (pulls everything).
2. Python for Odoo: `requests`, `Pillow`, `python-barcode`. A second Python with `playwright` + `playwright install chromium` for picture search (paths on the Product Confirmation settings page).
3. WhatsApp server (`WhatsApp_Server.zip`): Node 20, PostgreSQL database `evolution` (own role), `.env` from `env.example`, `npm install`, `npx prisma generate --schema prisma\postgresql-schema.prisma`, `npm run db:deploy:win`, `npm run build`, `node dist/main` (8085); panel: `npm install`, `.env`, `node server.js` (8086), then `node reset_login.js --admin "password"`. As platform administrator: vendor (+ login) → server → database (+ client login) → number (authorized phone, assigned to one or many databases) → scan the QR with that phone → paste the database's setup key into Odoo. Roles: admin sees all; vendor sees its databases/numbers and sets e-mail accounts + client passwords; client sees one database. Wrong phone on the QR = logged out and refused.
4. Odoo: WhatsApp ▸ Configuration ▸ Sessions: gateway URL `http://127.0.0.1:8086` + the key. Sales Automation ▸ Configuration ▸ WhatsApp Groups: the customer group + the employee session. AI Settings: Gemini key.
5. Public address: system parameter `sa_delivery.public_base_url` = the https address (Cloudflare named tunnel or domain). **Never change `web.base.url`** (the panel key is registered against it).
6. Catalogue: categories (menu order, vendors per category), products with pictures, prices and attributes.
7. Vendors: WhatsApp / WeChat ticks, phone, WeChat remark.
8. Optional WeChat PC: `WeChat_Bridge_DubaiPC.zip`, WeChat 3.9.x, `config.json` (public address, database, key, bridge id), `install_wechat_bridge.bat` once, `start_wechat_bridge.bat`.
9. Open Store ▸ Shop Queue on the counter PC and turn on the alarm.
10. Delivery ▸ Configuration ▸ Delivery Settings ▸ **WhatsApp order flow ends at**: Delivered (full flow) or an earlier step when riders are not used.

---

## 15. Public links (all go through a database doorway so a cold phone lands on the right database)

| Link | Page | Module |
|---|---|---|
| `/scoped_app/c?db=…&t=…` → `/wa/confirm/<token>` (+ `/image/<n>`, POST `/accept`, `/reject`) | Product confirmation page | sales_automation_confirm |
| `/scoped_app/wx?db=…&t=…` → `/sa/wx/<token>` | WeChat vendor answer page | sales_automation_wechat |
| `/scoped_app/wa-link?db=…&to=…` | Doorway for `/wa/pay`, `/wa/track`, `/wa/delivery`, `/wa/quote`, `/my/orders/…`, `/payment/pay` | sales_automation |
| `/wa/delivery/<id>?token=…`, `/wa/track/<id>?token=…` | Rider job page, customer tracking page | sales_automation_delivery |
| `/sa/wechat/heartbeat`, `outbox`, `sent`, `contacts`, `inbound` | Bridge API (X-SA-Key, X-Odoo-Database) | sales_automation_wechat |
| `/sa/manual`, `/sa/manual/pdf` | The manual (logged-in users) | sales_automation_manual |

---

## 16. Daily checks and troubleshooting

| Check / symptom | Where | Fix |
|---|---|---|
| Gateway paired, bridge alive | Sales Automation ▸ Configuration ▸ Connections | Re-scan QR in the panel; restart the bridge window |
| Bot silent in the group | Group not in WhatsApp Groups; panel 403 "registered to X not Y" (web.base.url mismatch); Evolution / panel not running | Fix the row; start `node dist/main` and `node server.js` |
| Links "Not Found" / unreachable | Quick tunnel changed after a restart | New hostname into `sa_delivery.public_base_url` and the bridge `config.json` |
| Page "Loading…" | Server still fetching pictures | It retries by itself for a minute |
| Wrong picture | No product photo, search guess | Put the right photo on the product / variant |
| Store / Enquiries screen "Oops! Invalid props" | Only in debug mode with store < 19.0.6.1.0 | Upgrade the store module (fixed) |
| "quota exceeded" from Gemini | Free tier used up | Wait for the daily reset or a paid key |
| Vendor reply hit the wrong enquiry | Several open checks, no `#REF` | Ask vendors to prefix `#REF`; the newest open check is assumed |
| WeChat vendor got nothing | WeChat 4.x on the PC, wrong remark, stale address | WeChat 3.9.12, remark = Odoo's, config.json |

---

## 17. Test files and working copies (reference server)

Rolled-back shell tests (mocked senders, gateway pointed at a dead port): `test_confirm.py` (62), `test_wechat_steps.py` (28), `test_wechat.py` (22) in `D:\mydata\sa_working_copies\scripts`. Working copies of every module, the manual source (`scripts\manual\User_Manual.html`) and the package builder (`make_package.py`) are in `D:\mydata\sa_working_copies`. Deploy scripts run elevated (`Start-Process -Verb RunAs`) and never delete a live module folder.
