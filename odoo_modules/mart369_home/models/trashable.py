from datetime import timedelta

from odoo import _, api, fields, models

DEFAULT_TRASH_DAYS = 30


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
        keep = self.env['mart369.home.config'].sudo()._trash_days()
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
