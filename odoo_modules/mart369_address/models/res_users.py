"""The customer's delivery addresses, reachable from their user form."""

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    mart369_address_ids = fields.One2many(
        'res.partner', 'parent_id', string='Delivery addresses',
        compute='_compute_mart369_address_ids', inverse='_inverse_mart369_address_ids',
        domain=[('type', 'in', ['delivery', 'other'])],
        help="Addresses this customer has saved in the 369 Mart app.")

    @api.depends('partner_id', 'partner_id.child_ids.type',
                 'partner_id.child_ids.mart369_default', 'partner_id.child_ids.active')
    def _compute_mart369_address_ids(self):
        for user in self:
            book = self.env['res.partner'].search([
                ('parent_id', '=', user.partner_id.id),
                ('type', 'in', ['delivery', 'other']),
            ], order='mart369_default desc, id asc')
            user.mart369_address_ids = book
            user.mart369_address_total = len(book)

    def _inverse_mart369_address_ids(self):
        """Rows added on the form belong to this customer and are deliveries."""
        for user in self:
            user.mart369_address_ids.filtered(lambda p: not p.parent_id).write({
                'parent_id': user.partner_id.id, 'type': 'other',
            })

    mart369_address_total = fields.Integer(
        string='Saved addresses', compute='_compute_mart369_address_ids',
        help="How many delivery addresses this customer keeps.")

    def action_mart369_add_address(self):
        """+ Add address on the customer form: the same dialog Edit opens."""
        self.ensure_one()
        return self.env['res.partner']._mart369_address_dialog(customer=self.partner_id)

    # ------------------------------------------------ the Customers screens
    # mart369_auth's desk and console read a customer's "area" off their own
    # partner, which is usually blank: where they live is in their address
    # book. These read the book too.

    def _mart369_admin_row(self, wallets=None):
        row = super()._mart369_admin_row(wallets=wallets)
        book = self.partner_id.sudo()._mart369_book()
        row['addressCount'] = len(book)
        home = book.filtered('mart369_default')[:1] or book[:1]
        if home.city:
            row['area'] = home.city
        return row

    @api.model
    def _mart369_admin_domain(self, tab=None, q=None, area=None, joined=None, wallet=None):
        domain = super()._mart369_admin_domain(tab=tab, joined=joined, wallet=wallet)
        term = (q or '').strip()
        if term:
            domain += ['|', '|', '|', '|', '|', '|',
                       ('name', 'ilike', term),
                       ('login', 'ilike', term),
                       ('phone', 'ilike', term),
                       ('partner_id.city', 'ilike', term),
                       ('partner_id.street2', 'ilike', term),
                       ('partner_id.child_ids.city', 'ilike', term),
                       ('partner_id.child_ids.zip', 'ilike', term)]
        area = (area or '').strip()
        if area:
            domain += ['|', '|',
                       ('partner_id.city', '=', area),
                       ('partner_id.street2', '=', area),
                       ('partner_id.child_ids.city', '=', area)]
        return domain

    @api.model
    def _mart369_admin_areas(self):
        names = set(super()._mart369_admin_areas())
        users = self.search(self._mart369_admin_base())
        names |= {a.city for a in users.partner_id.child_ids if a.city and a.type in ('delivery', 'other')}
        return sorted(names, key=str.lower)

    @api.model
    def mart369_admin_detail(self, user_id):
        """The drawer and the desk's side panel: add the address book, and
        which address each recent order went to."""
        row = super().mart369_admin_detail(user_id)
        if not row:
            return row
        user = self.browse(int(user_id))
        customer = user.partner_id.sudo()
        book = customer._mart369_book()
        row['addresses'] = [a._mart369_staff_card() for a in book]
        row['removedAddresses'] = len(
            customer._mart369_book(active_test=False).filtered(lambda a: not a.active))
        if row.get('recent') and 'sale.order' in self.env:
            refs = [o['ref'] for o in row['recent']]
            Order = self.env['sale.order'].sudo()
            key = 'mart369_ref' if 'mart369_ref' in Order._fields else 'name'
            where = {getattr(o, key) or o.name: o.partner_shipping_id
                     for o in Order.search([(key, 'in', refs)])}
            for order in row['recent']:
                shipped = where.get(order['ref'])
                order['addressLabel'] = (shipped.mart369_label or '') if shipped and shipped.parent_id else ''
        return row
