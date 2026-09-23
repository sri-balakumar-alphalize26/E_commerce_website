"""The Payments group of the console's Settings screen.

Whether the shop takes a method is what Odoo's payment providers already say -
the checkout asks `_get_compatible_providers`, which reads their state, their
limit and their countries. So this reads and writes those records. It does not
keep switches of its own: two places deciding whether UPI is on would drift,
and the checkout only listens to one of them.

What the console may do is deliberately narrower than what Odoo may do:

* **Switch any provider off.** Always safe.
* **Switch on only cash on delivery and the 369 Wallet** - the two that need no
  keys. A card or UPI gateway switched on without its keys takes a customer
  all the way to a payment page that fails, so those are set up in Odoo, where
  the keys are entered.
* **Set the cash-on-delivery limit**, which is the COD provider's own
  `maximum_amount` - the number the checkout already enforces.
"""

from odoo import _, api, models
from odoo.exceptions import UserError


class Mart369Config(models.Model):
    _inherit = 'mart369.config'

    @api.model
    def _mart369_admin_providers(self):
        """The providers worth showing: every one that is on or in test mode,
        plus cash on delivery and the wallet, which are always listed."""
        Provider = self.env['payment.provider']
        return Provider.search([
            ('company_id', '=', self.env.company.id),
            '|', '|',
            ('state', '!=', 'disabled'),
            ('mart369_is_cod', '=', True),
            ('mart369_is_wallet', '=', True),
        ], order='sequence, name')

    @api.model
    def _mart369_admin_settings_groups(self):
        groups = super()._mart369_admin_settings_groups()
        Provider = self.env['payment.provider']
        providers = self._mart369_admin_providers()
        cod = providers.filtered('mart369_is_cod')[:1]
        hidden = Provider.search_count([
            ('company_id', '=', self.env.company.id),
            ('id', 'not in', providers.ids)])
        groups['pay'] = {
            'providers': [{
                'id': p.id,
                'name': p.name,
                'state': p.state,
                'kind': 'cod' if p.mart369_is_cod else 'wallet' if p.mart369_is_wallet else 'gateway',
                'canEnable': bool(p.mart369_is_cod or p.mart369_is_wallet),
            } for p in providers],
            'codLimit': cod.maximum_amount if cod else 0.0,
            'hasCod': bool(cod),
            # Switched off and not shown - set up in Odoo, not here.
            'more': hidden,
            'currency': self.env['mart369.serializable']._mart369_currency(
                self.env.company.currency_id),
        }
        return groups

    @api.model
    def _mart369_admin_save_group(self, group, values):
        if group != 'pay':
            return super()._mart369_admin_save_group(group, values)
        providers = self._mart369_admin_providers()
        wanted = values.get('providers') or {}
        if not isinstance(wanted, dict):
            raise UserError(_('Nothing to save.'))
        for key, on in wanted.items():
            provider = providers.filtered(lambda p: str(p.id) == str(key))
            if not provider:
                raise UserError(_('That payment method is not one this screen manages.'))
            is_on = provider.state != 'disabled'
            if bool(on) == is_on:
                continue
            if on and not (provider.mart369_is_cod or provider.mart369_is_wallet):
                raise UserError(_(
                    '%s needs its keys set up in Odoo before it can be switched on.',
                    provider.name))
            provider.write({'state': 'enabled' if on else 'disabled',
                            'is_published': bool(on)})
        if 'codLimit' in values:
            cod = providers.filtered('mart369_is_cod')[:1]
            try:
                limit = float(values['codLimit'] or 0)
            except (TypeError, ValueError):
                raise UserError(_('The cash-on-delivery limit must be a number.'))
            if limit < 0:
                raise UserError(_('The cash-on-delivery limit cannot be negative.'))
            if cod:
                cod.maximum_amount = limit
        return True
