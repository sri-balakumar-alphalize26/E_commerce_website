# 369 Mart: what's still missing

A backlog of gaps between what the shop shows and what staff can control, plus common e-commerce features that don't exist yet. Tick an item off when it ships.

Audited 2026-09-29 across the storefront (`components/home`), the admin console (`components/admin`) and the Odoo modules (`odoo_modules/`).

## How to read this

The gaps fall into three kinds:

- **A. The shop shows made-up or ignored data.** Staff edit something and the shopper never sees it, or the shopper sees something invented. These are the most urgent, because they look as if they work.
- **B. The shop shows something staff can't edit.** It's drawn in the shop but hardcoded, or editable only deep in Odoo.
- **C. Common features that are missing entirely.**

The category logo was a type B gap. It's the first entry under **Done**.

## Done

- [x] **Category and sub-category logos.** Pick a built-in logo or upload and crop your own, in the console (Catalog → Categories) and the Odoo Catalogue desk. The size is shown as you add it: 18 × 18 px on a main category's pill, and a full tile for a sub-category. The pill, the home tile and the category-page circle follow the category. Screenshots are in `odoo_modules/mart369_catalog/static/description/category_logo_*.png`.

## A. The shop shows fake or ignored data (fix first)

- [ ] **1. The product page uses sample data.** Features, specs, dimensions and description edited by staff never show. The manufacturer, the dimensions and the reviews ("Anjali R.") are invented by `getDetails()`.
  - `components/home/productDetails.js`
  - `components/home/ProductDetail.jsx:274`
  - `components/admin/ProductPageSection.jsx:25` (says so)
- [ ] **2. Banners ignore their link and picture.** The banner hardcodes `href="#"`, blocks the click, and never draws `b.image`, although the console edits the link and Odoo stores the picture.
  - `components/home/Home.jsx:151-165`
- [ ] **3. Order tracking shows a made-up rider.** `riderFor()` hashes the order id into four hardcoded riders ("Arjun K.", …). The rider staff actually assign is never shown.
  - `components/home/orderState.js:69-75`
  - `components/home/OrderTrack.jsx:469,566`
  - Assignment: `components/admin/AdminOrders.jsx:455`
- [ ] **4. The rider tip is thrown away.** The page says "₹X tip sent to Arjun" and "100% goes to your rider", but the rating route doesn't store the tip.
  - `components/home/OrderTrack.jsx:262,299`
  - `odoo_modules/mart369_account/controllers/account_api.py:198-222`
- [ ] **5. The refund promise is wrong.** The shop promises a refund "to your original payment method in 3–5 days", but refunds only go to the 369 Wallet.
  - `components/home/Account.jsx:313`
  - `components/home/OrderTrack.jsx:422,488`
  - `odoo_modules/mart369_order/models/order_refund.py`
- [ ] **6. Two free-delivery amounts can disagree.** The home page's "add ₹X for free delivery" nudge and the fee actually charged come from two different settings.
  - Nudge: `home_mode.free_delivery_at` (`components/admin/PageEditor.jsx:268`)
  - Charge: `delivery_rule.free_above` (`components/admin/AdminDelivery.jsx:160`)
- [ ] **7. "Notify me" is fake.** It's local state and a toast; nothing is saved and nobody is notified. Customers are also offered Email/SMS alert switches, but email and SMS alerts are not set up.
  - `components/home/shared.jsx:361`
  - `components/home/ProductDetail.jsx:343`
  - `components/home/AccountExtras.jsx:760-767`
  - `components/admin/AdminMore.jsx:1224`

## B. The shop shows it, staff can't edit it

- [ ] **8. Footer, About, FAQ and legal pages.** Terms of use, Privacy, Shipping policy and Grievance redressal are dead links. The FAQ and About text are hardcoded. Indian e-commerce rules require these pages, including a grievance officer.
  - `components/home/Browse.jsx:932-956`
  - `components/home/Account.jsx:309,359-376`
