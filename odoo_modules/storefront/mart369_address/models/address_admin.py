"""What the app's own admin console reads, and what the addresses desk draws.

**Read-only, and deliberately so.** These are customers' home addresses: other
people's personal details, and the place their shopping is sent. Nothing here
creates, edits or deletes one, and there is no route behind such a thing either
- the decision is enforced by there being nothing to call rather than by a
check somebody can loosen later. A customer edits their own addresses in the
app; staff look, so they can tell somebody why a delivery failed.

Two things worth knowing before changing any of this.

**`mart369_gap_label` cannot be searched.** It is a non-stored compute, so it
may not appear in a domain, a group-by or a `search_count`. Every tile and tab
here counts the raw fields - `zip`, `phone`, `partner_latitude` - exactly as
the backend search view's three filters already do. Counting the label instead
looks tidier and returns nothing.

**An address is a child partner, not a model of its own.** A 369 Mart address
is a `res.partner` under the customer, typed `other`, except the chosen one
which is typed `delivery` - that is how Odoo decides where an order ships, and
why only `_mart369_set_default` may move it.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# The customer's own addresses, and nobody else's records. `parent_id` set and
# a 369 Mart type is what separates an address from a company contact.
BASE = [
    ('type', 'in', ('delivery', 'other')),
    ('parent_id', '!=', False),
]

# What each tab asks for. The gap tabs read raw fields because the label they
# would rather use is not stored.
TABS = {
    'all': [],
    'no_pincode': [('zip', '=', False)],
    'no_mobile': [('phone', '=', False)],
    'no_location': [('partner_latitude', '=', 0.0),
                    ('partner_longitude', '=', 0.0)],
    'archived': [('active', '=', False)],
}

MAX_ROWS = 100


class Mart369AddressAdmin(models.Model):
    _inherit = 'res.partner'

    # --------------------------------------------------------- serializing

    def _mart369_admin_row(self):
        """One address as the staff screens draw it.

        Its own shape rather than widening `_mart369_serialize`: that one goes
        to the customer who owns the address, and who else it belongs to is not
        theirs to read.
        """
        self.ensure_one()
        return {
            'id': self.id,
            'customer': self.parent_id.display_name or 'Someone',
            'customerId': self.parent_id.id,
            # The customer's login, so a screen can open the customer itself.
            'customerUser': self.parent_id.user_ids[:1].id or False,
            'label': self.mart369_label or '',
            'name': self.name or '',
            'phone': self.phone or '',
            'altPhone': self.mart369_alt_phone or '',
            'line': ', '.join(p for p in (self.street, self.street2) if p),
            'building': self.street or '',
            'area': self.street2 or '',
            'landmark': self.mart369_landmark or '',
            'city': self._mart369_city_line(),
            'town': self.city or '',
            'state': self.state_id.name or '',
            'country': self.country_id.name or '',
            'zip': self.zip or '',
            # The nouns the backend prints in red, as a list rather than the
            # joined string, so a screen can draw them however it likes.
            'gaps': self._mart369_gaps(),
            'isDefault': bool(self.mart369_default),
            'archived': not self.active,
            'lat': self.partner_latitude or 0.0,
            'lng': self.partner_longitude or 0.0,
        }

    # ------------------------------------------------------------ reading

    @api.model
    def _mart369_admin_domain(self, tab=None, q=None):
        domain = list(BASE) + list(TABS.get(tab or 'all', TABS['all']))
        term = (q or '').strip()
        if term:
            domain += ['|', '|', '|',
                       ('parent_id.name', 'ilike', term),
                       ('name', 'ilike', term),
                       ('city', 'ilike', term),
                       ('zip', 'ilike', term)]
        return domain

    @api.model
    def mart369_admin_list(self, tab=None, q=None, limit=30, offset=0):
        """One page of the addresses, and the tile counts above them."""
        domain = self._mart369_admin_domain(tab=tab, q=q)
        limit = max(1, min(int(limit or 30), MAX_ROWS))
        offset = max(0, int(offset or 0))

        # `active_test=False` on the archived tab, or the domain asks for
        # inactive records and Odoo has already filtered them out.
        books = self.with_context(active_test=False) if tab == 'archived' else self
        rows = books.search(domain, limit=limit, offset=offset,
                            order='parent_id, mart369_default desc, id asc')

        payload = self.mart369_admin_counts()
        payload.update({
            'addresses': self._mart369_admin_rows_with_totals(books, domain, rows),
            'total': books.search_count(domain),
            'limit': limit,
            'offset': offset,
        })
        return payload

    @api.model
    def mart369_admin_counts(self):
        """The tiles, and the number on each tab.

        `search_count` per tab, so the tiles count every address rather than
        whatever the screen is filtered to - a "missing a pincode" that fell
        when somebody typed in the search box would stop answering the only
        question it is there to answer.
        """
        counts = {}
        for key, where in TABS.items():
            books = self.with_context(active_test=False) if key == 'archived' else self
            counts[key] = books.search_count(BASE + where)

        # One row per customer who has an address, not per address.
        everyone = self.search(BASE)
        return {
            'counts': counts,
            'customers': len(set(everyone.mapped('parent_id').ids)),
            # Missing anything at all, which is not the sum of the three tabs:
            # one address can be missing two things.
            'incomplete': sum(1 for a in everyone if a._mart369_gaps()),
        }

    # --------------------------------------------------------------- demo

    @api.model
    def _mart369_load_address_demo(self):
        """A few addresses to look at, across whoever is signed up.

        Called from `data/address_demo.xml` rather than being records there,
        because an address is a child of a customer and this module ships
        none. Does nothing once a 369 Mart address exists, so a shop with real
        customers never sprouts examples.

        Three of the six are missing something on purpose - a pincode, a
        mobile, a map pin - because that is what the screens are for, and a
        perfect example set shows none of it.
        """
        if self.with_context(active_test=False).search_count(BASE):
            return False

        # Whoever is signed up. A portal user is a customer; staff are not.
        customers = self.env['res.users'].search(
            [('share', '=', True)], limit=3).mapped('partner_id')
        if not customers:
            # No customers, so nothing to hang an address on. The empty state
            # explains itself.
            return False

        places = [
            {'mart369_label': 'Home', 'street': '5/2 Sivamurugan Colony, 2nd Street',
             'street2': 'Sandai Road', 'city': 'Dindigul', 'zip': '624003',
             'phone': '+919486020356', 'partner_latitude': 10.3673,
             'partner_longitude': 77.9803, 'default': True},
            {'mart369_label': 'Work', 'street': '14 Bypass Road',
             'city': 'Dindigul', 'zip': '624005', 'phone': '+919486020357'},
            # No pincode.
            {'mart369_label': 'Home', 'street': '22 Gandhi Nagar',
             'city': 'Madurai', 'phone': '+919486020358'},
            # No mobile.
            {'mart369_label': 'Work', 'street': '3rd Cross, KK Nagar',
             'city': 'Madurai', 'zip': '625020'},
            # No map pin, which is the one a driver notices.
            {'mart369_label': 'Home', 'street': '8 Anna Salai',
             'city': 'Trichy', 'zip': '620001', 'phone': '+919486020359'},
            {'mart369_label': 'Home', 'street': '61 Race Course Road',
             'city': 'Coimbatore', 'zip': '641018', 'phone': '+919486020360',
             'partner_latitude': 11.0026, 'partner_longitude': 76.9666},
        ]

        made = self.browse()
        for index, place in enumerate(places):
            owner = customers[index % len(customers)]
            is_default = place.pop('default', False)
            address = self.create(dict(
                place, parent_id=owner.id, type='other',
                name=owner.name or 'Customer'))
            made |= address
            # Through the helper, never by writing the flag: it is what moves
            # `type='delivery'` and clears the sibling.
            if is_default:
                address._mart369_set_default()

        # Give every customer somewhere to ship to, so the list is not all
        # addresses and no default.
        for owner in customers:
            theirs = made.filtered(lambda a, o=owner: a.parent_id == o)
            if theirs and not theirs.filtered('mart369_default'):
                theirs[0]._mart369_set_default()

        _logger.info('369 Mart: seeded %s example address(es)', len(made))
        return True

    @api.model
    def _mart369_admin_rows_with_totals(self, books, domain, rows):
        """The rows, each carrying how many addresses its customer has under
        this tab - so a screen grouping them by customer can say "3 addresses"
        even when the page stops half way through somebody's list."""
        parents = rows.parent_id
        totals = {}
        if parents:
            for parent, count in books._read_group(
                    list(domain) + [('parent_id', 'in', parents.ids)], ['parent_id'], ['__count']):
                totals[parent.id] = count
        out = []
        for address in rows:
            row = address._mart369_admin_row()
            row['customerTotal'] = totals.get(address.parent_id.id, 1)
            out.append(row)
        return out
