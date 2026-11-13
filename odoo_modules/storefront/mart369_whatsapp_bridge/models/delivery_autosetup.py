"""The WhatsApp side of delivery setting itself up.

mart369_cart's automatic setup (models/delivery_autosetup.py) finds a branch's
pin and switches Quick on. A delivery made from an order still needs a
*delivery shop* (`sa.delivery.shop`) to leave from, with its own pin for
ranking riders - one more record per branch that nobody remembered to make, so
jobs went out with no shop at all.

So here:

* every branch on the map gets its delivery shop, made once, with the
  branch's pin. A shop somebody made or archived is never touched, except
  that an empty pin is filled from its branch;
* a job leaves from the shop of the warehouse its stock leaves from, when that
  shop was made here - the storefront already picked the branch that has it;
* "nearest shop" measures from the shop's own pin first (it read only the
  address contact's, so a pinned shop with an unpinned contact never counted);
* the checklist adds the shop and its riders. A rider is the one thing that
  cannot be made automatically.
"""

from odoo import api, fields, models

from odoo.addons.mart369_cart.models.branch import has_pin
from odoo.addons.mart369_cart.models.delivery_autosetup import OK, TODO, WAIT, OFF, check


class SaDeliveryShopAuto(models.Model):
    _inherit = 'sa.delivery.shop'

    mart369_auto = fields.Boolean(
        string='Made automatically', copy=False,
        help="Made by the automatic delivery setup for its branch, and its pin "
             "follows the branch's. Changing the pin here makes it yours.")

    def write(self, vals):
        if ('latitude' in vals or 'longitude' in vals) and 'mart369_auto' not in vals \
                and not self.env.context.get('mart369_auto_setup'):
            vals = dict(vals, mart369_auto=False)
        return super().write(vals)

    @api.model
    def _sa_pick_for(self, partner, warehouse=None):
        if warehouse and not self.env.context.get('qe_force_shop'):
            own = self.sudo().search([('warehouse_id', '=', warehouse.id),
                                      ('mart369_auto', '=', True)], limit=1)
            if own:
                return own
        return super()._sa_pick_for(partner, warehouse=warehouse)

    @api.model
    def _sa_nearest(self, partner, shops):
        lat, lon = partner.partner_latitude, partner.partner_longitude
        if not lat or not lon:
            return self.browse()
        best, best_km = self.browse(), None
        for shop in shops:
            here = shop._sa_position()
            if not here[0] or not here[1]:
                continue
            km = self._sa_km(lat, lon, here[0], here[1])
            if best_km is None or km < best_km:
                best, best_km = shop, km
        return best


class StockWarehouseAutoShop(models.Model):
    _inherit = 'stock.warehouse'

    @api.model
    def _mart369_auto_setup(self):
        done = super()._mart369_auto_setup()
        return done + self._mart369_auto_shops()

    @api.model
    def _mart369_auto_shops(self):
        """A delivery shop for every branch on the map that has none, and the
        branch's pin on every shop that has no pin (or follows its branch)."""
        Shop = self.env['sa.delivery.shop'].sudo().with_context(
            active_test=False, mart369_auto_setup=True)
        done = []
        for branch in self.sudo().search([]):
            if not has_pin(branch.mart369_lat, branch.mart369_lng):
                continue
            pin = {'latitude': branch.mart369_lat, 'longitude': branch.mart369_lng}
            shops = Shop.search([('warehouse_id', '=', branch.id)])
            if not shops:
                Shop.create(dict(pin, name=branch.name, warehouse_id=branch.id,
                                 mart369_auto=True))
                done.append(self.env._('%s: WhatsApp delivery shop made.', branch.name))
                continue
            for shop in shops.filtered('active'):
                empty = not (shop.latitude and shop.longitude)
                moved = shop.mart369_auto and (shop.latitude, shop.longitude) != (
                    pin['latitude'], pin['longitude'])
                if empty or moved:
                    shop.write(pin)
                    done.append(self.env._('%s: delivery shop pin set from the branch.',
                                           shop.name))
        return done

    def _mart369_setup_checks(self):
        checks = super()._mart369_setup_checks()
        if not has_pin(self.mart369_lat, self.mart369_lng):
            return checks
        _ = self.env._
        Shop = self.env['sa.delivery.shop'].sudo().with_context(active_test=False)
        shops = Shop.search([('warehouse_id', '=', self.id)])
        live = shops.filtered('active')
        if live:
            checks.append(check('shop', OK, _('WhatsApp delivery shop'), 'shop'))
        elif shops:
            checks.append(check('shop', OFF, _('WhatsApp delivery shop archived'), 'shop'))
            return checks
        else:
            checks.append(check('shop', WAIT, _('WhatsApp delivery shop being made'), 'shop'))
        riders = self.env['sa.delivery.partner'].sudo().search([]).filtered(
            lambda r: not r.shop_ids or (r.shop_ids & live))
        if riders:
            on = len(riders.filtered('on_duty'))
            line = (_('1 rider (%s on duty)', on) if len(riders) == 1 else
                    _('%(n)s riders (%(on)s on duty)', n=len(riders), on=on))
            checks.append(check('riders', OK, line, 'riders'))
        else:
            checks.append(check('riders', TODO, _('Add a rider for this branch'), 'riders'))
        return checks
