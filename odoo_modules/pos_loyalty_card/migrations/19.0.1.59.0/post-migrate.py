from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Ensure exactly one Points Rule is active after upgrade (is_active is new)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Rule = env['pos.loyalty.rule']
    if not Rule.search_count([('is_active', '=', True)]):
        rec = Rule.search([], limit=1)
        if rec:
            rec.with_context(_skip_active_sync=True).write({'is_active': True})
