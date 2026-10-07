# 369 Mart: categories, products and going live (how-to)

## 1. Create a category
**Web console:** `/admin` → Catalogue → **Catalog** → **+ New category** → Name, Under (None = main category, or pick a main category for a sub-category), logo, one line, colours → **Add category**.

**Odoo:** 369 Mart → Catalogue → **Catalog** (`/odoo/mart-catalog`), same form. Or Sales → Configuration → Product Categories → New (the website twin is made automatically).

- The category and its website twin stay in step (name, place, order, Hide).
- WhatsApp NEW ORDER shows a category only when it has a published sellable product, or vendors.
- Set the product's **Category** field (not only the website ticks) so WhatsApp and the website agree.

## 2. Make a product live
A product shows on the shop and in search only when:
1. It is **Published**.
2. Its type is **Goods**, not Service.
3. Its website category is a visible category (for category pages).

**Gap:** no 369 Mart screen has a Published switch. The Live / Hidden tag is read-only, and Odoo's own switch sits on the blank "Go to Website" preview.

**What worked:** create the product fresh in the 369 Mart **Products** desk, which publishes it automatically. Then archive the old record.

## 3. Why "Go to Website" is blank
It opens Odoo's built-in website preview. The shop is a separate site, so there is nothing to draw. The product is not broken.

## 4. Product menus
| Menu | Use |
|---|---|
| Catalogue → Products (`mart-stock`) | Stock list: price, stock, sales, Live / Hidden |
| Store → Product pages (`mart-products`) | What one product's page will show |
| Store → Product Page (`mart-product`) | Edit the shared page layout |

## 5. Specs and key features
- Key features are no longer printed on the product page.
- Specs: Product Page editor → Attributes & Variants → open a variant → Variant specs → + Add a line. Needs a product with real variants, and the Variant specs box may be off by default.

## 6. Banner size
1200 × 480 px (5:2). Stored at 1024 × 512.

## 7. Error "attribute BRAND must have at least one value"
An attribute line with no value. Add a value or remove the line.

## Known gaps
- **Published switch.** No 369 Mart screen offers a way to publish an existing product. New products publish automatically; existing unpublished ones must be re-created fresh or edited in developer mode.
- **Go to Website preview.** Opens a blank page because the shop is separate from Odoo. Consider opening the real shop page instead.
- **Product menu names.** Two menus are both called "Products", which is confusing. Consider renaming to "Stock & sales" and "Product page preview".
