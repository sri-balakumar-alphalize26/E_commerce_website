// Build "odoo documents\index.html": one row per module manual, in the manual template's look.
// Usage: node index.js "<odoo documents dir>" "<template html>"
const fs = require('fs');
const path = require('path');
const [root, tplPath] = process.argv.slice(2);

// Plain one-line purpose per module, grouped the way staff meet them.
const GROUPS = [
  ['Start here', [
    ['mart369_all', 'Installs the whole 369 Mart suite in one go.'],
    ['mart369', 'The 369 Mart menu and the settings every other part shares.'],
    ['mart369_roles', 'Who works at 369 Mart and what each person may do.'],
  ]],
  ['Shop front', [
    ['mart369_home', 'The app home page: banners, rows, tiles and tabs.'],
    ['mart369_catalog', 'Categories, browsing and search.'],
    ['mart369_product', 'What a product page shows, shop-wide or per product.'],
    ['mart369_pages', 'Footer pages: Terms, Privacy, About, Help, Contact.'],
    ['mart369_parts_demo', 'A sample computer-parts catalogue for trying things out.'],
  ]],
  ['Customers', [
    ['mart369_auth', 'Customer sign-up and sign-in, and the Customers desk.'],
    ['mart369_address', 'Customers’ delivery addresses.'],
    ['mart369_account', 'Reviews, referrals, rewards and notifications.'],
    ['mart369_support', 'The support bot and real support tickets.'],
  ]],
  ['Orders and money', [
    ['mart369_cart', 'Delivery fees, slots, service areas, coupons and deals.'],
    ['mart369_order', 'Orders from placed to delivered, and returns.'],
    ['mart369_store_board', 'The shop counter that rings for new orders.'],
    ['mart369_payment', 'Payments, the 369 Wallet and the Store Settings screen.'],
    ['mart369_loyalty', 'Loyalty points earned and spent on orders.'],
    ['pos_loyalty_card', 'Loyalty cards, the points rule and points history.'],
    ['mart369_whatsapp_bridge', 'One shop across the website and WhatsApp.'],
  ]],
];

const tpl = fs.readFileSync(tplPath, 'utf8');
const css = tpl.match(/<style>([\s\S]*?)<\/style>/)[1].replace('{{PRODUCT_NAME_TITLE}}', 'Module Manuals');
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');

let rows = '', count = 0;
for (const [group, mods] of GROUPS) {
  rows += `<h2>${group}</h2>\n<table><thead><tr><th style="width:34%">Manual</th><th>What it covers</th><th style="width:17%">Open</th></tr></thead><tbody>\n`;
  for (const [mod, line] of mods) {
    const dir = path.join(root, mod);
    const html = fs.existsSync(dir) && fs.readdirSync(dir).find(f => f.endsWith('_User_Manual.html'));
    if (!html) { console.log('NO MANUAL:', mod); continue; }
    const title = (fs.readFileSync(path.join(dir, html), 'utf8').match(/<title>([^<]*?)\s*(?:—|-)\s*User Manual<\/title>/) || [])[1] || html;
    const pdf = html.replace(/\.html$/, '.pdf');
    const enc = f => encodeURI(`${mod}/${f}`);
    const pdfLink = fs.existsSync(path.join(dir, pdf)) ? `<a href="${enc(pdf)}">PDF</a> · ` : '';
    rows += `<tr><td>${esc(title)}</td><td>${esc(line)}</td><td>${pdfLink}<a href="${enc(html)}">Web page</a></td></tr>\n`;
    count++;
  }
  rows += '</tbody></table>\n';
}

const out = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>369 Mart — Module Manuals</title>
<style>${css}
  td a{color:var(--navy); font-weight:700}
</style>
</head>
<body>
<div class="topbar"></div>
<div class="cover">
  <h1>369 Mart</h1>
  <div class="sub">Module Manuals</div>
  <div class="meta">User Manuals &nbsp;|&nbsp; 369ai</div>
</div>
<p>One manual for each part of 369 Mart. Each one explains what the part does, how an administrator sets it up, how staff use it day to day, and what to do when something goes wrong. Open the <b>PDF</b> to print or share it, or the <b>Web page</b> to read it in a browser.</p>
<div class="note tip"><span class="lbl">Tip:</span> New to 369 Mart? Read <b>369 Mart Suite</b>, then <b>369 Mart</b> and <b>369 Mart Roles</b> first. They explain the menu and who can do what.</div>
${rows}
</body>
</html>
`;
fs.writeFileSync(path.join(root, 'index.html'), out);
console.log(`index.html written with ${count} manuals`);
