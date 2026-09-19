"""A saved home page.

The app has one home page, and it changes for a festival and changes back. The
way to do that used to be editing the live page: swap nine banners on Thursday
night, swap them back on Monday, and hope nobody forgot one.

A version is the whole page saved under a name. Build "Diwali" once, keep it,
switch it on when the time comes - or give it a window and let it switch
itself. Everything a page is made of hangs off its two modes, so a version
owns those, and copying one copies the lot.

Two ideas, deliberately kept apart:

* **Switched on** (`is_current`) is the everyday page. Exactly one, always.
  It is the floor the shop returns to.
* **Scheduled** (`starts_on` / `ends_on`) is a page that takes over for a
  while. When its window closes the everyday page comes back on its own.

Which is why there is no cron here. The choice is made when the app asks, so
it is right even if nobody was awake at midnight, and right even if the server
was not running at the time.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Mart369HomeVersion(models.Model):

    _name = 'mart369.home.version'
    _description = '369 Mart Saved Home Page'
    _order = 'is_current desc, starts_on desc, id'

    name = fields.Char(
        string='Name', required=True,
        help='What this page is for: "Everyday", "Diwali 2026", "Clearance".')
    note = fields.Char(
        string='Note',
        help='A line for whoever opens this in six months.')
    config_id = fields.Many2one(
        'mart369.config', string='Settings',
        required=True, ondelete='cascade', index=True,
        default=lambda self: self.env['mart369.config'].sudo()._get())

    is_current = fields.Boolean(
        string='Everyday page', copy=False,
        help='The page the app shows when nothing is scheduled. Exactly one '
             'page has this, and switching another on turns it off here.')
    starts_on = fields.Datetime(
        string='Show from', copy=False,
        help='Optional. From this moment the app shows this page instead of '
             'the everyday one.')
    ends_on = fields.Datetime(
        string='Show until', copy=False,
        help='Optional. After this moment the everyday page comes back by '
             'itself.')

    mode_ids = fields.One2many(
        'mart369.home.mode', 'version_id', string='Modes', copy=True,
        help='The Quick and Express tabs of this saved page, and everything '
             'inside them.')

    state = fields.Selection([
        ('live', 'Live now'),
        ('scheduled', 'Scheduled'),
        ('ended', 'Ended'),
        ('off', 'Off'),
    ], string='Status', compute='_compute_state',
        help='What shoppers are seeing - the one thing on this screen that '
             'must never be ambiguous.')
    state_note = fields.Char(string='Because', compute='_compute_state')

    # ------------------------------------------------------------ the choice

    @api.model
    def _mart369_live(self):
        """The saved page the app should serve right now.

        A window beats the switch, and the window that opened most recently
        beats an earlier one - so a clearance started this morning wins over a
        month-long campaign, which is what anyone scheduling both would mean.
        """
        now = fields.Datetime.now()
        scheduled = self.sudo().search([
            '|', ('starts_on', '=', False), ('starts_on', '<=', now),
            '|', ('ends_on', '=', False), ('ends_on', '>=', now),
            '|', ('starts_on', '!=', False), ('ends_on', '!=', False),
        ], order='starts_on desc, id desc', limit=1)
        if scheduled:
            return scheduled
        return (self.sudo().search([('is_current', '=', True)], limit=1)
                or self.sudo().search([], limit=1))

    @api.depends('is_current', 'starts_on', 'ends_on')
    def _compute_state(self):
        now = fields.Datetime.now()
        live = self._mart369_live()
        for rec in self:
            if rec == live:
                rec.state = 'live'
                rec.state_note = (
                    _('scheduled until %s', rec.ends_on) if rec.ends_on
                    else _('the everyday page'))
            elif rec.ends_on and rec.ends_on < now:
                rec.state = 'ended'
                rec.state_note = _('finished %s', rec.ends_on)
            elif rec.starts_on and rec.starts_on > now:
                rec.state = 'scheduled'
                rec.state_note = _('starts %s', rec.starts_on)
            else:
                rec.state = 'off'
                rec.state_note = _('saved, not in use')

    # ------------------------------------------------------------- the rules

    def _mart369_keep_one_current(self):
        """Exactly one everyday page, always."""
        current = self.sudo().search([('is_current', '=', True)])
        if len(current) > 1:
            (current - current[0]).with_context(
                mart369_settling=True).write({'is_current': False})
        elif not current:
            first = self.sudo().search([], limit=1)
            if first:
                first.with_context(
                    mart369_settling=True).write({'is_current': True})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._mart369_keep_one_current()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'is_current' in vals and not self.env.context.get('mart369_settling'):
            if vals.get('is_current'):
                # Switching one on turns the others off in the same step, so
                # there is never a moment with two.
                others = self.sudo().search([
                    ('is_current', '=', True), ('id', 'not in', self.ids)])
                others.with_context(
                    mart369_settling=True).write({'is_current': False})
            self._mart369_keep_one_current()
        return result

    def unlink(self):
        if any(rec.is_current for rec in self):
            raise UserError(self.env._(
                'That is the everyday home page. Switch another one on first, '
                'or the app would be left with no home page at all.'))
        if self.sudo().search_count([]) <= len(self):
            raise UserError(self.env._(
                'This is the only saved home page. There has to be one.'))
        return super().unlink()

    # ------------------------------------------------------------- the moves

    def action_mart369_make_current(self):
        """Switch this page on - what the tile's switch calls."""
        self.ensure_one()
        self.write({'is_current': True})
        return True

    def action_mart369_duplicate(self):
        """How a new page is really made: copy the one you have, then edit it.

        `copy()` carries the modes and, through them, every band inside - so
        this is a whole working home page, not an empty one.
        """
        self.ensure_one()
        copied = self.copy({'name': self.env._('%s (copy)', self.name)})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': copied.id,
            'view_mode': 'form',
            'target': 'current',
        }
