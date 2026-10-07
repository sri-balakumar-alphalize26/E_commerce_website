"""Accounts that already have WhatsApp orders count as proven.

Before this version, a store account caught a WhatsApp chat on any matching
number. Accounts whose WhatsApp orders already landed on them keep them - and
keep catching their chats - rather than losing their history overnight.
"""

from odoo import SUPERUSER_ID, api, fields


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['sale.order'].search([('mart369_channel', '=', 'whatsapp')])
    customers = orders.mapped('partner_id.commercial_partner_id').filtered(
        lambda p: p.user_ids and p.phone and not p.mart369_phone_verified)
    customers.with_context(mart369_phone_proven=True).write({
        'mart369_phone_verified': True,
        'mart369_phone_verified_at': fields.Datetime.now(),
    })
