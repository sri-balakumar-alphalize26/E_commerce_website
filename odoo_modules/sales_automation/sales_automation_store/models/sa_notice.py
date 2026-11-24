# -*- coding: utf-8 -*-
"""A note at the side of the screen, and in the bell. It only tells."""
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

KEEP_DAYS = 14
BELL = 30
WAITING = 20
JOIN_MINUTES = 10           # prices of one enquiry are one note

LEVEL = {'order': 'blue', 'price': 'green', 'cheaper': 'red', 'paid': 'green', 'whatsapp': 'red', 'supply': 'red'}
MANAGERS_ONLY = ('cheaper', 'whatsapp', 'supply')


class SaNotice(models.Model):
    _name = 'sa.notice'
    _description = 'Side Notification'
    _order = 'told_on desc, id desc'

    kind = fields.Selection([('order', 'New order'), ('price', 'Vendor price'), ('cheaper', 'Cheaper vendor'),
                             ('paid', 'Payment'), ('whatsapp', 'WhatsApp problem'),
                             ('supply', 'Order from a vendor')], required=True)
    title = fields.Char(required=True)
    body = fields.Char()
    key = fields.Char(index=True, help="One note per key; a price note is renewed instead.")
    told_on = fields.Datetime(default=fields.Datetime.now, index=True)
    request_id = fields.Many2one('sa.group.request', ondelete='cascade')
    order_id = fields.Many2one('sale.order', ondelete='cascade')
    session_id = fields.Many2one('whatsapp.session', ondelete='cascade')
    user_ids = fields.Many2many('res.users', 'sa_notice_user_rel', string='For')
    seen_ids = fields.Many2many('res.users', 'sa_notice_seen_rel', string='Seen By')

    # ------------------------------------------------------------ telling
    @api.model
    def _tell(self, kind, title, body, key, request=None, order=None, session=None):
        """Never in the way of what happened: a note that cannot be made is logged."""
        try:
            with self.env.cr.savepoint():
                return self.sudo()._tell_now(kind, title, body, key, request, order, session)
        except Exception:  # noqa: BLE001
            _logger.exception("Side notification %s could not be made", key)
            return self.browse()

    @api.model
    def _tell_now(self, kind, title, body, key, request, order, session):
        if not self.env['sa.ai.settings'].sudo().get_settings().notice_on:
            return self.browse()
        users = self._audience(kind, request, order)
        if not users:
            return self.browse()
        note = self.search([('key', '=', key)], limit=1)
        now = fields.Datetime.now()
        if note and kind != 'price':
            return note                 # told already
        if note and note.told_on > now - timedelta(minutes=JOIN_MINUTES):
            note.write({'title': title, 'body': body, 'told_on': now, 'user_ids': [(6, 0, users.ids)], 'seen_ids': [(5,)]})
        else:
            note = self.create({
                'kind': kind, 'title': title, 'body': body, 'key': key, 'told_on': now,
                'request_id': request.id if request else False, 'order_id': order.id if order else False,
                'session_id': session.id if session else False, 'user_ids': [(6, 0, users.ids)]})
        for user in users:
            user.partner_id._bus_send('sa_notice/new', note._payload())
        return note

    @api.model
    def _audience(self, kind, request, order):
        """Managers; and the employee whose WhatsApp group it is, except for
        what is a manager's to decide. Only people of that company."""
        users = self.env.ref('sales_automation.group_sa_manager').sudo().all_user_ids
        if kind not in MANAGERS_ONLY and request:
            own = request.sudo().group_id.employee_session_id.employee_id.user_id
            users |= own & self.env.ref('sales_automation.group_sa_user').sudo().all_user_ids
        company = order.company_id if order else self.env['res.company']
        if not company and request and request.group_id:
            company = request._company_for(request.group_id) or company
        return users.filtered(lambda u: u.active and not u.share and (not company or company in u.company_ids))

    def _payload(self):
        self.ensure_one()
        return {'id': self.id, 'kind': self.kind, 'level': LEVEL[self.kind], 'key': self.key,
                'title': self.title, 'body': self.body or ''}

    # ------------------------------------------------------------ the bell
    @api.model
    def _allowed(self):
        """A Sales Automation user, while the toggle is on."""
        return self.env.user.has_group('sales_automation.group_sa_user') \
            and self.env['sa.ai.settings'].sudo().get_settings().notice_on

    @api.model
    def sa_notices(self):
        if not self._allowed():
            return {'allowed': False, 'unread': 0, 'rows': [], 'waiting': []}
        me = self.env.user
        mine = self.search([('user_ids', 'in', me.id)], limit=BELL)
        seen = mine.sudo().filtered(lambda n: me in n.seen_ids)
        return {
            'allowed': True,
            'unread': self.search_count([('user_ids', 'in', me.id), ('seen_ids', 'not in', me.id)]),
            'rows': [dict(n._payload(), at=n.told_on.isoformat() + 'Z', seen=n in seen) for n in mine.sudo()],
            'waiting': self._waiting()}

    @api.model
    def _waiting(self):
        """Every enquiry that needs somebody now, each on its own. The user's
        own rights decide which."""
        Request = self.env['sa.group.request']
        rows = []
        for kind, domain in (('pick', [('state', '=', 'awaiting_vendor_pick')]),
                             ('stalled', [('state', '=', 'sourcing'), '|', '|', ('sa_price_stalled', '=', True),
                                          ('sa_price_choice_pending', '=', True), ('sa_vendor_choice_pending', '=', True)])):
            for request in Request.search(domain, order='id desc', limit=WAITING).sudo():
                rows.append({
                    'id': request.id, 'kind': 'choice' if kind == 'stalled' and request.sa_price_choice_pending
                    else 'vendor' if kind == 'stalled' and request.sa_vendor_choice_pending else kind,
                    'ref': request.ref_code or str(request.id), 'qty': request.qty or 1.0,
                    'product': request.product_id.name or request.ai_search_term or request.raw_text or '',
                    'customer': request.requester_name or '', 'at': request.create_date.isoformat() + 'Z',
                    'seconds': request._sa_price_seconds_left(), 'price': request.sa_price_vendor or 0.0,
                    'currency': request.currency_id.name or ''})
        return rows

    @api.model
    def sa_notice_enquiry(self, request_id):
        """Where a waiting enquiry opens."""
        request = self.env['sa.group.request'].browse(int(request_id)).exists()
        if request and request.has_access('read'):
            return {'type': 'ir.actions.act_window', 'res_model': 'sa.group.request', 'res_id': request.id,
                    'views': [[False, 'form']], 'target': 'current'}
        return 'sales_automation_store.action_sa_enquiry_screen'

    @api.model
    def sa_notice_seen(self, ids=None):
        """Read: these, or all of mine."""
        if not self.env.user.has_group('sales_automation.group_sa_user'):
            raise AccessError(self.env._("Only Sales Automation users have notifications."))
        me = self.env.user
        domain = [('user_ids', 'in', me.id), ('seen_ids', 'not in', me.id)]
        if ids:
            domain.append(('id', 'in', [int(i) for i in ids]))
        self.search(domain).sudo().write({'seen_ids': [(4, me.id)]})
        return self.sa_notices()

    @api.model
    def sa_notice_open(self, notice_id):
        """Where a click goes: the record when this user may read it, else the
        Store screen it is on."""
        note = self.search([('id', '=', int(notice_id)), ('user_ids', 'in', self.env.user.id)], limit=1)
        if not note:
            return False
        note.sudo().write({'seen_ids': [(4, self.env.user.id)]})
        order, request, session = note.sudo().order_id, note.sudo().request_id, note.sudo().session_id
        for record, screen in ((order, 'sales_automation_store.action_sa_store_screen'),
                               (request, 'sales_automation_store.action_sa_enquiry_screen'),
                               (session, False)):
            if not record:
                continue
            if record.with_user(self.env.user).has_access('read'):
                return {'type': 'ir.actions.act_window', 'res_model': record._name, 'res_id': record.id,
                        'views': [[False, 'form']], 'target': 'current'}
            return screen
        return False

    @api.autovacuum
    def _gc_notices(self):
        self.sudo().search([('told_on', '<', fields.Datetime.now() - timedelta(days=KEEP_DAYS))]).unlink()
