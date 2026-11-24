'use strict';

/**
 * WhatsApp control panel.
 *
 *   Odoo (many servers, many databases)
 *        |  speaks Evolution's own API, with its own token
 *        v
 *   panel :8086  -- checks url+db, spam rules, quotas --
 *        |  adds the master key, which no tenant ever sees
 *        v
 *   Evolution :8085  ->  one instance per NUMBER; a number serves one or many databases
 *
 * The point of the middle layer is that a request is accepted only when the
 * server address it comes from AND the database name it claims are both
 * registered here and switched on, and only on the number the administrator
 * assigned to that database - paired with the ONE phone allowed to scan it.
 *
 * Logins (26 Sep 2026): platform admin -> vendor -> client (one per database).
 * Everything is checked against the session on the server; ids in the URL or
 * the form are never trusted on their own.
 */

const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const crypto = require('crypto');
const express = require('express');
const session = require('express-session');
const bcrypt = require('bcryptjs');

const { pool, init, origin } = require('./db');
const { layout, esc, LOGO } = require('./views');
const mailer = require('./mail');

const PORT = Number(process.env.PANEL_PORT || 8086);
const EVOLUTION_URL = (process.env.EVOLUTION_URL || 'http://127.0.0.1:8085').replace(/\/+$/, '');
const EVOLUTION_KEY = process.env.EVOLUTION_API_KEY || '';
const INSTANCE = process.env.EVOLUTION_INSTANCE || 'main';

/**
 * What a tenant may ask the gateway to do.
 *
 * Sending and read-only lookups only. Three things are deliberately absent:
 *
 *   instance/logout, instance/delete  - would unpair the number for every
 *                                       database sharing it.
 *   webhook/set                       - the webhook always points at this
 *                                       panel, which fans replies out to every
 *                                       database on the number.
 */
const ALLOWED = [
  { method: 'POST', re: /^\/message\/sendText\/[^/]+$/, kind: 'text' },
  { method: 'POST', re: /^\/message\/sendMedia\/[^/]+$/, kind: 'media' },
  { method: 'POST', re: /^\/message\/sendButtons\/[^/]+$/, kind: 'buttons' },
  // A list renders in groups where sendButtons arrives as "This message
  // couldn't load", so it is the only tappable prompt that actually works
  // there. Same kind as buttons: it carries its own choices, so it gets the
  // bare notice rather than a support link stapled on.
  { method: 'POST', re: /^\/message\/sendList\/[^/]+$/, kind: 'buttons' },
  // A poll is the only tappable prompt confirmed to render in a group on
  // this transport - buttons arrive as "couldn't load" and a list can be
  // accepted and then silently dropped. Its question and options carry no
  // free text to sign.
  { method: 'POST', re: /^\/message\/sendPoll\/[^/]+$/, kind: 'buttons' },
  { method: 'GET', re: /^\/instance\/connectionState\/[^/]+$/, kind: 'read' },
  { method: 'GET', re: /^\/instance\/fetchInstances$/, kind: 'read' },
  { method: 'POST', re: /^\/chat\/whatsappNumbers\/[^/]+$/, kind: 'read' },
  { method: 'POST', re: /^\/chat\/findContacts\/[^/]+$/, kind: 'read' },
  { method: 'POST', re: /^\/chat\/getBase64FromMediaMessage\/[^/]+$/, kind: 'read' },
  // The chats of the database's own number, for an administrator of it.
  { method: 'POST', re: /^\/chat\/findChats\/[^/]+$/, kind: 'read', quiet: true },
  { method: 'POST', re: /^\/chat\/findMessages\/[^/]+$/, kind: 'read', quiet: true },
  { method: 'GET', re: /^\/group\/fetchAllGroups\/[^/]+$/, kind: 'read' },
  // Delete-for-everyone, used by the conduct filter to pull an abusive
  // member's message out of a group. WhatsApp only honours it from a group
  // admin; the body carries the message key, not a recipient, so 'read'.
  { method: 'DELETE', re: /^\/chat\/deleteMessageForEveryone\/[^/]+$/, kind: 'read' },
  // Who is admin in a group: read-only, so the conduct filter can say
  // honestly whether a delete could have worked.
  { method: 'GET', re: /^\/group\/participants\/[^/]+$/, kind: 'read' },
  // A group's invite link, for "Back to the group". WhatsApp gives it to an
  // admin of that group only.
  { method: 'GET', re: /^\/group\/inviteCode\/[^/]+$/, kind: 'read' },
];

const app = express();
app.set('trust proxy', true);
app.use(express.json({ limit: '60mb' }));
app.use(express.urlencoded({ extended: true, limit: '2mb' }));

// ---------------------------------------------------------------- helpers

function token() {
  return crypto.randomBytes(24).toString('hex');
}

function clientIp(req) {
  return (req.headers['x-forwarded-for'] || '').split(',')[0].trim() || req.ip || '';
}

/**
 * Said on every message, whatever kind it is.
 *
 * Single asterisks, not double: *this* is how WhatsApp marks bold. Markdown's
 * **this** is not a thing here - it would arrive with the asterisks showing.
 */
const GROUP_SIG = (label) => '🏢 *' + label + '*';
const NOTICE = '🔔 *This is an automated notification. Please do not reply.*';

/**
 * A tap-to-chat link for a support number.
 *
 * wa.me wants digits with the country code and nothing else - it fails quietly
 * on anything shorter, opening a chat with nobody. A number that cannot be
 * dialled internationally therefore gets no link at all, which at least fails
 * where an administrator can see it rather than in a customer's hands.
 */
function waLink(number) {
  const digits = String(number || '').replace(/[^0-9]/g, '');
  return digits.length >= 10 ? `https://wa.me/${digits}` : '';
}

/**
 * The block a WhatsApp message ends with when it cannot carry a button.
 *
 * No link. Used only where one would be redundant or impossible: a button
 * message already carries the number as a button, and a client with no support
 * number set has nothing to link to.
 *
 * Media sends used to land here too, and that was wrong - Oman Photo House
 * sends its receipts as images, so every one of its customers was told not to
 * reply and given nowhere else to go. Those now use signatureWithLink below.
 */
function signature(row) {
  const label = (row.tenant_label || '').trim();
  return label ? `${NOTICE}\n\n🏢 *${label}*` : NOTICE;
}

/**
 * The same thing, with the number spelled out as a tappable wa.me link.
 *
 * For every message that cannot carry a button: plain-text email, and media
 * sends, whose caption is text and nothing more. Written as a URL rather than
 * as digits because WhatsApp Web does not turn a phone number into a link -
 * only mobile does - and half the recipients read on a desktop. The digits are
 * still legible inside the URL, so nothing is hidden by writing it this way.
 */
function signatureWithLink(row) {
  const label = (row.tenant_label || '').trim();
  const link = waLink(row.contact_number);
  if (link) return `${NOTICE}\n\n💬 *${label || 'WhatsApp Support'}:* ${link}`;
  return signature(row);
}

/** Marks a message this panel has already signed, so a resend cannot double it. */
const HTML_MARK = '<!-- wap-signature -->';

/**
 * The same footer for email, in both parts of the message.
 *
 * Email is the one channel that can have the button without any of WhatsApp's
 * conditions: an anchor is just an anchor, it survives an attachment, and it
 * needs no message type of its own. So the HTML part gets the labelled button
 * and never shows the number, and the plain-text part - which cannot have a
 * button at all - falls back to the same line WhatsApp text messages use.
 *
 * Laid out as a table with a bgcolor rather than a styled div, because Outlook
 * renders mail through Word and drops padding and background from everything
 * else.
 */
function emailSignature(row) {
  const label = (row.tenant_label || '').trim() || 'WhatsApp Support';
  const link = waLink(row.contact_number);
  const notice = 'This is an automated notification. Please do not reply.';

  const button = link ? `
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:14px 0 0">
        <tr><td bgcolor="#25D366" style="border-radius:4px">
          <a href="${esc(link)}" style="display:inline-block;padding:10px 20px;
             font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#ffffff;
             text-decoration:none">💬 ${esc(label)}</a>
        </td></tr>
      </table>` : `<br>🏢 <b>${esc(label)}</b>`;

  const html = `${HTML_MARK}
    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e0e0e0;
                font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#666666">
      🔔 <b>${esc(notice)}</b>${button}
    </div>`;

  return { html, text: signatureWithLink(row) };
}

/** Put the block inside the document rather than after it, where a client would
 *  be free to ignore it. */
function appendToHtml(html, block) {
  if (html.includes(HTML_MARK)) return html;
  const close = html.lastIndexOf('</body>');
  return close === -1 ? html + block : html.slice(0, close) + block + html.slice(close);
}

/**
 * What WhatsApp accepts in each field, so an over-long one is reported here
 * rather than coming back as an opaque failure from the gateway.
 */
const LIMITS = { text: 4096, caption: 1024, description: 1024 };

