# 369 Mart module user manuals: progress

- **Claude Code session ID:** `c31768f3-143a-4ff9-a148-5cf485215514`
- **Status (2026-10-12):** **all 19 manuals done**. Each has an HTML file and a PDF. Start from `index.html`.

## What was asked
- One user manual for each of the 19 modules in `odoo_modules\`, saved in this folder.
- Same UI as the "369ai User Manual Template" artifact: https://claude.ai/artifact/R661ecJXX9FPEPqsd15j4m
- Decisions:
  - **PDF + HTML** per module.
  - Short (1–2 page) manuals for the umbrella and sample-data modules.
  - Written for store admins, staff **and office employees**: plain words, with a "Words you'll see" table in each manual.
  - **Screenshots come only from each module's own `static\description\` folder.** Modules without images get text-only manuals.

## Status

| Module | Manual | Pages | Screenshots |
|---|---|---|---|
| mart369 | 369_Mart_User_Manual | 6 | 1 |
| mart369_all | 369_Mart_Suite_User_Manual | 2 | 0 (module has none) |
| mart369_roles | 369_Mart_Roles_User_Manual | 6 | 0 (module has none) |
| mart369_auth | 369_Mart_Sign_In_User_Manual | 10 | 9 |
| mart369_address | 369_Mart_Delivery_Addresses_User_Manual | 9 | 10 |
| mart369_cart | 369_Mart_Delivery_and_Pricing_User_Manual | 18 | 13 |
| mart369_catalog | 369_Mart_Catalog_User_Manual | 14 | 13 |
| mart369_product | 369_Mart_Product_Page_User_Manual | 14 | 12 |
| mart369_home | 369_Mart_Home_Page_User_Manual | 10 | 5 |
| mart369_pages | 369_Mart_Pages_User_Manual | 6 | 0 (module has none) |
| mart369_parts_demo | 369_Mart_Sample_Catalogue_Computer_Parts_User_Manual | 3 | 0 (module has none) |
| mart369_order | 369_Mart_Orders_User_Manual | 18 | 18 |
| mart369_store_board | 369_Mart_New_Orders_Board_User_Manual | 8 | 5 |
| mart369_payment | 369_Mart_Payments_and_Wallet_User_Manual | 10 | 3 |
| mart369_loyalty | 369_Mart_Loyalty_Points_User_Manual | 8 | 0 (module has none) |
| pos_loyalty_card | Loyalty_Card_User_Manual | 11 | 0 (module has none) |
| mart369_account | 369_Mart_Account_User_Manual | 12 | 12 |
| mart369_support | 369_Mart_Support_User_Manual | 8 | 6 |
| mart369_whatsapp_bridge | 369_Mart_WhatsApp_Bridge_User_Manual | 8 | 0 (module has none) |

- **17 Nov 2026:** updated for the 13–17 Nov code changes: **Delivery and Pricing** (Delivery settings page as Part 1 step 2, delivery sets itself up, slots on/off per company, no delivery line for out-of-stock products, Offers page timer, branch status table), **WhatsApp Bridge** (WhatsApp parts of Delivery settings, automatic delivery shops, delivery slots on the WhatsApp order page, tracking map pins), **369 Mart** (shop logo, updates install themselves) and **Loyalty Card** (one note: updates install themselves). Suite manual unchanged. PDFs re-rendered and checked page by page. Later the same day (ce7916b): the slot list on the Delivery settings page, saved with Save all, added to Delivery and Pricing (step 6) and WhatsApp Bridge (step 5).

**Checks done:**
- Every PDF was looked at page by page. There are no stranded headings, split tables or near-empty pages.
- No "Odoo", web addresses or `{{placeholders}}` appear in the text.

## Things the writers found in the code (worth knowing)
- **Cash-on-delivery limit:** it starts at 5,000. A limit of 0 ("no limit") is put back to 5,000 every time the Payments module is updated.
- **Loyalty Card → Reset to Default:** it resets more than its confirm box says: the card number format, mobile length, welcome message and mail server settings.
- **Loyalty Card → Generate Loyalty Cards:** it also turns Draft and Suspended cards back to Active.
- **Loyalty Points settings:** "Points are earned when" and the on/off switches have no backend screen. They are set only in the staff console, under Settings → Loyalty.
- **New Orders Board alarm:** its ring and pause settings are under **Delivery → Configuration → Delivery Settings** ("The Shop Counter"). If "Shop Confirms Orders" is off, the Counter stays empty.
- **Pages module FAQ:** its seeded text says refunds go "back to where you paid from". The Orders module refunds everything to the 369 Wallet.
- **Roles:** Packer and Accountant currently give only a plain staff login; nothing else checks for them yet. Seller opens no screens yet.
- **Delivery settings status:** a branch with no address shows the to-do "Add the branch's address (street, town, pincode)" (17 Nov 2026: it used to say "in Odoo").
- **Loyalty Card → Card Images:** nothing saves card pictures any more, so this gallery stays empty unless another module saves them.

## Updating a manual later
1. Edit `<module>\<Title>_User_Manual.html`, following `_tools\BRIEF.md`.
2. Render the PDF: `node _tools\render.js "<this folder>" <module>`
3. Make page images and look at them: `py _tools\pages.py "<this folder>" <outdir> <module>`
4. Rebuild the front page: `node _tools\index.js "<this folder>" _tools\manual_template.html`

## Tools in `_tools\`

| File | What it is |
|---|---|
| BRIEF.md | The writing rules: structure, wording, screenshots, checks. Its "S" scratch path means this `_tools` folder. |
| manual_template.html | The blank template from the artifact. Its CSS is unchanged; a small screenshots/glossary block is added at the end. |
| reference_signage_scan.html | The Signage Scan reference manual, for tone and depth. |
| render.js | HTML → A4 PDF with Chromium from 369Mart's Playwright install, pointed at the installed `chromium_headless_shell-1228`. WeasyPrint is not installed. |
| pages.py | PDF pages → PNG images for review. Needs PyMuPDF. |
| index.js | Builds `index.html` in the same look. |

## The combined guide (Word + PDF)

`369_Mart_Complete_Setup_and_Ordering_Guide.docx` / `.pdf` (28 Oct 2026, 188 pages): every module manual in one book,
in setup order, plus new chapters: Start here (what to install), How an order works, Your first product (worked
example), Delivery setup and Payment methods setup (every step in order), an "In simple words" box per chapter and
an A–Z glossary.

To rebuild after a manual changes:
1. In a scratch folder: `npm install docx@9.5.0`, then copy `_tools\guide\build.js` and `extra.js` there.
2. `node build.js "<this folder>" guide.docx`. It reads every `<module>\*_User_Manual.html` and its screenshots.
3. Open `guide.docx` in Word, right-click the contents and choose Update Field, then save it as .docx and as PDF here.

New wording lives in `extra.js`. The module manuals stay the single source for everything else.
