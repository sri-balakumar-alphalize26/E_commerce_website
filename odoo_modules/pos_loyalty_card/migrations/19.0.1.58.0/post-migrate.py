from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Ensure exactly one Loyalty Settings record is active after upgrade
    (the is_active flag is new; older records had none)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Settings = env['pos.loyalty.card.settings']
    if not Settings.search_count([('is_active', '=', True)]):
        rec = Settings.search([], limit=1)
        if rec:
            rec.with_context(_skip_active_sync=True).write({'is_active': True})
