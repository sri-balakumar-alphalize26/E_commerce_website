'use strict';

/**
 * Outgoing email for the panel.
 *
 * Sits beside WhatsApp deliberately rather than in a separate tool: a database
 * is already identified here by its key, its server address and its name, and
 * the same opt-out list, caps and activity log should cover whichever channel
 * it writes on. A customer who asked one vendor to stop should not have to ask
 * twice, once per channel.
 */

const nodemailer = require('nodemailer');

/** Transports are cached per account: building one per message would open a
 *  fresh TCP + TLS connection every time, which is slow and looks like abuse
 *  to most mail providers. Rebuilt when the account row changes. */
const cache = new Map();

function transportFor(account) {
  const stamp = [account.id, account.host, account.port, account.secure,
                 account.username, account.password].join('|');
  const hit = cache.get(account.id);
  if (hit && hit.stamp === stamp) return hit.transport;

  const transport = nodemailer.createTransport({
    host: account.host,
    port: Number(account.port) || 587,
    // secure=true means TLS from the first byte (port 465). Anything else
    // starts plain and upgrades with STARTTLS, which is what 587 expects.
    secure: !!account.secure,
    auth: account.username ? { user: account.username, pass: account.password } : undefined,
    pool: true,
    maxConnections: 3,
    connectionTimeout: 15000,
    greetingTimeout: 15000,
    socketTimeout: 30000,
  });
  cache.set(account.id, { stamp, transport });
  return transport;
}

function forget(accountId) {
  const hit = cache.get(accountId);
  if (hit) {
    try { hit.transport.close(); } catch (err) { /* already gone */ }
    cache.delete(accountId);
  }
}

/** Prove the settings work without sending anything to a real recipient. */
async function verify(account) {
  try {
    await transportFor(account).verify();
    return { ok: true };
  } catch (err) {
    forget(account.id);
    return { ok: false, error: err.message };
  }
}

async function send(account, message) {
  const from = account.from_name
    ? `"${account.from_name.replace(/"/g, '')}" <${account.from_email}>`
    : account.from_email;

  const mail = {
    from,
    to: message.to,
    subject: message.subject || '',
    replyTo: message.reply_to || undefined,
    cc: message.cc || undefined,
    bcc: message.bcc || undefined,
  };
  if (message.body_html) mail.html = message.body_html;
  if (message.body_text) mail.text = message.body_text;
  if (!mail.html && !mail.text) mail.text = '';

  if (Array.isArray(message.attachments) && message.attachments.length) {
    mail.attachments = message.attachments.slice(0, 10).map(a => ({
      filename: a.filename || 'attachment',
      content: Buffer.from(String(a.content || ''), 'base64'),
      contentType: a.mimetype || undefined,
    }));
  }

  try {
    const info = await transportFor(account).sendMail(mail);
    return { ok: true, id: info.messageId, accepted: info.accepted || [] };
  } catch (err) {
    // A failure often means the connection is now unusable - drop it so the
    // next attempt builds a fresh one instead of failing the same way.
    forget(account.id);
    return { ok: false, error: err.message };
  }
}

module.exports = { send, verify, forget };
