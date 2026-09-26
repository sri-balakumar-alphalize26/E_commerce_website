# -*- coding: utf-8 -*-
# WhatsApp session backed by the local Baileys Node helper (real image/video/PDF sending).
# Same model name / fields / method signatures as before, so all callers keep working.
import base64
import logging

import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_URL = 'http://127.0.0.1:8788'
DEFAULT_TOKEN = 'loyalty-wa-2026'

# Legacy in-memory maps kept as empty stubs so controllers/wizards that import them still load.
# The Baileys helper owns the live connection state; we mirror status/QR into the DB fields.
_wa_status = {}
_wa_qr_image = {}
_wa_clients = {}


class WhatsAppSession(models.Model):
    _name = 'whatsapp.session'
    _description = 'WhatsApp Session'
    _rec_name = 'name'

    name = fields.Char('Session Name', required=True, default='Default')
    status = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('waiting_qr', 'Scan QR Code'),
        ('connected', 'Connected'),
        ('error', 'Error'),
    ], string='Status', default='disconnected', readonly=True)
    phone_number = fields.Char('Connected Phone', readonly=True)
    qr_image = fields.Binary('QR Code', readonly=True, attachment=False)
    qr_last_update = fields.Datetime('QR Last Updated', readonly=True)
    db_path = fields.Char('Session DB Path', readonly=True)
    active = fields.Boolean(default=True)
    auto_reconnect = fields.Boolean('Auto Reconnect', default=True)
    message_ids = fields.One2many('whatsapp.message', 'session_id', string='Messages')
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company)
    message_count = fields.Integer(compute='_compute_message_count', string='Messages')
    error_message = fields.Text('Last Error', readonly=True)

    # ---------------------------------------------------------- helpers
    def _baileys(self):
        P = self.env['ir.config_parameter'].sudo()
        return (P.get_param('whatsapp.baileys_url', DEFAULT_URL),
                P.get_param('whatsapp.baileys_token', DEFAULT_TOKEN))

    def _call(self, path, method='get', payload=None, timeout=90):
        url, token = self._baileys()
        headers = {'X-Token': token}
        try:
            if method == 'get':
                return requests.get(url + path, headers=headers, timeout=timeout)
            return requests.post(url + path, headers=headers, json=(payload or {}), timeout=timeout)
        except Exception as e:
            raise UserError(_('WhatsApp helper service is not reachable (%s). '
                              'Make sure the Baileys service is running.') % e)

    @staticmethod
    def _clean_phone(phone):
        return ''.join(ch for ch in (phone or '') if ch.isdigit())

    @staticmethod
    def _as_b64(data):
        if isinstance(data, (bytes, bytearray)):
            return base64.b64encode(bytes(data)).decode()
        return data  # already a base64 str

    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)

    # ---------------------------------------------------------- connection
    def action_connect(self):
        self.ensure_one()
        r = self._call('/connect', 'post', timeout=40)
        if r.status_code != 200:
            self.write({'status': 'error', 'error_message': r.text[:300]})
            raise UserError(_('Could not start WhatsApp connection: %s') % r.text[:200])
        self._refresh_from_helper()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_disconnect(self):
        self.ensure_one()
        try:
            self._call('/logout', 'post', timeout=30)
        except Exception:
            pass
        self.write({'status': 'disconnected', 'qr_image': False, 'error_message': False})

    def action_refresh_status(self):
        self.ensure_one()
        self._refresh_from_helper()

    def _refresh_from_helper(self):
        try:
            resp = self._call('/status', 'get', timeout=15)
            data = resp.json()
        except Exception as e:
            self.sudo().write({'status': 'error', 'error_message': str(e)[:300]})
            return
        st = data.get('status') or 'disconnected'
        vals = {'status': st, 'error_message': False}
        if data.get('phone'):
            vals['phone_number'] = data.get('phone')
        qr = data.get('qr')
        if st == 'waiting_qr' and qr:
            b64 = qr.split(',', 1)[1] if ',' in qr else qr
            vals['qr_image'] = b64
            vals['qr_last_update'] = fields.Datetime.now()
        else:
            vals['qr_image'] = False
        self.sudo().write(vals)

    # ---------------------------------------------------------- gate
    def _get_connected_client(self):
        """Kept for API compatibility. Returns True if connected, else raises."""
        self.ensure_one()
        resp = self._call('/status', 'get', timeout=10)
        try:
            st = resp.json().get('status')
        except Exception:
            st = None
        if st != 'connected':
            self.sudo().write({'status': st or 'disconnected'})
            raise UserError(_('WhatsApp is not connected. Open Loyalty → WhatsApp and scan the QR.'))
        return True

    # ---------------------------------------------------------- send
    def _post_send(self, path, payload, what):
        self.ensure_one()
        self._get_connected_client()
        r = self._call(path, 'post', payload, timeout=120)
        ok = False
        err = ''
        try:
            j = r.json()
            ok = bool(j.get('ok'))
            err = j.get('error', '')
        except Exception:
            err = r.text[:200]
        if not ok:
            raise UserError(_('Failed to send %s: %s') % (what, err or r.status_code))
        return True

    def _log_msg(self, phone, message, ok=True):
        try:
            self.env['whatsapp.message'].sudo().create({
                'session_id': self.id,
                'phone': self._clean_phone(phone),
                'message': message,
                'direction': 'outgoing',
                'status': 'sent' if ok else 'failed',
            })
        except Exception:
            pass

    def send_message(self, phone, message):
        self._post_send('/send-text',
                        {'phone': self._clean_phone(phone), 'message': message or ''}, 'message')
        self._log_msg(phone, message)
        return True

    def send_image(self, phone, image_data, caption=''):
        self._post_send('/send-image',
                        {'phone': self._clean_phone(phone),
                         'image_base64': self._as_b64(image_data), 'caption': caption or ''}, 'image')
        self._log_msg(phone, ('📷 %s' % caption) if caption else '📷 Image')
        return True

    def send_document(self, phone, file_data, filename, caption='', mimetype='application/pdf'):
        self._post_send('/send-document',
                        {'phone': self._clean_phone(phone), 'file_base64': self._as_b64(file_data),
                         'filename': filename or 'file.pdf', 'mimetype': mimetype or 'application/pdf',
                         'caption': caption or ''}, 'document')
        self._log_msg(phone, '📎 %s' % (filename or 'document'))
        return True

    def send_odoo_report(self, phone, report_xmlid, record, caption=''):
        pdf, _ct = self.env['ir.actions.report'].sudo()._render_qweb_pdf(report_xmlid, [record.id])
        return self.send_document(phone, base64.b64encode(pdf).decode(),
                                  'document.pdf', caption=caption, mimetype='application/pdf')

    # ---------------------------------------------------------- buttons
    def action_view_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Messages'),
            'res_model': 'whatsapp.message', 'view_mode': 'list,form',
            'domain': [('session_id', '=', self.id)],
        }

    def action_send_message_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Send WhatsApp Message'),
            'res_model': 'whatsapp.send.message.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_session_id': self.id},
        }

    # ---------------------------------------------------------- crons / hooks
    @api.model
    def _cron_health_check(self):
        for s in self.search([('active', '=', True)]):
            try:
                s._refresh_from_helper()
            except Exception:
                pass
        # Self-heal: make sure the Baileys helper is actually running (restart if the
        # process died); if it was never provisioned (e.g. no internet at install time),
        # retry provisioning in the background so setup completes on its own.
        try:
            from . import baileys_provision
            if not baileys_provision.ensure_running():
                baileys_provision.provision_in_background()
        except Exception:
            pass

    @api.model
    def _cron_auto_reconnect(self):
        # The Baileys helper resumes its own login; just nudge a connect if idle.
        try:
            self._call('/connect', 'post', timeout=20)
        except Exception:
            pass
