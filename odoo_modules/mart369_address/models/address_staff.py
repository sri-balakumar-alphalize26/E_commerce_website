"""Support staff and a customer's address book - the Amazon / Flipkart way.

Staff (managers and owners) can see every address a customer keeps, add one,
fix one and choose which is the default. They cannot delete: removing an
address is the customer's call.

Every staff door - the Odoo dialog (wizard/address_wizard.py), the Customers
desk and the console's routes (controllers/admin_api.py) - comes through these
methods, so they check the same thing and leave the same note in the
customer's history. The group is checked here, in the model, before anything is
sudo'd; a route checking it too is a second lock, not the only one.
"""

from markupsafe import Markup, escape

from odoo import api, models
from odoo.exceptions import AccessError

from .res_partner import ADDRESS_TYPES

STAFF_GROUPS = ('website.group_website_designer', 'base.group_system')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ----------------------------------------------------------- the fences

    @api.model
    def _mart369_staff_check(self):
        if not any(self.env.user.has_group(group) for group in STAFF_GROUPS):
            raise AccessError(self.env._("Only 369 Mart managers can change a customer's addresses."))

    @api.model
    def _mart369_staff_customer(self, user_id):
        """The shopper behind a login - never a staff account or a company."""
        try:
            user = self.env['res.users'].sudo().browse(int(user_id)).exists()
        except (TypeError, ValueError):
            user = self.env['res.users']
        return user.partner_id if user and user.share else self.browse()

    @api.model
    def _mart369_staff_address(self, address_id):
        """One saved address of some shopper, or nothing."""
        try:
            address = self.sudo().browse(int(address_id)).exists()
        except (TypeError, ValueError):
            return self.browse()
        if (not address or address.type not in ADDRESS_TYPES
                or not address.parent_id.user_ids.filtered('share')):
            return self.browse()
        return address

    def _mart369_staff_note(self, message):
        """A line in the customer's history: who changed which address."""
        self.ensure_one()
        self.sudo().message_post(body=Markup('<p>%s</p>') % escape(message),
                                 author_id=self.env.user.partner_id.id,
                                 subtype_xmlid='mail.mt_note')

    # -------------------------------------------------------------- reading

    def _mart369_staff_card(self):
        """An address as support reads it: the customer's own shape, plus what
        is missing and whether it is still on the customer's list."""
        self.ensure_one()
        return dict(self._mart369_serialize(), gaps=self._mart369_gaps(), archived=not self.active)

    @api.model
    def mart369_admin_book(self, user_id):
        """Everything a customer keeps: their addresses, the default first."""
        self._mart369_staff_check()
        customer = self._mart369_staff_customer(user_id)
        if not customer:
            return {'ok': False, 'error': self.env._('There is no such customer.')}
        book = customer._mart369_book()
        removed = customer._mart369_book(active_test=False).filtered(lambda a: not a.active)
        return {
            'ok': True,
            'customer': {'id': customer.id, 'name': customer.name or '', 'phone': customer.phone or ''},
            'addresses': [a._mart369_staff_card() for a in book],
            'selected': book.filtered('mart369_default')[:1].id or None,
            'removed': len(removed),
        }

    # -------------------------------------------------------------- writing

    @api.model
    def mart369_admin_add(self, user_id, body):
        """Add an address for a customer. Answers {ok, address} or {ok: False,
        error, field} - the same shape the customer's own route gives."""
        self._mart369_staff_check()
        customer = self._mart369_staff_customer(user_id)
        if not customer:
            return {'ok': False, 'error': self.env._('There is no such customer.')}
        body = dict(body or {})
        for required in ('name', 'line', 'phone'):
            body.setdefault(required, '')
        values, error = self.sudo()._mart369_address_values(body, parent=customer)
        if error:
            return {'ok': False, 'error': error[0], 'field': error[1]}
        address = customer.sudo()._mart369_add_address(values)
        customer._mart369_staff_note(self.env._(
            'Delivery address %(label)s added by %(who)s.',
            label=address.mart369_label, who=self.env.user.name))
        return {'ok': True, 'address': address._mart369_staff_card()}

    @api.model
    def mart369_admin_edit(self, address_id, body):
        """Fix an address. One an order already went to is copied, not
        rewritten, so the order keeps what it was placed with."""
        self._mart369_staff_check()
        address = self._mart369_staff_address(address_id)
        if not address or not address.active:
            return {'ok': False, 'error': self.env._('There is no such address.')}
        values, error = self.sudo()._mart369_address_values(body or {}, address=address)
        if error:
            return {'ok': False, 'error': error[0], 'field': error[1]}
        saved = address._mart369_revise(values)
        note = self.env._('Delivery address %(label)s edited by %(who)s.',
                          label=saved.mart369_label, who=self.env.user.name)
        if saved != address:
            note += ' ' + self.env._('Orders already placed keep the old address.')
        saved.parent_id._mart369_staff_note(note)
        return {'ok': True, 'address': saved._mart369_staff_card(), 'replaced': saved != address}

    @api.model
    def mart369_admin_make_default(self, address_id):
        """Choose which address the customer's orders ship to by default."""
        self._mart369_staff_check()
        address = self._mart369_staff_address(address_id)
        if not address or not address.active:
            return {'ok': False, 'error': self.env._('There is no such address.')}
        if not address.mart369_default:
            address._mart369_set_default()
            address.parent_id._mart369_staff_note(self.env._(
                'Default delivery address set to %(label)s by %(who)s.',
                label=address.mart369_label, who=self.env.user.name))
        return {'ok': True, 'address': address._mart369_staff_card()}
