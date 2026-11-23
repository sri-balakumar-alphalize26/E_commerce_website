'use strict';

/** Minimal server-rendered HTML. No build step, no CDN, nothing to break. */

function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const CSS = `
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e6e8ee;--muted:#8b93a7;
--accent:#25d366;--bad:#ff6b6b;--warn:#f5b455;--radius:10px}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,sans-serif}
a{color:var(--accent);text-decoration:none}
header{display:flex;gap:18px;align-items:center;padding:14px 22px;
background:var(--card);border-bottom:1px solid var(--line);flex-wrap:wrap}
header .brand{font-weight:700;letter-spacing:.3px}
header .who{font-size:12px;color:var(--muted)}
header nav{display:flex;gap:16px;margin-left:auto;align-items:center;flex-wrap:wrap}
main{max-width:1000px;margin:26px auto;padding:0 18px}
h1{font-size:22px;margin:0 0 14px}
h2{font-size:16px;margin:22px 0 10px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
padding:18px;margin-bottom:18px}
.card.narrow{max-width:560px}
.card.danger{border-color:#40232a}
.card.warn{border-color:#5a4520}
label{display:block;margin:12px 0}
label .muted{display:block;font-size:12px;margin-top:4px}
input,select{width:100%;padding:9px 11px;border-radius:8px;border:1px solid var(--line);
background:#10131a;color:var(--fg);font-size:14px}
input[readonly]{opacity:.7}
label.check{display:flex;align-items:center;gap:9px}
label.check input{width:auto}
button,.btn{display:inline-block;padding:8px 14px;border-radius:8px;border:1px solid var(--line);
background:#1d212a;color:var(--fg);font-size:14px;cursor:pointer}
button.primary,.btn.primary{background:var(--accent);border-color:var(--accent);color:#06240f;font-weight:600}
button.bad-btn{background:#3a1f25;border-color:#5c2b34;color:#ffb4b4}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin-bottom:18px}
table.plain{background:none;border:none}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
tr:last-child td{border-bottom:none}
tr.off{opacity:.45}
td.right,th.right,.right{text-align:right}
td.num{font-variant-numeric:tabular-nums}
code{background:#10131a;padding:2px 6px;border-radius:5px;font-size:13px;
border:1px solid var(--line);word-break:break-all}
code.tok{display:block;padding:9px;margin-top:4px}
.muted{color:var(--muted)}
.bad{color:var(--bad)}
.warn-msg{color:var(--warn)}
.ok-msg{color:var(--accent)}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
.pill.ok{background:#123322;color:#5ce08e}
.pill.no{background:#37222a;color:#ff9a9a}
.pill.warn{background:#3a2f16;color:#f5b455}
.pill.dim{background:#20242e;color:#8b93a7}
.row{display:flex;align-items:center;gap:10px}
.row.between{justify-content:space-between;flex-wrap:wrap}
.row.gap{gap:10px;margin:12px 0}
.row.gap input{flex:1}
.qr{display:block;width:280px;max-width:100%;margin:14px auto;padding:10px;
background:#fff;border-radius:10px}
.big{font-size:20px;font-weight:700;letter-spacing:.5px}
.checks label{margin:6px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px}
.tile b{display:block;font-size:22px}.tile span{color:var(--muted);font-size:13px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:18px 0;overflow-x:auto}
.tabs a{padding:10px 14px;color:var(--muted);font-weight:600;white-space:nowrap;border-bottom:3px solid transparent}
.tabs a.on{color:var(--fg);border-bottom-color:var(--accent)}
section.tab[hidden]{display:none}
section.tab .card.narrow{max-width:640px}
.num-row.is-off{opacity:.7;border-style:dashed}
.num-free{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid var(--line);border-radius:10px;padding:12px;margin:8px 0}
h3{font-size:14px;margin:16px 0 8px}
.phone{margin:12px 0}
.ph-box{display:flex;align-items:stretch;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#10131a}
.ph-box:focus-within{border-color:var(--accent)}
.phone.good .ph-box{border-color:var(--accent)}
.ph-box .ph-dial{display:flex;align-items:center;padding:0 12px;background:#1d212a;font-weight:700}
.ph-box input.ph-num{flex:1;min-width:0;border:0;border-radius:0;font-size:17px;font-weight:600;letter-spacing:.5px}
.ph-box .ph-count{display:flex;align-items:center;padding:0 12px;color:var(--muted);font-size:12px}
.phone.good .ph-hint{color:var(--accent)}
.num-row{border:1px solid var(--line);border-radius:10px;padding:14px;margin:12px 0}
.num-no{display:inline-block;min-width:26px;height:26px;line-height:26px;text-align:center;border-radius:999px;background:#20242e;color:var(--muted);font-weight:700;font-size:13px;margin-right:8px}
.key-line{display:flex;align-items:center;gap:10px;margin-top:10px}
.key-line code{flex:1;min-width:0;max-height:3.4em;overflow:auto}
details summary{cursor:pointer;color:var(--muted);margin-top:8px}
details summary.btn.primary{display:inline-block;color:#06240f;list-style:none}
details.num-add{margin:16px 0}
.own-max{display:flex;align-items:center;gap:10px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:12px}
.own-max label{display:flex;align-items:center;gap:10px;margin:0}
.own-max input{width:80px}
@media (max-width:620px){.key-line{flex-wrap:wrap}header nav{width:100%;margin-left:0}main{padding:0 12px}}
`;

/** Which pages each role gets in the header. */
const NAV = {
  admin: [['/', 'Databases'], ['/numbers', 'Numbers'], ['/companies', 'Vendors'],
          ['/activity', 'Activity'], ['/blocked', 'Blocking'], ['/account', 'Account']],
  vendor: [['/', 'Databases'], ['/numbers', 'Numbers'], ['/activity', 'Activity'],
           ['/blocked', 'Opt-outs'], ['/account', 'Account']],
  client: [['/me', 'My WhatsApp'], ['/activity', 'Activity'], ['/blocked', 'Opt-outs'],
           ['/account', 'Account']],
};

/**
 * @param {string} title
 * @param {string} body
 * @param {boolean|object} nav  false = no header; or {role, who} for the signed-in header
 */
function layout(title, body, nav = true) {
  const role = nav && typeof nav === 'object' ? nav.role : 'admin';
  const who = nav && typeof nav === 'object' ? nav.who : '';
  const links = (NAV[role] || NAV.admin).map(([href, label]) => `<a href="${href}">${label}</a>`).join('\n    ');
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)} — WhatsApp Panel</title><style>${CSS}</style></head><body>
${nav ? `<header>
  <span class="brand">WhatsApp Panel</span>
  ${who ? `<span class="who">${esc(who)}</span>` : ''}
  <nav>
    ${links}
    <form method="post" action="/logout" style="margin:0"><button>Sign out</button></form>
  </nav>
</header>` : ''}
<main>${body}</main></body></html>`;
}

module.exports = { layout, esc };
