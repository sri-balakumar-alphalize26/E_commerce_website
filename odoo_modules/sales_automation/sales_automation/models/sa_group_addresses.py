# -*- coding: utf-8 -*-
"""One customer, many delivery addresses (owner, 5 Oct 2026).

Until now every address a customer typed on WhatsApp was written over the one
street on their contact, so yesterday's address was lost and every open order
of that customer moved with it. Now:

* the customer's contact keeps the FIRST address they gave (home);
* a different address typed for a later order is saved as its own delivery
  address under the customer, and only that order points at it
  (`sale.order.partner_shipping_id`, which the delivery job follows);
* a new order starts at the home address again; after NO > ADDRESS on the
  read-back the customer may answer with the number of a saved address or
  type a new one;
* a correction typed during the same order replaces what was just typed
  instead of piling up addresses.
The map pin and the note for the rider belong to the address of the order.
"""
import logging
import re

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class SaGroupRequestAddresses(models.Model):
    _inherit = 'sa.group.request'

    sa_addr_owned_id = fields.Many2one(
        'res.partner', 'Address typed for this order', copy=False,
        help="The contact / delivery address whose street was typed during "
             "this order's details. A correction overwrites it; any other "
             "address of the customer is left alone.")

    # ------------------------------------------------------------------
    # The customer's address book
    # ------------------------------------------------------------------
    @staticmethod
    def _sa_addr_key(text):
        return re.sub(r'[^a-z0-9]+', '', (text or '').lower())

    def _sa_saved_addresses(self, partner):
        """Home first, then the other delivery addresses, oldest first."""
        partner = partner.sudo()
        if not partner:
            return partner
        kids = partner.child_ids.filtered(
            lambda c: c.type == 'delivery' and c.active and c.street).sorted('id')
        return (partner if partner.street else partner.browse()) | kids

    def _sa_ship(self, order):
        """The address THIS order is delivered to."""
        order = order.sudo()
        main, ship = order.partner_id, order.partner_shipping_id
        if ship and (ship == main or ship.parent_id == main):
            return ship
        return main

    def _sa_use_address(self, order, addr):
        """Point the order (and its open delivery jobs) at `addr`."""
        order = order.sudo()
        main = order.partner_id
        if addr != main and (addr.name != main.name or addr.phone != main.phone):
            addr.write({'name': main.name, 'phone': main.phone})
        if order.partner_shipping_id != addr:
            order.write({'partner_shipping_id': addr.id})
        jobs = order.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel') and p.picking_type_code == 'outgoing'
            and p.partner_id != addr)
        if jobs:
            jobs.write({'partner_id': addr.id})
        return addr

    @staticmethod
    def _sa_addr_line(addr):
        street = addr.street or ''
        low = street.lower()
        extra = [x for x in (addr.city, addr.zip) if x and x.lower() not in low]
        return ', '.join(filter(None, [street] + extra))

    @staticmethod
    def _sa_addr_snapshot(main):
        """Everything a temporary write on the contact must put back. The
        pin is in it on purpose: Odoo clears a contact's map pin whenever an
        address field is written without the pin in the same write."""
        return {'street': main.street, 'zip': main.zip, 'country_id': main.country_id.id,
                'partner_latitude': main.partner_latitude, 'partner_longitude': main.partner_longitude}

    # ------------------------------------------------------------------
    # The ladder
    # ------------------------------------------------------------------
    def _sa_group_details_start(self, order):
        """A new order starts at the customer's home address, whatever the
        last order used."""
        self.ensure_one()
        order = order.sudo()
        main = order.partner_id
        if order.partner_shipping_id != main and order.partner_shipping_id.parent_id == main \
                and main.street:
            self._sa_use_address(order, main)
        if self.sa_addr_owned_id:
            self.sa_addr_owned_id = False
        return super()._sa_group_details_start(order)

    def _sa_profile_summary(self, partner):
        """The read-back shows the address of THIS order."""
        self.ensure_one()
        order = self.order_id.sudo()
        if order and order.partner_id == partner:
            ship = self._sa_ship(order)
            if ship != partner:
                if ship.name != partner.name or ship.phone != partner.phone:
                    ship.write({'name': partner.name, 'phone': partner.phone})
                return super()._sa_profile_summary(ship)
        return super()._sa_profile_summary(partner)

    def _sa_details_ask(self, order):
        """NO > ADDRESS: offer the saved addresses by number."""
        self.ensure_one()
        if self.sa_details_fix == 'address' and self.profile_step == 'address' \
                and not self.profile_retry:
            order = order.sudo()
            saved = self._sa_saved_addresses(order.partner_id)
            current = self._sa_ship(order)
            if len(saved) > 1 or (saved and saved[0] != current):
                lines = ['%s. %s%s' % (i, self._sa_addr_line(a),
                                       _(" (on this order now)") if a == current else '')
                         for i, a in enumerate(saved, 1)]
                self.profile_asked_on = fields.Datetime.now()
                self._say(_("\U0001F3E0 Where should order *#%(ref)s* be delivered?\n\n"
                            "%(lines)s\n\nReply with the *number* of a saved address, "
                            "or type a *new full address* (door number, street, area, city).",
                            ref=self.ref_code or order.name, lines='\n'.join(lines)))
                return True
        return super()._sa_details_ask(order)

    def _sa_take_profile_answer(self, text, order):
        self.ensure_one()
        step = self.profile_step or 'name'
        if step not in ('address', 'pin'):
            return super()._sa_take_profile_answer(text, order)
        order = order.sudo()
        main = order.partner_id.sudo()
        answer = (text or '').strip()
        if self._sa_is_cancel(answer):
            return super()._sa_take_profile_answer(text, order)

        if step == 'pin':
            target = self._sa_ship(order)
            if target == main:
                return super()._sa_take_profile_answer(text, order)
            # the postcode belongs to the order's address, not to home
            snap = self._sa_addr_snapshot(main)
            main.write({'zip': False})
            res = super()._sa_take_profile_answer(text, order)
            vals = {}
            if main.zip:
                vals['zip'] = main.zip
            if main.country_id.id != snap['country_id']:
                vals['country_id'] = main.country_id.id
            main.write(snap)
            if vals:
                target.write(vals)
            return res

        # ---- step == 'address' ----
        saved = self._sa_saved_addresses(main)
        if answer.isdigit() and len(answer) <= 2 and saved and 1 <= int(answer) <= len(saved) \
                and self.sa_details_fix == 'address':
            chosen = saved[int(answer) - 1]
            self._sa_use_address(order, chosen)
            self.write({'profile_step': 'confirm', 'profile_retry': 0,
                        'profile_last_bad': False, 'profile_restarted': False})
            _logger.info("Sales Automation: enquiry %s - order %s goes to saved address %s",
                         self.id, order.name, chosen.id)
            return None

        owned = self.sa_addr_owned_id
        if not main.street or owned == main:
            # the customer's first address, or a correction of it: on the contact
            before = main.street
            res = super()._sa_take_profile_answer(text, order)
            if main.street and (main.street != before or self.profile_step != 'address'):
                self.sa_addr_owned_id = main.id
                self._sa_use_address(order, main)
            return res

        # The customer already has a home address: this is another place.
        snap = self._sa_addr_snapshot(main)
        main.write({'zip': False})
        res = super()._sa_take_profile_answer(text, order)
        accepted = self.profile_step != 'address'
        new = {'street': main.street, 'zip': main.zip or False, 'country_id': main.country_id.id}
        main.write(snap)
        if not accepted:
            return res
        key = self._sa_addr_key(new['street'])
        match = saved.filtered(lambda a: self._sa_addr_key(a.street) == key)[:1]
        if owned and owned != main and owned.exists():
            # a correction of the address typed a moment ago for this order
            owned.write({k: v for k, v in new.items() if v or k == 'street'})
            target = owned
        elif match:
            target = match                       # they typed one we already have
            if new['zip'] and not target.zip:
                target.write({'zip': new['zip']})
        else:
            target = self.env['res.partner'].sudo().create({
                'parent_id': main.id, 'type': 'delivery', 'name': main.name,
                'phone': main.phone, 'street': new['street'], 'zip': new['zip'],
                'country_id': new['country_id'] or main.country_id.id,
                'city': False, 'street2': False,
            })
            self.sa_addr_owned_id = target.id
            _logger.info("Sales Automation: enquiry %s - new delivery address %s for %s (home kept)",
                         self.id, target.id, main.name)
        self._sa_use_address(order, target)
        return res