- [ ] **9. Store logo, favicon, social links and app-store links** are hardcoded.
  - `components/home/Browse.jsx:945`
  - `components/home/Account.jsx:348`
  - `app/icon.svg`
- [ ] **10. Search-box placeholder words** are a fixed list, not tied to the Trending searches staff already manage.
  - `components/home/shared.jsx:16` (`SEARCH_WORDS`)
  - `components/admin/AdminSearches.jsx`
- [ ] **11. Category order.** The console has no drag-to-reorder; the only way is Odoo's sequence field.
  - `components/admin/AdminCategories.jsx`
- [ ] **12. Banner and home-tile pictures** can only be uploaded in Odoo. The console says "images are still Odoo's". The new logo cropper can be reused here.
  - `components/admin/PageEditor.jsx:19`
  - `components/admin/LogoField.jsx`
- [ ] **13. The return window is set in two places.** The shop hardcodes 7 days, separately from the server's `mart369_support.return_days` setting, which staff can't see.
  - `components/home/orderState.js:32`
- [ ] **14. Other hardcoded lists**, each of which should come from the shop:
  - cancel reasons and return reasons (`components/home/OrderTrack.jsx:202,312`)
  - review tags (`components/home/AccountExtras.jsx:581-582`)
  - the "We accept" payment list, which doesn't follow the payment switches (`components/home/Browse.jsx`)
  - the bot's and agent's names, "Mitra" and "Anjali" (`components/home/support.js:21-22`)
  - the express hub journey, "Bengaluru hub → Kochi hub" (`components/home/OrderTrack.jsx:149-155`)
  - the referral goal (`components/home/accountStore.js:43`)
  - the site title and description (`app/layout.jsx:4`)
  - scratch-card prize amounts, hardcoded in Python (`odoo_modules/mart369_account/models/scratch.py:32`)

## C. Missing features

- [ ] **15. Product variants / pack sizes.** The storefront's `PackSizes` component exists, but the server always sends `variants: []`.
  - `odoo_modules/mart369_product/models/product_page.py:56`
- [ ] **16. SEO.** No per-product or per-category title and description, no sitemap, no robots file, no OG share images. The product page is fully client-rendered, with no `generateMetadata`.
  - `app/layout.jsx:4`
  - `app/product/[id]/page.jsx`
- [ ] **17. Product publish/unpublish switch** in the console. Today there's only a Live/Hidden label.
  - `components/admin/AdminCatalog.jsx:276`
- [ ] **18. Announcement bar**, e.g. "Free delivery above ₹499 today".
- [ ] **19. Search synonyms**, e.g. "mouse" = "mice", "ssd" = "storage".
- [ ] **20. CSV export** of orders and products from the console (only Odoo's own export exists).
- [ ] **21. Dashboard sales figures:** revenue trend, top products, sales by category. The dashboard shows orders, customers and delivery only.
  - `components/admin/AdminApp.jsx:235-330`
- [ ] **22. Block a customer account.** Today staff can only switch off cash on delivery.
  - `components/admin/AdminCatalog.jsx:762`
- [ ] **23. PWA manifest and app icons**, so the shop can be added to a phone's home screen properly.
- [ ] **24. Image alt text** for product, banner and category pictures.

## Housekeeping

- The dashboard still imports sample data it never uses (`components/admin/AdminApp.jsx:17-19`, `components/admin/adminData.js`).
- `RidersSection` is dead code built on fake riders (`components/admin/AdminCatalog.jsx:1029`).

## How each item gets done

Each item follows the pattern that worked for the category logos:

1. Odoo model fields, plus the admin allowlist, then the serializer, then the storefront, then both consoles (web and Odoo desk).
2. A test in the owning module, run through PowerShell and checked for more than 0 tests.
3. `-u` on `sparenix_test`, then a restart of 8069 and the 8097 dev server.
4. A Playwright + Edge check of the console flow and of the shop page it feeds, then cleanup of the test data.
5. Screenshots saved in the module's `static/description/`.
