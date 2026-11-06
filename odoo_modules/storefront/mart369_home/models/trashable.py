from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

DEFAULT_TRASH_DAYS = 30


def refuse_demo(env):
    """The one thing anybody is told when they try to change the Demo page."""
    raise UserError(env._(
        'This is the Demo page, the template that shows how a home page is '
        'laid out. It cannot be changed or removed. Duplicate it, then edit '
        'the copy.'))


class Mart369Trashable(models.AbstractModel):
    """Removing something puts it in the Trash instead of destroying it.

    It waits there for the number of days set in Home Page Settings, can be
    put back at any time before that, and is then deleted for good by a
    nightly job.

    `active` is left exactly as it was, so restoring returns a banner to the
    state the operator left it in - shown if it was shown, hidden if it was
    hidden. That is why hiding and removing are two different things here:
    hiding is a switch, removing starts a clock.
    """

    _name = 'mart369.home.trashable'
    _description = '369 Mart Trash'

    # What this is called in the Trash list. Overridden per model.
    _trash_what = 'Item'

    deleted_at = fields.Datetime(
        string='Moved to Trash', index=True, copy=False,
        help='When this was removed. Until the Trash empties it can be put '
             'back, unchanged.')
    trash_days_left = fields.Integer(
        string='Days left', compute='_compute_trash_days_left',
        help='How long this stays in the Trash before it is deleted for good.')

    @api.depends('deleted_at')
    def _compute_trash_days_left(self):
        keep = self.env['mart369.config'].sudo()._trash_days()
        now = fields.Datetime.now()
        for rec in self:
            if not rec.deleted_at:
                rec.trash_days_left = 0
                continue
            left = (rec.deleted_at + timedelta(days=keep)) - now
            # Round up: something with two hours left has "1 day left", not 0.
            rec.trash_days_left = max(0, -(-left.total_seconds() // 86400))

    # ------------------------------------------------------------- filtering

    def _live(self):
        """What the app should see: shown, and not in the Trash."""
        return self.filtered(lambda r: r.active and not r.deleted_at)

    def _kept(self):
        """What the builder should list: everything except the Trash."""
        return self.filtered(lambda r: not r.deleted_at)

    def _trashed(self):
        return self.filtered(lambda r: r.deleted_at)

    # ------------------------------------------------------------ the Demo page

    def _mart369_check_not_demo(self):
        """Refuse a change to anything on the Demo page. Checked here, on the
        records, so the Odoo screens and the staff console cannot differ.

        Only for what sits on a page, which is what has a `mode_id`. A saved
        page has its own rules, and other models share this mixin."""
        if self.env.context.get('mart369_demo_build') or 'mode_id' not in self._fields:
            return
        if any(self.sudo().mapped('mode_id.version_id.is_demo')):
            refuse_demo(self.env)

    @api.model_create_multi
    def create(self, vals_list):
        if 'mode_id' in self._fields:
            modes = self.env['mart369.home.mode'].browse(
                {vals['mode_id'] for vals in vals_list if vals.get('mode_id')})
            modes._mart369_check_not_demo()
        return super().create(vals_list)

    def write(self, vals):
        self._mart369_check_not_demo()
        return super().write(vals)

    def unlink(self):
        self._mart369_check_not_demo()
        return super().unlink()

    # --------------------------------------------------------------- actions

    def action_trash(self):
        """Remove, recoverably."""
        self.write({'deleted_at': fields.Datetime.now()})
        return True

    def action_restore(self):
        """Put back, exactly as it was."""
        self.write({'deleted_at': False})
        return True

    def _trash_vals(self):
        """One row of the Trash list in the builder."""
        self.ensure_one()
        name = self.display_name or getattr(self, 'key', '') or _('Untitled')
        return {
            'model': self._name,
            'id': self.id,
            'what': self._trash_what,
            'name': name,
            'deleted_at': fields.Datetime.to_string(self.deleted_at),
            'days_left': self.trash_days_left,
        }
