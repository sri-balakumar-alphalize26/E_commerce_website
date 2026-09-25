"""Tags and staff notes on a customer, for both Customers screens.

Nothing new is stored. A tag is Odoo's own contact tag (`res.partner.category`,
the `category_id` field), and a staff note is an internal note on the contact
(`message_post` with the Note subtype) - so both also show on the contact form
in Odoo, and a note carries who wrote it and when for free.

Everything hangs off the customer's **commercial partner**, the same record
the wallet and the orders are joined on, so a customer is one person however
many addresses they keep.

Staff only: every method checks the same group the customer routes do, and a
note is never sent to the customer - the Note subtype is internal.
"""

from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

EDITOR_GROUP = 'website.group_website_designer'
NOTE_MAX = 1000
NOTES_SHOWN = 30


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------------- helpers

    @api.model
    def _mart369_crm_check(self):
        if not self.env.user.has_group(EDITOR_GROUP):
            raise AccessError(self.env._('You do not have access to this.'))

    @api.model
    def _mart369_crm_customer(self, user_id):
        """The customer's commercial partner, or a UserError."""
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            user_id = 0
        user = self.search(self._mart369_admin_base() + [('id', '=', user_id)], limit=1)
        if not user:
            raise UserError(self.env._('There is no such customer.'))
        return user.partner_id.commercial_partner_id

    @api.model
    def _mart369_tag_row(self, tag):
        return {'id': tag.id, 'name': tag.name or '', 'color': tag.color or 0}

    @api.model
    def _mart369_note_rows(self, partner):
        note = self.env.ref('mail.mt_note')
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'res.partner'), ('res_id', '=', partner.id),
            ('message_type', '=', 'comment'), ('subtype_id', '=', note.id),
        ], order='date desc, id desc', limit=NOTES_SHOWN)
        me = self.env.user.partner_id
        return [{
            'id': m.id,
            'text': html2plaintext(m.body or '').strip(),
            'author': m.author_id.name or '',
            'at': int(m.date.timestamp() * 1000) if m.date else None,
            'mine': m.author_id == me,
        } for m in messages]

    # ------------------------------------------------------ list and detail

    @api.model
    def _mart369_admin_domain(self, *args, **kwargs):
        """The list's filters, plus a tag chosen in the Tag filter."""
        domain = super()._mart369_admin_domain(*args, **kwargs)
        tag = self.env.context.get('mart369_tag')
        if tag:
            try:
                domain += [('partner_id.commercial_partner_id.category_id', 'in', [int(tag)])]
            except (TypeError, ValueError):
                pass
        return domain

    @api.model
    def mart369_admin_list(self, *args, tag=None, **kwargs):
        # The desk passes `tag`; the console's route puts it on the context -
        # keep whichever came, never blank one with the other.
        tag = tag or self.env.context.get('mart369_tag') or None
        page = super(ResUsers, self.with_context(mart369_tag=tag)).mart369_admin_list(
            *args, **kwargs)
        page['tags'] = self.mart369_admin_tags()
        return page

    def _mart369_admin_row(self, *args, **kwargs):
        row = super()._mart369_admin_row(*args, **kwargs)
        row['tags'] = [self._mart369_tag_row(t)
                       for t in self.partner_id.commercial_partner_id.category_id]
        return row

    @api.model
    def mart369_admin_detail(self, user_id):
        row = super().mart369_admin_detail(user_id)
        if not row:
            return row
        partner = self._mart369_crm_customer(user_id)
        row['notes'] = self._mart369_note_rows(partner)
        # Digits only, for a wa.me link. A number saved without its country
        # code will not open the right chat - the screens say so.
        phone = row.get('phone') or partner.phone or ''
        row['waPhone'] = ''.join(ch for ch in phone if ch.isdigit())
        return row

    # ---------------------------------------------------------------- tags

    @api.model
    def mart369_admin_tags(self):
        """Every tag, for the picker and the list's Tag filter."""
        return [self._mart369_tag_row(t)
                for t in self.env['res.partner.category'].sudo().search([], order='name')]

    @api.model
    def mart369_admin_set_tags(self, user_id, names):
        """Replace the customer's tags with these names; a new name makes a new tag."""
        self._mart369_crm_check()
        partner = self._mart369_crm_customer(user_id)
        Tag = self.env['res.partner.category'].sudo()
        wanted = Tag.browse()
        for raw in names or []:
            name = ' '.join(str(raw or '').split())[:40]
            if not name:
                continue
            tag = Tag.search([('name', '=ilike', name)], limit=1) or Tag.create({'name': name})
            wanted |= tag
        partner.sudo().write({'category_id': [(6, 0, wanted.ids)]})
        return [self._mart369_tag_row(t) for t in partner.category_id]

    # --------------------------------------------------------------- notes

    @api.model
    def mart369_admin_add_note(self, user_id, text):
        """An internal note on the customer, signed by whoever is signed in."""
        self._mart369_crm_check()
        partner = self._mart369_crm_customer(user_id)
        text = (text or '').strip()
        if not text:
            raise UserError(self.env._('Write something first.'))
        if len(text) > NOTE_MAX:
            raise UserError(self.env._('A note is at most %s characters.', NOTE_MAX))
        partner.sudo().with_context(mail_create_nosubscribe=True).message_post(
            body=text, message_type='comment', subtype_xmlid='mail.mt_note',
            author_id=self.env.user.partner_id.id)
        return self._mart369_note_rows(partner)

    @api.model
    def _mart369_own_note(self, partner, note_id, verb):
        """The note, if it is this customer's and the caller may change it:
        its author, or an administrator."""
        note = self.env.ref('mail.mt_note')
        try:
            note_id = int(note_id)
        except (TypeError, ValueError):
            note_id = 0
        message = self.env['mail.message'].sudo().search([
            ('id', '=', note_id), ('model', '=', 'res.partner'),
            ('res_id', '=', partner.id), ('subtype_id', '=', note.id),
        ], limit=1)
        if not message:
            raise UserError(self.env._('That note was not found.'))
        if message.author_id != self.env.user.partner_id and not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Only the person who wrote a note can %s it.', verb))
        return message

    @api.model
    def mart369_admin_edit_note(self, user_id, note_id, text):
        """Change a note's words. It keeps its author and its time."""
        self._mart369_crm_check()
        partner = self._mart369_crm_customer(user_id)
        text = (text or '').strip()
        if not text:
            raise UserError(self.env._('Write something first.'))
        if len(text) > NOTE_MAX:
            raise UserError(self.env._('A note is at most %s characters.', NOTE_MAX))
        self._mart369_own_note(partner, note_id, self.env._('change')).write({'body': text})
        return self._mart369_note_rows(partner)

    @api.model
    def mart369_admin_delete_note(self, user_id, note_id):
        """Remove a note - only its author, or an administrator, may."""
        self._mart369_crm_check()
        partner = self._mart369_crm_customer(user_id)
        self._mart369_own_note(partner, note_id, self.env._('remove')).unlink()
        return self._mart369_note_rows(partner)
