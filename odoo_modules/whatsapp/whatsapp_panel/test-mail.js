'use strict';

/**
 * Check a vendor's mail account, and optionally send one real message.
 *
 *   node test-mail.js 369ai                    # verify the settings only
 *   node test-mail.js 369ai you@example.com    # verify, then send one email
 *
 * Verifying first matters: it separates "the credentials are wrong" from
 * "the credentials are fine but this particular message was rejected".
 */

const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const { pool } = require('./db');
const mailer = require('./mail');

(async () => {
  const vendor = process.argv[2];
  const to = process.argv[3];
  if (!vendor) {
    console.log('usage: node test-mail.js <vendor> [recipient]');
    process.exit(1);
  }

  const { rows } = await pool.query(
    `SELECT e.* FROM wap_email e JOIN wap_company c ON c.id = e.company_id
      WHERE lower(c.name) = lower($1)`, [vendor]);
  if (!rows.length) {
    console.log(`no mail account for vendor "${vendor}"`);
    process.exit(1);
  }
  const account = rows[0];
  console.log(`account : ${account.username} -> ${account.host}:${account.port}` +
              ` (secure=${account.secure})`);
  console.log(`sends as: ${account.from_name ? account.from_name + ' ' : ''}<${account.from_email}>`);

  process.stdout.write('verify  : ');
  const v = await mailer.verify(account);
  if (!v.ok) {
    console.log('FAILED');
    console.log('\n' + v.error);
    await pool.end();
    process.exit(1);
  }
  console.log('OK - the mail server accepted these credentials');

  if (to) {
    process.stdout.write(`send    : `);
    const r = await mailer.send(account, {
      to,
      subject: 'Test from the WhatsApp Panel',
      body_text: 'If you are reading this, the panel can send email.',
      body_html: '<p>If you are reading this, the panel can send email.</p>'
                 + `<p style="color:#888">Sent by ${account.from_email} via ${account.host}.</p>`,
    });
    console.log(r.ok ? `OK - accepted for ${(r.accepted || []).join(', ')} (${r.id})`
                     : `FAILED\n\n${r.error}`);
  }
  await pool.end();
})().catch(err => { console.error(err.message); process.exit(1); });
