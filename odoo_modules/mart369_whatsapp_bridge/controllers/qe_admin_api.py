"""The console's Delivery screen saves into the senior's records.

Same routes, same payloads and answers as mart369_cart's admin delivery API,
so components/admin/AdminDelivery.jsx is unchanged; where his
`sales_automation_quick_express` is installed, a save is a plain create or
write on his fee rules, slots, service areas and delivery shops (Quick on,
reach, pin). Nothing of his is overridden. Where he is not installed, every
route hands back to the website's own.

His ACL lets only his delivery managers write; the console's own gate
(`_may_edit`, the same check every console route makes) decides who may, and
the write itself runs as superuser for those people.
"""

from psycopg2 import IntegrityError

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.mart369_cart.controllers.admin_api import (
    Mart369DeliveryAdminApi, _PATCH, _POST)

from ..models.qe_link import (
    QUICK, THEIRS, area_row, qe_on, rule_row, shop_row, slot_row)


class Mart369DeliveryAdminQe(Mart369DeliveryAdminApi):

    def _qe(self):
        return qe_on(request.env)

    def _qe_model(self, name):
        return request.env[name].sudo().with_context(active_test=False)

    def _qe_save(self, record, values, row, status=200, creating_model=None):
        try:
            with request.env.cr.savepoint():
                if creating_model:
                    record = self._qe_model(creating_model).create(values)
                else:
                    record.write(values)
                record.flush_recordset()
        except (AccessError, UserError, ValidationError) as exc:
            return None, self._fail(str(exc))
        except IntegrityError:
            return None, self._fail('That already exists.', status=409)
        return record, None

    # ------------------------------------------------------------------ rules

    @http.route('/369mart/admin/delivery/rules/<int:rule_id>', **_PATCH)
    def update_rule(self, rule_id, **kwargs):
        if not self._qe():
            return super().update_rule(rule_id, **kwargs)
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        rule = self._one(self._qe_model('sa.qe.delivery.rule'), rule_id)
        if not rule:
            return self._fail('There is no such delivery rule.', status=404)
        try:
            values = self._rule_values(self._body())
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        if not values:
            return self._fail('Nothing to change.')
        rule, failed = self._qe_save(rule, values, rule_row)
        return failed or self._json({'ok': True, 'rule': rule_row(rule)})

    # ------------------------------------------------------------------ slots

    def _qe_slot_values(self, body, creating=False):
        values = self._slot_values(body)          # the console's own checks
        out = {}
        if 'mode' in values:
            out['mode'] = THEIRS.get(values['mode'], values['mode'])
        for field in ('kind', 'from_hour', 'to_hour', 'day_offset', 'order_before',
                      'fee', 'capacity', 'sequence', 'active'):
            if field in values:
                out[field] = values[field]
        # His slot has one name: the console's label, else its heading.
        name = values.get('label') or values.get('top')
        if name:
            out['name'] = name
        if creating and not out.get('name'):
            raise ValueError('top')
        return out

    @http.route('/369mart/admin/delivery/slots', **_POST)
    def create_slot(self, **kwargs):
        if not self._qe():
            return super().create_slot(**kwargs)
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            values = self._qe_slot_values(self._body(), creating=True)
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        values.setdefault('mode', THEIRS[QUICK])
        slot, failed = self._qe_save(None, values, slot_row,
                                     creating_model='sa.qe.delivery.slot')
        return failed or self._json({'ok': True, 'slot': slot_row(slot)}, status=201)

    @http.route('/369mart/admin/delivery/slots/<int:slot_id>', **_PATCH)
    def update_slot(self, slot_id, **kwargs):
        if not self._qe():
            return super().update_slot(slot_id, **kwargs)
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        slot = self._one(self._qe_model('sa.qe.delivery.slot'), slot_id)
        if not slot:
            return self._fail('There is no such slot.', status=404)
        try:
            values = self._qe_slot_values(self._body())
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        if not values:
            return self._fail('Nothing to change.')
        slot, failed = self._qe_save(slot, values, slot_row)
        return failed or self._json({'ok': True, 'slot': slot_row(slot)})

    # ------------------------------------------------------------------ areas

    @http.route('/369mart/admin/delivery/areas', **_POST)
    def create_area(self, **kwargs):
        if not self._qe():
            return super().create_area(**kwargs)
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            values = self._area_values(self._body(), creating=True)
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        Area = self._qe_model('sa.qe.service.area')
        taken = Area.search([('pincode', '=', Area._qe_clean(values['pincode']))], limit=1)
        if taken:
            return self._fail('There is already an area for %s.' % taken.pincode,
                              field='pincode', status=409)
        area, failed = self._qe_save(None, values, area_row,
                                     creating_model='sa.qe.service.area')
        return failed or self._json({'ok': True, 'area': area_row(area)}, status=201)

    @http.route('/369mart/admin/delivery/areas/<int:area_id>', **_PATCH)
    def update_area(self, area_id, **kwargs):
        if not self._qe():
            return super().update_area(area_id, **kwargs)
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        Area = self._qe_model('sa.qe.service.area')
        area = self._one(Area, area_id)
        if not area:
            return self._fail('There is no such service area.', status=404)
        try:
            values = self._area_values(self._body())
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        if not values:
            return self._fail('Nothing to change.')
        if values.get('pincode'):
            taken = Area.search([('pincode', '=', Area._qe_clean(values['pincode'])),
                                 ('id', '!=', area.id)], limit=1)
            if taken:
                return self._fail('There is already an area for %s.' % taken.pincode,
                                  field='pincode', status=409)
        area, failed = self._qe_save(area, values, area_row)
        return failed or self._json({'ok': True, 'area': area_row(area)})

    # --------------------------------------------------------------- branches

    @http.route('/369mart/admin/delivery/branches/<int:branch_id>', **_PATCH)
    def update_branch(self, branch_id, **kwargs):
        """A branch is one of his delivery shops now: Quick on, reach, pin."""
        if not self._qe():
            return super().update_branch(branch_id, **kwargs)
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        shop = self._one(self._qe_model('sa.delivery.shop'), branch_id)
        if not shop:
            return self._fail('There is no such branch.', status=404)
        body = self._body()
        values = {}
        if 'quick' in body:
            values['qe_quick'] = bool(body['quick'])
        for key, field in (('quickKm', 'qe_quick_km'), ('lat', 'latitude'), ('lng', 'longitude')):
            if key in body:
                try:
                    values[field] = float(body[key] or 0.0)
                except (TypeError, ValueError):
                    return self._fail('%s is a number.' % key, field=key)
        if not values:
            return self._fail('Nothing to change.')
        shop, failed = self._qe_save(shop, values, shop_row)
        return failed or self._json({'ok': True, 'branch': shop_row(shop)})