async function log(entry) {
  try {
    await pool.query(
      `INSERT INTO wap_log (database_id, claimed_url, claimed_db, remote_ip,
                            phone, endpoint, status, detail, channel)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
      [entry.databaseId || null, entry.url || '', entry.db || '', entry.ip || '',
       entry.phone || '', entry.endpoint || '', entry.status,
       (entry.detail || '').slice(0, 500), entry.channel || 'whatsapp']
    );
  } catch (err) {
    console.error('[panel] could not write log:', err.message);
  }
}

// ---------------------------------------------------------------- proxy

/**
 * Identify the caller, or explain precisely why it was refused.
 *
 * Three separate things must line up: the token has to exist, the server
 * address the caller reports has to be the one registered against that token,
 * and both the server and the database have to be switched on. Reporting which
 * of those failed is worth the small disclosure - the alternative is an
 * administrator staring at "forbidden" with no idea which field is wrong.
 */
async function identify(req) {
  const supplied = req.headers['apikey'] || req.headers['x-wa-token'] || '';
  const claimedDb = String(req.headers['x-odoo-db'] || '').trim();
  const claimedUrl = origin(req.headers['x-odoo-url'] || '');

  if (!supplied) return { error: 'no key was sent: paste the key of this number from the WhatsApp panel in Setup Key and save' };

  const { rows } = await pool.query(
    `SELECT d.id, d.db_name, d.tenant_label, d.contact_number, d.active AS db_active,
            d.daily_cap, d.per_minute, d.company_id, d.server_id, d.number_id, d.odoo_webhook_url, d.sign_messages, d.off_by,
            s.base_url, s.name AS server_name, s.active AS server_active,
            c.name AS company_name, c.active AS company_active,
            n.instance_name, n.authorized_number, n.paired_number, n.pair_state,
            n.last_wrong_number, n.active AS number_active, n.label AS number_label
       FROM wap_database d
       JOIN wap_server s ON s.id = d.server_id
       LEFT JOIN wap_company c ON c.id = d.company_id
       LEFT JOIN wap_number n ON n.id = d.number_id
      WHERE d.token = $1`,
    [supplied]
  );
  if (!rows.length) return { error: 'this key is not registered in the WhatsApp panel (reset, or not complete): copy it again there, paste it in Setup Key and save' };
  const row = rows[0];

  if (!row.company_id) {
    return { error: `database ${row.db_name} is not assigned to a software company`, row };
  }
  if (!row.company_active) return { error: `${row.company_name} is switched off`, row };
  if (!row.server_active) return { error: `server ${row.base_url} is switched off`, row };
  // Both headers are REQUIRED now. A bare token used to pass; that let a key
  // copied out of one Odoo be used from anywhere.
  if (!claimedDb) return { error: 'X-Odoo-Db header missing', row };
  if (claimedDb !== row.db_name) {
    return { error: `wrong key: it is the key of database ${row.db_name}, but this is ${claimedDb}. Open ${claimedDb} in the WhatsApp panel and copy the key there`, row };
  }
  if (!claimedUrl) return { error: 'X-Odoo-Url header missing', row };
  if (claimedUrl !== origin(row.base_url)) {
    return { error: `wrong address: this key is for ${row.base_url}, but this Odoo is ${claimedUrl}`, row };
  }
  // after the two above: with the wrong key, "switched off" would name the other database
  if (!row.db_active) return { error: `database ${row.db_name} is switched off in the WhatsApp panel. Press Activate on its page there`, row };
  if (row.off_by) return { error: 'this WhatsApp number is turned off', row, off: row.off_by };
  return { row };
}

/**
 * Why this database may not use WhatsApp right now, or '' when it may.
 *
 * The number is a record of its own: the administrator assigns it, the ONE
 * phone allowed to scan it is written on it, and a scan by any other phone is
 * logged out again. Until that is straight, nothing goes out on it.
 */
function numberGate(row) {
  if (!row.number_id || !row.instance_name) {
    return `database ${row.db_name} has no WhatsApp number assigned; the administrator assigns one in the panel`;
  }
  if (!row.number_active) return `the WhatsApp number for ${row.db_name} is switched off`;
  if (row.pair_state === 'missing') {
    return `the WhatsApp number for ${row.db_name} is missing on the gateway; reset it in the panel`;
  }
  if (row.pair_state === 'wrong_number') {
    return `WhatsApp for ${row.db_name} was scanned with ${row.last_wrong_number || 'another phone'}; `
         + `only ${row.authorized_number} is allowed. Scan again with the right phone`;
  }
  return '';
}

/** Spam and quota rules, applied before anything reaches WhatsApp. */
async function screen(row, body, kind) {
  const phone = String(body.number || '').replace(/[^0-9]/g, '');
  if (kind !== 'read' && !phone) return { block: 'no number in the request' };

  if (phone) {
    // A block for this database, or a vendor-wide one.
    // ... on any number of this database: people opt out of a business.
    const off = await pool.query(
      `SELECT 1 FROM wap_optout
        WHERE phone = $1 AND (database_id = ANY($2::int[]) OR (database_id IS NULL AND company_id = $3))`,
      [phone, (await siblings(row)).map(x => x.id), row.company_id]);
    if (off.rowCount) return { block: 'recipient has opted out', phone };
  }

  const text = [body.text, body.caption, body.description, body.title]
    .filter(Boolean).join(' ').toLowerCase();
  if (text) {
    const { rows } = await pool.query('SELECT pattern, reason FROM wap_block');
    for (const b of rows) {
      if (text.includes(String(b.pattern).toLowerCase())) {
        return { block: `blocked content: ${b.pattern}${b.reason ? ' (' + b.reason + ')' : ''}`, phone };
      }
    }
  }

  const day = await pool.query(
    `SELECT count(*)::int AS n FROM wap_log
      WHERE database_id = $1 AND status = 'sent'
        AND created_at >= date_trunc('day', now())`, [row.id]);
  if (row.daily_cap > 0 && day.rows[0].n >= row.daily_cap) {
    return { block: `daily cap reached (${day.rows[0].n}/${row.daily_cap})`, phone };
  }

  const minute = await pool.query(
    `SELECT count(*)::int AS n FROM wap_log
      WHERE database_id = $1 AND status = 'sent'
        AND created_at >= now() - interval '1 minute'`, [row.id]);
  if (row.per_minute > 0 && minute.rows[0].n >= row.per_minute) {
    // Not a refusal: the caller is told when, and sends it then.
    const free = await pool.query(
      `SELECT GREATEST(5, LEAST(60, CEIL(EXTRACT(EPOCH FROM
                (min(created_at) + interval '1 minute' - now())))))::int AS s
         FROM wap_log
        WHERE database_id = $1 AND status = 'sent'
          AND created_at >= now() - interval '1 minute'`, [row.id]);
    return { wait: free.rows[0].s || 30, block: `rate limit reached (${minute.rows[0].n}/min)`, phone };
  }

  return { phone };
}

app.all(/^\/(message|instance|chat|group|webhook)\b.*/, async (req, res) => {
  const ip = clientIp(req);
  const claimedDb = String(req.headers['x-odoo-db'] || '').trim();
  const claimedUrl = origin(req.headers['x-odoo-url'] || '');

  const rule = ALLOWED.find(a => a.method === req.method && a.re.test(req.path));
  if (!rule) {
    await log({ url: claimedUrl, db: claimedDb, ip, endpoint: req.method + ' ' + req.path,
                status: 'refused', detail: 'endpoint not permitted through the panel' });
    return res.status(403).json({
      error: 'This endpoint is not available through the panel.',
      detail: 'Sending and lookups are allowed. Logging the number out, deleting '
            + 'the instance and changing the webhook are not - the panel owns the '
            + 'number and its webhook.',
    });
  }

  const who = await identify(req);
  if (who.error) {
    await log({ databaseId: who.row ? who.row.id : null, url: claimedUrl, db: claimedDb, ip,
                endpoint: req.path, status: 'refused', detail: who.error });
    return res.status(403).json({ error: 'Refused', detail: who.error });
  }
  const row = who.row;

  // The two state reads are answered by the panel itself whenever the number
  // is not usable, so Odoo can show WHY instead of a bare refusal.
  const gate = numberGate(row);
  if (rule.kind === 'read' && /^\/instance\/connectionState\//.test(req.path)) {
    if (gate) {
      return res.json({ instance: { instanceName: row.instance_name || '',
        state: row.pair_state === 'wrong_number' ? 'wrong_number' : 'close' }, detail: gate });
    }
  } else if (rule.kind === 'read' && req.path === '/instance/fetchInstances') {
    if (gate) return res.json([]);
  } else if (gate) {
    await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip,
                endpoint: req.path, status: 'refused', detail: gate });
    return res.status(403).json({ error: 'Refused', detail: gate });
  }

  let body = req.body && typeof req.body === 'object' ? { ...req.body } : {};
  // Nothing but the chat and the page: another instance cannot be asked for.
  if (rule.quiet) {
    const jid = String((((body.where || {}).key || {}).remoteJid) || '');
    if (/findMessages/.test(req.path) && !/^[0-9A-Za-z._:-]+@(s\.whatsapp\.net|g\.us|lid)$/.test(jid)) {
      return res.status(400).json({ error: 'Which chat?' });
    }
    body = /findMessages/.test(req.path)
      ? { where: { key: { remoteJid: jid } }, page: Math.max(1, parseInt(body.page, 10) || 1), offset: 50 } : {};
  }
  // Usually what the caller asked for, but a text send that gains a button has
  // to be posted to the endpoint that accepts buttons instead.
  let apiPath = req.path;
  let phone = '';
  if (rule.kind !== 'read') {
    const verdict = await screen(row, body, rule.kind);
    phone = verdict.phone || '';
    if (verdict.wait) {
      await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone,
                  endpoint: req.path, status: 'held', detail: `${verdict.block} - again in ${verdict.wait} s` });
      res.set('Retry-After', String(verdict.wait));
      return res.status(429).json({ error: 'Rate limited', detail: verdict.block });
    }
    if (verdict.block) {
      await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone,
                  endpoint: req.path, status: 'blocked', detail: verdict.block });
      return res.status(429).json({ error: 'Blocked', detail: verdict.block });
    }
    // Sign every outgoing message. When a number is shared by several
    // databases the recipient sees one number whoever is writing, so without
    // this they have no way of telling which business it is.
    const link = waLink(row.contact_number);
    const label = (row.tenant_label || '').trim() || 'WhatsApp Support';

    // A group message is a conversation, not a notification. The assistant asks
    // questions in there and waits for the answer, so "please do not reply"
    // would contradict the very message it is stapled to.
    const isGroup = String(body.number || '').includes('@g.us');

    // Promoting text to a button message is off, and should stay off: the
    // button type arrives on WhatsApp Web as "This message couldn't load".
    const PROMOTE_TEXT_TO_BUTTONS = false;

    if (PROMOTE_TEXT_TO_BUTTONS && !isGroup && rule.kind === 'text' && link
        && typeof body.text === 'string' && body.text.trim()) {
      const raw = body.text;
      const cut = raw.indexOf('\n');
      const head = (cut === -1 ? raw : raw.slice(0, cut)).replace(/\*/g, '').trim();
      const rest = cut === -1 ? '' : raw.slice(cut + 1).replace(/^\n+/, '');
      const description = rest.includes(NOTICE) ? rest
        : (rest ? `${rest}\n\n${NOTICE}` : NOTICE);

      apiPath = req.path.replace('/message/sendText/', '/message/sendButtons/');
      delete body.text;
      body.title = head || label;
      body.description = description;
      if (!body.footer) body.footer = label;
      body.buttons = [{ type: 'url', displayText: label, url: link }];

      if (description.length > LIMITS.description) {
        console.warn(`[panel] ${row.db_name}: button body is ${description.length} `
          + `chars, over the ${LIMITS.description} WhatsApp allows`);
      }
    } else {
      const isButtons = rule.kind === 'buttons';
      // The footer is optional per database (Settings > tick). Off = the
      // message goes exactly as Odoo wrote it.
      const sig = !row.sign_messages ? ''
        : isGroup ? (label ? GROUP_SIG(label) : '')
        : isButtons ? NOTICE : signatureWithLink(row);
      // A list / poll carries its own footer; signing its description produces
      // a message WhatsApp never displays.
      const isList = apiPath.includes('/message/sendList/')
        || apiPath.includes('/message/sendPoll/');
      for (const field of (isList ? [] : ['text', 'caption', 'description'])) {
        const value = body[field];
        if (typeof value === 'string' && value && sig && !value.includes(sig)) {
          body[field] = `${value}\n\n${sig}`;
          if (body[field].length > LIMITS[field]) {
            console.warn(`[panel] ${row.db_name}: signed ${field} is `
              + `${body[field].length} chars, over the ${LIMITS[field]} WhatsApp allows`);
          }
        }
      }
      if (row.sign_messages && isButtons && link && Array.isArray(body.buttons)) {
        if (body.buttons.some(b => b && b.url === link)) {
          // already there - nothing to do
        } else if (body.buttons.length >= 3) {
          console.warn(`[panel] ${row.db_name}: no room for the support button, `
            + `the message already carries ${body.buttons.length}`);
        } else {
          body.buttons.push({ type: 'url', displayText: label, url: link });
        }
      }
      if (row.sign_messages && isButtons && !body.footer) body.footer = label;
    }
  }

  // Force the request onto THIS database's assigned number, whatever instance
  // the caller named in the URL. Otherwise one Odoo could send from another
  // database's number simply by changing the path.
  const forwardPath = apiPath.replace(/\/[^/]+$/, m => (
    /^\/(message|chat|group)\//.test(apiPath) || /^\/instance\/connectionState\//.test(apiPath)
      ? '/' + row.instance_name : m));

  // Evolution needs the query string on its GET reads - fetchAllGroups answers
  // 400 without it, and req.path drops it. Restricted to allowlisted GET reads.
  const qAt = req.originalUrl.indexOf('?');
  const search = (req.method === 'GET' && rule.kind === 'read' && qAt !== -1)
    ? req.originalUrl.slice(qAt)
    : '';

  try {
    const upstream = await fetch(EVOLUTION_URL + forwardPath + search, {
      method: req.method,
      headers: { 'Content-Type': 'application/json', apikey: EVOLUTION_KEY },
      body: req.method === 'GET' ? undefined : JSON.stringify(body),
    });
    let text = await upstream.text();
    // The instance list would show every vendor's number; the caller only gets
    // its own.
    if (upstream.ok && req.path === '/instance/fetchInstances') {
      try {
        const list = JSON.parse(text);
        if (Array.isArray(list)) {
          text = JSON.stringify(list.filter(entry => {
            const i = entry.instance || entry;
            return (i.name || i.instanceName) === row.instance_name;
          }));
        }
      } catch (err) { /* not JSON - pass through */ }
    }
    if (!rule.quiet || !upstream.ok) await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone,
                endpoint: apiPath === req.path ? req.path : `${req.path} -> ${apiPath}`,
                status: upstream.ok ? (rule.kind === 'read' ? 'read' : 'sent') : 'failed',
                detail: upstream.ok ? '' : text.slice(0, 400) });
    res.status(upstream.status);
    res.type('application/json').send(text);
  } catch (err) {
    await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone,
                endpoint: req.path, status: 'failed', detail: 'gateway unreachable: ' + err.message });
    res.status(502).json({ error: 'The WhatsApp gateway is not reachable.', detail: err.message });
  }
});

// ---------------------------------------------------------------- the gateway

async function evo(pathname, method = 'GET', body) {
  const res = await fetch(EVOLUTION_URL + pathname, {
    method,
    headers: { 'Content-Type': 'application/json', apikey: EVOLUTION_KEY },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20000),
  });
  const text = await res.text();
  try { return { ok: res.ok, data: JSON.parse(text) }; }
  catch (err) { return { ok: res.ok, data: { raw: text } }; }
}

// Every country: [code, name, dial code, fewest digits, most digits, number may begin with 0, example]
const COUNTRIES = require('./countries.json');

/** Country picker + digits box. The whole number goes out as `name`. */
function phoneField(name, label, opts = {}) {
  const value = String(opts.value || '').trim();
  if (value) opts = { ...opts, like: digits(value) };
  const known = opts.like ? [...COUNTRIES].sort((a, b) => b[2].length - a[2].length).find(c => opts.like.startsWith(c[2])) : null;
  const first = (known && (COUNTRIES.find(c => c[0] === ({ 91: 'IN', 971: 'AE', 968: 'OM', 1: 'US', 44: 'GB', 7: 'RU' })[known[2]]) || known))
    || COUNTRIES.find(c => c[0] === 'AE') || COUNTRIES[0];
  return `<div class="phone">
      <label>${label}
        <select class="ph-country" name="${name}_country" aria-label="Country">${COUNTRIES.map(c => `<option value="${c[0]}" data-d="${c[2]}" data-a="${c[3]}" data-b="${c[4]}" data-z="${c[5]}" data-e="${c[6]}" ${c === first ? 'selected' : ''}>${esc(c[1])} (+${c[2]})</option>`).join('')}</select></label>
      <div class="ph-box"><span class="ph-dial">+${first[2]}</span><input class="ph-num" value="${known && value ? esc(digits(value).slice(known[2].length)) : ''}" type="text" inputmode="numeric" autocomplete="off" ${opts.required ? 'required' : ''} aria-label="Phone number"><span class="ph-count"></span></div>
      <input type="hidden" name="${name}" class="ph-all" value="${esc(value)}" data-was="${esc(value)}">
      <span class="muted ph-hint"></span>
    </div>`;
}

const PHONE_SCRIPT = `<script>
document.querySelectorAll('.phone').forEach(function (box) {
  var sel = box.querySelector('.ph-country'), num = box.querySelector('.ph-num'), all = box.querySelector('.ph-all');
  var hint = box.querySelector('.ph-hint'), count = box.querySelector('.ph-count'), dial = box.querySelector('.ph-dial');
  function rule() { var o = sel.options[sel.selectedIndex].dataset; return { d: o.d, a: +o.a, b: +o.b, z: o.z === '1', e: o.e }; }
  function clean() {
    var r = rule(), v = num.value.replace(/[^0-9]/g, '');
    if (v.length > r.b && v.indexOf(r.d) === 0) { v = v.slice(r.d.length); }
    if (!r.z) { v = v.replace(/^0+/, ''); }
    v = v.slice(0, r.b);
    if (num.value !== v) { num.value = v; }
    dial.textContent = '+' + r.d; num.placeholder = r.e; count.textContent = v.length + '/' + r.b;
    var good = v.length >= r.a && v.length <= r.b;
    all.value = v ? r.d + v : '';
    box.classList.toggle('good', good);
    hint.textContent = !v ? (r.a === r.b ? r.b : r.a + ' to ' + r.b) + ' digits' : good ? '\\u2713 +' + r.d + ' ' + v : (r.a === r.b ? r.b : r.a + ' to ' + r.b) + ' digits, ' + v.length + ' typed';
    num.setCustomValidity(!v || good ? '' : 'This country has ' + (r.a === r.b ? r.b : r.a + ' to ' + r.b) + ' digits.');
  }
  // what is saved stays as it is until somebody types
  var was = all.dataset.was || '', has = was.replace(/[^0-9]/g, '');
  function first() {
    clean();
    if (!was) { return; }
    var same = all.value === has && num.checkValidity();
    all.value = was;
    if (!same) { num.value = ''; num.required = false; num.setCustomValidity(''); count.textContent = ''; box.classList.remove('good'); hint.textContent = 'Saved now: ' + was; }
  }
  num.addEventListener('keydown', function (e) { if (e.key.length === 1 && !/[0-9]/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); } });
  num.addEventListener('input', clean); sel.addEventListener('change', function () { if (was && all.value === was && !num.value) { var r = rule(); dial.textContent = '+' + r.d; num.placeholder = r.e; return; } clean(); }); first();
});
</script>`;

// Copies the key of one number. The old way first: it is done at once, before
// the Odoo tab takes the focus, and it also works on a plain http address.
const KEY_SCRIPT = `<script>
function wapCopyKey(b, say) {
  var row = b.closest('.num-row'), text = row.querySelector('.key-line code').textContent.trim();
  var box = document.createElement('textarea'), ok = false;
  box.value = text; box.style.position = 'fixed'; box.style.opacity = '0';
  document.body.appendChild(box); box.select();
  try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  box.remove();
  var line = row.querySelector('.key-line');
  if (ok) { line.classList.add('copied'); setTimeout(function () { line.classList.remove('copied'); }, 1800); }
  if (say) {
    var tell = function (done) { b.textContent = done ? 'Copied' : 'Copy it by hand'; b.classList.toggle('done', done); setTimeout(function () { b.textContent = 'Copy'; b.classList.remove('done'); }, 1800); };
    if (ok || !navigator.clipboard) { tell(ok); }
    else { navigator.clipboard.writeText(text).then(function () { tell(true); }, function () { tell(false); }); }
  } else if (!ok && navigator.clipboard) { navigator.clipboard.writeText(text).catch(function () {}); }
  return ok;
}
function wapConnect(b) {
  if (wapCopyKey(b, false) && window.wapToast) { window.wapToast('Key copied. Paste it in Setup Key in Odoo.'); }
  var steps = b.closest('.num-row').querySelector('details.odoo-steps');
  if (steps) { steps.open = true; }
}
</script>`;

const TABS_SCRIPT = `<script>
(function () {
  var links = document.querySelectorAll('.tabs a'), parts = document.querySelectorAll('section.tab'), key = 'wapTab' + location.pathname;
  function keep(v) { try { if (v) { sessionStorage.setItem(key, v); } return sessionStorage.getItem(key) || ''; } catch (e) { return ''; } }
  function show(name, save) {
    var there = false;
    parts.forEach(function (p) { if (p.dataset.tab === name) { there = true; } });
    if (!there) { name = 'numbers'; }
    parts.forEach(function (p) { p.hidden = p.dataset.tab !== name; });
    links.forEach(function (a) { a.classList.toggle('on', a.dataset.tab === name); if (a.dataset.tab === name) { a.setAttribute('aria-current', 'page'); } else { a.removeAttribute('aria-current'); } });
    if (save) { keep(name); }
  }
  function wanted() {
    var h = location.hash.slice(1);
    if (/^n[0-9]+$/.test(h)) { return 'numbers'; }
    return h || (/[?&]tested=/.test(location.search) ? 'email' : keep()) || 'numbers';
  }
  links.forEach(function (a) { a.addEventListener('click', function (e) { e.preventDefault(); show(a.dataset.tab, true); history.replaceState(null, '', location.pathname + '#' + a.dataset.tab); }); });
  window.addEventListener('hashchange', function () { show(wanted(), true); });
  show(wanted(), true);
  var at = location.hash && document.getElementById(location.hash.slice(1));
  if (at) { at.scrollIntoView(); }
  // a form goes back to the tab it was sent from
  document.querySelectorAll('section.tab form').forEach(function (f) { f.addEventListener('submit', function () { keep(f.closest('section.tab').dataset.tab); }); });
})();
</script>`;

/** What is wrong with a number typed for a country, or ''. */
function phoneWrong(b, name) {
  const n = digits(b[name]);
  const c = COUNTRIES.find(x => x[0] === String(b[name + '_country'] || ''));
  if (!n || !c) return '';
  const own = n.startsWith(c[2]) ? n.slice(c[2].length) : '';
  if (own.length >= c[3] && own.length <= c[4]) return '';
  return `A number in ${c[1]} has ${c[3] === c[4] ? c[4] : c[3] + ' to ' + c[4]} digits after +${c[2]}.`;
}

/** "+971501234567"; what is no plain number stays as typed. */
function plusNumber(value) {
  const text = String(value || '').trim();
  return /^[0-9]+$/.test(text) ? '+' + text : text;
}

function digits(value) {
  return String(value || '').replace(/[^0-9]/g, '');
}

/** Every instance the gateway knows, keyed by name. */
async function fetchInstanceMap() {
  const list = await evo('/instance/fetchInstances');
  const map = {};
  for (const entry of (Array.isArray(list.data) ? list.data : [])) {
    const i = entry.instance || entry;
    const name = i.name || i.instanceName;
    if (!name) continue;
    map[name] = {
      state: i.connectionStatus || (i.instance && i.instance.state) || i.state || '',
      owner: digits(String(i.ownerJid || i.owner || '').split('@')[0].split(':')[0]),
      profile: i.profileName || '',
    };
  }
  return map;
}

async function loadNumber(id) {
  const { rows } = await pool.query('SELECT * FROM wap_number WHERE id = $1', [id]);
  return rows[0] || null;
}

/** Every row of one Odoo database: one per number. The first is the oldest. */
/**
 * The last thing this database's Odoo was refused, unless it got through since.
 * Also when it used the key of another database of the same vendor.
 */
async function lastProblem(d, ids) {
  const { rows } = await pool.query(
    `SELECT l.status, l.detail, l.created_at FROM wap_log l
       LEFT JOIN wap_database k ON k.id = l.database_id
      WHERE l.created_at > now() - interval '30 minutes' AND l.remote_ip <> '' AND l.claimed_db = $1
        AND (l.database_id = ANY($2::int[]) OR ((k.company_id = $3 OR l.database_id IS NULL) AND l.claimed_url = $4))
      ORDER BY l.id DESC LIMIT 1`, [d.db_name, ids, d.company_id, origin(d.base_url)]);
  return rows.length && rows[0].status === 'refused' ? rows[0] : null;
}

async function siblings(row) {
  if (!row.server_id) {
    const own = await pool.query('SELECT server_id FROM wap_database WHERE id = $1', [row.id]);
    row.server_id = own.rows.length ? own.rows[0].server_id : 0;
  }
  const { rows } = await pool.query(
    `SELECT d.*, n.label AS number_label, n.authorized_number, n.pair_state, n.active AS number_active
       FROM wap_database d LEFT JOIN wap_number n ON n.id = d.number_id
      WHERE d.server_id = $1 AND d.db_name = $2 ORDER BY d.id`, [row.server_id, row.db_name]);
  return rows;
}

/** The databases a number is assigned to. */
async function numberDatabases(numberId) {
  const { rows } = await pool.query(
    `SELECT d.id, d.db_name, d.active AND d.off_by = '' AS active, d.odoo_webhook_url, s.base_url
       FROM wap_database d JOIN wap_server s ON s.id = d.server_id
      WHERE d.number_id = $1 ORDER BY d.db_name`, [numberId]);
  return rows;
}

/**
 * Point the instance's webhook at THIS panel. The panel then fans every
 * incoming message out to all the databases on that number (see /hook/).
 */
async function applyHook(n) {
  const base = (process.env.PANEL_PUBLIC_URL || `http://127.0.0.1:${PORT}`).replace(/\/+$/, '');
  try {
    const r = await evo(`/webhook/set/${n.instance_name}`, 'POST', {
      webhook: {
        enabled: true,
        url: `${base}/hook/${n.instance_name}?s=${n.hook_secret}`,
        byEvents: false,
        base64: false,
        headers: { 'X-Hook-Secret': n.hook_secret, 'Content-Type': 'application/json' },
        events: ['MESSAGES_UPSERT'],
      },
    });
    await pool.query('UPDATE wap_number SET webhook_applied = $1 WHERE id = $2', [!!r.ok, n.id]);
    return r.ok;
  } catch (err) {
    console.error(`[panel] webhook for ${n.instance_name} not applied: ${err.message}`);
    return false;
  }
}

/**
 * Compare what is paired with what is allowed, and act on it.
 *
 * Runs on the QR page, on /v1/config and every 30 s. A phone that is not the
 * authorized one is logged out on the spot, the attempt is recorded on every
 * database of the number, and the number stays refused until the right phone
 * scans. Empty authorized_number means "adopt whatever scanned" - that is how
 * the pre-existing shared number picked up its digits after the upgrade.
 */
async function checkPairing(n, map) {
  const e = map[n.instance_name];
  const next = { pair_state: n.pair_state, paired_number: n.paired_number, profile_name: n.profile_name,
                 authorized_number: n.authorized_number };
  let wrong = '';

  if (!e) {
    next.pair_state = 'missing';
    next.paired_number = '';
  } else if (e.state === 'open' && e.owner) {
    if (!n.authorized_number) {
      next.authorized_number = e.owner;
      next.pair_state = 'open';
      next.paired_number = e.owner;
      next.profile_name = e.profile;
    } else if (e.owner !== n.authorized_number) {
      wrong = e.owner;
      try { await evo(`/instance/logout/${n.instance_name}`, 'DELETE'); } catch (err) { /* retried by the sweep */ }
      next.pair_state = 'wrong_number';
      next.paired_number = '';
      next.profile_name = '';
    } else {
      next.pair_state = 'open';
      next.paired_number = e.owner;
      next.profile_name = e.profile;
    }
  } else {
    // close / connecting, or open with the owner not reported yet. A
    // wrong-number verdict stays until the right phone scans.
    if (n.pair_state === 'wrong_number') { /* sticky */ }
    else if (e.state === 'open') next.pair_state = n.pair_state === 'open' ? 'open' : 'connecting';
    else next.pair_state = e.state || 'close';
    if (next.pair_state !== 'open') { next.paired_number = ''; next.profile_name = ''; }
  }

  const changed = next.pair_state !== n.pair_state || next.paired_number !== n.paired_number
    || next.profile_name !== n.profile_name || next.authorized_number !== n.authorized_number;
  if (wrong) {
    await pool.query(
      `UPDATE wap_number SET pair_state=$1, paired_number='', profile_name='',
              last_wrong_number=$2, wrong_number_at=now(), wrong_number_count=wrong_number_count+1,
              pair_checked_at=now() WHERE id=$3`, ['wrong_number', wrong, n.id]);
    const detail = `scanned with ${wrong}, only ${n.authorized_number} is allowed - logged out`;
    for (const d of await numberDatabases(n.id)) {
      await log({ databaseId: d.id, db: d.db_name, phone: wrong, endpoint: 'pair', status: 'wrong_number', detail });
    }
    console.warn(`[panel] ${n.instance_name}: ${detail}`);
  } else if (changed) {
    await pool.query(
      `UPDATE wap_number SET pair_state=$1, paired_number=$2, profile_name=$3, authorized_number=$4,
              pair_checked_at=now() WHERE id=$5`,
      [next.pair_state, next.paired_number, next.profile_name, next.authorized_number, n.id]);
  } else {
    await pool.query('UPDATE wap_number SET pair_checked_at=now() WHERE id=$1', [n.id]);
  }
  return { ...n, ...next, last_wrong_number: wrong || n.last_wrong_number };
}

/** Refresh one number against the gateway; returns the updated row. */
async function refreshNumber(n) {
  try {
    const map = await fetchInstanceMap();
    return await checkPairing(n, map);
  } catch (err) {
    return { ...n, gateway_error: err.message };
  }
}

let sweepInFlight = false;
async function pairingSweep() {
  if (sweepInFlight) return;
  sweepInFlight = true;
  try {
    const map = await fetchInstanceMap();
    const { rows } = await pool.query('SELECT * FROM wap_number WHERE active ORDER BY id');
    for (const n of rows) {
      await checkPairing(n, map);
      if (!n.webhook_applied) await applyHook(n);
    }
  } catch (err) {
    console.error('[panel] pairing sweep skipped:', err.message);
  } finally {
    sweepInFlight = false;
  }
}

/**
 * Evolution -> panel -> every database on that number.
 *
 * The gateway can call one URL per instance. With a number shared by several
 * databases that URL is this one, and the panel forwards the event to each
 * Odoo in turn. Each Odoo already ignores senders it does not know.
 */
app.post('/hook/:instance', async (req, res) => {
  const { rows } = await pool.query('SELECT * FROM wap_number WHERE instance_name = $1', [req.params.instance]);
  if (!rows.length) return res.status(404).json({ error: 'unknown instance' });
  const n = rows[0];
  const secret = String(req.headers['x-hook-secret'] || req.query.s || '');
  if (!n.hook_secret || secret !== n.hook_secret) return res.status(403).json({ error: 'bad secret' });
  res.json({ ok: true });

  const arrived = nextArrival();
  const payload = JSON.stringify(req.body || {});
  const targets = (await numberDatabases(n.id)).filter(d => d.active && d.odoo_webhook_url);
  await Promise.allSettled(targets.map(async d => {
    // Behind those already waiting, so messages keep their order.
    const waiting = await pool.query('SELECT 1 FROM wap_retry WHERE database_id = $1 LIMIT 1', [d.id]);
    if (waiting.rowCount) return keepForLater(d, n.id, payload, '', arrived);
    const got = await deliver(d, payload);
    if (got.ok) return;
    if (got.again) return keepForLater(d, n.id, payload, got.detail, arrived);
    await log({ databaseId: d.id, db: d.db_name, endpoint: 'hook', status: 'failed', detail: got.detail });
  }));
});

// Odoo was not there to read it (restarting): its proxy says so, or nothing
// listens. Anything else - a timeout, a 500, a 504 - may have been handled and
// is never sent twice.
const NOT_THERE = new Set([502, 503, 521, 523, 530]);
const NO_LISTENER = new Set(['ECONNREFUSED', 'ENOTFOUND', 'EAI_AGAIN', 'EHOSTUNREACH', 'ENETUNREACH']);
const RETRY_AFTER = [5, 10, 20, 30];     // seconds, then every 30
const RETRY_FOR = 570;                   // Odoo forgets a message id after 600 s

async function deliver(d, payload) {
  try {
    const r = await fetch(d.odoo_webhook_url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Odoo-Database': d.db_name },
      body: payload,
      signal: AbortSignal.timeout(10000),
    });
    if (r.ok) return { ok: true };
    return { again: NOT_THERE.has(r.status), detail: `Odoo answered ${r.status} on ${shortHook(d)}` };
  } catch (err) {
    const code = (err.cause && err.cause.code) || '';
    return { again: NO_LISTENER.has(code), detail: `Odoo unreachable at ${shortHook(d)}: ${code || err.message}` };
  }
}

/** The address without its secret: the log is shown on pages. */
function shortHook(d) {
  return String(d.odoo_webhook_url || '').replace(/(\/webhook\/).*/, '$1...');
}

let lastArrival = 0;
/** Grows with every message: the order they came in, whatever is saved first. */
function nextArrival() {
  lastArrival = Math.max(lastArrival + 1, Date.now() * 1000);
  return lastArrival;
}

async function keepForLater(d, numberId, payload, detail, arrived) {
  await pool.query(
    `INSERT INTO wap_retry (database_id, number_id, payload, arrived, next_at)
     VALUES ($1, $2, $3, $4, now() + interval '5 seconds')`, [d.id, numberId, payload, arrived]);
  if (detail) {
    await log({ databaseId: d.id, db: d.db_name, endpoint: 'hook', status: 'waiting', detail: detail + ' - kept, sent again' });
  }
}

let retryInFlight = false;
/** Send what waits, oldest first, one database after the other's first failure. */
async function retrySweep() {
  if (retryInFlight) return;
  retryInFlight = true;
  try {
    await pool.query('SELECT 1');
    const dead = await pool.query(
      `DELETE FROM wap_retry r USING wap_database d
        WHERE d.id = r.database_id AND (r.first_at < now() - make_interval(secs => $1) OR NOT d.active OR d.off_by <> ''
              OR d.odoo_webhook_url = '' OR d.number_id IS DISTINCT FROM r.number_id)
        RETURNING r.database_id, d.db_name`, [RETRY_FOR]);
    for (const g of new Map(dead.rows.map(x => [x.database_id, x])).values()) {
      const n = dead.rows.filter(x => x.database_id === g.database_id).length;
      await log({ databaseId: g.database_id, db: g.db_name, endpoint: 'hook', status: 'failed',
                  detail: `${n} incoming message(s) given up: Odoo was not there in time` });
    }
    const due = await pool.query(
      `SELECT DISTINCT r.database_id FROM wap_retry r
        WHERE r.id = (SELECT x.id FROM wap_retry x WHERE x.database_id = r.database_id ORDER BY x.arrived, x.id LIMIT 1) AND r.next_at <= now()`);
    await Promise.allSettled(due.rows.map(async row => {
      for (;;) {
        const { rows } = await pool.query(
          `SELECT r.*, d.db_name, d.odoo_webhook_url FROM wap_retry r JOIN wap_database d ON d.id = r.database_id
            WHERE r.database_id = $1 ORDER BY r.arrived, r.id LIMIT 1`, [row.database_id]);
        if (!rows.length) return;
        const m = rows[0];
        const got = await deliver({ id: m.database_id, ...m }, m.payload);
        if (!got.ok && got.again) {
          const wait = RETRY_AFTER[Math.min(m.tries, RETRY_AFTER.length - 1)];
          await pool.query('UPDATE wap_retry SET tries = tries + 1, next_at = now() + make_interval(secs => $1) WHERE id = $2',
            [wait, m.id]);
          return;
        }
        await pool.query('DELETE FROM wap_retry WHERE id = $1', [m.id]);
        await log({ databaseId: m.database_id, db: m.db_name, endpoint: 'hook',
                    status: got.ok ? 'delivered' : 'failed', detail: got.ok ? 'sent again after Odoo came back' : got.detail });
      }
    }));
  } catch (err) {
    console.error('[panel] retry sweep skipped:', err.message);
  } finally {
    retryInFlight = false;
  }
}

// ---------------------------------------------------------------- self-setup

/**
 * A setup key carries the panel's own address inside it.
 *
 *   wa1_<base64url of "<panel url>|<token>">
 */
function setupKey(token) {
  const base = (process.env.PANEL_PUBLIC_URL || `http://127.0.0.1:${PORT}`).replace(/\/+$/, '');
  return 'wa1_' + Buffer.from(`${base}|${token}`, 'utf8').toString('base64url');
}

/**
 * GET /v1/config - what this database should use.
 *
 * Which number it sends on and the ONE phone allowed to scan it, the name it
 * signs as, the mail address it sends from. Odoo shows these read-only. Odoo
 * also tells the panel its webhook URL here (X-Odoo-Webhook), so incoming
 * messages can be forwarded to it without anybody typing the address.
 */
