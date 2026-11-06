"""Pop-ups on the customer's phone or computer, even with the shop closed.

The bell lists what happened; this taps the customer on the shoulder when it
happens. It is the browser's own Web Push: the customer says yes once, their
browser hands the shop an address (`endpoint`) and two keys, and from then on
every step of an order is sent there - confirmed, packed, on the way,
delivered, cancelled - and shows up like a message from an app.

Two pieces of standard cryptography, and nothing installed beyond what Odoo
already needs (`cryptography`, `requests`):

* **VAPID** (RFC 8292) - the shop signs each send with its own key, so a
  browser's push service knows the send came from the shop the customer said
  yes to. The key pair is made once and kept in System Parameters.
* **aes128gcm** (RFC 8291 / 8188) - the message is encrypted for that one
  browser; the push service in the middle (Google's, Mozilla's, Apple's)
  carries it without being able to read it.

Sending never holds up an order: it happens after the order's step is saved,
on its own thread, and a device that has gone away (uninstalled browser,
permission taken back) is simply forgotten.
"""

import base64
import json
import logging
import os
import struct
import threading
import time
from urllib.parse import urlsplit

import requests

from odoo import SUPERUSER_ID, api, fields, models

_logger = logging.getLogger(__name__)

PARAM_PRIVATE = 'mart369_account.vapid_private'
PARAM_SUBJECT = 'mart369_account.vapid_subject'

# What the pop-up says for each step. The bell's wording (notification.py
# ORDER_NOTES) for the same step, except packed: the bell folds packed into
# "confirmed", but a pop-up saying "confirmed" twice would read as a mistake.
PUSH_NOTES = {
    'placed': ("Order confirmed", "%(ref)s is confirmed. %(eta)s"),
    'packed': ("Order packed", "%(ref)s is packed and waiting for the rider."),
    'shipped': ("Order shipped", "%(ref)s has been handed to our delivery partner."),
    'out': ("Your order is on the way", "%(ref)s is out for delivery. %(eta)s"),
    'delivered': ("Delivered · rate your order", "How was %(ref)s? Tell us in a moment."),
    'cancelled': ("Order cancelled", "%(ref)s was cancelled. Any refund is on its way."),
}
# The bell's id for the same step, so opening the pop-up marks that row read.
FEED_SUFFIX = {'packed': 'placed'}

