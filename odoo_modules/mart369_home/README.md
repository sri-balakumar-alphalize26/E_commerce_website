# 369 Mart Home Page (`mart369_home`)

The 369 Mart phone app gets its whole home page from this module. An
operator edits it from **369 Mart → Home Page** — a phone-sized mock of the
app, drawn with the app's own stylesheet, that they edit in place:

- drag a band (product row or banner strip) to reorder the page;
- click a band to edit it in the side panel; every change saves on its own;
- the eye hides a band from the app without deleting it;
- ⚙ on the tabs / banners / tiles strip opens that strip's list;
- Quick and Express are configured separately.

The app reads it all from **`GET /369mart/home`**:

```json
{ "quick": { "tabs": [...], "banners": [...], "categories": [...], "sections": [...], "freeDeliveryAt": 499 },
  "all":   { ... } }
```

That is exactly the `modes` prop `components/home/Home.jsx` in the storefront
repo already accepts. Optional keys are omitted, never `null`. A banner strip
serialises to `{"banner": ["b3","b4"]}` and nothing else — that key alone is
how the app tells it from a product row.

**369 Mart → Advanced** keeps the plain Odoo forms for anything the builder
does not expose (`rule_days`, `hide_out_of_stock`, `image_base_url`, …).

## Removing things: the Trash

Nothing the operator removes is destroyed straight away. Banners, category
tiles, tabs and whole rows go to a **Trash**, kept for the number of days set
in *Advanced → Home Page Settings* (`trash_days`, default **30**, `0` = keep
until emptied by hand). A nightly `ir.cron` deletes what is past its time.

- The 🗑 chip in the control panel shows how many items are waiting.
- **Put back** returns a record *exactly as it was* — a banner that was hidden
  comes back hidden. `active` is never touched by trashing, which is what
  keeps hiding and removing two separate ideas: hiding is a switch, removing
  starts a clock.
- **Delete for good** / **Empty** skip the rest of the retention.
- A trashed record leaves the app immediately — including a banner that a
  strip still points at.

The mechanics live in `models/trashable.py`, an `AbstractModel` the four
models inherit. The filters it provides are the ones to use:

| helper | means |
|---|---|
| `_live()` | shown and not trashed — what the app serialises |
| `_kept()` | not trashed — what the builder lists |
| `_trashed()` | what the Trash panel lists |

The form screens under *Advanced* default to `search_default_kept`, with
**In the Trash** / **Not in the Trash** filters and a *Put back* button.

Lines *inside* a row — a hand-picked product, a banner placed in a strip —
are links rather than content, so removing one is immediate. The product and
the banner themselves are untouched.

## How a row decides what to show

`mart369.home.section._resolve_products()` is the one path the builder
preview *and* the API share, so what the operator sees is what a customer
gets. Four sources:

| source | how |
|---|---|
| `category` | published products in a `product.public.category` (optionally its children) |
| `manual` | an ordered line model, `mart369.home.section.product` — a many2many would come back sorted by product name |
| `rule` | newest (`publish_date`), best sellers (aggregated from `sale.report`, **not** `sales_count`, which is 0 for non-salespeople even under `sudo()`), biggest discount (`compare_list_price` ratio) |
| `tag` | published products carrying a `product.tag` |

## Layout

```
models/        serializers.py (vocabularies + helpers), one file per model,
               product_template.py adds the mart_* card-copy fields
controllers/   home_api.py — the public JSON route (type='http', cors='*')
static/src/builder/   the OWL client action (builder.js / .xml / .scss)
static/src/scss/storefront.scss   VERBATIM copy of the app's stylesheet (see below)
views/         forms, the client action, menus
data/          seed data mirroring the storefront's sampleData.js
tests/         API contract, builder_load contract, a browser tour
```

### `storefront.scss` is generated — do not hand-edit

It is `components/home/home.css` + the *product image gallery* section of
`extras.css` + the *floating pill* section of `cartfx.css` (and its phone
`@media` block) from the storefront repo, with `@media (max-width: N)`
rewritten to `@container mart-phone (max-width: N)` and viewport units to
container units, so the app's phone breakpoints fire inside the 390px frame.
When the storefront changes, regenerate it:

```
python tools/gen_storefront_scss.py [path-to-storefront-repo]
```

The generator finds those blocks by their `/* ---- title ---- */` headers and
by brace balance — **never by line number**. An earlier version sliced by line
range; one edit to `cartfx.css` shifted a block by two lines, the copy lost a
closing `}`, and every Odoo page showed *"Style error: the style compilation
failed"* until it was regenerated. If you ever see that banner after touching
the storefront, this file is the first suspect. The generator refuses to write
an unbalanced file, and this checks the result the way Odoo will:

```
python -c "import io,sass; sass.compile(string=io.open('static/src/scss/storefront.scss',encoding='utf-8').read()); print('ok')"
```

## Screenshots

`static/description/builder_quick.png` and `builder_express.png` — the
builder in both modes, captured from a real browser.

## Running the tests

```
odoo-bin -c odoo.conf -d <db> -u mart369_home --test-enable --test-tags=/mart369_home --stop-after-init
```

From Git Bash on Windows prefix `MSYS_NO_PATHCONV=1`, or `/mart369_home` gets
rewritten into a file path.

**Browser tour on Windows.** Odoo's harness treats "the Chrome process I
started has exited" as a crash. Chrome launched from an elevated shell
relaunches itself de-elevated and the launcher exits 0, so the tour is
*skipped*. Run the tests through a wrapper that adds `--do-not-de-elevate`
to Chrome's command line (patch `odoo.tests.common.ChromeBrowser._spawn_chrome`).
Also run the tour on an already-upgraded database — with `-u` in the same
run the asset-bundle rebuild races the browser and boot fails with
`Failed to fetch`. On Linux CI neither applies.

Two more test-mode facts worth knowing: with `--test-enable` Odoo serves
`readonly=True` routes from a **separate connection** (`orm/registry.py`,
`_db_readonly`) that cannot see the test transaction's uncommitted writes — so
tests that mutate and then read over HTTP check the serializer instead; and
`web_resequence` is how drag-reorder persists (`web/models/models.py`).
