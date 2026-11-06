"""Who the order is for, and the team's notes on it - on both Orders screens.

* **The customer, not just a name.** Each row carries the customer's account
  id (so the name can open their full profile) and their staff tags; the
  detail adds the short risk line (cancelled / refused / COD off) and a
  WhatsApp number. What support needs before calling the door.
* **Order notes.** Internal notes on the order - "gate locked", "called, no
  answer" - as Odoo's own notes on the sale order, so they carry who and when,
  and also show on the order in Odoo. Never sent to the customer. The notes the
  system already leaves (an address changed, an item replaced) show here too.
"""

from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

EDITOR_GROUP = 'website.group_website_designer'
NOTE_MAX = 1000
NOTES_SHOWN = 30
# What marks a note a person wrote here, apart from the notes the system leaves
# ("out of stock, offered…", "address changed…"), which go to the history.
STAFF_SUBJECT = 'Staff note'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------ customer

    def _mart369_admin_row(self):
        row = super()._mart369_admin_row()
        partner = self.partner_id.commercial_partner_id
        user = partner.user_ids[:1] or self.partner_id.user_ids[:1]
        row['customer']['userId'] = user.id or False
        row['customer']['tags'] = [
            {'id': t.id, 'name': t.name or '', 'color': t.color or 0} for t in partner.category_id]
        row['customer']['codOff'] = bool(partner.mart369_cod_off)
        return row

    def _mart369_admin_detail(self):
        row = super()._mart369_admin_detail()
        partner = self.partner_id.commercial_partner_id
        row['customer']['risk'] = self.env['res.users']._mart369_risk(partner)
        phone = row['customer'].get('phone') or ''
        row['customer']['waPhone'] = ''.join(ch for ch in phone if ch.isdigit())
        row['notes'] = self._mart369_note_rows()
        row['activity'] = self._mart369_note_rows(staff=False)
        return row

    # --------------------------------------------------------------- notes

    def _mart369_note_rows(self, staff=True):
        """Staff notes (written here), or with staff=False the system's own
        notes on the order - the activity log."""
        self.ensure_one()
        note = self.env.ref('mail.mt_note')
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'sale.order'), ('res_id', '=', self.id),
            ('message_type', 'in', ('comment', 'notification')), ('subtype_id', '=', note.id),
        ], order='date desc, id desc', limit=NOTES_SHOWN * 2)
        messages = messages.filtered(lambda m: (m.subject == STAFF_SUBJECT) == staff)[:NOTES_SHOWN]
        me = self.env.user.partner_id
        return [{
            'id': m.id,
            'text': html2plaintext(m.body or '').strip(),
            'author': m.author_id.name or self.env._('System'),
            'at': int(m.date.timestamp() * 1000) if m.date else None,
            'mine': m.author_id == me and m.message_type == 'comment',
        } for m in messages if (m.body or '').strip()]

    @api.model
    def _mart369_notes_order(self, ref):
        if not self.env.user.has_group(EDITOR_GROUP):
            raise AccessError(self.env._('You do not have access to this.'))
        # sudo after the group check: order access comes from a sales group
        # the delivery staff may not have, and the notes are the point here.
        order = self.sudo()._mart369_admin_find(ref)
        if not order:
            raise UserError(self.env._('There is no such order.'))
        return order

    @api.model
    def _mart369_clean_note(self, text):
        text = (text or '').strip()
        if not text:
            raise UserError(self.env._('Write something first.'))
        if len(text) > NOTE_MAX:
            raise UserError(self.env._('A note is at most %s characters.', NOTE_MAX))
        return text

    def _mart369_own_order_note(self, note_id, verb):
        self.ensure_one()
        try:
            note_id = int(note_id)
        except (TypeError, ValueError):
            note_id = 0
        message = self.env['mail.message'].sudo().search([
            ('id', '=', note_id), ('model', '=', 'sale.order'), ('res_id', '=', self.id),
            ('subtype_id', '=', self.env.ref('mail.mt_note').id), ('message_type', '=', 'comment'),
            ('subject', '=', STAFF_SUBJECT),
        ], limit=1)
        if not message:
            raise UserError(self.env._('That note was not found.'))
        if message.author_id != self.env.user.partner_id and not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Only the person who wrote a note can %s it.', verb))
        return message

    @api.model
    def mart369_admin_add_order_note(self, ref, text):
        order = self._mart369_notes_order(ref)
        order.with_context(mail_create_nosubscribe=True).message_post(
            body=self._mart369_clean_note(text), message_type='comment', subject=STAFF_SUBJECT,
            subtype_xmlid='mail.mt_note', author_id=self.env.user.partner_id.id)
        return order._mart369_note_rows()

    @api.model
    def mart369_admin_edit_order_note(self, ref, note_id, text):
        order = self._mart369_notes_order(ref)
        text = self._mart369_clean_note(text)
        order._mart369_own_order_note(note_id, self.env._('change')).write({'body': text})
        return order._mart369_note_rows()

    @api.model
    def mart369_admin_delete_order_note(self, ref, note_id):
        order = self._mart369_notes_order(ref)
        order._mart369_own_order_note(note_id, self.env._('remove')).unlink()
        return order._mart369_note_rows()
