# 369 Mart module user manuals: progress

- **Claude Code session ID:** `c31768f3-143a-4ff9-a148-5cf485215514`
- **Stopped on:** 2026-10-12, on request. Work stopped partway; 14 of 19 manuals are written.

## What was asked
- One user manual for each of the 19 modules in `odoo_modules\`, saved in this folder.
- Same UI as the "369ai User Manual Template" artifact: https://claude.ai/artifact/R661ecJXX9FPEPqsd15j4m
- Decisions taken along the way:
  - **PDF + HTML** for each module.
  - Short (1–2 page) manuals for the umbrella and sample-data modules.
  - Written for store admins, staff **and office employees**: plain words, with a "Words you'll see" table in each manual.
  - **Screenshots come only from each module's own `static\description\` folder.** Modules without images get text-only manuals.
  - No test server was used.

## Status

| Module | Manual | Pages | Screenshots | State |
|---|---|---|---|---|
| mart369 | 369_Mart_User_Manual | 5 | 1 | Done |
| mart369_all | 369_Mart_Suite_User_Manual | 2 | 0 (module has none) | Done |
| mart369_auth | 369_Mart_Sign_In_User_Manual | 10 | 9 | Done |
| mart369_address | 369_Mart_Delivery_Addresses_User_Manual | 9 | 10 | Done |
| mart369_cart | 369_Mart_Delivery_and_Pricing_User_Manual | 14 | 13 | Done |
| mart369_catalog | 369_Mart_Catalog_User_Manual | 14 | 13 | Done |
| mart369_product | 369_Mart_Product_Page_User_Manual | 14 | 12 | Done |
| mart369_home | 369_Mart_Home_Page_User_Manual | 10 | 5 | Done |
| mart369_pages | 369_Mart_Pages_User_Manual | 6 | 0 (module has none) | Done |
| mart369_order | 369_Mart_Orders_User_Manual | 18 | 18 | Done |
| mart369_account | 369_Mart_Account_User_Manual | 12 | 12 | Done |
| mart369_support | 369_Mart_Support_User_Manual | 8 | 6 | Done |
| mart369_whatsapp_bridge | 369_Mart_WhatsApp_Bridge_User_Manual | 7 | 0 (module has none) | Done |
| mart369_parts_demo | 369_Mart_Sample_Catalogue_Computer_Parts_User_Manual | — | 0 (module has none) | HTML only: **PDF not rendered yet** |
| mart369_loyalty | — | — | — | **Not started** |
| mart369_payment | — | — | — | **Not started** |
| mart369_roles | — | — | — | **Not started** |
| mart369_store_board | — | — | — | **Not started** |
| pos_loyalty_card | — | — | — | **Not started** |

**Checks on the 14 written manuals:**
- Every file is complete.
- No `{{placeholders}}` are left.
- The word "Odoo" does not appear in the text.

**Still to do:** a page-by-page visual review of every PDF. The writers were stopped while checking pages, so a few manuals may still have layout issues: a heading left at the foot of a page, or a large figure.

## What is left
1. Render the missing PDF: `node _tools\render.js "<this folder>" mart369_parts_demo`
2. Write the five missing manuals, following `_tools\BRIEF.md`. Notes for each:
   - **mart369_loyalty** (no screenshots):
     - Points are earned at a chosen step, by default **Delivered**.
     - Points are spent at checkout within the points rule: once a day, with a minimum and a maximum share.
     - Points are given back on cancel or return.
     - A loyalty card is made automatically on the first order.
     - The "Points are earned when" setting has no backend screen; it is set in the staff console.
   - **mart369_payment** (3 screenshots):
     - The Payments desk and the Wallets desk.
     - The **Cash collected** button.
     - The 369 Wallet: limit 10,000, minimum top-up 10.
     - **Store → Settings**, which has the tabs Store, Payments, Customers, Orders, Reviews, Alerts.
     - The cash-on-delivery limit.
   - **mart369_roles** (no screenshots):
     - The roles Owner, Manager and Packer, plus the Accountant and Rider ticks.
     - The **Staff & roles** screen (Owner only) and **Invite staff**.
     - The Seller role grants nothing yet.
   - **mart369_store_board** (5 screenshots):
     - The Counter (New / Quick / Express tabs, and Counter ⇄ All orders).
     - The buttons Accept, Goods arrived, Packed - call the rider, Put back.
     - The alarm rings until an order is accepted and has no off switch.
   - **pos_loyalty_card** (no screenshots):
     - Card statuses Draft / Active / Suspended.
     - One active points rule at a time.
     - Loyalty Settings: card format, size, colours.
     - Email Settings.
     - Delete and restore cards; Generate Loyalty Cards; Download Card Images (ZIP).
     - Its menus move under 369 Mart → Loyalty when 369 Mart Loyalty Points is installed.
3. Look at every PDF page: `py _tools\pages.py "<this folder>" <outdir> [module]`, then open the PNGs.
4. Build the front page `index.html`, which links every manual: `node _tools\index.js "<this folder>" _tools\manual_template.html`

## Tools in `_tools\`

| File | What it is |
|---|---|
| BRIEF.md | The full writing rules the manuals follow: structure, wording, screenshots, checks. Its "S" scratch path now means this `_tools` folder. |
| manual_template.html | The blank template from the artifact. Its CSS is kept unchanged; one small screenshots/glossary block is added at the end. |
| reference_signage_scan.html | The Signage Scan reference manual, for tone and depth. |
| render.js | Turns each `*_User_Manual.html` into an A4 PDF. It uses Chromium from 369Mart's Playwright install, pointed at the installed `chromium_headless_shell-1228`, because WeasyPrint is not installed. |
| pages.py | Turns each PDF page into a PNG for review. Needs PyMuPDF. |
| index.js | Builds `index.html` in the same look, with a short plain purpose line for each module. |

## Folder layout
```
odoo documents\
  MANUALS_PROGRESS.md        (this file)
  _tools\                    (brief, template, scripts)
  <module>\
    <Title>_User_Manual.html
    <Title>_User_Manual.pdf
    screenshots\NN-<what>.png   (copied from that module's own static\description\)
```
