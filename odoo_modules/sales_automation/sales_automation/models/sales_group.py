"""A WhatsApp group the number belongs to, and what it is for.

One row per group. `enabled` is the tick: off, the group is listed and
ignored; on, every message posted there is acted on according to `group_type`.

Two kinds of group, and they behave nothing alike:

- **customer** - people asking to buy. Messages are classified, confirmed and
  turned into sourcing requests.
- **vendor** - people we buy from, organised by product category. Messages here
  are read only as prices against an open request. Nothing is ever classified
  as an enquiry, and the bot never replies.

Getting the type wrong is the one configuration mistake that matters, which is
why it is a required choice with no silent default on the vendor side.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.whatsapp_employee_tracker.models.phone_digits import same_number

_logger = logging.getLogger(__name__)


class SalesGroup(models.Model):
    _name = 'sa.sales.group'
    _description = 'WhatsApp Sales Group'
    _order = 'enabled desc, group_type, name'
    _rec_name = 'name'

    name = fields.Char('Group Name', required=True)
    group_jid = fields.Char(
        'Group JID', required=True, index=True, readonly=True,
        help="The group's WhatsApp address, e.g. 120363xxxxxxxx@g.us. "
             "Set by Sync Groups; it is what inbound messages are matched on.",
    )
    session_id = fields.Many2one(
        'whatsapp.session', string='WhatsApp Session',
        required=True, ondelete='cascade', index=True,
    )
    employee_session_id = fields.Many2one(
        'wa.employee.session', string='Employee Session',
        compute='_compute_employee_session_id', store=True, readonly=False,
        help="Whose tracker session handles the private follow-up. Defaults to "
             "the employee assigned to this WhatsApp session; override it to "
             "route a group's leads to someone else.",
    )
    member_count = fields.Integer('Members', readonly=True)
    active = fields.Boolean(default=True)

    # ---- What this group is ----
    group_type = fields.Selection([
        ('customer', 'Customer Group'),
        ('vendor', 'Vendor Group'),
    ], string='Group Type', default='customer', required=True, index=True,
        help="Customer: enquiries are read here and answered. "
             "Vendor: messages are read only as prices against an open "
             "request, and the bot never replies.",
    )

    # ---- The tick ----
    enabled = fields.Boolean(
        'Sales Automation', default=False,
        help="Take part in the sales flow. Off, the group is left completely "
             "alone - nothing is read, logged or replied to.",
    )

    # ==========================================================
    # Customer-group settings
    # ==========================================================
    ai_enabled = fields.Boolean(
        'Use AI Classification', default=True,
        help="Ask the configured AI whether a message is a product enquiry "
             "before searching the catalog. Off, or when the AI is "
             "unreachable, the catalog keywords decide on their own.",
    )
    max_products = fields.Integer(
        'Max Products to Match', default=5,
        help="How many catalog matches to consider. The best one is quoted.",
    )
    min_confidence = fields.Float(
        'Minimum AI Confidence', default=0.6,
        help="Below this the enquiry is recorded but not answered. 0 answers "
             "everything the AI calls a product.",
    )
    handoff_dm = fields.Boolean(
        'Continue in Private Chat', default=False,
        help="Move price, bargaining, address and payment into a direct chat "
             "instead of posting them in the group. Off, the whole group sees "
             "every quoted price - and, over many enquiries, the margin "
             "pattern behind them.",
    )
    use_virtual_stock = fields.Boolean(
        'Count Incoming Stock', default=False,
        help="Judge availability on forecasted quantity instead of what is "
             "physically on hand.",
    )
    require_confirmation = fields.Boolean(
        'Confirm Product First', default=True,
        help="Ask the customer to confirm the matched product before asking "
             "vendors to price it. Keyword matching is loose enough that this "
             "is what stops the wrong product being sourced.",
    )

    # ---- Pricing ----
    markup_percent = fields.Float(
        'Margin (%)', default=20.0,
        help="Added to what the product costs us - the cheapest vendor reply, "
             "or the vendor price list when nobody replies: "
             "quoted = cost x (1 + margin / 100).",
    )
    dm_use_buttons = fields.Boolean(
        'Use Buttons in the Private Chat',
        help="Off (the default), the private follow-up is sent as plain text. "
             "Button messages render on the WhatsApp phone app but arrive on "
             "WhatsApp Web and Desktop as \"This message couldn't load\" - so a "
             "customer at a computer sees nothing to answer. The text already "
             "carries the same numbered choices, and works everywhere.",
    )
    group_use_buttons = fields.Boolean(
        'Ask with Buttons in the Private Chat',
        help="Off (the default), a question is asked in the group as a "
             "poll. A poll is the only tappable prompt that renders in a "
             "group: WhatsApp refuses to draw a button message there, on the "
             "phone as well as on desktop, and shows \"This message couldn't "
             "load\" instead.\n\n"
             "On, the question moves to the customer's own chat and is sent "
             "as tappable buttons, which render properly one-to-one. The "
             "group is left a single line saying the conversation moved, so "
             "quoted prices stop being posted in front of everyone.\n\n"
             "A requester whose number is hidden has no private chat to move "
             "to, so their question stays in the group as a poll.",
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
        help="Which business this group sells for. Stock, price, vendor and "
             "the sale order are all read in this company.\n\n"
             "It has to live here rather than being taken from the WhatsApp "
             "session: one session serves every group, and a message arrives "
             "with no user logged in, so there is nothing else to infer it "
             "from. Left empty, the session's company is used as before.",
    )
    auto_confirm_order = fields.Boolean(
        'Confirm and Take Payment Automatically',
        help="Off (the default), the assistant stops at a draft quotation: no "
             "confirmation, no payment request, no invoice. A salesperson "
             "reviews it, confirms the order, sends the invoice and records "
             "the payment in Sales as usual.\n\n"
             "On, the assistant confirms the order itself and asks the "
             "customer to pay over WhatsApp.",
    )

    # ==========================================================
    # Vendor-group settings
    # ==========================================================
    product_category_ids = fields.Many2many(
        'product.category', 'sa_sales_group_product_category_rel',
        'group_id', 'category_id', string='Categories Covered',
        help="Which product categories this vendor group can price. Child "
             "categories are included automatically.",
    )
    is_fallback_vendor_group = fields.Boolean(
        'Fallback Vendor Group',
        help="Receives requests whose category matches no other vendor group - "
             "including products that are not in the catalog at all. At most "
             "one per WhatsApp session.",
    )
    sourcing_window_minutes = fields.Integer(
        'Reply Window (minutes)', default=10,
        help="How long to collect vendor prices before quoting the customer "
             "the cheapest one. Too short and you lose the better price that "
             "was still coming; too long and the customer gives up.",
    )

    notes = fields.Text('Notes')

    request_count = fields.Integer('Enquiries', compute='_compute_request_count')
    order_count = fields.Integer('Orders', compute='_compute_request_count')
    quote_count = fields.Integer('Vendor Quotes', compute='_compute_quote_count')

    _unique_group = models.Constraint(
        'UNIQUE (session_id, group_jid)',
        'This group is already linked to that WhatsApp session.',
    )

    @api.depends('session_id')
    def _compute_employee_session_id(self):
        EmployeeSession = self.env['wa.employee.session']
        for rec in self:
            current = rec.employee_session_id
            if current and current.active and current.session_id == rec.session_id:
                continue  # a deliberate override, leave it alone
            rec.employee_session_id = EmployeeSession.search(
                [('session_id', '=', rec.session_id.id)], limit=1)

    def _sa_ensure_employee_session(self):
        """The employee session this group hands private threads to - found,
        or made on the spot.

        A fresh database has none, and every step that needs one (the
        private thread, the sale order) used to fail with a misleading
        message. One per WhatsApp session (unique constraint), owned by an
        employee called "Shop Counter" unless a session already exists.
        """
        self.ensure_one()
        if self.employee_session_id.active:
            return self.employee_session_id
        EmployeeSession = self.env['wa.employee.session'].sudo()
        session = self.session_id
        if not session:
            return EmployeeSession
        found = EmployeeSession.search([('session_id', '=', session.id)], limit=1)
        if not found:
            # an old one only for the number the session is now (23 Nov 2026)
            number = session.authorized_number or session.phone_number
            found = EmployeeSession.with_context(active_test=False).search(
                [('session_id', '=', session.id)], order='until desc, id desc').filtered(
                    lambda r: not number or r._number_now() == number or same_number(r.own_number, number))[:1]
            if found and EmployeeSession.search_count([('employee_id', '=', found.employee_id.id)], limit=1):
                found = EmployeeSession          # that employee has another number now
        if found:
            if not found.active:
                found.active = True
        else:
            Employee = self.env['hr.employee'].sudo()
            employee = Employee.search([('name', '=', 'Shop Counter')], limit=1) \
                or Employee.create({'name': 'Shop Counter'})
            found = EmployeeSession.create({
                'employee_id': employee.id,
                'session_id': session.id,
                'phone_number': ('+' + session.authorized_number if session.authorized_number
                                 else session.phone_number or session.name or 'shop'),
            })
            _logger.info("Sales Automation: created employee session %s "
                         "(Shop Counter) for WhatsApp session %s", found.id,
                         session.name)
        self.sudo().write({'employee_session_id': found.id})
        return found

    def _sa_employee_session_for(self, session_id):
        """The employee session already linked to this WhatsApp session."""
        if not session_id:
            return self.env['wa.employee.session']
        return self.env['wa.employee.session'].search(
            [('session_id', '=', session_id)], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        # Switched on at birth with nobody assigned: take the session's
        # employee, the same one the compute would pick.
        for vals in vals_list:
            if vals.get('enabled') and not vals.get('employee_session_id') \
                    and vals.get('group_type', 'customer') == 'customer':
                found = self._sa_employee_session_for(vals.get('session_id'))
                if found:
                    vals['employee_session_id'] = found.id
        return super().create(vals_list)

    def write(self, vals):
        # The stored compute only runs when session_id changes, so a group
        # synced before its session got an employee stays empty forever and
        # switching it on hit the constraint. Fill the gap first.
        if vals.get('enabled') and not vals.get('employee_session_id'):
            for rec in self:
                if rec.employee_session_id or \
                        vals.get('group_type', rec.group_type) != 'customer':
                    continue
                found = rec._sa_employee_session_for(
                    vals.get('session_id', rec.session_id.id))
                if found:
                    super(SalesGroup, rec).write({'employee_session_id': found.id})
        return super().write(vals)

    def _compute_request_count(self):
        Request = self.env['sa.group.request']
        for rec in self:
            rec.request_count = Request.search_count([('group_id', '=', rec.id)])
            rec.order_count = Request.search_count([
                ('group_id', '=', rec.id), ('order_id', '!=', False),
            ])

    def _compute_quote_count(self):
        Quote = self.env['sa.vendor.quote']
        for rec in self:
            rec.quote_count = Quote.search_count([('group_id', '=', rec.id)])

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------
    @api.constrains('enabled', 'group_type', 'employee_session_id')
    def _check_enabled_has_employee_session(self):
        for rec in self:
            # Only a customer group hands a conversation to an employee. A
            # vendor group never talks to anyone, so it needs nobody assigned.
            if rec.enabled and rec.group_type == 'customer' \
                    and not rec.employee_session_id:
                raise ValidationError(rec._sa_no_employee_text())

    def _sa_no_employee_text(self):
        """Why this group cannot be switched on, and what to press."""
        self.ensure_one()
        session = self.session_id
        lines = [
            _("\"%s\" cannot be turned on yet: no employee is chosen to answer "
              "its customers.", self.name),
            _("It uses the WhatsApp session \"%s\", and nobody is linked to "
              "that session.", session.name),
        ]
        # The same number in a second session that does have an employee: the
        # group belongs there, linking one more employee would not help.
        number = session.sudo().authorized_number
        other = self.env['wa.employee.session'].sudo().search([
            ('session_id.active', '=', True),
            ('session_id', '!=', session.id),
            ('session_id.authorized_number', '=', number),
        ], limit=1) if number else False
        if other:
            lines.append(_(
                "What to do: the session \"%(other)s\" has the same WhatsApp "
                "number and already has %(employee)s. Open that session, press "
                "Sync Groups, and turn on \"%(group)s\" there. Turn off the "
                "session \"%(session)s\": one number needs only one session.",
                other=other.session_id.name, employee=other.employee_id.name,
                group=self.name, session=session.name))
        else:
            lines.append(_(
                "What to do: in WhatsApp Numbers, press Give to an employee "
                "beside \"%(session)s\" and choose the employee. Then turn on "
                "\"%(group)s\" again.",
                session=session.name, group=self.name))
        lines.append(_("If this is a group of suppliers, change its Group Type "
                       "to Vendor Group; it needs no employee."))
        return '\n\n'.join(lines)

    @api.constrains('is_fallback_vendor_group', 'session_id', 'group_type')
    def _check_single_fallback(self):
        for rec in self:
            if not rec.is_fallback_vendor_group:
                continue
            if rec.group_type != 'vendor':
                raise ValidationError(_(
                    "Only a vendor group can be the fallback. '%(name)s' is a "
                    "customer group.", name=rec.name))
            clash = self.search([
                ('id', '!=', rec.id),
                ('session_id', '=', rec.session_id.id),
                ('is_fallback_vendor_group', '=', True),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "'%(other)s' is already the fallback vendor group for this "
                    "WhatsApp session. There can only be one, or a request "
                    "would go to two groups at once.", other=clash.name))

    @api.constrains('group_type', 'enabled', 'group_jid')
    def _check_one_role_per_group(self):
        """The same WhatsApp group cannot be both sides of a deal.

        Two Odoo sessions can point at one WhatsApp instance, so the same group
        can be added twice under different session records. Enabled as a
        customer group on one and a vendor group on the other, it would be read
        as an enquiry and as a price at the same time.
        """
        for rec in self:
            if not rec.enabled:
                continue
            clash = self.search([
                ('id', '!=', rec.id),
                ('group_jid', '=', rec.group_jid),
                ('group_type', '!=', rec.group_type),
                ('enabled', '=', True),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "'%(name)s' is already switched on as a %(other)s on "
                    "session '%(session)s'. The same WhatsApp group cannot be "
                    "a customer group and a vendor group at once - switch that "
                    "one off first.",
                    name=rec.name,
                    other=dict(self._fields['group_type'].selection)[clash.group_type],
                    session=clash.session_id.name))

    @api.constrains('sourcing_window_minutes', 'group_type')
    def _check_window(self):
        for rec in self:
            if rec.group_type == 'vendor' and rec.sourcing_window_minutes < 1:
                raise ValidationError(_(
                    "The reply window for '%(name)s' must be at least one "
                    "minute, or no vendor price can ever be collected.",
                    name=rec.name))

    # ----------------------------------------------------------
    # Routing: which vendor group prices this product?
    # ----------------------------------------------------------
    @api.model
    def _find_vendor_group(self, session, product=None):
        """The vendor group that covers `product`, or the fallback.

        Categories are walked upwards: a group registered for "Electronics"
        answers for "Electronics / Cables / USB" without anyone having to list
        every leaf. The nearest match wins, so a group registered for the leaf
        beats one registered for its parent.
        """
        groups = self.search([
            ('session_id', '=', session.id),
            ('group_type', '=', 'vendor'),
            ('enabled', '=', True),
        ])
        if not groups:
            return self.browse()

        category = product.categ_id if product else None
        while category:
            match = groups.filtered(lambda g: category in g.product_category_ids)
            if match:
                return match[0]
            category = category.parent_id

        return groups.filtered('is_fallback_vendor_group')[:1]

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------
    def action_view_requests(self):
        self.ensure_one()
        field = 'sourcing_group_id' if self.group_type == 'vendor' else 'group_id'
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enquiries - %s', self.name),
            'res_model': 'sa.group.request',
            'view_mode': 'list,form',
            'domain': [(field, '=', self.id)],
            'context': {'default_group_id': self.id},
        }

    def action_view_quotes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Quotes - %s', self.name),
            'res_model': 'sa.vendor.quote',
            'view_mode': 'list,form',
            'domain': [('group_id', '=', self.id)],
        }

    def action_open_picker(self):
        """Open the group picker for whichever list this was pressed from.

        The type comes from the action's context rather than from two separate
        buttons, so Customer Groups and Vendor Groups share one New button.

        Deliberately NOT @api.model. A button calls this through `call_button`,
        which passes the selected ids as the first argument; `_call_kw_model`
        forwards args untouched, so an @api.model method receives that list as
        an extra positional and dies with "takes 1 positional argument but 2
        were given". `_call_kw_multi` strips the ids into `self` instead, which
        is what a button expects - `self` is simply empty here.
        """
        group_type = self.env.context.get('default_group_type') or 'customer'
        xmlid = ('sales_automation.action_sa_group_picker_vendor'
                 if group_type == 'vendor'
                 else 'sales_automation.action_sa_group_picker_customer')
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        action['context'] = dict(self.env.context, default_group_type=group_type)
        return action

    def action_sync_groups(self):
        """Same refresh as the button on the session, reachable from here."""
        self.ensure_one()
        return self.session_id.action_sa_sync_groups()