app.get('/v1/config', async (req, res) => {
  const who = await identify(req);
  if (who.error) {
    return res.status(403).json({ error: 'Refused', detail: who.error });
  }
  const row = who.row;

  const hook = String(req.headers['x-odoo-webhook'] || '').trim();
  if (hook && /^https?:\/\//i.test(hook) && hook !== row.odoo_webhook_url) {
    await pool.query('UPDATE wap_database SET odoo_webhook_url = $1 WHERE id = $2', [hook.slice(0, 500), row.id]);
  }

  const mail = await pool.query(
    'SELECT from_email, from_name FROM wap_email WHERE database_id = $1 AND active', [row.id]);

  let n = row.number_id ? await loadNumber(row.number_id) : null;
  if (n) n = await refreshNumber(n);
  const shared = n ? (await numberDatabases(n.id)).filter(d => d.id !== row.id).length : 0;
  const gate = numberGate({ ...row, ...(n ? {
    instance_name: n.instance_name, authorized_number: n.authorized_number, pair_state: n.pair_state,
    last_wrong_number: n.last_wrong_number, number_active: n.active } : {}) });

  res.json({
    vendor: row.company_name,
    instance: n ? n.instance_name : '',
    tenant_label: row.tenant_label || row.company_name,
    contact_number: row.contact_number || '',
    database: row.db_name,
    server: row.base_url,
    whatsapp: {
      state: n ? (n.gateway_error ? 'unreachable' : n.pair_state) : 'none',
      authorized_number: n ? n.authorized_number : '',
      paired_number: n ? n.paired_number : '',
      instance: n ? n.instance_name : '',
      shared_with: shared,
      detail: gate,
    },
    email: mail.rows.length
      ? { configured: true, from: mail.rows[0].from_email, name: mail.rows[0].from_name }
      : { configured: false },
    limits: { daily_cap: row.daily_cap, per_minute: row.per_minute },
  });
});

let addingNumber = Promise.resolve();

/**
 * Numbers of the caller's own database.
 *
 * GET  - which there are (never a key).
 * POST - one more: {number, label}. Only when the administrator allowed it for
 *        this database, up to the count set there, and only for a phone number
 *        no other database or vendor has. Answers the new number's setup key.
 *        Asked again for a number of this database that no Odoo session uses
 *        yet (its first answer was lost), it gets a fresh key.
 */
const FREE_NUMBERS = `SELECT n.* FROM wap_number n WHERE n.active AND n.company_id IS NOT DISTINCT FROM $1
        AND NOT EXISTS (SELECT 1 FROM wap_database x WHERE x.number_id = n.id)
      ORDER BY (n.pair_state = 'open') DESC, n.label`;

/**
 * Where a number is, for the database that asks: here (in this database), off
 * (here, turned off), free (of this vendor, in no database), elsewhere, new.
 * Never whose it is.
 */
async function whereIs(row, number, all) {
  const same = all.filter(x => x.number_id && x.authorized_number === number);
  if (same.length) {
    const x = same.find(y => !y.off_by) || same[0];
    return { where: x.off_by ? 'off' : 'here', row: x };
  }
  const { rows } = await pool.query(
    `SELECT n.*, EXISTS (SELECT 1 FROM wap_database x WHERE x.number_id = n.id) AS taken
       FROM wap_number n WHERE n.authorized_number = $1 ORDER BY n.active DESC, n.id DESC`, [number]);
  if (!rows.length) return { where: 'new' };
  if (rows.some(n => n.taken)) return { where: 'elsewhere' };
  const free = rows.find(n => n.active && n.company_id === row.company_id);
  return free ? { where: 'free', row: free } : { where: 'elsewhere' };
}

// How often a database asks where a number is: 30 times a minute.
const asked = new Map();
function mayAsk(id) {
  const now = Date.now();
  const list = (asked.get(id) || []).filter(t => now - t < 60000);
  if (list.length >= 30) return false;
  list.push(now);
  asked.set(id, list);
  return true;
}

app.get('/v1/numbers', async (req, res) => {
  const who = await identify(req);
  if (who.error) return res.status(403).json({ error: 'Refused', detail: who.error });
  const all = await siblings(who.row);
  if (req.query.check !== undefined) {
    const number = digits(req.query.check);
    if (number.length < 8 || number.length > 15) return res.status(400).json({ error: 'Refused', detail: 'The phone number needs 8 to 15 digits, with the country code.' });
    if (!mayAsk(who.row.id)) return res.status(429).json({ error: 'Refused', detail: 'too many checks, try again in a minute' });
    const it = await whereIs(who.row, number, all);
    const mine = it.where === 'here' || it.where === 'off';
    return res.json({ check: it.where, in_use: mine ? !!it.row.odoo_webhook_url : false });
  }
  const max = Math.max(0, ...all.map(x => x.own_numbers_max));
  // of this vendor and in no database, as on the panel page; only for who may add
  const free = max ? (await pool.query(FREE_NUMBERS, [who.row.company_id])).rows : [];
  res.json({
    may_add: max,
    free: free.filter(x => x.authorized_number).map(x => ({ label: x.label, authorized_number: x.authorized_number, state: x.pair_state })),
    numbers: all.filter(x => x.number_id).map(x => ({
      label: x.number_label, authorized_number: x.authorized_number, state: x.pair_state, in_use: !!x.odoo_webhook_url })),
  });
});

app.post('/v1/numbers', async (req, res) => {
  const who = await identify(req);
  if (who.error) {
    await log({ databaseId: who.row ? who.row.id : null, ip: clientIp(req), endpoint: '/v1/numbers', status: 'refused', detail: who.error });
    return res.status(403).json({ error: 'Refused', detail: who.error });
  }
  const run = addingNumber.then(() => addOwnNumber(who.row, req.body || {}, clientIp(req)));
  addingNumber = run.catch(() => {});          // one at a time
  try {
    const out = await run;
    res.status(out.status || 200).json(out.body);
  } catch (err) {
    console.error('[panel] number not added:', err.message);
    res.status(500).json({ error: 'Failed', detail: 'the number could not be added' });
  }
});

async function addOwnNumber(row, body, ip) {
  const refuse = async (detail, status = 409) => {
    await log({ databaseId: row.id, db: row.db_name, ip, endpoint: '/v1/numbers', status: 'refused', detail });
    return { status, body: { error: 'Refused', detail } };
  };
  const number = digits(body.number);
  const label = String(body.label || '').trim().slice(0, 60);
  const all = await siblings(row);
  const max = Math.max(0, ...all.map(x => x.own_numbers_max));
  if (!max) return refuse('adding numbers from Odoo is not allowed for this database; the panel administrator allows it', 403);
  if (number.length < 8 || number.length > 15) return refuse('The phone number needs 8 to 15 digits, with the country code.', 400);
  const it = await whereIs(row, number, all);
  if (it.where === 'off') return refuse(`+${number} is in this database and turned off.`);
  if (it.where === 'here') {
    const same = it.row;
    if (same.odoo_webhook_url || same.id === row.id) return refuse(`+${number} is already connected to this database.`);
    const fresh = token();
    await pool.query('UPDATE wap_database SET token = $1 WHERE id = $2', [fresh, same.id]);
    return { body: { key: setupKey(fresh), authorized_number: number, state: same.pair_state } };
  }
  if (all.filter(x => x.number_id).length >= max) return refuse(`This database may have ${max} number(s); the panel administrator can allow more.`);
  let numberId;
  if (it.where === 'elsewhere') return refuse(`+${number} is already used elsewhere.`);
  if (it.where === 'free') {
    numberId = it.row.id;
  } else {
    const made = await createNumber(row.company_id, label || (row.db_name + ' +' + number), number);
    if (made.error) return refuse(made.error);
    numberId = made.row.id;
  }
  const fresh = token();
  await pool.query(
    `INSERT INTO wap_database (server_id, company_id, number_id, db_name, tenant_label, contact_number,
                               token, daily_cap, per_minute, sign_messages, active, own_numbers_max)
     SELECT server_id, company_id, $2, db_name, tenant_label, contact_number,
            $3, daily_cap, per_minute, sign_messages, active, own_numbers_max
       FROM wap_database WHERE id = $1`, [row.id, numberId, fresh]);
  await log({ databaseId: row.id, db: row.db_name, ip, phone: number, endpoint: '/v1/numbers', status: 'number added', detail: 'from Odoo' });
  const n = await loadNumber(numberId);
  return { body: { key: setupKey(fresh), authorized_number: n.authorized_number, state: n.pair_state } };
}

/**
 * POST /v1/self {do: 'off' | 'on' | 'remove'} - a key about its own number.
 * On: only what Odoo itself turned off. Remove: never the only number.
 */
app.post('/v1/self', async (req, res) => {
  const who = await identify(req);
  const what = String((req.body || {}).do || '');
  const row = who.row;
  const mine = row && (!who.error || (who.off && ['on', 'remove'].includes(what)));
  const refuse = async (detail, status = 403) => {
    await log({ databaseId: row ? row.id : null, db: row ? row.db_name : '', ip: clientIp(req), endpoint: '/v1/self', status: 'refused', detail });
    return res.status(status).json({ error: 'Refused', detail });
  };
  if (!mine) return refuse(who.error || 'refused');
  if (what === 'off') {
    await pool.query(`UPDATE wap_database SET off_by = 'odoo' WHERE id = $1`, [row.id]);
  } else if (what === 'on') {
    if (who.off && who.off !== 'odoo') return refuse('the panel administrator turned this number off');
    await pool.query(`UPDATE wap_database SET off_by = '' WHERE id = $1`, [row.id]);
  } else if (what === 'remove') {
    if ((await siblings(row)).length < 2) return refuse('This is the only number of the database; it cannot be removed.', 409);
    await dropRow(row);
  } else {
    return refuse('do: off, on or remove', 400);
  }
  await log({ databaseId: what === 'remove' ? null : row.id, db: row.db_name, ip: clientIp(req), endpoint: '/v1/self', status: 'number ' + what, detail: 'from Odoo' });
  res.json({ ok: true });
});

/** Take one number out of a database; what belongs to the whole database stays with it. */
async function dropRow(row) {
  const rest = (await siblings(row)).filter(x => x.id !== row.id);
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    if (rest.length) {
      const heir = rest[0].id;
      await client.query(`UPDATE wap_email SET database_id = $1 WHERE database_id = $2
                             AND NOT EXISTS (SELECT 1 FROM wap_email e WHERE e.database_id = $1)`, [heir, row.id]);
      await client.query(`UPDATE wap_admin SET database_id = $1 WHERE database_id = $2
                             AND NOT EXISTS (SELECT 1 FROM wap_admin a WHERE a.database_id = $1)`, [heir, row.id]);
      await client.query(`UPDATE wap_optout o SET database_id = $1 WHERE database_id = $2
                             AND NOT EXISTS (SELECT 1 FROM wap_optout x WHERE x.database_id = $1 AND x.phone = o.phone)`, [heir, row.id]);
      await client.query(`UPDATE wap_email_optout o SET database_id = $1 WHERE database_id = $2
                             AND NOT EXISTS (SELECT 1 FROM wap_email_optout x WHERE x.database_id = $1 AND lower(x.email) = lower(o.email))`, [heir, row.id]);
    }
    await client.query('DELETE FROM wap_database WHERE id=$1', [row.id]);
    await client.query('COMMIT');
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
  return rest.length ? rest[0].id : 0;
}

const qrAsked = new Map();

/**
 * GET /v1/qr - the QR of THIS key's number, for the Odoo administrator's
 * "Connect a number" screen. Only while it is not connected, and only for a
 * number whose phone is written down: any other phone is logged out again.
 */
app.get('/v1/qr', async (req, res) => {
  const who = await identify(req);
  if (who.error) return res.status(403).json({ error: 'Refused', detail: who.error });
  const row = who.row;
  let n = row.number_id ? await loadNumber(row.number_id) : null;
  if (!n || !n.active) return res.status(403).json({ error: 'Refused', detail: 'no WhatsApp number assigned, or it is switched off' });
  n = await refreshNumber(n);
  const out = { state: n.gateway_error ? 'unreachable' : n.pair_state, authorized_number: n.authorized_number, qr: '' };
  if (!n.authorized_number) return res.status(403).json({ error: 'Refused', detail: 'this number is connected in the panel' });
  if (['open', 'missing', 'unreachable'].includes(out.state)) return res.json(out);
  const last = qrAsked.get(n.id);
  if (last && Date.now() - last.at < 4000) return res.json({ ...out, qr: last.qr });
  try {
    const c = await evo(`/instance/connect/${n.instance_name}`);
    if (c.data && c.data.base64) out.qr = c.data.base64;
  } catch (err) { /* asked again in a few seconds */ }
  qrAsked.set(n.id, { at: Date.now(), qr: out.qr });
  await log({ databaseId: row.id, db: row.db_name, ip: clientIp(req), endpoint: '/v1/qr', status: 'read' });
  res.set('Cache-Control', 'no-store');
  res.json(out);
});

// ---------------------------------------------------------------- email

/**
 * POST /email/send  - same key, same URL+DB check. The account is the
 * DATABASE's own; whatever "from" the caller puts in the body is dropped.
 *
 * Body: {to, subject, body_html, body_text, cc, bcc, reply_to, attachments[]}
 */
app.post('/email/send', async (req, res) => {
  const ip = clientIp(req);
  const claimedDb = String(req.headers['x-odoo-db'] || '').trim();
  const claimedUrl = origin(req.headers['x-odoo-url'] || '');

  const who = await identify(req);
  if (who.error) {
    await log({ databaseId: who.row ? who.row.id : null, url: claimedUrl, db: claimedDb,
                ip, endpoint: '/email/send', channel: 'email',
                status: 'refused', detail: who.error });
    return res.status(403).json({ error: 'Refused', detail: who.error });
  }
  const row = who.row;
  const body = req.body || {};
  delete body.from;
  delete body.sender;
  const to = String(body.to || '').trim();
  if (!to) return res.status(400).json({ error: 'No recipient' });

  const acct = await pool.query(
    'SELECT * FROM wap_email WHERE database_id = $1 AND active = TRUE', [row.id]);
  if (!acct.rows.length) {
    const detail = `database ${row.db_name} has no email account set up in the panel`;
    await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone: to,
                endpoint: '/email/send', channel: 'email', status: 'failed', detail });
    return res.status(503).json({ error: 'No email account', detail });
  }
  const account = acct.rows[0];

  const optout = await pool.query(
    `SELECT 1 FROM wap_email_optout
      WHERE lower(email) = lower($1)
        AND (database_id = $2 OR (database_id IS NULL AND company_id = $3))`,
    [to, row.id, row.company_id]);
  if (optout.rowCount) {
    await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone: to,
                endpoint: '/email/send', channel: 'email',
                status: 'blocked', detail: 'recipient has unsubscribed' });
    return res.status(429).json({ error: 'Blocked', detail: 'recipient has unsubscribed' });
  }

  const text = [body.subject, body.body_text, body.body_html].filter(Boolean).join(' ').toLowerCase();
  const blocks = await pool.query('SELECT pattern, reason FROM wap_block');
  for (const b of blocks.rows) {
    if (text.includes(String(b.pattern).toLowerCase())) {
      const detail = `blocked content: ${b.pattern}`;
      await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone: to,
                  endpoint: '/email/send', channel: 'email', status: 'blocked', detail });
      return res.status(429).json({ error: 'Blocked', detail });
    }
  }

  const day = await pool.query(
    `SELECT count(*)::int AS n FROM wap_log
      WHERE database_id = $1 AND channel = 'email' AND status = 'sent'
        AND created_at >= date_trunc('day', now())`, [row.id]);
  if (account.daily_cap > 0 && day.rows[0].n >= account.daily_cap) {
    const detail = `daily email cap reached (${day.rows[0].n}/${account.daily_cap})`;
    await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone: to,
                endpoint: '/email/send', channel: 'email', status: 'blocked', detail });
    return res.status(429).json({ error: 'Blocked', detail });
  }
  const minute = await pool.query(
    `SELECT count(*)::int AS n FROM wap_log
      WHERE database_id = $1 AND channel = 'email' AND status = 'sent'
        AND created_at >= now() - interval '1 minute'`, [row.id]);
  if (account.per_minute > 0 && minute.rows[0].n >= account.per_minute) {
    const detail = `email rate limit reached (${minute.rows[0].n}/min)`;
    await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone: to,
                endpoint: '/email/send', channel: 'email', status: 'blocked', detail });
    return res.status(429).json({ error: 'Blocked', detail });
  }

  // Signed after the content checks, so the panel's own footer is never the
  // thing that trips a blocked word.
  const signed = { ...body };
  if (row.sign_messages) {
    const sig = emailSignature(row);
    if (signed.body_html) signed.body_html = appendToHtml(signed.body_html, sig.html);
    if (signed.body_text && !signed.body_text.includes(NOTICE)) {
      signed.body_text = `${signed.body_text}\n\n${sig.text}`;
    }
    if (!signed.body_html && !signed.body_text) signed.body_text = sig.text;
  }
  if (!signed.body_html && !signed.body_text) signed.body_text = '';

  const result = await mailer.send(account, signed);
  await log({ databaseId: row.id, url: claimedUrl, db: row.db_name, ip, phone: to,
              endpoint: '/email/send', channel: 'email',
              status: result.ok ? 'sent' : 'failed',
              detail: result.ok ? '' : result.error });
  if (!result.ok) return res.status(502).json({ error: 'Send failed', detail: result.error });
  return res.json({ ok: true, id: result.id, accepted: result.accepted });
});


// ---------------------------------------------------------------- admin

app.use(session({
  name: 'wapanel',
  secret: process.env.PANEL_SESSION_SECRET || 'change-me',
  resave: false,
  saveUninitialized: false,
  cookie: { httpOnly: true, sameSite: 'lax', maxAge: 8 * 60 * 60 * 1000 },
}));

/** What the header shows and which pages it links. */
function nav(req) {
  const s = req.session || {};
  const who = s.role === 'admin' ? 'platform administrator'
    : s.role === 'vendor' ? `${s.vendor} · vendor`
    : s.role === 'client' ? `${s.vendor} · ${s.dbName}` : '';
  return { role: s.role || 'admin', who };
}

function page(req, res, title, body, status = 200) {
  if (body.includes('class="phone"')) body += PHONE_SCRIPT;
  res.status(status).send(layout(title, body, nav(req)));
}

function forbidden(req, res, why) {
  return page(req, res, 'Not allowed', `
    <div class="card narrow"><h1>Not allowed</h1>
    <p>${esc(why || 'Your login does not cover this.')}</p>
    <a class="btn" href="/">Back</a></div>`, 403);
}

function requireLogin(req, res, next) {
  if (req.session && req.session.adminId) return next();
  return res.redirect('/login');
}

function requireRole(...roles) {
  return (req, res, next) => {
    if (req.session && roles.includes(req.session.role)) return next();
    return forbidden(req, res, `Only ${roles.join(' or ')} logins can do this.`);
  };
}
const requireAdmin = requireRole('admin');
const requireVendorOrAdmin = requireRole('admin', 'vendor');

/**
 * Load the database named in the URL and refuse it unless the login covers it.
 * Every /database/:id route goes through here, so a changed id in the address
 * bar is answered with 403, never with somebody else's page.
 */
function scopeDatabase(param = 'id') {
  return async (req, res, next) => {
    const { rows } = await pool.query(
      `SELECT d.*, s.base_url, s.name AS server_name, c.name AS company_name,
              n.label AS number_label, n.instance_name, n.authorized_number, n.paired_number,
              n.pair_state, n.last_wrong_number, n.active AS number_active,
              e.id AS email_id, e.from_email, e.from_name, e.host, e.port, e.secure,
              e.username AS email_username, e.active AS email_active,
              e.daily_cap AS email_daily_cap, e.per_minute AS email_per_minute,
              (SELECT username FROM wap_admin a WHERE a.database_id = d.id LIMIT 1) AS client_username
         FROM wap_database d
         JOIN wap_server s ON s.id = d.server_id
         LEFT JOIN wap_company c ON c.id = d.company_id
         LEFT JOIN wap_number n ON n.id = d.number_id
         LEFT JOIN wap_email e ON e.database_id = d.id
        WHERE d.id = $1`, [Number(req.params[param]) || 0]);
    if (!rows.length) return page(req, res, 'Not found', '<div class="card narrow"><h1>No such database</h1><a class="btn" href="/">Back</a></div>', 404);
    const d = rows[0];
    const s = req.session;
    if (s.role === 'vendor' && d.company_id !== s.companyId) return forbidden(req, res, 'That database belongs to another vendor.');
    if (s.role === 'client' && d.id !== s.databaseId) return forbidden(req, res, 'That is not your database.');
    req.db = d;
    next();
  };
}

/** Same for a number: admin any; vendor its own; client the one on its database. */
function scopeNumber(param = 'id') {
  return async (req, res, next) => {
    const { rows } = await pool.query(
      `SELECT n.*, c.name AS company_name FROM wap_number n
         JOIN wap_company c ON c.id = n.company_id WHERE n.id = $1`, [Number(req.params[param]) || 0]);
    if (!rows.length) return page(req, res, 'Not found', '<div class="card narrow"><h1>No such number</h1><a class="btn" href="/">Back</a></div>', 404);
    const n = rows[0];
    const s = req.session;
    if (s.role === 'vendor' && n.company_id !== s.companyId) return forbidden(req, res, 'That number belongs to another vendor.');
    if (s.role === 'client') {
      const own = await pool.query(
        `SELECT 1 FROM wap_database d JOIN wap_database me ON me.id = $1
          WHERE d.server_id = me.server_id AND d.db_name = me.db_name AND d.number_id = $2`, [s.databaseId, n.id]);
      if (!own.rows.length) return forbidden(req, res, 'That number is not assigned to your database.');
    }
    req.number = n;
    next();
  };
}

app.get('/login', (req, res) => {
  res.send(layout('Sign in', `
    <div class="auth-wrap">
      <div class="auth-side">
        <div class="auth-logo"><i></i><i></i>${LOGO}</div>
        <h1>WhatsApp Panel</h1>
        <p>One sign-in for everybody. What you see depends on the login: the
        administrator sees everything, a vendor its own databases and numbers,
        a client its one database.</p>
        <div class="bubbles" aria-hidden="true">
          <span>Scan the number once</span>
          <span>Connected to Odoo &#10003;&#10003;</span>
          <span><span class="dots"><i></i><i></i><i></i></span></span>
        </div>
      </div>
      <form method="post" action="/login" class="card auth-card ${req.query.bad ? 'shake' : ''}">
        <h2>Sign in</h2>
        ${req.query.bad ? '<p class="wrong" role="alert">Wrong vendor, username or password.</p>' : ''}
        <div class="field">
          <label for="si-vendor">Vendor name</label>
          <div class="in"><input id="si-vendor" name="vendor" autofocus placeholder="your software company">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 21V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v16M15 10h4a1 1 0 0 1 1 1v10M3 21h18M8 8h3M8 12h3M8 16h3"/></svg></div>
          <span class="hint">Vendors and clients type the vendor's name. Leave empty only if you are the platform administrator.</span>
        </div>
        <div class="field">
          <label for="si-user">Username</label>
          <div class="in"><input id="si-user" name="username" autocomplete="username">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/></svg></div>
        </div>
        <div class="field">
          <label for="si-pass">Password</label>
          <div class="in"><input id="si-pass" name="password" type="password" autocomplete="current-password">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>
            <button type="button" class="peek" aria-pressed="false" aria-controls="si-pass" hidden>Show</button></div>
          <span class="hint caps" role="status" hidden>Caps Lock is on.</span>
        </div>
        <button class="primary">Sign in</button>
      </form>
    </div>`, false));
});

