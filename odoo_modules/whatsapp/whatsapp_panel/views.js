'use strict';

const { CSS, LOGO, SCRIPT } = require('./ui');

/** Minimal server-rendered HTML. No build step, no CDN, nothing to break. */

function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

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
<html lang="en"><head><script>document.documentElement.classList.add('js')</script><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)} — WhatsApp Panel</title><style>${CSS}</style></head><body${nav ? '' : ' class="auth"'}>
${nav ? `<header>
  <a class="brand" href="/">${LOGO} WhatsApp Panel</a>
  ${who ? `<span class="who">${esc(who)}</span>` : ''}
  <nav>
    ${links}
    <form method="post" action="/logout" style="margin:0" onsubmit="return confirm('Sign out of the panel?')"><button>Sign out</button></form>
  </nav>
</header>` : ''}
<main>${body}</main>${SCRIPT}</body></html>`;
}

module.exports = { layout, esc, LOGO };
