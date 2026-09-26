// Loyalty WhatsApp helper — Baileys engine (send text/image/document). Localhost only.
const express = require('express');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const qrcode = require('qrcode');
const pino = require('pino');
const fs = require('fs');
const path = require('path');

const PORT = 8788;
const HOST = '127.0.0.1';
const TOKEN = process.env.WA_TOKEN || 'loyalty-wa-2026';
const AUTH_DIR = path.join(__dirname, 'auth');

const logger = pino({ level: 'silent' });

let sock = null;
let status = 'disconnected'; // disconnected | waiting_qr | connected
let qrDataUrl = null;
let phone = null;
let starting = false;

async function startSock() {
  if (starting || sock) return; // keep ONE socket; close-handler nulls it before reconnect
  starting = true;
  try {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    let version;
    try { ({ version } = await fetchLatestBaileysVersion()); } catch (e) { version = undefined; }
    sock = makeWASocket({
      version,
      auth: state,
      logger,
      printQRInTerminal: false,
      browser: ['Loyalty POS', 'Chrome', '1.0'],
      syncFullHistory: false,
    });
    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('connection.update', async (u) => {
      const { connection, lastDisconnect, qr } = u;
      if (qr) {
        status = 'waiting_qr';
        try { qrDataUrl = await qrcode.toDataURL(qr); } catch (e) { qrDataUrl = null; }
      }
      if (connection === 'open') {
        status = 'connected';
        qrDataUrl = null;
        phone = sock.user && sock.user.id ? String(sock.user.id).split(':')[0].split('@')[0] : null;
      }
      if (connection === 'close') {
        status = 'disconnected';
        const code = lastDisconnect && lastDisconnect.error instanceof Boom
          ? lastDisconnect.error.output.statusCode : 0;
        sock = null; // allow exactly one fresh socket on reconnect
        if (code === DisconnectReason.loggedOut) {
          try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch (e) {}
        } else {
          setTimeout(() => { startSock().catch(() => {}); }, 4000); // auto-reconnect
        }
      }
    });
  } catch (e) {
    status = 'disconnected';
  } finally {
    starting = false;
  }
}

function jid(p) {
  return String(p || '').replace(/[^0-9]/g, '') + '@s.whatsapp.net';
}
function connected(res) {
  if (status !== 'connected' || !sock) { res.status(409).json({ ok: false, error: 'not connected' }); return false; }
  return true;
}

const app = express();
app.use(express.json({ limit: '80mb' }));
app.use((req, res, next) => {
  if (req.path === '/status' || req.path === '/') return next();
  if (req.get('X-Token') !== TOKEN) return res.status(401).json({ ok: false, error: 'bad token' });
  next();
});

app.get('/', (req, res) => res.json({ ok: true, service: 'loyalty-wa-baileys' }));
app.get('/status', (req, res) => res.json({ ok: true, status, phone, qr: qrDataUrl }));
app.post('/connect', async (req, res) => { await startSock(); res.json({ ok: true, status }); });
app.post('/logout', async (req, res) => {
  try { if (sock) await sock.logout(); } catch (e) {}
  status = 'disconnected'; qrDataUrl = null;
  try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch (e) {}
  res.json({ ok: true });
});

app.post('/send-text', async (req, res) => {
  if (!connected(res)) return;
  try { await sock.sendMessage(jid(req.body.phone), { text: req.body.message || '' }); res.json({ ok: true }); }
  catch (e) { res.status(500).json({ ok: false, error: String(e && e.message || e) }); }
});
app.post('/send-image', async (req, res) => {
  if (!connected(res)) return;
  try {
    const buf = Buffer.from(req.body.image_base64, 'base64');
    await sock.sendMessage(jid(req.body.phone), { image: buf, caption: req.body.caption || '' });
    res.json({ ok: true });
  } catch (e) { res.status(500).json({ ok: false, error: String(e && e.message || e) }); }
});
app.post('/send-document', async (req, res) => {
  if (!connected(res)) return;
  try {
    const buf = Buffer.from(req.body.file_base64, 'base64');
    await sock.sendMessage(jid(req.body.phone), {
      document: buf,
      mimetype: req.body.mimetype || 'application/pdf',
      fileName: req.body.filename || 'file.pdf',
      caption: req.body.caption || '',
    });
    res.json({ ok: true });
  } catch (e) { res.status(500).json({ ok: false, error: String(e && e.message || e) }); }
});

app.listen(PORT, HOST, () => console.log(`loyalty-wa-baileys on http://${HOST}:${PORT}`));
// resume an existing login on boot
if (fs.existsSync(path.join(AUTH_DIR, 'creds.json'))) { startSock().catch(() => {}); }
