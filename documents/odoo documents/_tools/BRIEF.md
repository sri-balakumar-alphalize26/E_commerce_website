# Brief: 369 Mart module user manuals

You write customer-facing user manuals for 369 Mart backend modules, one HTML file per module.
Scratch dir (call it S): C:\Users\sriba\AppData\Local\Temp\claude\c--Projects-APK-s-369Delivery-partner\c31768f3-143a-4ff9-a148-5cf485215514\scratchpad\manuals
Modules: C:\Projects\Websites\369Mart\odoo_modules\<module>\   (READ ONLY - never edit anything there)
Output:  C:\Projects\Websites\369Mart\documents\odoo documents\<module>\   (folder already exists)

## Inputs
- `S\manual_template.html`: the blank template. Copy its whole `<head>`/CSS exactly. Only change `<title>`, the
  `@page` footer `369ai · <Title>`, and the body. Add the CSS block below at the end of `<style>`.
- `S\reference_signage_scan.html`: a finished manual. Match its tone, depth and how each component is used. Read it fully first.
- The module source: manifest, views/*.xml, models/*.py, static/src (desk screens, OWL/JS/XML templates), data/*.xml,
  security/*, controllers/*, README.md. This is your **only source of facts**. Quote on-screen labels exactly as they
  appear in views/templates/JS. Do not invent fields, buttons, menus or behaviour. Leave out anything you cannot confirm.

## Readers
Store admins and staff, **and office employees with no technical background**. Use everyday words and short sentences.
Write in the second person ("Open **Orders** and…"). Explain each term the first time it is used.
- Never write "Odoo"; say "the backend" or "the main menu".
- Never write code names: no model names, technical field names, URLs/routes like /369mart/..., group XML ids,
  config-parameter keys, Python, or file names. Say "the shop app" / "the website" for the customer side, and
  "the staff console" for the separate web admin console.
- Group names: use the plain role names "Owner", "Manager", "Packer", "Accountant", "Rider" (from 369 Mart Roles),
  "Website designer", "Salesperson", "Administrator (Settings)", "Internal user", "Loyalty User", "Loyalty Manager".

## Structure (keep this order; same components as the template)
1. Cover: product name (the module's display name, e.g. "369 Mart Orders"), an orange tagline, "User Manual | 369ai".
2. **What this does**: 2 short paragraphs with navy key terms (`<span class="k">`), a `.flow` of 3–4 cards, and a `note start` BEFORE YOU START.
3. **Words you'll see**: a small `<table class="gloss">` (Word · What it means), 4–8 rows, plain words.
4. **How the manual is arranged**: one paragraph naming each Part.
5. **Part 1 — Setting Up** (admin, done once). Step 1 is always "Where everything lives" (menu map, `ul.f`, paths with
   `<span class="arr">→</span>`). Each step: "Open **X** and …", field bullets (`ul.f`: **Field** — meaning, with defaults stated).
6. **Part 2 — Everyday Use** (staff, daily). Add a screen/purpose table where there is a desk/board.
   Where the module has a shopper side, describe it in words from the staff's point of view ("What the customer sees").
7. **Part 3 — Keeping It Secure & In Order**: permissions, history/logs, a "Who can do what" role table, privacy notes.
8. Reference tables (`h2`): a status table (State · Meaning · How to change it), plus any option/mode matrix.
9. **Quick tips**: 6–8 one-liners.
10. **If something goes wrong**: What you see → What to do (name the exact screen and field).

Callouts (`.note tip|warn|good|imp`), at most about 2 per step: TIP, WATCH OUT, GOOD TO KNOW, IMPORTANT.
Keep it compact. No marketing fluff and no repeats between sections.

**Short manuals** (umbrella or sample-data modules only): Cover, What this does, Words you'll see (optional),
"What it installs" or "What it loads" (table), "When to use it", "How to remove it" (what happens on uninstall),
"If something goes wrong". Aim for 1–2 pages.

## Screenshots: only from the module's own folder
- Use **only** images in `<module>\static\description\` (never icon.png, never another module's images). If the module
  has none, the manual has no screenshots (do not mention it).
- Open each image with the Read tool to see what it shows, then pick the ones that illustrate a step. Use most of them;
  skip duplicates and near-duplicates. At most about 1–2 per step.
- Copy each one you use (PowerShell Copy-Item or bash cp) to `<output module folder>\screenshots\NN-<short-kebab-name>.png`,
  numbered in the order they appear in the manual (01, 02, …). Reference them relatively: `screenshots/01-orders-desk.png`.
- Markup, placed right under the paragraph it illustrates:
  `<figure class="shot"><img src="screenshots/01-orders-desk.png" alt="…"><figcaption>Figure 1 — The Orders desk: …</figcaption></figure>`
  The caption must describe what is actually visible in the picture.
- A phone-sized (tall, narrow) image gets `class="shot phone"`.
- If an image shows something that looks like a real person's private details (a real-looking personal phone number,
  email or home address, not obvious sample data), still use it, but list it in your final report.

## CSS to append at the end of the template's <style> (identical in every manual)
```
  /* ---------- Screenshots + glossary (added for 369 Mart manuals) ---------- */
  figure.shot{margin:8pt 0 12pt; page-break-inside:avoid; break-inside:avoid; text-align:center}
  figure.shot img{max-width:100%; max-height:118mm; border:1px solid var(--line); border-radius:6px; box-shadow:0 1px 4px rgba(30,42,120,.12)}
  figure.shot.phone img{max-width:62mm}
  figure.shot figcaption{font-size:8.5pt; color:var(--muted); margin-top:4pt; text-align:left}
  table.gloss td:first-child{width:28%}
  h2, h3.step, .part{break-after:avoid}
```

## File name
`<output module folder>\<Title_With_Underscores>_User_Manual.html`, e.g. `369_Mart_Orders_User_Manual.html`,
`Loyalty_Card_User_Manual.html`. Use the module's display name from the manifest (drop a "369 Mart:" colon).

## Check before you finish (each manual)
1. Render it: `node "S\render.js" "C:\Projects\Websites\369Mart\documents\odoo documents" <module>` (prints MISSING IMAGES if a path is wrong).
2. Make page images: `py "S\pages.py" "C:\Projects\Websites\369Mart\documents\odoo documents" "S\pages" <module>`, then Read
   every `S\pages\<module>\pNN.png`. Fix: a heading left alone at the bottom of a page, a table or figure split badly,
   overflow, or a nearly empty page caused by a large figure (shrink it with an inline `style="max-height:…"`).
3. grep your HTML for `Odoo`, `/369mart`, `{{`, `mart369.` and `_id`: none may remain in visible text.
4. Final report (short): for each module give the file name, the page count, the number of screenshots used, anything
   you left out because it was unclear, and any images with possible private details.