TIMEOUT = 10
GONE = (404, 410)


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _unb64(text):
    text = (text or '').strip()
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def encrypt(payload, p256dh, auth):
    """`payload` encrypted for one browser, as an aes128gcm body (RFC 8291).

    `p256dh` and `auth` are the two keys the browser gave when it subscribed.
    A fresh key pair and salt per message, as the RFC requires.
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    ua_public = _unb64(p256dh)
    auth_secret = _unb64(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)

    as_private = ec.generate_private_key(ec.SECP256R1())
    as_public = as_private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = as_private.exchange(ec.ECDH(), ua_key)

    ikm = HKDF(hashes.SHA256(), 32, salt=auth_secret,
               info=b'WebPush: info\x00' + ua_public + as_public).derive(shared)
    salt = os.urandom(16)
    cek = HKDF(hashes.SHA256(), 16, salt=salt,
               info=b'Content-Encoding: aes128gcm\x00').derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt=salt,
                 info=b'Content-Encoding: nonce\x00').derive(ikm)

    # One record, so it is the last one: the plaintext, then the 0x02 delimiter.
    body = AESGCM(cek).encrypt(nonce, payload + b'\x02', None)
    header = salt + struct.pack('!I', 4096) + bytes([len(as_public)]) + as_public
    return header + body


class Mart369PushSubscription(models.Model):
    """One browser that said yes to pop-ups, and whose it is."""
    _name = 'mart369.push.subscription'
    _description = '369 Mart Pop-up Device'
    _order = 'id desc'

    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, index=True, ondelete='cascade')
    endpoint = fields.Char(string='Push address', required=True)
    p256dh = fields.Char(required=True)
    auth = fields.Char(required=True)
    device = fields.Char(string='Device', help="The browser it was turned on in.")
    last_sent = fields.Datetime(string='Last pop-up', readonly=True)

    _endpoint_uniq = models.Constraint(
        'unique (endpoint)',
        'That browser is already signed up for pop-ups.',
    )


class Mart369Push(models.AbstractModel):
    """Signs, encrypts and sends the pop-ups."""
    _name = 'mart369.push'
    _description = '369 Mart Pop-ups'

    # ------------------------------------------------------------ the key

    @api.model
    def _mart369_vapid(self):
        """The shop's signing key and its public half (what browsers are given).

        Made the first time it is asked for - on install, through the data
        file - and kept: a new key would orphan every browser already signed up.
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        params = self.env['ir.config_parameter'].sudo()
        pem = params.get_param(PARAM_PRIVATE)
        if not pem:
            key = ec.generate_private_key(ec.SECP256R1())
            pem = key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()).decode()
            params.set_param(PARAM_PRIVATE, pem)
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        public = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        return key, _b64(public)

    @api.model
    def _mart369_public_key(self):
        return self._mart369_vapid()[1]

    @api.model
    def _mart369_subject(self):
        """Who the push services can contact about these sends (RFC 8292 `sub`):
        the setting if there is one, else the company's email, else the shop's
        own address."""
        subject = self.env['ir.config_parameter'].sudo().get_param(PARAM_SUBJECT)
        if subject:
            return subject
        email = self.env.company.email
        if email:
            return 'mailto:%s' % email
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        return base if base.startswith('https://') else 'mailto:admin@369mart.app'

    # -------------------------------------------------------- subscribing

    @api.model
    def _mart369_subscribe(self, partner, body, device=None):
        """Remember this browser for this customer. One browser, one row: a
        shared computer signed into by someone else moves to them."""
        endpoint = (body.get('endpoint') or '').strip()
        keys = body.get('keys') or {}
        p256dh = (keys.get('p256dh') or '').strip()
        auth = (keys.get('auth') or '').strip()
        if not endpoint.startswith('https://') or len(endpoint) > 2000:
            return False
        try:
            if len(_unb64(p256dh)) != 65 or len(_unb64(auth)) != 16:
                return False
        except (ValueError, TypeError):
            return False
        Sub = self.env['mart369.push.subscription'].sudo()
        values = {'partner_id': partner.id, 'p256dh': p256dh, 'auth': auth,
                  'device': (device or '')[:250]}
        row = Sub.search([('endpoint', '=', endpoint)], limit=1)
        if row:
            row.write(values)
        else:
            row = Sub.create(dict(values, endpoint=endpoint))
        return row

    @api.model
    def _mart369_unsubscribe(self, partner, endpoint):
        rows = self.env['mart369.push.subscription'].sudo().search([
            ('partner_id', '=', partner.id), ('endpoint', '=', endpoint or '')])
        rows.unlink()
        return bool(rows)

    # ------------------------------------------------------------ sending

    @api.model
    def _mart369_order_message(self, order, state):
        note = PUSH_NOTES.get(state)
        if not note or not order.mart369_ref:
            return None
        title, template = note
        ref = order.mart369_ref
        return {
            'id': 'n-%s-%s' % (ref, FEED_SUFFIX.get(state, state)),
            'title': title,
            'body': (template % {'ref': ref, 'eta': order.mart369_eta or ''}).strip(),
            'url': '/track/%s' % ref,
        }

    @api.model
    def _mart369_jobs(self, partner, message):
        """Everything needed to send `message` to each of `partner`'s browsers,
        worked out now, while there is a database to ask."""
        subs = self.env['mart369.push.subscription'].sudo().search(
            [('partner_id', '=', partner.id)])
        if not subs or not message:
            return []
        key, public = self._mart369_vapid()
        subject = self._mart369_subject()
        payload = json.dumps(message).encode()
        return [{'sub': sub.id, 'endpoint': sub.endpoint, 'p256dh': sub.p256dh,
                 'auth': sub.auth, 'key': key, 'public': public,
                 'subject': subject, 'payload': payload} for sub in subs]

    @api.model
    def _mart369_send_one(self, job):
        """One encrypted, signed POST to one browser's push service. Answers
        'sent', 'gone' (forget this browser) or 'failed'."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

        parts = urlsplit(job['endpoint'])
        head = _b64(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())
        claims = _b64(json.dumps({
            'aud': '%s://%s' % (parts.scheme, parts.netloc),
            'exp': int(time.time()) + 12 * 3600,
            'sub': job['subject'],
        }, separators=(',', ':')).encode())
        signed = ('%s.%s' % (head, claims)).encode()
        r, s = decode_dss_signature(job['key'].sign(signed, ec.ECDSA(hashes.SHA256())))
        token = '%s.%s.%s' % (head, claims, _b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big')))
        try:
            response = requests.post(job['endpoint'], timeout=TIMEOUT, headers={
                'Authorization': 'vapid t=%s, k=%s' % (token, job['public']),
                'Content-Encoding': 'aes128gcm',
                'Content-Type': 'application/octet-stream',
                'TTL': str(24 * 3600),
                'Urgency': 'high',
            }, data=encrypt(job['payload'], job['p256dh'], job['auth']))
        except Exception:  # noqa: BLE001
            _logger.warning('mart369: pop-up to %s did not go', parts.netloc, exc_info=True)
            return 'failed'
        if response.status_code in GONE:
            return 'gone'
        if response.status_code >= 300:
            _logger.warning('mart369: pop-up to %s refused: %s %s', parts.netloc,
                            response.status_code, response.text[:200])
            return 'failed'
        return 'sent'

    @api.model
    def _mart369_deliver(self, jobs):
        """Send every job, then write down what happened: when each browser
        last got one, and forget the ones that have gone away."""
        results = {job['sub']: self._mart369_send_one(job) for job in jobs}
        sent = [sub for sub, result in results.items() if result == 'sent']
        gone = [sub for sub, result in results.items() if result == 'gone']
        if sent or gone:
            Sub = self.env['mart369.push.subscription'].sudo()
            Sub.browse(sent).exists().write({'last_sent': fields.Datetime.now()})
            Sub.browse(gone).exists().unlink()
        return results

    @api.model
    def _mart369_send_later(self, jobs):
        """After this transaction commits, on a thread of its own: the order's
        step is saved first, and nobody waits on a push service."""
        if not jobs:
            return
        dbname = self.env.cr.dbname
        registry = self.env.registry

        def work():
            try:
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env['mart369.push']._mart369_deliver(jobs)
            except Exception:  # noqa: BLE001
                _logger.exception('mart369: sending pop-ups on %s failed', dbname)

        self.env.cr.postcommit.add(
            lambda: threading.Thread(target=work, name='mart369-push', daemon=True).start())

    @api.model
    def _mart369_on_order_step(self, order, state):
        # The same customer the bell lists this order for (notification.py).
        self._mart369_send_later(
            self._mart369_jobs(order.partner_id, self._mart369_order_message(order, state)))
