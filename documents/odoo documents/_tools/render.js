// Render every manual HTML under "odoo documents" to an A4 PDF beside it.
// Usage: node render.js "<odoo documents dir>" [module ...]
const path = require('path');
const fs = require('fs');
const { chromium } = require('C:/Projects/Websites/369Mart/node_modules/playwright');

(async () => {
  const [root, ...only] = process.argv.slice(2);
  const mods = fs.readdirSync(root).filter(d => fs.statSync(path.join(root, d)).isDirectory())
    .filter(d => !only.length || only.includes(d));
  const browser = await chromium.launch({
    executablePath: path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-win64/chrome-headless-shell.exe'),
  });
  const page = await browser.newPage();
  for (const m of mods) {
    const dir = path.join(root, m);
    for (const f of fs.readdirSync(dir).filter(f => f.endsWith('_User_Manual.html'))) {
      const html = path.join(dir, f);
      await page.goto('file:///' + html.replace(/\\/g, '/'), { waitUntil: 'networkidle' });
      await page.emulateMedia({ media: 'print' });
      const pdf = html.replace(/\.html$/, '.pdf');
      await page.pdf({ path: pdf, format: 'A4', preferCSSPageSize: true, printBackground: true });
      const missing = await page.evaluate(() => [...document.images].filter(i => !i.naturalWidth).map(i => i.getAttribute('src')));
      console.log(`${m}/${path.basename(pdf)}${missing.length ? '  MISSING IMAGES: ' + missing.join(', ') : ''}`);
    }
  }
  await browser.close();
})();