app.post('/login', async (req, res) => {
  const vendor = String((req.body || {}).vendor || '').trim();
  const username = String((req.body || {}).username || '').trim();
  const password = String((req.body || {}).password || '');

  let companyId = null;
  if (vendor) {
    // Matched case-insensitively: a vendor name is typed by a person.
    const c = await pool.query('SELECT id, name FROM wap_company WHERE lower(name) = lower($1)', [vendor]);
    if (!c.rows.length) return res.redirect('/login?bad=1');
    companyId = c.rows[0].id;
  }

  // Three shapes of login share one form:
  //   admin  - no vendor, row with neither company nor database
  //   vendor - vendor given, row with that company and no database
  //   client - vendor given, row bound to a database of that vendor
  const { rows } = await pool.query(
    `SELECT a.*, d.db_name, d.company_id AS db_company_id, c.name AS vendor_name
       FROM wap_admin a
       LEFT JOIN wap_database d ON d.id = a.database_id
       LEFT JOIN wap_company c ON c.id = COALESCE(d.company_id, a.company_id)
      WHERE a.username = $1
        AND (   ($2::int IS NULL AND a.company_id IS NULL AND a.database_id IS NULL)
             OR ($2::int IS NOT NULL AND a.database_id IS NULL AND a.company_id = $2)
             OR ($2::int IS NOT NULL AND a.database_id IS NOT NULL AND d.company_id = $2))
      ORDER BY a.database_id NULLS FIRST`,
    [username, companyId]);

  for (const row of rows) {
    if (!bcrypt.compareSync(password, row.password_hash)) continue;
    req.session.adminId = row.id;
    req.session.username = row.username;
    req.session.role = row.database_id ? 'client' : (row.company_id ? 'vendor' : 'admin');
    req.session.companyId = row.database_id ? row.db_company_id : (row.company_id || null);
    req.session.databaseId = row.database_id || null;
    req.session.dbName = row.db_name || '';
    req.session.vendor = row.vendor_name || vendor || null;
    return res.redirect(req.session.role === 'client' ? '/me' : '/');
  }
  res.redirect('/login?bad=1');
});

app.post('/logout', (req, res) => req.session.destroy(() => res.redirect('/login')));

// ---------------------------------------------------------------- shared bits

const STATE_TEXT = {
  open: ['ok', 'connected'],
  close: ['no', 'not connected'],
  connecting: ['warn', 'connecting'],
  wrong_number: ['no', 'WRONG PHONE'],
  missing: ['no', 'missing on gateway'],
  none: ['dim', 'no number'],
};
function statePill(state) {
  const [cls, text] = STATE_TEXT[state] || ['dim', state || 'unknown'];
  return `<span class="pill ${cls}">${esc(text)}</span>`;
}
function fmtNumber(digits) {
  return digits ? '+' + digits : '';
}
function logRows(rows) {
  return rows.length ? `<table>
      <tr><th>When</th><th></th><th>To</th><th>What</th><th>Result</th><th>Detail</th></tr>
      ${rows.map(l => `<tr>
        <td class="muted">${new Date(l.created_at).toLocaleString()}</td>
        <td class="muted">${l.channel === 'email' ? '&#9993;' : '&#128172;'}</td>
        <td>${esc(l.phone)}</td>
        <td class="muted">${esc(l.endpoint)}</td>
        <td><span class="pill ${l.status === 'sent' || l.status === 'read' ? 'ok' : 'no'}">${esc(l.status)}</span></td>
        <td class="muted">${esc(l.detail)}</td></tr>`).join('')}
    </table>` : '<div class="card"><p class="muted">Nothing yet.</p></div>';
}
function slug(text, max) {
  return String(text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, max);
}
/** A client username must not collide with the vendor's login or with another
 *  client of the same vendor, or "vendor + username" at sign-in is ambiguous. */
async function usernameTaken(username, companyId, exceptAdminId) {
  const { rows } = await pool.query(
    `SELECT 1 FROM wap_admin a LEFT JOIN wap_database d ON d.id = a.database_id
      WHERE a.username = $1 AND COALESCE(d.company_id, a.company_id) = $2 AND a.id <> $3`,
    [username, companyId, exceptAdminId || 0]);
  return rows.length > 0;
}

// ---------------------------------------------------------------- SMTP presets

const SMTP_PRESETS = [
  { key: 'gmail',   name: 'Gmail / Google Workspace', host: 'smtp.gmail.com',        port: 587, secure: false, hint: 'Use an App Password (Google account > Security > App passwords), not the normal password.' },
  { key: 'zoho',    name: 'Zoho Mail (zoho.com)',     host: 'smtp.zoho.com',         port: 587, secure: false, hint: 'Zoho: turn on SMTP access in Mail settings; an App Password if 2FA is on.' },
  { key: 'zohoin',  name: 'Zoho Mail India (zoho.in)', host: 'smtp.zoho.in',         port: 587, secure: false, hint: 'Accounts hosted in India use smtp.zoho.in.' },
  { key: 'office',  name: 'Outlook / Microsoft 365',  host: 'smtp.office365.com',    port: 587, secure: false, hint: 'SMTP AUTH must be enabled for the mailbox in Microsoft 365 admin.' },
  { key: 'yahoo',   name: 'Yahoo Mail',               host: 'smtp.mail.yahoo.com',   port: 465, secure: true,  hint: 'Use an App Password from Yahoo account security.' },
  { key: 'sendgrid', name: 'SendGrid',                host: 'smtp.sendgrid.net',     port: 587, secure: false, hint: 'Username is the word apikey; the password is the API key.' },
  { key: 'ses',     name: 'Amazon SES',               host: 'email-smtp.us-east-1.amazonaws.com', port: 587, secure: false, hint: 'Use the SMTP credentials from the SES console; change the region in the host if needed.' },
  { key: 'custom',  name: 'Custom SMTP server',       host: '', port: 587, secure: false, hint: 'Type the host, port and whether it wants SSL from the first byte (465) or STARTTLS (587).' },
];

