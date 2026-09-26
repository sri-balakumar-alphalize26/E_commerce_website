"""Which door the order came in through.

The website's orders carry a `mart369_ref`; the WhatsApp flow's orders carry a
group enquiry (or a private conversation). Until now each stack only saw its
own. The channel field is the one word both stacks agree on, and it is what
lets the console's board show the whole shop.

A WhatsApp order deliberately gets **no `mart369_ref`**. Too much of the
website's machinery keys off that field - the shopper's own order list, the
wallet refunds, payment-by-reference, the support bot - and a WhatsApp
customer has none of those. On the console a WhatsApp order is shown under its
Odoo name (S00042), which cannot collide with the app's 369M- numbers.
"""

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mart369_channel = fields.Selection(
        [('website', 'Website'), ('whatsapp', 'WhatsApp')],
        string='Channel', compute='_compute_mart369_channel', store=True,
        index=True, copy=False,
        help="Which door this order came in through. WhatsApp when it grew "
             "out of a group enquiry or a private chat; the website "
             "otherwise.")

    # The stack links enquiry -> order (`sa.group.request.order_id`) and only
    # sometimes writes the reverse `sa_group_request_id`. This One2many is the
    # reverse of the stack's own field, so the compute sees both directions.
    mart369_sa_request_ids = fields.One2many(
        'sa.group.request', 'order_id', string='WhatsApp enquiries',
        copy=False)

    @api.depends('mart369_ref', 'sa_group_request_id',
                 'mart369_sa_request_ids', 'wa_conversation_id')
    def _compute_mart369_channel(self):
        for order in self:
            if order.mart369_ref:
                order.mart369_channel = 'website'
            elif (order.sa_group_request_id or order.mart369_sa_request_ids
                    or order.wa_conversation_id):
                order.mart369_channel = 'whatsapp'
            else:
                order.mart369_channel = 'website'

    # ------------------------------------------------------------- the board

    @api.model
    def _mart369_board_domain(self):
        """The board now answers for both doors.

        A WhatsApp order has no `mart369_ref`, so the base rule alone would
        never show one. The state guard still applies to both: a WhatsApp
        order only gets a `mart369_state` once it is confirmed
        (sale_order_sync.py), so drafts and abandoned enquiries stay off the
        screen exactly as unpaid website baskets do.
        """
        return ['|', ('mart369_ref', '!=', False),
                ('mart369_channel', '=', 'whatsapp'),
                ('mart369_state', 'not in', (False, 'draft'))]

    # ----------------------------------------------------------- the console

    @api.model
    def _mart369_admin_domain(self, tab=None, mode=None, when=None, q=None,
                              pay=None):
        domain = super()._mart369_admin_domain(
            tab=tab, mode=mode, when=when, q=q, pay=pay)
        channel = self.env.context.get('mart369_channel')
        if channel in ('website', 'whatsapp'):
            domain += [('mart369_channel', '=', channel)]
        # The search box knows the website's numbers; teach it the WhatsApp
        # orders' names too, in place - the leaf is replaced, not appended, so
        # the OR structure around it stays intact.
        term = (q or '').strip()
        if term:
            domain = [
                ['|', ('mart369_ref', 'ilike', term), ('name', 'ilike', term)]
                if leaf == ('mart369_ref', 'ilike', term) else leaf
                for leaf in domain
            ]
            # Flatten the one nested replacement back into the domain.
            flat = []
            for leaf in domain:
                if isinstance(leaf, list) and leaf and leaf[0] == '|':
                    flat.extend(leaf)
                else:
                    flat.append(leaf)
            domain = flat
        return domain

    @api.model
    def mart369_admin_list(self, tab=None, mode=None, when=None, q=None,
                           sort=None, limit=30, offset=0, pay=None,
                           channel=None):
        """The console's list, with the channel filter carried in context -
        the base method's signature stays untouched that way."""
        records = self
        if channel in ('website', 'whatsapp'):
            records = self.with_context(mart369_channel=channel)
        return super(SaleOrder, records).mart369_admin_list(
            tab=tab, mode=mode, when=when, q=q, sort=sort, limit=limit,
            offset=offset, pay=pay)

    @api.model
    def _mart369_admin_find(self, ref):
        """A WhatsApp order is found by its Odoo name.

        The website's numbers are 369M-…; Odoo's are S…; the two cannot
        collide, so one lookup can serve both screens.
        """
        order = super()._mart369_admin_find(ref)
        if order or not ref or not isinstance(ref, str):
            return order
        return self.search(self._mart369_board_domain() + [
            ('mart369_channel', '=', 'whatsapp'), ('name', '=', ref),
        ], limit=1)

    def _mart369_admin_row(self):
        row = super()._mart369_admin_row()
        row['channel'] = self.mart369_channel or 'website'
        if not self.mart369_ref:
            row['ref'] = self.name
        # Sudo'd on purpose: console staff have no rights on the WhatsApp
        # stack's own models (groups, jobs, riders), and these five words on
        # a card must not demand any. Read-only facts, chosen one by one.
        job = self.sudo()._mart369_bridge_job()
        if job:
            row['wa'] = {
                'job': job.sa_ref_code or '',
                'group': self.sudo().sa_group_id.name or '',
                'shop': job.sa_shop_id.name or '',
                'rider': job.sa_delivery_partner_id.name or '',
                'stage': dict(job._fields['sa_delivery_state'].selection).get(
                    job.sa_delivery_state, ''),
            }
        return row

    def _mart369_admin_detail(self):
        row = super()._mart369_admin_detail()
        if self.mart369_channel == 'whatsapp':
            # Removing a line or offering a replacement refunds to the 369
            # Wallet - which a WhatsApp customer does not have. Their refunds
            # are the stack's own (the Store screen's Refund button).
            row['canRemove'] = False
            row['canReplace'] = False
        return row
