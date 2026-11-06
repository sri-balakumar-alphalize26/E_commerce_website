"""Pick groups off a WhatsApp session and switch them on.

Adding a group by hand meant typing a `group_jid` - an 18-digit address nobody
knows by heart, and which is silently useless if one digit is wrong, because
inbound messages are matched on it. So groups are chosen from a list of what
the number has actually joined, and the address is never typed.

The list is merged from three sources, because no single one is reliable:

- rows already in `sa.sales.group`, which work with the gateway offline;
- groups seen in inbound messages, which need no gateway call at all; and
- a live fetch from Evolution, for groups joined but not yet heard from.

The middle one is not redundant. `/group/fetchAllGroups` is unusable through
the hosted panel at whatsappmail.alphalize.com: the panel forwards the path but
drops the query string, and Evolution then answers 400 "The getParticipants
needs to be informed in the query" - for every value, and with no query at all.
Until that is fixed panel-side, any group that has ever spoken to us is still
discoverable here, because the webhook records `group_jid` on every inbound
group message whether or not the group is configured.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaGroupPicker(models.TransientModel):
    _name = 'sa.group.picker'
    _description = 'Add WhatsApp Groups'

    session_id = fields.Many2one(
        'whatsapp.session', string='WhatsApp Session', required=True,
        default=lambda self: self.env['whatsapp.session'].search([], limit=1),
        help="Whose group list to choose from.",
    )
    # Vendor groups are gone: vendors are contacts listed on a product
    # category and are messaged privately. Only customer groups are added here.
    group_type = fields.Selection([
        ('customer', 'Customer Group'),
    ], string='Add As', required=True, default='customer')

    line_ids = fields.One2many(
        'sa.group.picker.line', 'picker_id', string='Groups')
    selected_count = fields.Integer(compute='_compute_selected_count')

    # ---- Applied to every group added in this run ----
    product_category_ids = fields.Many2many(
        'product.category', string='Categories Covered',
        help="Which product categories these vendor groups can price. A "
             "request for a product in one of them is posted here.",
    )
    is_fallback_vendor_group = fields.Boolean(
        'Use as Fallback',
        help="Receives requests whose category matches no other vendor group. "
             "Only one group per session can be the fallback, so pick a single "
             "group when ticking this.",
    )
    sourcing_window_minutes = fields.Integer('Reply Window (minutes)', default=10)
    enable_now = fields.Boolean(
        'Switch On Immediately', default=True,
        help="Off, the groups are added but left alone until you tick them.",
    )

    fetch_error = fields.Char(readonly=True)

    @api.depends('line_ids.selected')
    def _compute_selected_count(self):
        for rec in self:
            rec.selected_count = len(rec.line_ids.filtered('selected'))

    # ----------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        session_id = values.get('session_id')
        if session_id:
            commands, _err = self._build_lines(
                self.env['whatsapp.session'].browse(session_id))
            values['line_ids'] = commands
        return values

    @api.onchange('session_id')
    def _onchange_session_id(self):
        for rec in self:
            rec.line_ids = [(5, 0, 0)]
            rec.fetch_error = False
            if rec.session_id:
                commands, _err = rec._build_lines(rec.session_id)
                rec.line_ids = commands

    @api.model
    def _build_lines(self, session, live=False):
        """Command list of groups for `session`, stored ones plus fetched ones."""
        linked = {
            rec.group_jid: rec
            for rec in self.env['sa.sales.group'].search(
                [('session_id', '=', session.id)])
        }
        rows = {
            jid: {
                'group_jid': jid,
                'name': rec.name,
                'member_count': rec.member_count,
                'linked_type': rec.group_type,
                'is_enabled': rec.enabled,
            }
            for jid, rec in linked.items()
        }

        # Groups that have messaged us. Free, and works when the gateway's
        # group listing does not.
        self.env.cr.execute("""
            SELECT m.group_jid, MAX(m.create_date) AS last_seen, COUNT(*) AS msgs
              FROM whatsapp_message m
             WHERE m.session_id = %s
               AND m.group_jid IS NOT NULL
               AND m.group_jid <> ''
          GROUP BY m.group_jid
          ORDER BY last_seen DESC
             LIMIT 200
        """, (session.id,))
        for jid, _last_seen, msgs in self.env.cr.fetchall():
            row = rows.setdefault(jid, {'group_jid': jid})
            row.setdefault('linked_type', False)
            row.setdefault('is_enabled', False)
            # The subject is not carried on inbound messages, so an unlinked
            # group is shown by its address with a hint of how busy it is.
            row.setdefault('name', '%s (%d message(s) seen)' % (jid.split('@')[0], msgs))

        error = ''
        if live:
            try:
                for group in session._sa_fetch_groups():
                    row = rows.setdefault(group['jid'], {'group_jid': group['jid']})
                    row.update({'name': group['name'],
                                'member_count': group['size']})
                    row.setdefault('linked_type', False)
                    row.setdefault('is_enabled', False)
            except UserError as err:
                # Offline is not a dead end: whatever was synced before is
                # still listed, so setup can carry on.
                error = str(err).replace('\n', ' ')[:200]
                _logger.info("Sales Automation: live group fetch failed (%s); "
                             "showing %d stored group(s).", error, len(rows))

        commands = [(5, 0, 0)]
        for row in sorted(rows.values(), key=lambda r: (r.get('name') or '').lower()):
            commands.append((0, 0, row))
        return commands, error

    # ----------------------------------------------------------
    def action_refresh(self):
        """Ask WhatsApp for the current group list."""
        self.ensure_one()
        if not self.session_id:
            raise UserError(_("Choose a WhatsApp session first."))
        commands, error = self._build_lines(self.session_id, live=True)
        self.write({'line_ids': commands, 'fetch_error': error or False})
        return self._reopen()

    def action_select_all(self):
        self.ensure_one()
        self.line_ids.filtered(
            lambda l: l.group_jid and not l.linked_type).selected = True
        return self._reopen()

    def action_clear(self):
        self.ensure_one()
        self.line_ids.selected = False
        return self._reopen()

    def action_add(self):
        """Create or update `sa.sales.group` for every ticked line."""
        self.ensure_one()
        chosen = self.line_ids.filtered(lambda l: l.selected and l.group_jid)
        if not chosen:
            raise UserError(_("Tick at least one group to add."))

        if self.group_type == 'vendor' and self.is_fallback_vendor_group \
                and len(chosen) > 1:
            raise UserError(_(
                "Only one group can be the fallback, but %(n)s are ticked. "
                "Add them without the fallback tick, then set it on the single "
                "group that should catch everything.", n=len(chosen)))

        SalesGroup = self.env['sa.sales.group']
        values = {'group_type': self.group_type}
        if self.enable_now:
            values['enabled'] = True
        if self.group_type == 'vendor':
            values.update({
                'product_category_ids': [(6, 0, self.product_category_ids.ids)],
                'is_fallback_vendor_group': self.is_fallback_vendor_group,
                'sourcing_window_minutes': self.sourcing_window_minutes or 10,
            })

        touched = SalesGroup.browse()
        for line in chosen:
            # Archived rows still hold the UNIQUE (session, jid) slot, so an
            # archived group is brought back rather than created twice.
            record = SalesGroup.with_context(active_test=False).search([
                ('session_id', '=', self.session_id.id),
                ('group_jid', '=', line.group_jid),
            ], limit=1)
            if record:
                vals = dict(values, name=line.name or record.name, active=True,
                            member_count=line.member_count or record.member_count)
                # The stored employee session is computed from session_id and
                # is not recomputed when the employee session was created later
                # than the group; fill it now or "enable" is refused.
                if not record.employee_session_id:
                    emp = self.env['wa.employee.session'].search(
                        [('session_id', '=', self.session_id.id)], limit=1)
                    if emp:
                        vals['employee_session_id'] = emp.id
                record.write(vals)
            else:
                record = SalesGroup.create(dict(
                    values,
                    session_id=self.session_id.id,
                    group_jid=line.group_jid,
                    name=line.name or line.group_jid,
                    member_count=line.member_count,
                ))
            touched |= record

        _logger.info("Sales Automation: added %d %s group(s) on session '%s'.",
                     len(touched), self.group_type, self.session_id.name)
        return {
            'type': 'ir.actions.act_window',
            'name': (_('Customer Groups') if self.group_type == 'customer'
                     else _('Vendor Groups')),
            'res_model': 'sa.sales.group',
            'view_mode': 'list,form',
            'domain': [('id', 'in', touched.ids)],
        }

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }


class SaGroupPickerLine(models.TransientModel):
    _name = 'sa.group.picker.line'
    _description = 'Selectable WhatsApp Group'
    _order = 'name'

    picker_id = fields.Many2one('sa.group.picker', required=True, ondelete='cascade')
    selected = fields.Boolean('Add')
    name = fields.Char('Group Name', readonly=True)
    # Deliberately not required. The list is editable so the Add toggle can be
    # clicked inline, and an editable x2many hands the client blank filler rows;
    # touching one used to create a record with no address and blow up with
    # "Missing required value for the field 'Group Address'" - on switching the
    # Add As radio, of all things. A scratch row is allowed to be empty; what
    # matters is that it can never be *added*, which action_add enforces.
    group_jid = fields.Char('Group Address', readonly=True)
    member_count = fields.Integer('Members', readonly=True)
    linked_type = fields.Selection([
        ('customer', 'Customer Group'),
        ('vendor', 'Vendor Group'),
    ], string='Already Added As', readonly=True)
    is_enabled = fields.Boolean('Currently On', readonly=True)