/** The provider picker + the fields it fills. `cur` = existing account row or null. */
function smtpFields(cur, opts = {}) {
  const host = cur ? cur.host || '' : '';
  const match = SMTP_PRESETS.find(x => x.host && x.host === host);
  const selected = match ? match.key : (host ? 'custom' : (opts.defaultKey || 'gmail'));
  const preset = SMTP_PRESETS.find(x => x.key === selected);
  return `
      <label>Mail provider<select name="smtp_preset" class="smtp-preset">
        ${SMTP_PRESETS.map(x => `<option value="${x.key}" data-host="${esc(x.host)}" data-port="${x.port}" data-secure="${x.secure ? 1 : 0}" data-hint="${esc(x.hint)}" ${x.key === selected ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
      </select><span class="muted smtp-hint">${esc(preset ? preset.hint : '')}</span></label>
      <label>SMTP server<input name="host" class="smtp-host" value="${esc(host || (cur ? '' : preset.host))}" placeholder="smtp.example.com"></label>
      <div class="row gap">
        <label style="flex:1">Port<input name="port" type="number" class="smtp-port" value="${cur ? (cur.port || 587) : preset.port}"></label>
        <label class="check" style="flex:1"><input type="checkbox" name="secure" class="smtp-secure" ${cur ? (cur.secure ? 'checked' : '') : (preset.secure ? 'checked' : '')}> SSL from the start (465)</label>
      </div>
      <label>SMTP username<input name="username" value="${esc(cur ? cur.email_username || cur.username || '' : '')}" autocomplete="off" placeholder="usually the full e-mail address"></label>
      <label>SMTP password<input name="password" type="password" autocomplete="new-password" placeholder="${cur && cur.email_id ? 'unchanged - type to replace' : ''}">
        <span class="muted">Stored on this server, never sent to Odoo.</span></label>`;
}

const SMTP_SCRIPT = `<script>
document.querySelectorAll('.smtp-preset').forEach(function (sel) {
  sel.addEventListener('change', function () {
    var o = sel.options[sel.selectedIndex], f = sel.closest('form');
    f.querySelector('.smtp-hint').textContent = o.dataset.hint || '';
    if (o.value !== 'custom') {
      f.querySelector('.smtp-host').value = o.dataset.host;
      f.querySelector('.smtp-port').value = o.dataset.port;
      f.querySelector('.smtp-secure').checked = o.dataset.secure === '1';
    } else { f.querySelector('.smtp-host').focus(); }
  });
});
</script>`;

// ---------------------------------------------------------------- dashboard

app.get('/', requireLogin, async (req, res) => {
  const s = req.session;
  if (s.role === 'client') return res.redirect('/me');
  const isAdmin = s.role === 'admin';

  const servers = isAdmin ? await pool.query('SELECT * FROM wap_server ORDER BY name') : { rows: [] };
  const dbs = await pool.query(
    `SELECT d.*, s.base_url, s.name AS server_name, c.name AS company_name,
            n.label AS number_label, n.authorized_number, n.pair_state,
            e.id AS email_id, e.from_email, e.daily_cap AS email_cap,
            (SELECT username FROM wap_admin a WHERE a.database_id = d.id LIMIT 1) AS client_username,
            (SELECT count(*)::int FROM wap_log l
              WHERE l.database_id = d.id AND l.status = 'sent' AND l.channel = 'whatsapp'
                AND l.created_at >= date_trunc('day', now())) AS wa_today,
            (SELECT count(*)::int FROM wap_log l
              WHERE l.database_id = d.id AND l.status = 'sent' AND l.channel = 'email'
                AND l.created_at >= date_trunc('day', now())) AS mail_today
       FROM wap_database d
       JOIN wap_server s ON s.id = d.server_id
       LEFT JOIN wap_company c ON c.id = d.company_id
       LEFT JOIN wap_number n ON n.id = d.number_id
       LEFT JOIN wap_email e ON e.database_id = d.id AND e.active
      WHERE ($1::int IS NULL OR d.company_id = $1)
      ORDER BY c.name, s.name, d.db_name`, [isAdmin ? null : s.companyId]);

  // one line per database, with all its numbers
  const lines = new Map();
  for (const d of dbs.rows) {
    const key = d.server_id + '|' + d.db_name;
    const first = lines.get(key);
    if (!first) { lines.set(key, { ...d, nums: [d] }); continue; }
    if (d.id < first.id) { const nums = first.nums; Object.assign(first, d, { nums }); }
    first.nums.push(d);
  }
  dbs.rows = [...lines.values()].map(x => {
    x.nums.sort((a, b) => a.id - b.id);
    const mail = x.nums.find(y => y.email_id) || x;
    return { ...x, active: x.nums.some(y => y.active), wa_today: x.nums.reduce((t, y) => t + y.wa_today, 0),
             mail_today: x.nums.reduce((t, y) => t + y.mail_today, 0), email_id: mail.email_id, from_email: mail.from_email, email_cap: mail.email_cap,
             daily_cap: x.nums.some(y => !y.daily_cap) ? 0 : x.nums.reduce((t, y) => t + y.daily_cap, 0),
             client_username: (x.nums.find(y => y.client_username) || {}).client_username };
  });

  const rowsHtmlUnused = dbs.rows.map(d => `
    <tr class="${d.active && d.company_name ? '' : 'off'}">
      ${isAdmin ? `<td>${d.company_name ? '<b>' + esc(d.company_name) + '</b>' : '<span class="bad">no vendor</span>'}</td>` : ''}
      <td><code>${esc(d.db_name)}</code><br><span class="muted">${esc(d.server_name)}</span></td>
      <td>${d.number_label
        ? `${esc(fmtNumber(d.authorized_number)) || '<span class="muted">number not adopted yet</span>'}<br>${statePill(d.pair_state)}`
        : '<span class="bad">no number</span>'}</td>
      <td>${d.email_id ? '<code>' + esc(d.from_email) + '</code>' : '<span class="muted">none</span>'}</td>
      <td>${d.client_username ? '<code>' + esc(d.client_username) + '</code>' : '<span class="muted">none</span>'}</td>
      <td class="num">${d.wa_today} / ${d.daily_cap || '&infin;'}<br><span class="muted">${d.email_id ? d.mail_today + ' / ' + (d.email_cap || '&infin;') : '&mdash;'}</span></td>
      <td><span class="pill ${d.active ? 'ok' : 'no'}">${d.active ? 'on' : 'off'}</span></td>
      <td class="right"><a class="btn" href="/database/${d.id}">Open</a></td>
    </tr>`).join('');

  const dbRow = d => `
    <tr class="${d.active && d.company_name ? '' : 'off'}">
      <td><code>${esc(d.db_name)}</code><br><span class="muted">${esc(d.server_name)}</span></td>
      <td>${d.nums.some(x => x.number_id) ? d.nums.filter(x => x.number_id).map(x =>
        `${esc(fmtNumber(x.authorized_number)) || '<span class="muted">number not adopted yet</span>'} ${x.off_by ? '<span class="pill no">off</span>' : statePill(x.pair_state)}`).join('<br>')
        : '<span class="bad">no number</span>'}</td>
      <td>${d.email_id ? '<code>' + esc(d.from_email) + '</code>' : '<span class="muted">none</span>'}</td>
      <td>${d.client_username ? '<code>' + esc(d.client_username) + '</code>' : '<span class="muted">none</span>'}</td>
      <td class="num">${d.wa_today} / ${d.daily_cap || '&infin;'}<br><span class="muted">${d.email_id ? d.mail_today + ' / ' + (d.email_cap || '&infin;') : '&mdash;'}</span></td>
      <td><span class="pill ${d.active ? 'ok' : 'no'}">${d.active ? 'active' : 'STOPPED'}</span></td>
      <td class="right"><div class="row" style="justify-content:flex-end">
        ${isAdmin ? `<form method="post" action="/database/${d.id}/toggle" style="margin:0">
          <button class="${d.active ? 'bad-btn' : 'primary'}" title="${d.active ? 'Stop all numbers and e-mail of this database (the phones stay paired)' : 'Let this database send again'}">${d.active ? 'Deactivate' : 'Activate'}</button>
        </form>` : ''}
        <a class="btn" href="/database/${d.id}">Open</a></div></td>
    </tr>`;
  const dbHead = '<tr><th>Database</th><th>WhatsApp number</th><th>Email from</th><th>User</th><th>Today</th><th></th><th></th></tr>';

  let body;
  if (isAdmin) {
    const vendors = await pool.query(`
      SELECT c.*, (SELECT string_agg(a.username, ', ') FROM wap_admin a WHERE a.company_id = c.id AND a.database_id IS NULL) AS logins,
             (SELECT count(*)::int FROM wap_number n WHERE n.company_id = c.id) AS numbers
        FROM wap_company c ORDER BY c.name`);
    body = `
    <div class="row between">
      <h1>Vendors and their databases</h1>
      <div>
        <a class="btn primary" href="/numbers/new">Add number</a>
        <a class="btn" href="/database/new">Add database</a>
        <a class="btn" href="/companies/new">Add vendor</a>
        <a class="btn" href="/server/new">Add server</a>
      </div>
    </div>
    <p class="muted">Order of work: register the <b>WhatsApp number</b> first and scan its QR,
    then attach <b>databases</b> to it - on any Odoo URL, as many as you like, and only if you want
    (a database can also live without a number and get one later). A vendor is the software company
    the number and its databases belong to.</p>
    ${vendors.rows.length ? vendors.rows.map(c => {
      const mine = dbs.rows.filter(d => d.company_id === c.id);
      return `<div class="card ${c.active ? '' : 'off'}">
        <div class="row between">
          <h2 style="margin:0"><a href="/company/${c.id}">${esc(c.name)}</a>
            <span class="muted" style="text-transform:none;letter-spacing:0">&middot; login <code>${esc(c.logins || '-')}</code> &middot; ${c.numbers} number(s)</span></h2>
          <div>
            <a class="btn" href="/company/${c.id}">Vendor settings</a>
            <a class="btn primary" href="/database/new?company_id=${c.id}">Add database</a>
          </div>
        </div>
        ${mine.length ? `<table style="margin-top:12px">${dbHead}${mine.map(dbRow).join('')}</table>`
          : '<p class="muted" style="margin:12px 0 0">No databases under this vendor yet.</p>'}
      </div>`; }).join('')
    : `<div class="card"><p>No vendors yet.</p>
       <p class="muted">A vendor is the software company. Add it first; its databases, users, numbers and mail go under it.</p>
       <a class="btn primary" href="/companies/new">Add the first vendor</a></div>`}`;
  } else {
    body = `
    <h1>Databases</h1>
    ${dbs.rows.length ? `<table>${dbHead}${dbs.rows.map(dbRow).join('')}</table>
    <p class="muted">These are the databases assigned to you. You set each one's mail account and its client password; the administrator assigns numbers.</p>`
    : '<div class="card"><p>No databases assigned to you yet.</p></div>'}`;
  }

  page(req, res, isAdmin ? 'Vendors' : 'Databases', `
    ${body}
    ${servers.rows.length ? `<h2>Servers</h2><table>
      <tr><th>Name</th><th>Address</th><th></th><th></th></tr>
      ${servers.rows.map(sv => `<tr class="${sv.active ? '' : 'off'}">
        <td>${esc(sv.name)}</td><td><code>${esc(sv.base_url)}</code></td>
        <td><span class="pill ${sv.active ? 'ok' : 'no'}">${sv.active ? 'on' : 'off'}</span></td>
        <td class="right"><div class="row" style="justify-content:flex-end">
          <a class="btn" href="/server/${sv.id}">Open</a>
          <form method="post" action="/server/${sv.id}/delete" style="margin:0"
                onsubmit="return confirm('Remove server ${esc(sv.name).replace(/'/g, '')}? Its databases go with it.')">
            <button class="bad-btn" title="Remove server">&#128465; Delete</button>
          </form></div></td></tr>`).join('')}
    </table>` : ''}`);
});

// ---------------------------------------------------------------- client home

app.get('/me', requireLogin, async (req, res) => {
  const s = req.session;
  if (s.role !== 'client') return res.redirect('/');
  req.params.id = String(s.databaseId);
  return scopeDatabase('id')(req, res, async () => {
    const d = req.db;
    let map = null;
    try { map = await fetchInstanceMap(); } catch (err) { /* shown from the last known state */ }
    const mine = [];
    for (const x of await siblings(d)) {
      let n = x.number_id ? await loadNumber(x.number_id) : null;
      if (n && map) n = await checkPairing(n, map);
      mine.push({ ...x, n });
    }
    const ids = mine.map(x => x.id);
    const logs = await pool.query('SELECT * FROM wap_log WHERE database_id = ANY($1::int[]) ORDER BY created_at DESC LIMIT 40', [ids]);
    const optouts = await pool.query('SELECT * FROM wap_optout WHERE database_id = ANY($1::int[]) ORDER BY created_at DESC LIMIT 100', [ids]);
    const why = n => ({
      open: 'Connected.',
      close: 'Not connected. Scan the QR with the phone that holds this number.',
      connecting: 'Not connected yet. Scan the QR with the phone that holds this number.',
      wrong_number: `The QR was scanned with ${n ? fmtNumber(n.last_wrong_number) : 'another phone'}, which is not allowed, so it was logged out again. Scan with the right phone.`,
      missing: 'The number is missing on the gateway. Ask your vendor or the administrator to reset it.',
      none: 'No WhatsApp number has been assigned yet. Ask your vendor or the administrator.',
    }[n ? n.pair_state : 'none'] || '');
    page(req, res, d.db_name, `
      <h1>${esc(d.db_name)}</h1>
      <p class="muted">${esc(d.company_name)} &middot; ${esc(d.server_name)} &middot; <code>${esc(d.base_url)}</code></p>
      <div class="card">
        <h2 style="margin:0">WhatsApp numbers</h2>
        ${mine.map((x, i) => `
        <div class="num-row ${x.off_by || !x.active ? 'is-off' : ''}">
          <div class="row between">
            <div><span class="num-no">${i + 1}</span><span class="big">${esc(fmtNumber(x.n ? x.n.authorized_number : '')) || 'not set'}</span>
              ${x.n && x.n.label ? `<span class="muted">&nbsp;${esc(x.n.label)}</span>` : ''}</div>
            <div class="row">${x.off_by || !x.active ? '<span class="pill no">OFF</span>' : ''}${statePill(x.n ? x.n.pair_state : 'none')}
              ${x.n ? `<a class="btn ${x.n.pair_state === 'open' ? '' : 'primary'}" href="/number/${x.n.id}/qr">${x.n.pair_state === 'open' ? 'Connection' : 'Scan / connect'}</a>` : ''}</div>
          </div>
          <p class="${x.n && x.n.pair_state === 'open' ? 'muted' : 'warn-msg'}" style="margin:6px 0 0">${esc(why(x.n))}</p>
        </div>`).join('')}
        <p class="muted">The numbers and the mail address are fixed by your vendor and the administrator.
        A scan by any other phone is refused.</p>
      </div>
      <div class="card narrow">
        <h2>Email</h2>
        <table class="plain">
          <tr><th>Sends from</th><td>${d.email_id ? '<code>' + esc(d.from_email) + '</code>' + (d.from_name ? ' &middot; ' + esc(d.from_name) : '') : '<span class="muted">no mail account yet</span>'}</td></tr>
          <tr><th>Status</th><td>${d.email_id ? `<span class="pill ${d.email_active ? 'ok' : 'no'}">${d.email_active ? 'on' : 'off'}</span>` : ''}</td></tr>
        </table>
      </div>
      <h2>Opted out (this database)</h2>
      <div class="card narrow">
        <form method="post" action="/blocked/optout" class="row gap">
          ${phoneField('phone', 'Country', { required: true, like: (mine.map(x => x.n && x.n.authorized_number).find(Boolean)) || '' })}
          <input name="reason" placeholder="why">
          <button class="primary">Add</button>
        </form>
        ${optouts.rows.length ? `<table class="plain">${optouts.rows.map(o => `<tr>
          <td><code>${esc(o.phone)}</code></td><td class="muted">${esc(o.reason)}</td>
          <td class="right"><form method="post" action="/blocked/optout/${o.id}/delete"><button>Remove</button></form></td>
        </tr>`).join('')}</table>` : '<p class="muted">Nobody has opted out.</p>'}
      </div>
      <h2>Recent activity</h2>
      ${logRows(logs.rows)}`);
  });
});

// ---------------------------------------------------------------- servers (admin)

/**
 * The databases an Odoo server has, from its own /web/database/list.
 * Returns {dbs: [...]} or {error}. Odoo answers this without a login unless
 * list_db is switched off in its odoo.conf, in which case the name is typed.
 */
async function fetchOdooDbList(baseUrl) {
  try {
    const r = await fetch(String(baseUrl).replace(/\/+$/, '') + '/web/database/list', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
      signal: AbortSignal.timeout(8000),
    });
    const data = await r.json();
    if (Array.isArray(data.result)) return { dbs: data.result };
    const msg = (data.error && (data.error.data && data.error.data.message || data.error.message)) || ('HTTP ' + r.status);
    return { error: msg };
  } catch (err) {
    return { error: err.message };
  }
}

/** numberfirst: a typed Odoo URL becomes a server row (found by origin or
 *  created, named after its host), so a database can be attached to a number
 *  without registering the server first. Returns the row or null. */
async function serverFromUrl(raw) {
  const url = origin(raw);
  if (!url) return null;
  const found = await pool.query('SELECT * FROM wap_server WHERE base_url = $1', [url]);
  if (found.rows.length) return found.rows[0];
  let name = url;
  try { name = new URL(url).host; } catch (err) { /* keep the origin */ }
  const { rows } = await pool.query('INSERT INTO wap_server (name, base_url) VALUES ($1,$2) RETURNING *', [name, url]);
  return rows[0];
}

app.get('/server/new', requireLogin, requireAdmin, (req, res) => {
  page(req, res, 'Add server', `
    <form method="post" action="/server/new" class="card narrow">
      <h1>Add server</h1>
      <p class="muted">The address Odoo reports as its own (web.base.url). Only
      requests claiming this address are accepted.</p>
      <label>Name<input name="name" placeholder="e.g. Cloud server" required></label>
      <label>Server address<input name="base_url" placeholder="https://odoo.example.com" required></label>
      <button class="primary">Add</button> <a class="btn" href="/">Cancel</a>
    </form>`);
});

app.post('/server/new', requireLogin, requireAdmin, async (req, res) => {
  const name = String(req.body.name || '').trim();
  const url = origin(req.body.base_url);
  if (!name || !url) return page(req, res, 'Add server', `<div class="card narrow"><p class="bad">Give a name and a valid address.</p><a class="btn" href="/server/new">Back</a></div>`);
  let id;
  try {
    const { rows } = await pool.query('INSERT INTO wap_server (name, base_url) VALUES ($1,$2) RETURNING id', [name, url]);
    id = rows[0].id;
  } catch (err) {
    return page(req, res, 'Add server', `<div class="card narrow"><p class="bad">${esc(url)} is already registered.</p><a class="btn" href="/">Back</a></div>`);
  }
  res.redirect('/server/' + id);
});

app.get('/server/:id', requireLogin, requireAdmin, async (req, res) => {
  const { rows } = await pool.query('SELECT * FROM wap_server WHERE id = $1', [Number(req.params.id) || 0]);
  if (!rows.length) return res.redirect('/');
  const sv = rows[0];
  const listed = await fetchOdooDbList(sv.base_url);
  const registered = await pool.query('SELECT db_name, id FROM wap_database WHERE server_id = $1', [sv.id]);
  const regMap = {};
  const regCount = {};
  for (const r of registered.rows) {
    regCount[r.db_name] = (regCount[r.db_name] || 0) + 1;
    if (!regMap[r.db_name] || r.id < regMap[r.db_name]) regMap[r.db_name] = r.id;
  }
  page(req, res, 'Server', `
    <form method="post" action="/server/${sv.id}" class="card narrow">
      <h1>${esc(sv.name)}</h1>
      <label>Name<input name="name" value="${esc(sv.name)}"></label>
      <label>Server address<input name="base_url" value="${esc(sv.base_url)}"></label>
      <label class="check"><input type="checkbox" name="active" ${sv.active ? 'checked' : ''}> Allowed to send</label>
      <button class="primary">Save</button> <a class="btn" href="/">Back</a>
    </form>
    <div class="card narrow">
      <h2>Databases on this server</h2>
      ${listed.dbs ? (listed.dbs.length ? `<table class="plain">${listed.dbs.map(n => `<tr>
          <td><code>${esc(n)}</code></td>
          <td class="right">${regMap[n]
            ? `<a class="btn" href="/database/${regMap[n]}">Registered${regCount[n] > 1 ? ' - ' + regCount[n] + ' numbers' : ''} - open</a>`
            : `<a class="btn primary" href="/database/new?server_id=${sv.id}&db_name=${encodeURIComponent(n)}">Add</a>`}</td>
        </tr>`).join('')}</table>
        <p class="muted">Read live from <code>${esc(sv.base_url)}/web/database/list</code>.</p>`
        : '<p class="muted">The server reports no databases.</p>')
      : `<p class="bad">Could not read the list from ${esc(sv.base_url)}: ${esc(listed.error)}</p>
         <p class="muted">The server may be off, unreachable from here, or has <code>list_db = False</code>. The database name can still be typed on the Add database form.</p>`}
    </div>
    <form method="post" action="/server/${sv.id}/delete" class="card narrow danger">
      <p class="muted">Removing a server also removes its databases, and they stop sending immediately.</p>
      <button class="bad-btn">Remove server</button>
    </form>`);
});

app.post('/server/:id', requireLogin, requireAdmin, async (req, res) => {
  await pool.query('UPDATE wap_server SET name=$1, base_url=$2, active=$3 WHERE id=$4',
    [String(req.body.name || '').trim(), origin(req.body.base_url), !!req.body.active, Number(req.params.id) || 0]);
  res.redirect('/');
});

app.post('/server/:id/delete', requireLogin, requireAdmin, async (req, res) => {
  await pool.query('DELETE FROM wap_server WHERE id = $1', [Number(req.params.id) || 0]);
  res.redirect('/');
});

// ---------------------------------------------------------------- databases

app.get('/database/new', requireLogin, requireAdmin, async (req, res) => {
  const servers = await pool.query('SELECT * FROM wap_server ORDER BY name');
  const companies = await pool.query('SELECT * FROM wap_company ORDER BY name');
  const numbers = await pool.query('SELECT n.*, c.name AS company_name FROM wap_number n JOIN wap_company c ON c.id = n.company_id WHERE n.active ORDER BY c.name, n.label');
  if (!companies.rows.length) {
    return page(req, res, 'Add database', `
      <div class="card narrow"><h1>Add database</h1><p>A vendor (the software company) has to exist first.</p>
      <a class="btn primary" href="/companies/new">Add vendor</a> <a class="btn" href="/">Back</a></div>`);
  }
  // numberfirst: a typed URL finds or creates the server row; ?number_id=
  // preselects the number and its vendor.
  const typedServer = req.query.url ? await serverFromUrl(req.query.url) : null;
  if (req.query.url && !typedServer) {
    const q = Object.assign({}, req.query, { bad: 'That is not a valid Odoo address - type it like https://odoo.example.com' });
    delete q.url;
    return res.redirect('/database/new?' + new URLSearchParams(q).toString());
  }
  if (typedServer && !servers.rows.some(x => x.id === typedServer.id)) servers.rows.push(typedServer);
  const presetNumber = numbers.rows.find(n => n.id === (Number(req.query.number_id) || 0));
  const fixed = companies.rows.find(c => c.id === (Number(req.query.company_id) || 0))
    || (presetNumber ? companies.rows.find(c => c.id === presetNumber.company_id) : null);
  const chosenServer = typedServer || servers.rows.find(x => x.id === (Number(req.query.server_id) || 0)) || servers.rows[0];
  const listed = chosenServer ? await fetchOdooDbList(chosenServer.base_url) : { error: 'no server yet - type its address above' };
  const taken = await pool.query('SELECT db_name FROM wap_database WHERE server_id = $1', [chosenServer ? chosenServer.id : 0]);
  const takenSet = new Set(taken.rows.map(r => r.db_name));
  const preset = String(req.query.db_name || '');
  const choices = (listed.dbs || []).filter(n => !takenSet.has(n));
  const keep = ['company_id', 'number_id', 'bad'].filter(k => req.query[k]).map(k => k + '=' + encodeURIComponent(req.query[k])).join('&');
  page(req, res, 'Add database', `
    <form method="post" action="/database/new" class="card narrow">
      <h1>Add database${fixed ? ' under ' + esc(fixed.name) : ''}</h1>
      ${req.query.bad ? `<p class="bad">${esc(req.query.bad)}</p>` : ''}
      ${fixed ? `<input type="hidden" name="company_id" value="${fixed.id}">
      <label>Vendor<input value="${esc(fixed.name)}" readonly></label>`
      : `<label>Vendor<select name="company_id">
        ${companies.rows.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}
      </select><span class="muted">The software company this database is assigned to.</span></label>`}
      <label>Odoo URL (any server)<div class="row gap">
        <input id="url_typed" style="flex:1" value="${esc(chosenServer ? chosenServer.base_url : '')}" placeholder="https://dubai.369ai.biz">
        <button type="button" class="btn" onclick="location.href='/database/new?url='+encodeURIComponent(document.getElementById('url_typed').value)+'${keep ? '&' + keep.replace(/'/g, '') : ''}'">Load databases</button>
      </div><span class="muted">Local or cloud address of the Odoo that owns the database. A new address is remembered as a server automatically.</span></label>
      ${servers.rows.length ? `<label>Known servers<select name="server_id" onchange="location.href='/database/new?server_id='+this.value+'${keep ? '&' + keep.replace(/'/g, '') : ''}'">
        ${servers.rows.map(sv => `<option value="${sv.id}" ${chosenServer && sv.id === chosenServer.id ? 'selected' : ''}>${esc(sv.name)} — ${esc(sv.base_url)}</option>`).join('')}
      </select><span class="muted">Changing the server reloads the database list below.</span></label>` : '<input type="hidden" name="server_id" value="">'}
      ${choices.length ? `
      <label>Database<select name="db_name" id="db_pick" onchange="document.getElementById('db_manual').style.display = this.value ? 'none' : 'block'">
        ${choices.map(n => `<option value="${esc(n)}" ${n === preset ? 'selected' : ''}>${esc(n)}</option>`).join('')}
        <option value="">— another name (type it) —</option>
      </select><span class="muted">Read live from ${esc(chosenServer.base_url)}. Databases already registered here are left out.</span></label>
      <label id="db_manual" style="display:none">Database name<input name="db_name_manual" placeholder="typed exactly as Odoo calls it"></label>`
      : `<label>Database name<input name="db_name" value="${esc(preset)}" placeholder="STRETCH_AND_GO" required>
        <span class="muted">${listed.dbs ? 'Every database on this server is already registered - type a new name only if you know it exists.'
          : 'Could not read the list from ' + esc(chosenServer ? chosenServer.base_url : '?') + ' (' + esc(listed.error) + '). Type the name exactly as Odoo calls it.'}</span></label>`}
      ${chosenServer ? '' : '<p class="bad">Type the Odoo URL above and press Load databases first.</p>'}
      <input type="hidden" name="odoo_url" value="${esc(chosenServer ? chosenServer.base_url : '')}">
      <label>Sends as<input name="tenant_label" placeholder="Danat Spa"></label>
      <label class="check"><input type="checkbox" name="sign_messages" checked> Add the automatic no-reply footer (optional)</label>
      <span class="muted">Adds to every WhatsApp message and e-mail: <i>"This is an automated notification. Please do not reply."</i> and, when a support number is given below, a tap-to-chat link to it. Untick to send messages exactly as Odoo writes them.</span>
      ${phoneField('contact_number', 'WhatsApp Support number (optional)')}
      <span class="muted">Shown in that footer as the number to contact. Leave empty for no number.</span>
      <div class="row gap">
        <label style="flex:1">Daily cap<input name="daily_cap" type="number" value="500"></label>
        <label style="flex:1">Messages per minute<input name="per_minute" type="number" value="20"></label>
      </div>
      <h2>This database's user</h2>
      <p class="muted">The person at the shop signs in with the vendor name, the <b>database name as username</b>, and this password. They see only this database.</p>
      <label>Password for that user<input name="client_password" type="password" autocomplete="new-password" minlength="6" placeholder="leave empty for no login yet"></label>
      <h2>This database's WhatsApp number (optional)</h2>
      <p class="muted">Pick the number the administrator registered - databases on any URL may share it -
      or register a new one here, or leave both empty and assign a number later from the number's page.</p>
      <label>Existing number<select name="number_id">
        <option value="">— none yet —</option>
        ${numbers.rows.map(n => `<option value="${n.id}" ${presetNumber && presetNumber.id === n.id ? 'selected' : ''}>${esc(n.company_name)} — ${esc(n.label)} ${esc(fmtNumber(n.authorized_number))}</option>`).join('')}
      </select></label>
      ${phoneField('new_number', 'Or a new WhatsApp number')}
      <span class="muted">A new connection is created for it and you scan its QR next. Leave it empty when you chose a number above.</span>
      <h2>This database's e-mail</h2>
      <p class="muted">Every e-mail from this database goes out from this account. Leave empty to set it later.</p>
      <label>From address<input name="from_email" type="email" placeholder="noreply@shop.com"></label>
      <label>From name<input name="from_name" placeholder="Shop name"></label>
      ${smtpFields(null)}
      <button class="primary">Register database</button> <a class="btn" href="/">Cancel</a>
    </form>${SMTP_SCRIPT}`);
});

app.post('/database/new', requireLogin, requireAdmin, async (req, res) => {
  const b = req.body || {};
  const companyId = Number(b.company_id) || null;
  const numberId = Number(b.number_id) || null;
  // username is the database name; the admin only chooses a password
  const clientPass = String(b.client_password || '');
  const clientUser = clientPass ? String(b.db_name || '').trim() : '';
  const back = msg => res.redirect('/database/new?bad=' + encodeURIComponent(msg) + (companyId ? '&company_id=' + companyId : '') + (numberId ? '&number_id=' + numberId : ''));
  if (!companyId) return back('Choose a vendor.');
  if (numberId) {
    const n = await pool.query('SELECT id FROM wap_number WHERE id = $1', [numberId]);
    if (!n.rows.length) return back('That number no longer exists.');
  }
  // numberfirst: the server comes from the select, or from the typed URL.
  let serverId = Number(b.server_id) || 0;
  if (!serverId && b.odoo_url) {
    const sv = await serverFromUrl(b.odoo_url);
    if (sv) serverId = sv.id;
  }
  if (!serverId) return back('Type the Odoo URL and press Load databases first.');
  if (clientUser) {
    if (clientPass.length < 6) return back('Client password must be at least 6 characters.');
    if (await usernameTaken(clientUser, companyId, 0)) return back(`Username ${clientUser} is already used under this vendor.`);
  }
  const newNumber = digits(b.new_number);
  if (phoneWrong(b, 'contact_number')) return back('Support number: ' + phoneWrong(b, 'contact_number'));
  if (newNumber) {
    if (phoneWrong(b, 'new_number')) return back(phoneWrong(b, 'new_number'));
    const dup = await pool.query('SELECT label FROM wap_number WHERE authorized_number = $1', [newNumber]);
    if (dup.rows.length) return back(`+${newNumber} is already registered as "${dup.rows[0].label}".`);
    if (newNumber.length < 8 || newNumber.length > 15) return back('The WhatsApp number needs 8 to 15 digits, with the country code.');
  }
  const dbName = String(b.db_name || '').trim() || String(b.db_name_manual || '').trim();
  if (!dbName) return back('Give the database name.');
  const there = await pool.query('SELECT id FROM wap_database WHERE server_id = $1 AND db_name = $2 LIMIT 1', [serverId, dbName]);
  if (there.rows.length) return back('That database is already registered on that server. Open it and use "Add another number".');
  const client = await pool.connect();
  let dbId;
  try {
    await client.query('BEGIN');
    const { rows } = await client.query(
      `INSERT INTO wap_database (server_id, company_id, number_id, db_name, tenant_label, contact_number,
                                 token, daily_cap, per_minute)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id`,
      [serverId, companyId, newNumber ? null : numberId, dbName,
       String(b.tenant_label || '').trim(), plusNumber(b.contact_number), token(),
       Number(b.daily_cap || 0), Number(b.per_minute || 0)]);
    dbId = rows[0].id;
    await client.query('UPDATE wap_database SET sign_messages = $1 WHERE id = $2', [!!b.sign_messages, dbId]);
    if (clientUser) {
      await client.query(
        'INSERT INTO wap_admin (username, password_hash, company_id, database_id) VALUES ($1,$2,$3,$4)',
        [clientUser, bcrypt.hashSync(clientPass, 10), companyId, dbId]);
    }
    await client.query('COMMIT');
  } catch (err) {
    await client.query('ROLLBACK');
    return back(/duplicate/i.test(err.message) ? 'That database is already registered on that server.' : err.message.slice(0, 160));
  } finally {
    client.release();
  }
  const notes = [];
  if (String(b.from_email || '').trim()) {
    const err = await saveEmailAccount({ id: dbId, company_id: companyId }, { ...b, active: true });
    if (err) notes.push('E-mail not saved: ' + err);
  }
  if (newNumber) {
    const made = await createNumber(companyId, dbName + ' +' + newNumber, newNumber);
    if (made.error) notes.push('Number not created: ' + made.error);
    else {
      await pool.query('UPDATE wap_database SET number_id = $1 WHERE id = $2', [made.row.id, dbId]);
      return res.redirect(`/number/${made.row.id}/qr` + (notes.length ? '?bad=' + encodeURIComponent(notes.join(' ')) : ''));
    }
  }
  return res.redirect(`/database/${dbId}?` + (notes.length ? 'bad=' + encodeURIComponent(notes.join(' ')) : 'ok=' + encodeURIComponent('Database registered.')));
});

app.get('/database/:id', requireLogin, scopeDatabase('id'), async (req, res) => {
  const d = req.db;
  const s = req.session;
  const isAdmin = s.role === 'admin';
  const canEdit = s.role !== 'client';
  const q = req.query;
  // One page for one database, whichever of its numbers was opened
  const all = await siblings(d);
  if (all[0].id !== d.id && s.role !== 'client') {
    const qs = new URLSearchParams(q).toString();
    return res.redirect(`/database/${all[0].id}${qs ? '?' + qs : ''}#n${d.id}`);
  }
  let map = null;
  try { map = await fetchInstanceMap(); } catch (err) { /* shown from the last known state */ }
  const rowsOfDb = [];
  for (const x of all.filter(y => s.role !== 'vendor' || y.company_id === s.companyId)) {
    let n = x.number_id ? await loadNumber(x.number_id) : null;
    if (n && map) n = await checkPairing(n, map);
    const shared = n ? (await numberDatabases(n.id)).filter(y => y.id !== x.id).map(y => y.db_name) : [];
    rowsOfDb.push({ ...x, n, shared, on: x.active && !x.off_by });
  }
  const anyActive = rowsOfDb.some(x => x.active);
  const companies = isAdmin ? await pool.query('SELECT * FROM wap_company ORDER BY name') : { rows: [] };
  const numbers = isAdmin ? await pool.query(FREE_NUMBERS, [d.company_id]) : { rows: [] };
  const freeNumbers = numbers.rows;         // this vendor's, in no database yet
  const logs = await pool.query('SELECT * FROM wap_log WHERE database_id = ANY($1::int[]) ORDER BY created_at DESC LIMIT 40', [rowsOfDb.map(x => x.id)]);
  const msg = q.ok ? `<p class="ok-msg">${esc(q.ok)}</p>` : q.bad ? `<p class="bad">${esc(q.bad)}</p>` : '';
  const connected = rowsOfDb.filter(x => x.on && x.n && x.n.pair_state === 'open').length;
  const withNumber = rowsOfDb.filter(x => x.number_id);

  // Every number is its own session in Odoo: a new one is opened for it, so that
  // its key is never pasted over another number's.
  // with the database's name: the browser may be signed in to another one
  const odooAction = (name, tail = '') => `${d.base_url}/odoo/action-${name}${tail}?db=${encodeURIComponent(d.db_name)}`;
  const sessionsUrl = odooAction('whatsapp_gateway.action_whatsapp_session');
  const newSessionUrl = odooAction('whatsapp_gateway.action_whatsapp_session', '/new');
  const ownMax = Math.max(0, ...all.map(y => y.own_numbers_max));
  const odooSteps = x => {
    const used = !!x.odoo_webhook_url;
    const another = rowsOfDb.some(y => y.id !== x.id && y.odoo_webhook_url);
    const out = (url, text) => `<a href="${esc(url)}" target="_blank" rel="noopener"${url === sessionsUrl ? ' onclick="wapConnect(this)"' : ''}>${text}</a>`;
    return `
        <details class="odoo-steps">
          <summary>${used ? 'Load its groups, or paste a new key' : 'Steps: paste the key, load settings, load groups'}</summary>
          <ol class="muted">
            <li>The button copies the key and opens the database <code>${esc(d.db_name)}</code> (sign in when asked). The key works only there.</li>
            ${used ? `<li>Open ${out(sessionsUrl, 'the numbers in Odoo')} and choose the session with <b>Instance</b>
              <code>${esc(x.n.instance_name || '')}</code>. Do not press New: this number has its session already. After <b>Reset key</b>: paste it in <b>Setup Key</b> and save.</li>` : `
            <li><b>Connect with Odoo</b> copies the key and opens a new session. Give it a name, paste the key in <b>Setup Key</b>${another
              ? ', untick <b>Email</b> and <b>Send all 369ai email through the gateway</b> (the first number has the e-mail)' : ''} and save.
              Do not paste it into another number's session.</li>`}
            <li>Press <b>Load Settings</b>. Odoo shows this number; when it is not connected, scan its QR here.</li>
            <li>Press <b>Sync Groups</b> (with Sales Automation). To choose them one by one: ${out(odooAction('sales_automation.action_sa_customer_group'), 'Customer Groups')} or
              ${out(odooAction('sales_automation.action_sa_vendor_group'), 'Vendor Groups')} &rarr; <b>New</b> &rarr; choose this session &rarr; <b>Load Groups</b>.</li>
            ${used ? '' : `<li>If Odoo's list has <b>+ Connect a number</b>, that screen does all of this: ${out(sessionsUrl, 'open the list')}, press it and paste the key there when it asks.</li>`}
          </ol>
        </details>`;
  };

  const problem = canEdit && anyActive ? await lastProblem(d, rowsOfDb.map(x => x.id)) : null;
  const problemCard = problem ? `
    <div class="card warn" role="alert">
      <b class="warn-msg">Odoo was refused at ${esc(new Date(problem.created_at).toLocaleTimeString())}</b>
      <p style="margin:6px 0 0">${esc(problem.detail)}</p>
      <p class="muted" style="margin:6px 0 0">This goes away by itself when Odoo gets through.</p>
    </div>` : '';

  const numberRow = (x, i) => {
    const n = x.n;
    const only = rowsOfDb.length < 2;
    return `
      <div class="num-row ${x.on ? '' : 'is-off'}" id="n${x.id}">
        <div class="row between">
          <div>
            <span class="num-no">${i + 1}</span>
            <span class="big">${n ? (esc(fmtNumber(n.authorized_number)) || 'the first phone that scans') : 'No number yet'}</span>
            ${n && n.label ? `<span class="muted">&nbsp;${esc(n.label)}</span>` : ''}
          </div>
          <div class="row">
            ${x.off_by ? `<span class="pill no">OFF${x.off_by === 'odoo' ? ' (from Odoo)' : ''}</span>` : ''}
            ${x.active ? '' : '<span class="pill no">STOPPED</span>'}
            ${statePill(n ? n.pair_state : 'none')}
            ${n ? `<a class="btn ${n.pair_state === 'open' ? '' : 'primary'}" href="/number/${n.id}/qr">${n.pair_state === 'open' ? 'Connection' : 'Scan QR'}</a>` : ''}
            ${isAdmin && n ? `<form method="post" action="/database/${x.id}/number/toggle" style="margin:0"
                ${x.off_by ? '' : `onsubmit="return confirm('Turn off ${esc(fmtNumber(n.authorized_number))}? It sends nothing and its groups get no answer until it is turned on. The phone stays linked; the other numbers go on.')"`}>
              <button class="${x.off_by ? 'primary' : ''}">${x.off_by ? 'Turn on' : 'Turn off'}</button></form>` : ''}
          </div>
        </div>
        ${n && n.pair_state === 'wrong_number' ? `<p class="bad">Scanned with ${esc(fmtNumber(n.last_wrong_number))}; only ${esc(fmtNumber(n.authorized_number))} is allowed. Scan again.</p>` : ''}
        ${canEdit ? `
        <div class="key-line">
          <span class="muted">Key</span>
          <code>${esc(setupKey(x.token))}</code>
          <button type="button" onclick="wapCopyKey(this, true)">Copy</button>
          <form method="post" action="/database/${x.id}/rotate" style="margin:0"
                onsubmit="return confirm('The present key of this number stops working at once. The new one has to be pasted in its Odoo session. Reset the key?')">
            <button class="bad-btn">Reset key</button></form>
          ${!n ? '' : !x.active
            ? (isAdmin && !anyActive ? `<form method="post" action="/database/${d.id}/toggle" style="margin:0"><button class="primary">Activate first</button></form>`
                       : '<span class="warn-msg">Stopped: ask the administrator</span>')
            : x.off_by ? '<span class="warn-msg">Turn it on first</span>'
            : x.odoo_webhook_url
            ? `<a class="btn" href="${esc(sessionsUrl)}" target="_blank" rel="noopener" onclick="wapConnect(this)">Open in Odoo</a>`
            : `<a class="btn primary" href="${esc(newSessionUrl)}" target="_blank" rel="noopener" onclick="wapConnect(this)">Connect with Odoo</a>`}
        </div>
        ${n ? odooSteps(x) : ''}` : ''}
        <p class="muted" style="margin:6px 0 0">${x.odoo_webhook_url ? '&#10003; Used by Odoo' : '&#9675; Not used by Odoo yet'}
          &middot; at most ${x.daily_cap || 'unlimited'} messages a day, ${x.per_minute || 'unlimited'} a minute
          ${x.shared.length ? `&middot; <span class="warn-msg">also used by ${esc(x.shared.join(', '))}: both may answer</span>` : ''}</p>
        ${canEdit ? `
        <details>
          <summary>More</summary>
          <table class="plain"><tr><th>Incoming messages</th><td>${x.odoo_webhook_url ? 'go to <code>' + esc(shortHook(x)) + '</code>' : '<span class="muted">Odoo has not used this key yet</span>'}</td></tr>
            ${n ? `<tr><th>Paired phone</th><td>${esc(fmtNumber(n.paired_number)) || '<span class="muted">none</span>'}</td></tr>` : ''}</table>
          <form method="post" action="/database/${x.id}/limits" class="own-max">
            <label>Messages a day<input name="daily_cap" type="number" min="0" value="${x.daily_cap}"></label>
            <label>a minute<input name="per_minute" type="number" min="0" value="${x.per_minute}"></label>
            <button>Save</button><span class="muted">0 = unlimited. For this number only.</span>
          </form>
          ${isAdmin ? `
          <form method="post" action="/database/${x.id}/number" class="own-max"
                onsubmit="return confirm('This replaces the number of this key. To have one more number, use Add another number. Replace it?')">
            <label>${n ? 'Change this number' : 'Give it a number'}<select name="number_id">
              ${n ? `<option value="${n.id}" selected>${esc(n.label)} ${esc(fmtNumber(n.authorized_number))}</option>` : ''}
              <option value="">&mdash; none &mdash;</option>
              ${freeNumbers.map(y => `<option value="${y.id}">${esc(y.label)} ${esc(fmtNumber(y.authorized_number))}</option>`).join('')}
            </select></label>
            <button>Replace</button>
          </form>` : ''}
          <div class="row" style="margin-top:10px;flex-wrap:wrap">
            ${isAdmin && n ? `<a class="btn" href="/number/${n.id}">Number and phone</a>` : ''}
            ${isAdmin && !only ? `<form method="post" action="/database/${x.id}/delete" style="margin:0"
                  onsubmit="return confirm('Remove ${n ? esc(fmtNumber(n.authorized_number)) : 'this number'} from this database? Its key stops at once. The other numbers stay. The number is free to use again.')">
              <input type="hidden" name="sure" value="1"><button class="bad-btn">Remove from this database</button></form>` : ''}
          </div>
        </details>` : ''}
      </div>`;
  };

  const numbersCard = `
    ${problemCard}
    <div class="card" id="numbers">
      <div class="row between">
        <h2 style="margin:0">WhatsApp numbers</h2>
        <span class="muted">${connected} of ${withNumber.length} connected</span>
      </div>
      <p class="muted">One number for one employee, each with its own key and its own session in Odoo.
        ${ownMax > 0
          ? 'Odoo adds and connects numbers itself under <b>Connect a number</b>; a key is pasted only for the first one.'
          : (canEdit ? 'Press <b>Connect with Odoo</b> beside a number to paste its key there.' : '')}
        ${canEdit ? `<a href="${esc(sessionsUrl)}" target="_blank" rel="noopener">Open the numbers in Odoo</a>` : ''}</p>
      ${rowsOfDb.map(numberRow).join('')}
      ${canEdit ? KEY_SCRIPT : ''}
      ${isAdmin ? `
      <details class="num-add" ${q.add || !withNumber.length ? 'open' : ''}>
        <summary class="btn primary">+ Add another number</summary>
        ${freeNumbers.length ? `
        <h3>Numbers you already added</h3>
        ${freeNumbers.map(x => `
        <form method="post" action="/database/${d.id}/number/add" class="num-free">
          <input type="hidden" name="number_id" value="${x.id}">
          <div><b>${esc(fmtNumber(x.authorized_number)) || esc(x.instance_name)}</b> <span class="muted">${esc(x.label)}</span><br>${statePill(x.pair_state)}</div>
          <button class="primary">Use this number</button>
        </form>`).join('')}
        <h3>Or a new number</h3>` : ''}
        <form method="post" action="/database/${d.id}/number/add">
          ${phoneField('new_number', 'Country', { like: (withNumber.map(x => x.n && x.n.authorized_number).find(Boolean)) || '', required: true })}
          <label>Area / employee<input name="label" maxlength="60" placeholder="Deira - Ravi"></label>
          <button class="primary">Add number and scan</button>
        </form>
      </details>
      <form method="post" action="/database/${d.id}/own-numbers" class="own-max">
        <label>Odoo may have, at most<input name="max" type="number" min="0" max="50" value="${ownMax}"></label>
        <span class="muted">numbers, and adds them itself under "Connect a number". 0 = only you add numbers here.</span>
        <button>Save</button>
      </form>` : ''}
    </div>`;

  const emailCard = canEdit ? `
    <form method="post" action="/database/${d.id}/email" class="card narrow">
      <h2>Email account for this database</h2>
      ${q.tested ? `<p class="${q.testbad ? 'bad' : 'ok-msg'}">${esc(q.testbad || 'The mail server accepted these settings.')}</p>` : ''}
      <label>From address<input name="from_email" type="email" required value="${esc(d.from_email || '')}"></label>
      <label>From name<input name="from_name" value="${esc(d.from_name || '')}" placeholder="${esc(d.tenant_label || d.company_name)}"></label>
      ${smtpFields(d.email_id ? d : null)}
      <div class="row gap">
        <label style="flex:1">Daily cap<input name="daily_cap" type="number" value="${d.email_daily_cap || 1000}"></label>
        <label style="flex:1">Per minute<input name="per_minute" type="number" value="${d.email_per_minute || 30}"></label>
      </div>
      <label class="check"><input type="checkbox" name="active" ${d.email_id ? (d.email_active ? 'checked' : '') : 'checked'}> Allowed to send email</label>
      <button class="primary">Save</button>
      ${d.email_id ? `<button formaction="/database/${d.id}/email/test">Test connection</button>` : ''}
      <p class="muted">Odoo sends every email from this address and cannot replace it.</p>
    </form>${SMTP_SCRIPT}` : '';

  const clientCard = canEdit ? `
    <form method="post" action="/database/${d.id}/client" class="card narrow">
      <h2>Client login</h2>
      <p class="muted">The person at <b>${esc(d.db_name)}</b> signs in with vendor
      <code>${esc(d.company_name)}</code>, username <code>${esc(d.db_name)}</code> and this
      password, and sees only this database: its number, its QR, its mail address and its activity.</p>
      <label>Username<input value="${esc(d.db_name)}" readonly><span class="muted">Always the database name.</span></label>
      <label>${d.client_username ? 'New password' : 'Password'}<input name="password" type="password" autocomplete="new-password" minlength="6" ${d.client_username ? '' : 'required'}>
        <span class="muted">${d.client_username ? 'Leave empty to keep the current password.' : 'At least 6 characters.'}</span></label>
      <button class="primary">${d.client_username ? 'Save' : 'Create login'}</button>
      ${d.client_username && isAdmin ? `<button formaction="/database/${d.id}/client/delete" class="bad-btn">Remove login</button>` : ''}
    </form>` : '';

  const today = await pool.query(
    `SELECT count(*) FILTER (WHERE channel = 'whatsapp')::int AS wa, count(*) FILTER (WHERE channel = 'email')::int AS mail
       FROM wap_log WHERE database_id = ANY($1::int[]) AND status = 'sent' AND created_at >= date_trunc('day', now())`, [all.map(x => x.id)]);
  const tab = (key, text, note) => `<a href="#${key}" data-tab="${key}">${text}${note ? ` <span class="pill dim">${esc(note)}</span>` : ''}</a>`;

  page(req, res, d.db_name, `
    <p class="muted" style="margin:0 0 6px"><a href="/">&larr; All databases</a></p>
    <div class="row between">
      <h1 style="margin:0">${esc(d.db_name)} <span class="pill ${anyActive ? 'ok' : 'no'}">${anyActive ? 'active' : 'STOPPED'}</span></h1>
      <span class="muted">${esc(d.company_name)} &middot; <code>${esc(d.base_url)}</code></span>
    </div>
    <div class="tiles">
      <div class="tile"><b class="${connected === withNumber.length && connected ? 'ok-msg' : 'warn-msg'}">${connected} / ${withNumber.length}</b><span>numbers connected</span></div>
      <div class="tile"><b>${today.rows[0].wa}</b><span>WhatsApp messages today</span></div>
      <div class="tile"><b>${d.email_id ? today.rows[0].mail : '&mdash;'}</b><span>${d.email_id ? 'e-mails today' : 'no e-mail account yet'}</span></div>
    </div>
    ${anyActive ? '' : `<div class="card danger"><b>Stopped.</b> Every WhatsApp message and e-mail from this database is refused
      ("database ${esc(d.db_name)} is switched off") and incoming replies are not forwarded to it. The phone stays paired,
      nothing has to be scanned again. Press <b>Activate</b> to continue.</div>`}
    ${msg}
    <nav class="tabs">${tab('numbers', 'Numbers', String(withNumber.length))}${tab('settings', 'Settings')}${canEdit ? tab('email', 'E-mail', d.email_id ? '' : 'not set') + tab('login', 'Client login', d.client_username ? '' : 'none') : ''}${tab('activity', 'Activity')}</nav>
    <section class="tab" data-tab="numbers">${numbersCard}</section>
    <section class="tab" data-tab="settings">
    ${canEdit ? `
    <form method="post" action="/database/${d.id}" class="card narrow">
      <h2>Settings of the whole database</h2>
      ${isAdmin ? `
      <label>Vendor<select name="company_id">
        ${companies.rows.map(c => `<option value="${c.id}" ${c.id === d.company_id ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}
      </select><span class="muted">Changing the vendor drops the number assignment (numbers belong to a vendor).</span></label>
      <label>Database name<input name="db_name" value="${esc(d.db_name)}"></label>` : ''}
      <label>Sends as<input name="tenant_label" value="${esc(d.tenant_label)}"></label>
      <label class="check"><input type="checkbox" name="sign_messages" ${d.sign_messages ? 'checked' : ''}> Add the automatic no-reply footer (optional)</label>
      <span class="muted">Adds to every WhatsApp message and e-mail: <i>"This is an automated notification. Please do not reply."</i> and, when a support number is given below, a tap-to-chat link to it. Untick to send messages exactly as Odoo writes them.</span>
      ${phoneField('contact_number', 'WhatsApp Support number (optional)', { value: d.contact_number })}
      <span class="muted">Shown in that footer as the number to contact.</span>
      <button class="primary">Save</button> <a class="btn" href="/">Back</a>
    </form>` : `
    <div class="card narrow"><h2>Settings</h2><table class="plain">
      <tr><th>Sends as</th><td>${esc(d.tenant_label) || '<span class="muted">not set</span>'}</td></tr>
      <tr><th>Auto footer</th><td>${d.sign_messages ? 'on (no-reply notice' + (d.contact_number ? ' + support number)' : ')') : 'off'}</td></tr>
      <tr><th>Support number</th><td>${esc(d.contact_number) || '<span class="muted">not set</span>'}</td></tr>
      <tr><th>Email from</th><td>${d.email_id ? '<code>' + esc(d.from_email) + '</code>' : '<span class="muted">none</span>'}</td></tr>
    </table></div>`}
    ${isAdmin ? `
    <div class="card narrow danger">
      <h2 style="margin-top:0">Whole database</h2>
      <form method="post" action="/database/${d.id}/toggle" ${anyActive ? `onsubmit="return confirm('Stop the whole database, all its numbers and its e-mail? To stop one number use Turn off beside it.')"` : ''}>
        <p class="muted" style="margin-top:0">${anyActive ? 'Stops all its numbers and its e-mail. The phones stay paired. For one number use Turn off beside it.' : 'It is stopped: nothing goes out and nothing comes in.'}</p>
        <button class="${anyActive ? 'bad-btn' : 'primary'}">${anyActive ? 'Stop the whole database' : 'Activate - continue'}</button>
      </form>
      ${rowsOfDb.length < 2 ? `<form method="post" action="/database/${d.id}/delete" style="margin-top:14px">
      <label class="check"><input type="checkbox" name="sure" required> Remove this database and its client login</label>
      <button class="bad-btn">Remove database</button>
      </form>` : ''}
    </div>` : ''}
    </section>
    ${canEdit ? `<section class="tab" data-tab="email">${emailCard}</section>
    <section class="tab" data-tab="login">${clientCard}</section>` : ''}
    <section class="tab" data-tab="activity"><div class="card" style="overflow:auto">${logRows(logs.rows)}</div></section>
    ${TABS_SCRIPT}`);
});

app.post('/database/:id', requireLogin, requireVendorOrAdmin, scopeDatabase('id'), async (req, res) => {
  const d = req.db;
  const b = req.body || {};
  const isAdmin = req.session.role === 'admin';
  // a number saved before the country was asked is only checked when it changes
  const same = String(b.contact_number || '').trim() === String(d.contact_number || '').trim();
  if (!same && phoneWrong(b, 'contact_number')) return res.redirect(`/database/${d.id}?bad=` + encodeURIComponent('Support number: ' + phoneWrong(b, 'contact_number')));
  await pool.query(
    `UPDATE wap_database SET tenant_label=$1, contact_number=$2, sign_messages=$4 WHERE id = ANY($3::int[])`,
    [String(b.tenant_label || '').trim(), same ? String(d.contact_number || '').trim() : plusNumber(b.contact_number),
     (await siblings(d)).map(x => x.id), !!b.sign_messages]);
  if (isAdmin) {
    const companyId = Number(b.company_id) || d.company_id;
    const dbName = String(b.db_name || '').trim() || d.db_name;
    try {
      // the name and the vendor belong to the database: every number of it
      const ids = (await siblings(d)).map(x => x.id);
      if (dbName !== d.db_name) {
        const there = await pool.query('SELECT 1 FROM wap_database WHERE server_id = $1 AND db_name = $2 LIMIT 1', [d.server_id, dbName]);
        if (there.rowCount) throw new Error('duplicate name');
      }
      await pool.query('UPDATE wap_database SET db_name=$1, company_id=$2 WHERE id = ANY($3::int[])',
        [dbName, companyId, ids]);
      if (companyId !== d.company_id) {
        await pool.query('UPDATE wap_database SET number_id = NULL WHERE id = ANY($1::int[])', [ids]);
        await pool.query('UPDATE wap_admin SET company_id = $1 WHERE database_id = ANY($2::int[])', [companyId, ids]);
      }
    } catch (err) {
      return res.redirect(`/database/${d.id}?bad=` + encodeURIComponent(/duplicate/i.test(err.message) ? 'That name is already registered on this server.' : err.message.slice(0, 160)));
    }
  }
  res.redirect(`/database/${d.id}?ok=Saved.`);
});

app.post('/database/:id/number', requireLogin, requireAdmin, scopeDatabase('id'), async (req, res) => {
  const d = req.db;
  const numberId = Number(req.body.number_id) || null;
  if (numberId) {
    const n = await pool.query('SELECT id FROM wap_number WHERE id = $1', [numberId]);
    if (!n.rows.length) return res.redirect(`/database/${d.id}?bad=` + encodeURIComponent('That number no longer exists.'));
  }
  if (numberId && (await siblings(d)).some(x => x.id !== d.id && x.number_id === numberId)) {
    return res.redirect(`/database/${d.id}?bad=` + encodeURIComponent('This database has that number already, with its own key.'));
  }
  await pool.query('UPDATE wap_database SET number_id = $1 WHERE id = $2', [numberId, d.id]);
  res.redirect(`/database/${d.id}?ok=` + encodeURIComponent(numberId ? 'Number assigned.' : 'Number removed.'));
});

app.post('/database/:id/own-numbers', requireLogin, requireAdmin, scopeDatabase('id'), async (req, res) => {
  const max = Math.max(0, Math.min(50, Math.floor(Number((req.body || {}).max) || 0)));
  await pool.query('UPDATE wap_database SET own_numbers_max = $1 WHERE id = ANY($2::int[])', [max, (await siblings(req.db)).map(x => x.id)]);
  await log({ databaseId: req.db.id, db: req.db.db_name, endpoint: 'admin', status: 'own numbers', detail: `at most ${max}, by ${req.session.username}` });
  res.redirect(`/database/${req.db.id}?ok=` + encodeURIComponent(max ? `Odoo may have up to ${max} number(s).` : 'Only you add numbers now.') + '#numbers');
});

/** One number off or on; the phone stays paired, the other numbers go on. */
app.post('/database/:id/number/toggle', requireLogin, requireAdmin, scopeDatabase('id'), async (req, res) => {
  const d = req.db;
  await pool.query('UPDATE wap_database SET off_by = $2 WHERE id = $1', [d.id, d.off_by ? '' : 'admin']);
  await log({ databaseId: d.id, db: d.db_name, phone: d.authorized_number || '', endpoint: 'admin',
              status: d.off_by ? 'number on' : 'number off', detail: `by ${req.session.username}` });
  res.redirect(`/database/${d.id}?ok=` + encodeURIComponent(`${fmtNumber(d.authorized_number)} is ${d.off_by ? 'on' : 'off'} now.`));
});

app.post('/database/:id/limits', requireLogin, requireVendorOrAdmin, scopeDatabase('id'), async (req, res) => {
  const whole = v => Math.max(0, Math.min(100000, Math.floor(Number(v) || 0)));
  await pool.query('UPDATE wap_database SET daily_cap = $2, per_minute = $3 WHERE id = $1',
    [req.db.id, whole(req.body.daily_cap), whole(req.body.per_minute)]);
  res.redirect(`/database/${req.db.id}?ok=` + encodeURIComponent('Limits of that number saved.'));
});

/** One more number for the same Odoo database: its own row, key and caps. */
app.post('/database/:id/number/add', requireLogin, requireAdmin, scopeDatabase('id'), async (req, res) => {
  const d = req.db;
  const b = req.body || {};
  const back = msg => res.redirect(`/database/${d.id}?bad=` + encodeURIComponent(msg));
  const label = String(b.label || '').trim().slice(0, 60);
  let numberId = Number(b.number_id) || 0;
  const typed = digits(b.new_number);
  if (numberId && typed) return back('Type a new number or choose one, not both.');
  if (!numberId && !typed) return back('Type the new number, with the country code.');
  if (typed && phoneWrong(b, 'new_number')) return back(phoneWrong(b, 'new_number'));
  if (typed) {
    const made = await createNumber(d.company_id, label || (d.db_name + ' +' + typed), typed);
    if (made.error) return back(made.error);
    numberId = made.row.id;
  } else {
    const n = await pool.query('SELECT id FROM wap_number WHERE id = $1 AND active', [numberId]);
    if (!n.rows.length) return back('That number no longer exists, or it is switched off.');
    const here = await siblings(d);
    if (here.some(x => x.number_id === numberId)) return back('This database has that number already, with its own key.');
    const other = (await numberDatabases(numberId)).filter(x => !here.some(y => y.id === x.id));
    if (other.length && !b.shared) {
      return back('That number is used by ' + other.map(x => x.db_name).join(', ')
        + '. Both databases would get its messages and both may answer. Tick the box if that is really wanted.');
    }
  }
  try {
    const empty = (await siblings(d)).find(x => !x.number_id);
    if (empty) await pool.query('UPDATE wap_database SET number_id = $2 WHERE id = $1', [empty.id, numberId]);
    else await pool.query(
      `INSERT INTO wap_database (server_id, company_id, number_id, db_name, tenant_label, contact_number,
                                 token, daily_cap, per_minute, sign_messages, active, own_numbers_max)
       SELECT server_id, company_id, $2, db_name, tenant_label, contact_number,
              $3, daily_cap, per_minute, sign_messages, active, own_numbers_max
         FROM wap_database WHERE id = $1`, [d.id, numberId, token()]);
  } catch (err) {
    return back(/duplicate|unique/i.test(err.message) ? 'This database has that number already, with its own key.' : err.message.slice(0, 160));
  }
  await log({ databaseId: d.id, db: d.db_name, endpoint: 'admin', status: 'number added', detail: `by ${req.session.username}` });
  if (typed) return res.redirect(`/number/${numberId}/qr`);
  res.redirect(`/database/${d.id}?ok=` + encodeURIComponent('Number added. Its key is in the list below.') + '#numbers');
});

app.post('/database/:id/number/new', requireLogin, requireAdmin, scopeDatabase('id'), async (req, res) => {
  const d = req.db;
  const number = digits(req.body.new_number);
  if (d.number_id) {
    return res.redirect(`/database/${d.id}?bad=` + encodeURIComponent('This key has a number already. Use "Add another number".'));
  }
  if (phoneWrong(req.body, 'new_number')) return res.redirect(`/database/${d.id}?bad=` + encodeURIComponent(phoneWrong(req.body, 'new_number')));
  const made = await createNumber(d.company_id, d.db_name + ' +' + number, number);
  if (made.error) return res.redirect(`/database/${d.id}?bad=` + encodeURIComponent(made.error));
  await pool.query('UPDATE wap_database SET number_id = $1 WHERE id = $2', [made.row.id, d.id]);
  res.redirect(`/number/${made.row.id}/qr`);
});

/** Stop or resume one database. Used when a client has not paid: nothing goes
 *  out and nothing comes in for it, but the WhatsApp session is kept, so
 *  resuming is one click and no re-scan. */
app.post('/database/:id/toggle', requireLogin, requireAdmin, scopeDatabase('id'), async (req, res) => {
  const d = req.db;
  // the whole database: every number of it
  const everyone = await siblings(d);
  d.active = everyone.some(x => x.active);
  await pool.query('UPDATE wap_database SET active = $2 WHERE id = ANY($1::int[])', [everyone.map(x => x.id), !d.active]);
  await log({ databaseId: d.id, db: d.db_name, endpoint: 'admin', status: d.active ? 'deactivated' : 'activated',
              detail: `by ${req.session.username}` });
  res.redirect(String(req.headers.referer || '').includes('/database/') ? `/database/${d.id}` : '/');
});

app.post('/database/:id/rotate', requireLogin, requireVendorOrAdmin, scopeDatabase('id'), async (req, res) => {
  await pool.query('UPDATE wap_database SET token=$1 WHERE id=$2', [token(), req.db.id]);
  res.redirect(`/database/${req.db.id}?ok=` + encodeURIComponent('New key issued. Paste it into Odoo.'));
});

app.post('/database/:id/delete', requireLogin, requireAdmin, scopeDatabase('id'), async (req, res) => {
  if (!req.body.sure) return res.redirect('/database/' + req.db.id);
  if ((await siblings(req.db)).length > 1) {
    try {
      const heir = await dropRow(req.db);
      await log({ databaseId: heir, db: req.db.db_name, endpoint: 'admin', status: 'number removed', detail: `by ${req.session.username}` });
      return res.redirect(`/database/${heir}?ok=` + encodeURIComponent('That number and its key were removed from this database.'));
    } catch (err) {
      return res.redirect(`/database/${req.db.id}?bad=` + encodeURIComponent(err.message.slice(0, 160)));
    }
  }
  await pool.query('DELETE FROM wap_database WHERE id=$1', [req.db.id]);
  res.redirect('/');
});

app.post('/database/:id/email', requireLogin, requireVendorOrAdmin, scopeDatabase('id'), async (req, res) => {
  const d = req.db;
  const err = await saveEmailAccount(d, { ...(req.body || {}), active: !!(req.body || {}).active });
  if (err) return res.redirect(`/database/${d.id}?bad=` + encodeURIComponent(err));
  res.redirect(`/database/${d.id}?ok=` + encodeURIComponent('Email account saved.'));
});

app.post('/database/:id/email/test', requireLogin, requireVendorOrAdmin, scopeDatabase('id'), async (req, res) => {
  const { rows } = await pool.query('SELECT * FROM wap_email WHERE database_id=$1', [req.db.id]);
  if (!rows.length) return res.redirect(`/database/${req.db.id}?bad=` + encodeURIComponent('Save the account first.'));
  const result = await mailer.verify(rows[0]);
  res.redirect(`/database/${req.db.id}?tested=1` + (result.ok ? '' : '&testbad=' + encodeURIComponent(result.error.slice(0, 200))));
});

app.post('/database/:id/client', requireLogin, requireVendorOrAdmin, scopeDatabase('id'), async (req, res) => {
  const d = req.db;
  const isAdmin = req.session.role === 'admin';
  const existing = await pool.query('SELECT * FROM wap_admin WHERE database_id = $1 LIMIT 1', [d.id]);
  const cur = existing.rows[0];
  const username = d.db_name;
  const password = String(req.body.password || '');
  const bad = msg => res.redirect(`/database/${d.id}?bad=` + encodeURIComponent(msg));
  if (!username) return bad('Give the client a username.');
  if (!cur && password.length < 6) return bad('Password must be at least 6 characters.');
  if (password && password.length < 6) return bad('Password must be at least 6 characters.');
  if (await usernameTaken(username, d.company_id, cur ? cur.id : 0)) return bad(`Username ${username} is already used under ${d.company_name}.`);
  if (cur) {
    await pool.query('UPDATE wap_admin SET username=$1, company_id=$2' + (password ? ', password_hash=$4' : '') + ' WHERE id=$3',
      password ? [username, d.company_id, cur.id, bcrypt.hashSync(password, 10)] : [username, d.company_id, cur.id]);
  } else {
    await pool.query('INSERT INTO wap_admin (username, password_hash, company_id, database_id) VALUES ($1,$2,$3,$4)',
      [username, bcrypt.hashSync(password, 10), d.company_id, d.id]);
  }
  res.redirect(`/database/${d.id}?ok=` + encodeURIComponent(`Client login ${username} saved.`));
});

app.post('/database/:id/client/delete', requireLogin, requireAdmin, scopeDatabase('id'), async (req, res) => {
  await pool.query('DELETE FROM wap_admin WHERE database_id = $1', [req.db.id]);
  res.redirect(`/database/${req.db.id}?ok=` + encodeURIComponent('Client login removed.'));
});

// ---------------------------------------------------------------- numbers

app.get('/numbers', requireLogin, requireVendorOrAdmin, async (req, res) => {
  const isAdmin = req.session.role === 'admin';
  const { rows } = await pool.query(
    `SELECT n.*, c.name AS company_name,
            (SELECT string_agg(d.db_name, ', ' ORDER BY d.db_name) FROM wap_database d WHERE d.number_id = n.id) AS dbs
       FROM wap_number n JOIN wap_company c ON c.id = n.company_id
      WHERE ($1::int IS NULL OR n.company_id = $1)
      ORDER BY c.name, n.label`, [isAdmin ? null : req.session.companyId]);
  try {
    const map = await fetchInstanceMap();
    for (let i = 0; i < rows.length; i++) rows[i] = await checkPairing(rows[i], map);
  } catch (err) { /* shown from the last known state */ }
  page(req, res, 'Numbers', `
    <div class="row between">
      <h1>WhatsApp numbers</h1>
      ${isAdmin ? '<a class="btn primary" href="/numbers/new">Add number</a>' : ''}
    </div>
    <p class="muted">A number is one connection to WhatsApp and the ONE phone
    allowed to scan it. ${isAdmin ? 'Assign it to one database or to several.' : 'The administrator creates and assigns them.'}
    A scan by any other phone is logged out again and refused.</p>
    ${rows.length ? `<table>
      <tr>${isAdmin ? '<th>Vendor</th>' : ''}<th>Number</th><th>Authorized</th><th>Paired</th><th>State</th><th>Databases</th><th></th></tr>
      ${rows.map(n => `<tr class="${n.active ? '' : 'off'}">
        ${isAdmin ? `<td>${esc(n.company_name)}</td>` : ''}
        <td><a href="/number/${n.id}"><b>${esc(n.label)}</b></a><br><span class="muted"><code>${esc(n.instance_name)}</code></span></td>
        <td>${esc(fmtNumber(n.authorized_number)) || '<span class="muted">adopts first scan</span>'}</td>
        <td>${esc(fmtNumber(n.paired_number)) || '<span class="muted">—</span>'}</td>
        <td>${statePill(n.pair_state)}</td>
        <td>${n.dbs ? esc(n.dbs) : '<span class="muted">none</span>'}</td>
        <td class="right"><a class="btn" href="/number/${n.id}/qr">${n.pair_state === 'open' ? 'Connection' : 'Scan QR'}</a></td>
      </tr>`).join('')}
    </table>` : `<div class="card"><p>No numbers yet.</p>${isAdmin ? '<a class="btn primary" href="/numbers/new">Add the first number</a>' : ''}</div>`}`);
});

app.get('/numbers/new', requireLogin, requireAdmin, async (req, res) => {
  const companies = await pool.query('SELECT * FROM wap_company ORDER BY name');
  page(req, res, 'Add number', `
    <form method="post" action="/numbers/new" class="card narrow">
      <h1>Add WhatsApp number</h1>
      ${req.query.bad ? `<p class="bad">${esc(req.query.bad)}</p>` : ''}
      <label>Vendor<select name="company_id">
        ${companies.rows.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}
      </select></label>
      <label>Label<input name="label" placeholder="Spa main line" required></label>
      ${phoneField('authorized_number', 'Country', { required: true })}
      <span class="muted">This is the ONLY phone that may scan the QR. Databases are attached afterwards.</span>
      <p><button class="primary">Create</button> <a class="btn" href="/numbers">Cancel</a></p>
    </form>`);
});

/**
 * Create a number: the instance on the gateway, the row, the webhook.
 * Returns {row} or {error}. Used by Numbers > Add and by the database forms.
 */
async function createNumber(companyId, label, rawNumber) {
  const number = digits(rawNumber);
  const company = await pool.query('SELECT * FROM wap_company WHERE id = $1', [companyId]);
  if (!company.rows.length) return { error: 'Choose a vendor.' };
  if (number.length < 8 || number.length > 15) return { error: 'The phone number needs 8 to 15 digits, with the country code.' };
  const dup = await pool.query('SELECT label FROM wap_number WHERE authorized_number = $1', [number]);
  if (dup.rows.length) return { error: `+${number} is already used by "${dup.rows[0].label}".` };
  label = String(label || '').trim() || ('+' + number);

  let instance = `${slug(company.rows[0].name, 18)}-${number}`;
  try {
    const map = await fetchInstanceMap();
    if (map[instance]) instance += '-' + Date.now().toString(36).slice(-4);
  } catch (err) { /* the create call will say */ }
  try {
    const made = await evo('/instance/create', 'POST', { instanceName: instance, qrcode: true, integration: 'WHATSAPP-BAILEYS' });
    if (!made.ok) {
      const detail = (made.data && (made.data.response || made.data.message)) || 'gateway refused it';
      return { error: JSON.stringify(detail).slice(0, 160) };
    }
  } catch (err) {
    return { error: 'The gateway is not reachable: ' + err.message.slice(0, 120) };
  }
  const { rows } = await pool.query(
    `INSERT INTO wap_number (company_id, label, authorized_number, instance_name, hook_secret)
     VALUES ($1,$2,$3,$4,$5) RETURNING *`, [companyId, label, number, instance, token()]);
  await applyHook(rows[0]);
  return { row: rows[0] };
}

/** Write a database's mail account from a form body; empty password keeps the old one. */
async function saveEmailAccount(d, b) {
  const existing = await pool.query('SELECT * FROM wap_email WHERE database_id=$1', [d.id]);
  const password = String(b.password || '') || (existing.rows[0] ? existing.rows[0].password : '');
  const vals = [String(b.host || '').trim(), Number(b.port) || 587, !!b.secure,
                String(b.username || '').trim(), password,
                String(b.from_name || '').trim(), String(b.from_email || '').trim(),
                Number(b.daily_cap) || 0, Number(b.per_minute) || 0, b.active === undefined ? true : !!b.active];
  if (!vals[0] || !vals[6]) return 'SMTP server and From address are required.';
  if (existing.rows.length) {
    await pool.query(
      `UPDATE wap_email SET host=$1, port=$2, secure=$3, username=$4, password=$5,
                            from_name=$6, from_email=$7, daily_cap=$8, per_minute=$9, active=$10
        WHERE database_id=$11`, [...vals, d.id]);
    mailer.forget(existing.rows[0].id);
  } else {
    await pool.query(
      `INSERT INTO wap_email (host, port, secure, username, password, from_name, from_email,
                              daily_cap, per_minute, active, database_id, company_id)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`, [...vals, d.id, d.company_id]);
  }
  return '';
}

app.post('/numbers/new', requireLogin, requireAdmin, async (req, res) => {
  const b = req.body || {};
  if (phoneWrong(b, 'authorized_number')) return res.redirect('/numbers/new?bad=' + encodeURIComponent(phoneWrong(b, 'authorized_number')));
  const made = await createNumber(Number(b.company_id) || 0, b.label, b.authorized_number);
  if (made.error) return res.redirect('/numbers/new?bad=' + encodeURIComponent(made.error));
  res.redirect(`/number/${made.row.id}/qr`);
});

app.get('/number/:id', requireLogin, requireVendorOrAdmin, scopeNumber('id'), async (req, res) => {
  const isAdmin = req.session.role === 'admin';
  const n = await refreshNumber(req.number);
  const dbs = await pool.query(`SELECT d.id, d.db_name, d.number_id, s.base_url, c.name AS company_name
                                   FROM wap_database d JOIN wap_server s ON s.id = d.server_id
                                   LEFT JOIN wap_company c ON c.id = d.company_id
                                  ORDER BY s.base_url, d.db_name`);
  const assigned = dbs.rows.filter(d => d.number_id === n.id);
  const q = req.query;
  page(req, res, n.label, `
    <h1>${esc(n.label)} <span class="muted">— ${esc(n.company_name)}</span></h1>
    ${q.ok ? `<p class="ok-msg">${esc(q.ok)}</p>` : ''}${q.bad ? `<p class="bad">${esc(q.bad)}</p>` : ''}
    <div class="card narrow">
      <p>${statePill(n.pair_state)}</p>
      <table class="plain">
        <tr><th>Authorized</th><td class="big">${esc(fmtNumber(n.authorized_number)) || '<span class="muted">adopts the first phone that scans</span>'}</td></tr>
        <tr><th>Paired</th><td>${esc(fmtNumber(n.paired_number)) || '<span class="muted">none</span>'} ${esc(n.profile_name)}</td></tr>
        ${n.last_wrong_number ? `<tr><th>Last refused</th><td class="bad">${esc(fmtNumber(n.last_wrong_number))} (${n.wrong_number_count}x, ${n.wrong_number_at ? new Date(n.wrong_number_at).toLocaleString() : ''})</td></tr>` : ''}
        <tr><th>Instance</th><td><code>${esc(n.instance_name)}</code></td></tr>
        <tr><th>Webhook</th><td>${n.webhook_applied ? '<span class="pill ok">points at the panel</span>' : '<span class="pill warn">not applied yet</span>'}</td></tr>
      </table>
      <a class="btn primary" href="/number/${n.id}/qr">${n.pair_state === 'open' ? 'Connection' : 'Scan / connect'}</a>
      <a class="btn" href="/numbers">Back</a>
    </div>
    ${isAdmin ? `
    <form method="post" action="/number/${n.id}" class="card narrow">
      <h2>Settings</h2>
      <label>Label<input name="label" value="${esc(n.label)}" required></label>
      ${phoneField('authorized_number', 'Authorized phone number', { value: n.authorized_number })}
      <span class="muted">Changing it while another phone is paired logs that phone out.</span>
      <label class="check"><input type="checkbox" name="active" ${n.active ? 'checked' : ''}> Allowed to send</label>
      <button class="primary">Save</button>
    </form>
    <form method="get" action="/database/new" class="card narrow">
      <h2>Attach a database on any Odoo URL</h2>
      <p class="muted">Type the address of the Odoo server (local or cloud); its database
      list is read live and the new database is registered on this number.</p>
      <input type="hidden" name="number_id" value="${n.id}">
      <label>Odoo URL<input name="url" placeholder="https://dubai.369ai.biz" required></label>
      <button class="primary">Continue</button>
    </form>
    <form method="post" action="/number/${n.id}/assign" class="card narrow">
      <h2>Assigned databases</h2>
      <p class="muted">Tick every database that sends on this number - any vendor, any server.
      Replies are delivered to all of them, so keep only ONE of them Active for the
      customer chat (the others answer "hi" too); notification-only databases can share freely.</p>
      <div class="checks">
        ${dbs.rows.length ? dbs.rows.map(d => `<label class="check"><input type="checkbox" name="db" value="${d.id}" ${d.number_id === n.id ? 'checked' : ''}>
          <code>${esc(d.db_name)}</code> <span class="muted">${esc(d.base_url)}${d.company_name ? ' &middot; ' + esc(d.company_name) : ''}</span> ${d.number_id && d.number_id !== n.id ? '<span class="muted">(on another number now)</span>' : ''}</label>`).join('')
          : '<p class="muted">No databases registered yet - attach one above.</p>'}
      </div>
      <label class="check"><input type="checkbox" name="sure"> Replace the number of a ticked database that has another one now</label>
      <button class="primary">Save assignment</button>
    </form>
    <form method="post" action="/number/${n.id}/delete" class="card narrow danger">
      <h2>Delete number</h2>
      ${assigned.length ? `<p class="bad">Still assigned to ${assigned.map(d => '<code>' + esc(d.db_name) + '</code>').join(' ')}. Unassign them first.</p>`
        : `<label class="check"><input type="checkbox" name="sure" required> Delete the number and its connection on the gateway</label><button class="bad-btn">Delete</button>`}
    </form>` : `
    <div class="card narrow"><h2>Assigned databases</h2>
      ${assigned.length ? assigned.map(d => `<p><a href="/database/${d.id}"><code>${esc(d.db_name)}</code></a></p>`).join('') : '<p class="muted">None.</p>'}
    </div>`}`);
});

app.post('/number/:id', requireLogin, requireAdmin, scopeNumber('id'), async (req, res) => {
  const n = req.number;
  const label = String(req.body.label || '').trim() || n.label;
  const number = digits(req.body.authorized_number);
  const bad = msg => res.redirect(`/number/${n.id}?bad=` + encodeURIComponent(msg));
  if (number !== n.authorized_number && phoneWrong(req.body, 'authorized_number')) return bad(phoneWrong(req.body, 'authorized_number'));
  if (number && (number.length < 8 || number.length > 15)) return bad('The phone number needs 8 to 15 digits.');
  const dup = await pool.query('SELECT label FROM wap_number WHERE authorized_number = $1 AND id <> $2 AND $1 <> \'\'', [number, n.id]);
  if (dup.rows.length) return bad(`+${number} is already used by "${dup.rows[0].label}".`);
  await pool.query('UPDATE wap_number SET label=$1, authorized_number=$2, active=$3, last_wrong_number=CASE WHEN $2 <> authorized_number THEN \'\' ELSE last_wrong_number END, pair_state=CASE WHEN pair_state=\'wrong_number\' AND $2 <> authorized_number THEN \'close\' ELSE pair_state END WHERE id=$4',
    [label, number, !!req.body.active, n.id]);
  if (number && n.paired_number && n.paired_number !== number) {
    try { await evo(`/instance/logout/${n.instance_name}`, 'DELETE'); } catch (err) { /* sweep retries */ }
    await pool.query('UPDATE wap_number SET paired_number=\'\', profile_name=\'\', pair_state=\'close\' WHERE id=$1', [n.id]);
  }
  res.redirect(`/number/${n.id}?ok=Saved.`);
});

app.post('/number/:id/assign', requireLogin, requireAdmin, scopeNumber('id'), async (req, res) => {
  const n = req.number;
  const picked = [].concat(req.body.db || []).map(Number).filter(Boolean);
  const same = await pool.query(
    `SELECT db_name FROM wap_database WHERE id = ANY($1::int[]) GROUP BY server_id, db_name HAVING count(*) > 1`, [picked]);
  if (same.rows.length) {
    return res.redirect(`/number/${n.id}?bad=` + encodeURIComponent(`${same.rows[0].db_name} is ticked twice: a number can be in a database only once.`));
  }
  const steals = await pool.query(
    `SELECT d.db_name FROM wap_database d WHERE d.id = ANY($1::int[]) AND d.number_id IS NOT NULL AND d.number_id <> $2`, [picked, n.id]);
  if (steals.rows.length && !req.body.sure) {
    return res.redirect(`/number/${n.id}?bad=` + encodeURIComponent(`${steals.rows.map(x => x.db_name).join(', ')} would lose the number it has now. Tick "Replace" as well, or use "Add another number" on the database page.`));
  }
  // numberfirst: a number may serve databases of any vendor on any server.
  await pool.query('UPDATE wap_database SET number_id = NULL WHERE number_id = $1 AND NOT (id = ANY($2::int[]))', [n.id, picked]);
  await pool.query('UPDATE wap_database SET number_id = $1 WHERE id = ANY($2::int[])', [n.id, picked]);
  res.redirect(`/number/${n.id}?ok=` + encodeURIComponent('Assignment saved.'));
});

app.post('/number/:id/delete', requireLogin, requireAdmin, scopeNumber('id'), async (req, res) => {
  const n = req.number;
  if (!req.body.sure) return res.redirect(`/number/${n.id}`);
  const used = await pool.query('SELECT count(*)::int AS c FROM wap_database WHERE number_id = $1', [n.id]);
  if (used.rows[0].c) return res.redirect(`/number/${n.id}?bad=` + encodeURIComponent('Unassign its databases first.'));
  try { await evo(`/instance/logout/${n.instance_name}`, 'DELETE'); } catch (err) { /* fine */ }
  try { await evo(`/instance/delete/${n.instance_name}`, 'DELETE'); } catch (err) { /* fine */ }
  await pool.query('DELETE FROM wap_number WHERE id = $1', [n.id]);
  res.redirect('/numbers');
});

/** The QR / connection page. Every role that covers the number may open it. */
app.get('/number/:id/qr', requireLogin, scopeNumber('id'), async (req, res) => {
  const n = await refreshNumber(req.number);
  const dbs = await numberDatabases(n.id);
  const isClient = req.session.role === 'client';
  const backHref = isClient ? '/me' : `/number/${n.id}`;
  let qr = '';
  if (n.pair_state !== 'open' && n.pair_state !== 'missing') {
    try {
      const c = await evo(`/instance/connect/${n.instance_name}`);
      if (c.data && c.data.base64) qr = c.data.base64;
    } catch (err) { /* leave qr empty */ }
  }
  const allowed = fmtNumber(n.authorized_number);
  page(req, res, n.label, `
    <h1>${esc(n.label)} <span class="muted">— WhatsApp connection</span></h1>
    <p class="muted">Used by ${dbs.length ? dbs.map(d => '<code>' + esc(d.db_name) + '</code>').join(' ') : 'no database yet'}.</p>
    ${n.pair_state === 'open' ? `
      <div class="card narrow" id="qr-open">
        <p>${statePill('open')}</p>
        <table class="plain">
          <tr><th>Number</th><td class="big">${esc(fmtNumber(n.paired_number))}</td></tr>
          <tr><th>Name</th><td>${esc(n.profile_name)}</td></tr>
        </table>
        <p class="muted">Keep the SIM active — if the phone stays offline for about
        two weeks WhatsApp drops the link and it must be scanned again.</p>
        <a class="btn" href="${backHref}">Back</a>
      </div>
      <div class="card narrow danger">
        <h2>Disconnect</h2>
        <p class="muted">Unlinks this phone. Every database on this number stops sending until it is scanned again.</p>
        <form method="post" action="/number/${n.id}/logout">
          <label class="check"><input type="checkbox" name="sure" required> I understand</label>
          <button class="bad-btn">Disconnect</button>
        </form>
      </div>` : `
      <div id="qr-live">
      ${n.pair_state === 'wrong_number' ? `
      <div class="card narrow danger">
        <h2 class="bad">Wrong phone</h2>
        <p>This QR was scanned with <b>${esc(fmtNumber(n.last_wrong_number))}</b>.
        Only <b>${esc(allowed)}</b> is allowed for this number, so that phone was
        logged out again${n.wrong_number_count > 1 ? ` (${n.wrong_number_count} attempts)` : ''}.</p>
      </div>` : ''}
      <div class="card narrow">
        <p>${statePill(n.pair_state)}</p>
        ${n.pair_state === 'missing' ? `<p class="bad">The gateway has no instance called <code>${esc(n.instance_name)}</code>.</p>
          ${isClient ? '<p class="muted">Ask your vendor or the administrator to reset it.</p>' : ''}`
        : qr ? `
          <p>Scan this with the phone holding <b class="big">${esc(allowed) || 'the number for this database'}</b>:</p>
          <p class="muted">WhatsApp &rarr; <b>Linked devices</b> &rarr; <b>Link a device</b></p>
          <div class="qr-box"><img class="qr" src="${esc(qr)}" alt="WhatsApp QR code"></div>
          <div class="qr-time" aria-hidden="true"><i></i></div>
          <p class="muted">The code expires in under a minute. It renews
          itself — leave it open and point the camera again. Any other phone is
          refused.</p>
        ` : `<p class="bad">No QR yet.</p><p class="muted">The gateway may still be starting. Wait and reload.</p>`}
        <form method="post" action="/number/${n.id}/restart" style="margin-top:14px"><button>Reload the code</button></form>
        <a class="btn" href="${backHref}">Back</a>
      </div>
      </div>
      ${isClient ? '' : `
      <div class="card narrow danger">
        <h2>Stuck on "${esc(n.pair_state)}"?</h2>
        <p class="muted">Throw the connection away and make a clean one. Reloading
        alone cannot fix a half-finished pairing.</p>
        <form method="post" action="/number/${n.id}/reset">
          <label class="check"><input type="checkbox" name="sure" required> Discard and start over</label>
          <button class="bad-btn">Reset and scan again</button>
        </form>
      </div>`}
      <noscript><meta http-equiv="refresh" content="12"></noscript>`}`);
});

app.post('/number/:id/restart', requireLogin, scopeNumber('id'), async (req, res) => {
  try { await evo(`/instance/restart/${req.number.instance_name}`, 'POST'); } catch (err) { /* shown on the page */ }
  res.redirect(`/number/${req.number.id}/qr`);
});

app.post('/number/:id/logout', requireLogin, scopeNumber('id'), async (req, res) => {
  if (!req.body.sure) return res.redirect(`/number/${req.number.id}/qr`);
  try { await evo(`/instance/logout/${req.number.instance_name}`, 'DELETE'); } catch (err) { /* shown on the page */ }
  await pool.query('UPDATE wap_number SET pair_state=\'close\', paired_number=\'\', profile_name=\'\' WHERE id=$1', [req.number.id]);
  res.redirect(`/number/${req.number.id}/qr`);
});

app.post('/number/:id/reset', requireLogin, requireVendorOrAdmin, scopeNumber('id'), async (req, res) => {
  const n = req.number;
  if (!req.body.sure) return res.redirect(`/number/${n.id}/qr`);
  try { await evo(`/instance/logout/${n.instance_name}`, 'DELETE'); } catch (err) { /* may not be linked */ }
  try { await evo(`/instance/delete/${n.instance_name}`, 'DELETE'); } catch (err) { /* may not exist */ }
  try {
    await evo('/instance/create', 'POST', { instanceName: n.instance_name, qrcode: true, integration: 'WHATSAPP-BAILEYS' });
  } catch (err) { /* the page will show it is missing */ }
  await pool.query('UPDATE wap_number SET pair_state=\'close\', paired_number=\'\', profile_name=\'\', webhook_applied=FALSE WHERE id=$1', [n.id]);
  await applyHook({ ...n, webhook_applied: false });
  res.redirect(`/number/${n.id}/qr`);
});

// ---------------------------------------------------------------- vendors (admin)

app.get('/companies', requireLogin, requireAdmin, async (req, res) => {
  const { rows } = await pool.query(`
    SELECT c.*,
           (SELECT count(*)::int FROM wap_database d WHERE d.company_id = c.id) AS dbs,
           (SELECT count(*)::int FROM wap_number n WHERE n.company_id = c.id) AS numbers,
           (SELECT string_agg(a.username, ', ') FROM wap_admin a WHERE a.company_id = c.id AND a.database_id IS NULL) AS logins
      FROM wap_company c ORDER BY c.name`);
  page(req, res, 'Vendors', `
    <div class="row between">
      <h1>Vendors</h1>
      <a class="btn primary" href="/companies/new">Add vendor</a>
    </div>
    <p class="muted">A vendor is a software company. It signs in with its name and
    sees only the databases and numbers you assign to it.</p>
    ${rows.length ? `<table>
      <tr><th>Vendor</th><th>Login</th><th>Databases</th><th>Numbers</th><th></th><th></th></tr>
      ${rows.map(c => `<tr class="${c.active ? '' : 'off'}">
        <td><a href="/company/${c.id}"><b>${esc(c.name)}</b></a></td>
        <td><code>${esc(c.logins || '')}</code></td>
        <td class="num">${c.dbs}</td>
        <td class="num">${c.numbers}</td>
        <td><span class="pill ${c.active ? 'ok' : 'no'}">${c.active ? 'on' : 'off'}</span></td>
        <td class="right"><a class="btn" href="/company/${c.id}">Settings</a></td>
      </tr>`).join('')}
    </table>` : `<div class="card"><p>No vendors yet.</p><a class="btn primary" href="/companies/new">Add the first one</a></div>`}`);
});

app.get('/companies/new', requireLogin, requireAdmin, (req, res) => {
  page(req, res, 'Add vendor', `
    <form method="post" action="/companies/new" class="card narrow">
      <h1>Add vendor</h1>
      <p class="muted">A login of its own is created. Numbers are added separately under Numbers.</p>
      <label>Vendor name<input name="name" placeholder="369ai" required>
        <span class="muted">Typed at sign-in, together with the username below.</span></label>
      <label>Username<input name="username" value="admin" required></label>
      <label>Password<input name="password" type="password" required minlength="6"></label>
      ${req.query.bad ? `<p class="bad">${esc(req.query.bad)}</p>` : ''}
      <button class="primary">Add</button> <a class="btn" href="/companies">Cancel</a>
    </form>`);
});

app.post('/companies/new', requireLogin, requireAdmin, async (req, res) => {
  const name = String(req.body.name || '').trim();
  const username = String(req.body.username || 'admin').trim() || 'admin';
  const password = String(req.body.password || '');
  if (!name) return res.redirect('/companies/new?bad=Give+it+a+name');
  if (password.length < 6) return res.redirect('/companies/new?bad=' + encodeURIComponent('Set a password of at least 6 characters.'));
  try {
    const { rows } = await pool.query('INSERT INTO wap_company (name) VALUES ($1) RETURNING id', [name]);
    await pool.query('INSERT INTO wap_admin (username, password_hash, company_id) VALUES ($1,$2,$3)',
      [username, bcrypt.hashSync(password, 10), rows[0].id]);
    return page(req, res, 'Vendor added', `
      <div class="card narrow">
        <h1>${esc(name)} added</h1>
        <table class="plain">
          <tr><th>Vendor name</th><td><code>${esc(name)}</code></td></tr>
          <tr><th>Username</th><td><code>${esc(username)}</code></td></tr>
          <tr><th>Password</th><td class="muted">the one you just set</td></tr>
        </table>
        <a class="btn primary" href="/database/new?company_id=${rows[0].id}">Add its first database</a>
        <a class="btn" href="/">Done</a>
      </div>`);
  } catch (err) {
    return res.redirect('/companies/new?bad=' + encodeURIComponent(/duplicate/i.test(err.message) ? 'That vendor already exists.' : err.message.slice(0, 160)));
  }
});

app.get('/company/:id', requireLogin, requireAdmin, async (req, res) => {
  const { rows } = await pool.query('SELECT * FROM wap_company WHERE id = $1', [Number(req.params.id) || 0]);
  if (!rows.length) return res.redirect('/companies');
  const c = rows[0];
  const dbs = await pool.query('SELECT id, db_name FROM wap_database WHERE company_id = $1 ORDER BY db_name', [c.id]);
  const numbers = await pool.query('SELECT id, label, authorized_number, pair_state FROM wap_number WHERE company_id = $1 ORDER BY label', [c.id]);
  const logins = await pool.query('SELECT id, username FROM wap_admin WHERE company_id = $1 AND database_id IS NULL ORDER BY username', [c.id]);
  const q = req.query;
  page(req, res, c.name, `
    <h1>${esc(c.name)}</h1>
    ${q.ok ? `<p class="ok-msg">${esc(q.ok)}</p>` : ''}${q.bad ? `<p class="bad">${esc(q.bad)}</p>` : ''}
    <form method="post" action="/company/${c.id}" class="card narrow">
      <label>Vendor name<input name="name" value="${esc(c.name)}"><span class="muted">Typed at sign-in.</span></label>
      <label class="check"><input type="checkbox" name="active" ${c.active ? 'checked' : ''}> Allowed to send</label>
      <button class="primary">Save</button> <a class="btn" href="/companies">Back</a>
    </form>
    <div class="card narrow">
      <h2>Vendor login</h2>
      ${logins.rows.map(l => `
        <form method="post" action="/company/${c.id}/password" class="row gap">
          <input type="hidden" name="admin_id" value="${l.id}">
          <code>${esc(l.username)}</code>
          <input name="password" type="password" placeholder="new password" minlength="6" required autocomplete="new-password">
          <button>Reset password</button>
        </form>`).join('') || '<p class="muted">No vendor login.</p>'}
      <form method="post" action="/company/${c.id}/login" class="row gap">
        <input name="username" placeholder="new login username" required autocomplete="off">
        <input name="password" type="password" placeholder="password" minlength="6" required autocomplete="new-password">
        <button>Add login</button>
      </form>
    </div>
    <div class="card narrow">
      <h2>Numbers</h2>
      ${numbers.rows.length ? `<table class="plain">${numbers.rows.map(n => `<tr>
        <td><a href="/number/${n.id}">${esc(n.label)}</a></td><td>${esc(fmtNumber(n.authorized_number))}</td><td>${statePill(n.pair_state)}</td></tr>`).join('')}</table>` : '<p class="muted">None yet.</p>'}
      <a class="btn" href="/numbers/new">Add number</a>
    </div>
    <div class="card narrow">
      <h2>Databases</h2>
      ${dbs.rows.length ? dbs.rows.map(d => `<p><a href="/database/${d.id}"><code>${esc(d.db_name)}</code></a></p>`).join('') : '<p class="muted">None yet.</p>'}
      <a class="btn primary" href="/database/new?company_id=${c.id}">Add database under ${esc(c.name)}</a>
    </div>
    <div class="card narrow danger">
      <h2>Delete vendor</h2>
      ${dbs.rows.length || numbers.rows.length ? `<p class="bad">Remove its databases and numbers first.</p>` : `
        <form method="post" action="/company/${c.id}/delete">
          <label class="check"><input type="checkbox" name="sure" required> I want to delete ${esc(c.name)}</label>
          <button class="bad-btn">Delete ${esc(c.name)}</button>
        </form>`}
    </div>`);
});

app.post('/company/:id', requireLogin, requireAdmin, async (req, res) => {
  const name = String(req.body.name || '').trim();
  const id = Number(req.params.id) || 0;
  if (name) await pool.query('UPDATE wap_company SET name=$1, active=$2 WHERE id=$3', [name, !!req.body.active, id]);
  res.redirect(`/company/${id}?ok=Saved.`);
});

app.post('/company/:id/password', requireLogin, requireAdmin, async (req, res) => {
  const id = Number(req.params.id) || 0;
  const password = String(req.body.password || '');
  if (password.length < 6) return res.redirect(`/company/${id}?bad=` + encodeURIComponent('At least 6 characters.'));
  const r = await pool.query('UPDATE wap_admin SET password_hash=$1 WHERE id=$2 AND company_id=$3 AND database_id IS NULL',
    [bcrypt.hashSync(password, 10), Number(req.body.admin_id) || 0, id]);
  res.redirect(`/company/${id}?` + (r.rowCount ? 'ok=Password+reset.' : 'bad=No+such+login.'));
});

app.post('/company/:id/login', requireLogin, requireAdmin, async (req, res) => {
  const id = Number(req.params.id) || 0;
  const username = String(req.body.username || '').trim();
  const password = String(req.body.password || '');
  if (!username || password.length < 6) return res.redirect(`/company/${id}?bad=` + encodeURIComponent('Username and a password of at least 6 characters.'));
  if (await usernameTaken(username, id, 0)) return res.redirect(`/company/${id}?bad=` + encodeURIComponent(`${username} is already used under this vendor.`));
  await pool.query('INSERT INTO wap_admin (username, password_hash, company_id) VALUES ($1,$2,$3)', [username, bcrypt.hashSync(password, 10), id]);
  res.redirect(`/company/${id}?ok=` + encodeURIComponent(`Login ${username} added.`));
});

app.post('/company/:id/delete', requireLogin, requireAdmin, async (req, res) => {
  const id = Number(req.params.id) || 0;
  if (!req.body.sure) return res.redirect('/company/' + id);
  const used = await pool.query('SELECT (SELECT count(*) FROM wap_database WHERE company_id=$1) + (SELECT count(*) FROM wap_number WHERE company_id=$1) AS n', [id]);
  if (Number(used.rows[0].n)) return res.redirect(`/company/${id}?bad=` + encodeURIComponent('Remove its databases and numbers first.'));
  await pool.query('DELETE FROM wap_optout WHERE company_id=$1', [id]);
  await pool.query('DELETE FROM wap_email_optout WHERE company_id=$1', [id]);
  await pool.query('DELETE FROM wap_email WHERE company_id=$1 AND database_id IS NULL', [id]);
  await pool.query('DELETE FROM wap_admin WHERE company_id=$1', [id]);
  await pool.query('DELETE FROM wap_company WHERE id=$1', [id]);
  res.redirect('/companies');
});

// ---------------------------------------------------------------- legacy addresses

app.get(['/number/:companyId/legacy', '/inbound', '/email'], requireLogin, (req, res) => res.redirect('/'));
app.post(['/inbound', '/email/:companyId', '/email/:companyId/test', '/company/:id/reset'], requireLogin, (req, res) => res.redirect('/'));

// ---------------------------------------------------------------- blocking

/** Which opt-out rows a login may see or touch. */
function optoutScope(req) {
  const s = req.session;
  if (s.role === 'admin') return { sql: 'TRUE', params: [] };
  if (s.role === 'vendor') return { sql: 'o.company_id = $1', params: [s.companyId] };
  return { sql: 'o.database_id = $1', params: [s.databaseId] };
}

app.get('/blocked', requireLogin, async (req, res) => {
  const s = req.session;
  const isAdmin = s.role === 'admin';
  if (s.role === 'client') return res.redirect('/me');
  const scope = optoutScope(req);
  const optouts = await pool.query(`
    SELECT o.*, c.name AS company_name, d.db_name FROM wap_optout o
      LEFT JOIN wap_company c ON c.id = o.company_id
      LEFT JOIN wap_database d ON d.id = o.database_id
     WHERE ${scope.sql} ORDER BY o.created_at DESC LIMIT 200`, scope.params);
  const blocks = isAdmin ? await pool.query('SELECT * FROM wap_block ORDER BY pattern') : { rows: [] };
  const targets = await pool.query(
    `SELECT d.id, d.db_name, c.name AS company_name, d.company_id FROM wap_database d
       JOIN wap_company c ON c.id = d.company_id
      WHERE ($1::int IS NULL OR d.company_id = $1) ORDER BY c.name, d.db_name`, [isAdmin ? null : s.companyId]);
  const companies = await pool.query('SELECT id, name FROM wap_company WHERE ($1::int IS NULL OR id = $1) ORDER BY name', [isAdmin ? null : s.companyId]);
  page(req, res, isAdmin ? 'Blocking' : 'Opt-outs', `
    <h1>${isAdmin ? 'Blocking' : 'Opt-outs'}</h1>
    ${isAdmin ? `
    <div class="card narrow">
      <h2>Blocked words</h2>
      <p class="muted">A message containing any of these never leaves any number.</p>
      <form method="post" action="/blocked/word" class="row gap">
        <input name="pattern" placeholder="word or phrase" required>
        <input name="reason" placeholder="why">
        <button class="primary">Block</button>
      </form>
      ${blocks.rows.length ? `<table class="plain">${blocks.rows.map(b => `<tr>
        <td><code>${esc(b.pattern)}</code></td><td class="muted">${esc(b.reason)}</td>
        <td class="right"><form method="post" action="/blocked/word/${b.id}/delete"><button>Remove</button></form></td>
      </tr>`).join('')}</table>` : '<p class="muted">Nothing blocked yet.</p>'}
    </div>` : ''}
    <div class="card narrow">
      <h2>Opted out</h2>
      <p class="muted">A row for one database blocks that database's number for that person; a vendor-wide row blocks every database of the vendor.</p>
      <form method="post" action="/blocked/optout" class="row gap">
        <select name="target">
          ${companies.rows.map(c => `<option value="c${c.id}">${esc(c.name)} — all databases</option>`).join('')}
          ${targets.rows.map(d => `<option value="d${d.id}">${esc(d.company_name)} — ${esc(d.db_name)}</option>`).join('')}
        </select>
        ${phoneField('phone', 'Country', { required: true })}
        <input name="reason" placeholder="why">
        <button class="primary">Add</button>
      </form>
      ${optouts.rows.length ? `<table class="plain">${optouts.rows.map(o => `<tr>
        <td>${esc(o.company_name || '—')}${o.db_name ? ' / <code>' + esc(o.db_name) + '</code>' : ' <span class="muted">(all)</span>'}</td>
        <td><code>${esc(o.phone)}</code></td><td class="muted">${esc(o.reason)}</td>
        <td class="right"><form method="post" action="/blocked/optout/${o.id}/delete"><button>Remove</button></form></td>
      </tr>`).join('')}</table>` : '<p class="muted">Nobody has opted out.</p>'}
    </div>`);
});

app.post('/blocked/word', requireLogin, requireAdmin, async (req, res) => {
  const p = String(req.body.pattern || '').trim();
  if (p) await pool.query('INSERT INTO wap_block (pattern, reason) VALUES ($1,$2) ON CONFLICT (pattern) DO NOTHING',
    [p, String(req.body.reason || '').trim()]);
  res.redirect('/blocked');
});
app.post('/blocked/word/:id/delete', requireLogin, requireAdmin, async (req, res) => {
  await pool.query('DELETE FROM wap_block WHERE id=$1', [Number(req.params.id) || 0]); res.redirect('/blocked');
});

app.post('/blocked/optout', requireLogin, async (req, res) => {
  const s = req.session;
  const phone = digits(req.body.phone);
  const reason = String(req.body.reason || '').trim();
  if (phoneWrong(req.body, 'phone')) return page(req, res, 'Opted out', `<div class="card narrow"><p class="bad">${esc(phoneWrong(req.body, 'phone'))}</p><a class="btn" href="${s.role === 'client' ? '/me' : '/blocked'}">Back</a></div>`);
  let companyId = null, databaseId = null;
  if (s.role === 'client') {
    databaseId = s.databaseId; companyId = s.companyId;
  } else {
    const t = String(req.body.target || '');
    if (t.startsWith('c')) companyId = Number(t.slice(1)) || null;
    else if (t.startsWith('d')) databaseId = Number(t.slice(1)) || null;
    // The target must be inside the login's scope, whatever the form said.
    if (databaseId) {
      const d = await pool.query('SELECT company_id FROM wap_database WHERE id = $1', [databaseId]);
      if (!d.rows.length) return res.redirect('/blocked');
      companyId = d.rows[0].company_id;
    }
    if (s.role === 'vendor' && companyId !== s.companyId) return forbidden(req, res, 'Not your vendor.');
  }
  if (phone && (companyId || databaseId)) {
    await pool.query(
      `INSERT INTO wap_optout (phone, reason, company_id, database_id) VALUES ($1,$2,$3,$4)
       ON CONFLICT (COALESCE(company_id, 0), COALESCE(database_id, 0), phone) DO NOTHING`,
      [phone, reason, companyId, databaseId]);
  }
  res.redirect(s.role === 'client' ? '/me' : '/blocked');
});

app.post('/blocked/optout/:id/delete', requireLogin, async (req, res) => {
  const scope = optoutScope(req);
  await pool.query(`DELETE FROM wap_optout o WHERE o.id = $${scope.params.length + 1} AND ${scope.sql}`,
    [...scope.params, Number(req.params.id) || 0]);
  res.redirect(req.session.role === 'client' ? '/me' : '/blocked');
});

// ---------------------------------------------------------------- activity

app.get('/activity', requireLogin, async (req, res) => {
  const s = req.session;
  const { rows } = await pool.query(
    `SELECT l.*, d.db_name, s.name AS server_name
       FROM wap_log l
       LEFT JOIN wap_database d ON d.id = l.database_id
       LEFT JOIN wap_server s ON s.id = d.server_id
      WHERE ($1::int IS NULL OR d.company_id = $1)
        AND ($2::int IS NULL OR d.id = $2)
      ORDER BY l.created_at DESC LIMIT 200`,
    [s.role === 'admin' ? null : s.companyId, s.role === 'client' ? s.databaseId : null]);
  page(req, res, 'Activity', `
    <h1>Activity</h1>
    <table>
      <tr><th>When</th><th></th><th>Where from</th><th>To</th><th>Result</th><th>Detail</th></tr>
      ${rows.map(l => `<tr>
        <td class="muted">${new Date(l.created_at).toLocaleString()}</td>
        <td class="muted">${l.channel === 'email' ? '&#9993;' : '&#128172;'}</td>
        <td>${l.db_name ? esc(l.server_name) + ' / <code>' + esc(l.db_name) + '</code>'
                        : '<span class="muted">' + esc(l.claimed_url || l.remote_ip) + '</span>'}</td>
        <td>${esc(l.phone)}</td>
        <td><span class="pill ${l.status === 'sent' || l.status === 'read' ? 'ok' : 'no'}">${esc(l.status)}</span></td>
        <td class="muted">${esc(l.detail)}</td></tr>`).join('')}
    </table>`);
});

// ---------------------------------------------------------------- account

app.get('/account', requireLogin, (req, res) => {
  page(req, res, 'Account', `
    <form method="post" action="/account" class="card narrow">
      <h1>Change password</h1>
      <p class="muted">Signed in as <code>${esc(req.session.username)}</code> (${esc(req.session.role)}).</p>
      ${req.query.bad ? '<p class="bad">Current password is wrong.</p>' : ''}
      ${req.query.ok ? '<p class="ok-msg">Password changed.</p>' : ''}
      <label>Current password<input type="password" name="current" required></label>
      <label>New password<input type="password" name="next" required minlength="6"></label>
      <button class="primary">Change</button>
    </form>`);
});

app.post('/account', requireLogin, async (req, res) => {
  // By id, never by username: several logins are called "admin".
  const { rows } = await pool.query('SELECT * FROM wap_admin WHERE id=$1', [req.session.adminId]);
  if (!rows.length || !bcrypt.compareSync(String(req.body.current || ''), rows[0].password_hash)) {
    return res.redirect('/account?bad=1');
  }
  if (String(req.body.next || '').length < 6) return res.redirect('/account?bad=1');
  await pool.query('UPDATE wap_admin SET password_hash=$1 WHERE id=$2',
    [bcrypt.hashSync(String(req.body.next), 10), rows[0].id]);
  res.redirect('/account?ok=1');
});

// ---------------------------------------------------------------- start

init({ companyName: process.env.PANEL_FIRST_COMPANY, instance: INSTANCE })
  .then(() => app.listen(PORT, () => {
    console.log(`[panel] listening on ${PORT}, forwarding to ${EVOLUTION_URL}`);
    // First sweep straight away (adopts the pre-existing number and points its
    // webhook at the panel), then every 30 s.
    pairingSweep();
    setInterval(pairingSweep, 30000);
    retrySweep();
    setInterval(retrySweep, 5000);
  }))
  .catch(err => {
    console.error('[panel] could not start:', err);
    process.exit(1);
  });
