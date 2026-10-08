"""Pop-ups the shop decides on.

* A notice (369 Mart > Store > Notifications) can also go out as a pop-up:
  tick "Also send as a pop-up". It goes to every customer with pop-ups on
  who has not switched that kind off (offers, wallet), once it is live - at
  once when saved live, or when its start time comes (a job every 5 min).
* Each order step's pop-up can be switched off, and its words changed:
  369 Mart > Store > Order pop-ups. Empty words keep the shop's own.
"""

from odoo import api, fields, models

from .push import PUSH_NOTES

STEPS = ('placed', 'packed', 'shipped', 'out', 'delivered', 'cancelled')

# A notice's "Opens" as a page address on the shop.
GO_PATHS = {
    'offers': '/offers', 'categories': '/categories', 'buyagain': '/buy-again',
    'cart': '/cart', 'home': '/',
}


def _go_path(view, param):
    view = (view or 'offers').strip()
    param = (param or '').strip()
    if view in GO_PATHS:
        return GO_PATHS[view]
    if view in ('account', 'category', 'product', 'page', 'track', 'order') and param:
        return '/%s/%s' % (view, param)
    if view == 'account':
        return '/account'
    return '/'


class Mart369NoticePopup(models.Model):
    _inherit = 'mart369.notice'

    popup = fields.Boolean(
        string='Also send as a pop-up',
        help='A pop-up on the phone or computer of every customer who has pop-ups on '
             '(and has not switched this kind off), once the notification is live.')
    popup_sent_at = fields.Datetime(string='Pop-up sent', readonly=True, copy=False)
    popup_count = fields.Integer(string='Pop-ups sent to', readonly=True, copy=False)

    def _mart369_popup_message(self):
        self.ensure_one()
        return {
            'id': 'n-notice-%s' % self.id,
            'title': self.name or '',
            'body': (self.text or '').strip(),
            'url': _go_path(self.go_view, self.go_param),
        }

    @api.model
    def _mart369_push_due(self):
        """Send the pop-ups of every live notice that asked for one and has
        not gone yet. Each is sent once."""
        now = fields.Datetime.now()
        due = self.sudo().search([
            ('popup', '=', True), ('popup_sent_at', '=', False), ('active', '=', True),
            ('publish_at', '<=', now), '|', ('until', '=', False), ('until', '>=', now),
        ])
        Push = self.env['mart369.push'].sudo()
        Sub = self.env['mart369.push.subscription'].sudo()
        for notice in due:
            partners = Sub.search([]).partner_id
            if notice.kind == 'offer':
                partners = partners.filtered('mart369_notify_offers')
            elif notice.kind == 'wallet':
                partners = partners.filtered('mart369_notify_wallet')
            message = notice._mart369_popup_message()
            jobs = []
            for partner in partners:
                jobs += Push._mart369_jobs(partner, message)
            Push._mart369_send_later(jobs)
            notice.write({'popup_sent_at': now, 'popup_count': len(partners)})
        return len(due)

    @api.model_create_multi
    def create(self, vals_list):
        notices = super().create(vals_list)
        if any(n.popup for n in notices):
            self._mart369_push_due()
        return notices

    def write(self, vals):
        result = super().write(vals)
        if vals.get('popup') or 'publish_at' in vals:
            self._mart369_push_due()
        return result


class Mart369ConfigPopups(models.Model):
    _inherit = 'mart369.config'

    push_on_placed = fields.Boolean(string='Confirmed', default=True)
    push_on_packed = fields.Boolean(string='Packed', default=True)
    push_on_shipped = fields.Boolean(string='Shipped', default=True)
    push_on_out = fields.Boolean(string='On the way', default=True)
    push_on_delivered = fields.Boolean(string='Delivered', default=True)
    push_on_cancelled = fields.Boolean(string='Cancelled', default=True)
    push_text_placed = fields.Char(string='Confirmed - words', help=PUSH_NOTES['placed'][1])
    push_text_packed = fields.Char(string='Packed - words', help=PUSH_NOTES['packed'][1])
    push_text_shipped = fields.Char(string='Shipped - words', help=PUSH_NOTES['shipped'][1])
    push_text_out = fields.Char(string='On the way - words', help=PUSH_NOTES['out'][1])
    push_text_delivered = fields.Char(string='Delivered - words', help=PUSH_NOTES['delivered'][1])
    push_text_cancelled = fields.Char(string='Cancelled - words', help=PUSH_NOTES['cancelled'][1])

    def mart369_action_order_popups(self):
        """Open the one settings record on its Order pop-ups form."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Order pop-ups',
            'res_model': 'mart369.config',
            'res_id': self.sudo()._get().id,
            'view_mode': 'form',
            'views': [(self.env.ref('mart369_account.view_mart369_order_popups_form').id, 'form')],
            'target': 'current',
        }


class Mart369PushSteps(models.AbstractModel):
    _inherit = 'mart369.push'

    @api.model
    def _mart369_order_message(self, order, state):
        """The shop's switch and words for this step, over the built-in ones."""
        config = self.env['mart369.config'].sudo()._get()
        if state in STEPS and not config['push_on_%s' % state]:
            return None
        message = super()._mart369_order_message(order, state)
        own = (config['push_text_%s' % state] if state in STEPS else '') or ''
        if message and own.strip():
            try:
                message['body'] = (own % {'ref': order.mart369_ref or '',
                                          'eta': order.mart369_eta or ''}).strip()
            except (KeyError, TypeError, ValueError):
                # Words with a stray % are sent as they were typed.
                message['body'] = own.strip()
        return message
