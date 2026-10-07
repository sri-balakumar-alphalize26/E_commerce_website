"""Delivery by the senior's rules: areas, Quick reach, fees, slots, promise.

The website kept its own copy of what delivery costs and where Quick reaches
(mart369_cart: service areas, two fee rules, slots, the warehouses' pins).
The WhatsApp side keeps the same things in `sales_automation_quick_express`,
and the two could disagree. Where that module is installed, the website now
reads and writes the senior's records and calls his helpers - his page,
section 5, "what to call" - so the website and WhatsApp always agree:

  * is this pincode served             sa.qe.service.area._qe_match(pin)
  * Quick or Express, and from where   sa.delivery.shop (_qe_ready, _qe_in_reach,
                                       _qe_has_stock) + the product's delivery text
  * what delivery costs                sa.qe.delivery.rule._qe_for(mode); one fee
                                       per order, his formula
  * which slots are open               sa.qe.delivery.slot (_qe_is_open, _qe_day,
                                       _qe_due)
  * the fee line on a placed order     his sale.order._qe_apply_fee()

A soft dependency, on purpose: without his module (a database that does not
run it) every method here hands straight back to the website's own, so
nothing changes there. His names for the two deliveries are 'quick' and
'express'; the website's are 'quick' and 'all'.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

QUICK, EXPRESS = 'quick', 'all'          # the website's names
THEIRS = {'quick': 'quick', 'all': 'express'}
OURS = {'quick': 'quick', 'express': 'all'}
SLOT_PREFIX = 'qe:'


def qe_on(env):
    """Is the senior's Quick / Express module installed here?"""
    return 'sa.qe.delivery.rule' in env and 'sa.qe.delivery.slot' in env


def clock(hour):
    """18.5 -> '6:30 PM', 8 -> '8 AM'."""
    hour = float(hour or 0.0)
    h, m = int(hour), int(round((hour - int(hour)) * 60))
    suffix = 'AM' if h < 12 or h == 24 else 'PM'
    h12 = h % 12 or 12
    return ('%d:%02d %s' % (h12, m, suffix)) if m else ('%d %s' % (h12, suffix))


class QeRule:
    """One of his fee rules, wearing the website rule's face: the same field
    names (label, eta, min_order, free_above, fee) plus the shopper's
    serializer, so the cart, the rules route and the support bot read it
    unchanged."""

    def __init__(self, record):
        self.record = record
        self.label = record.label or ''
        self.eta = record.eta or ''
        self.min_order = record.min_order or 0.0
        self.free_above = record.free_above or 0.0
        self.fee = record.fee or 0.0
        self.mode = OURS.get(record.mode, record.mode)

    def __bool__(self):
        return bool(self.record)

    def _mart369_serialize(self):
        return {
            'label': self.label,
            'eta': self.eta,
            'minOrder': round(self.min_order, 2),
            'freeAbove': round(self.free_above, 2),
            'fee': round(self.fee, 2),
        }


def qe_rules(env):
    """{'quick': QeRule, 'all': QeRule} from his two rules."""
    Rule = env['sa.qe.delivery.rule'].sudo()
    found = {}
    for ours, theirs in THEIRS.items():
        rule = Rule._qe_for(theirs)
        if rule:
            found[ours] = QeRule(rule)
    return found


def slot_sub(slot):
    if slot.kind == 'now':
        return slot.name or ''
    if slot.kind == 'days':
        return _('In %s day(s)', slot.day_offset or 1)
    return '%s - %s' % (clock(slot.from_hour), clock(slot.to_hour))


def slot_chip(slot):
    """One of his slots as a checkout chip, the shape the website reads."""
    mode = OURS.get(slot.mode, slot.mode)
    chip = {'key': '%s%d' % (SLOT_PREFIX, slot.id), 'top': slot.name or '',
            'sub': slot_sub(slot), 'label': slot.name or ''}
    if mode == EXPRESS or slot.fee:
        chip['fee'] = round(slot.fee or 0.0, 2)
    return chip


# ------------------------------------------------------------- the console rows

def rule_row(rule):
    mode = OURS.get(rule.mode, rule.mode)
    return {
        'id': rule.id, 'mode': mode,
        'modeLabel': 'Quick' if mode == QUICK else 'Express',
        'label': rule.label or '', 'eta': rule.eta or '',
        'minOrder': round(rule.min_order or 0.0, 2),
        'freeAbove': round(rule.free_above or 0.0, 2),
        'fee': round(rule.fee or 0.0, 2), 'active': bool(rule.active),
    }


def slot_row(slot):
    mode = OURS.get(slot.mode, slot.mode)
    kinds = dict(slot._fields['kind'].selection)
    return {
        'id': slot.id, 'sequence': slot.sequence, 'mode': mode,
        'modeLabel': 'Quick' if mode == QUICK else 'Express',
        'kind': slot.kind, 'kindLabel': kinds.get(slot.kind, slot.kind or ''),
        'key': '%s%d' % (SLOT_PREFIX, slot.id),
        'top': slot.name or '', 'sub': slot_sub(slot), 'label': slot.name or '',
        'fromHour': round(slot.from_hour or 0.0, 2),
        'toHour': round(slot.to_hour or 0.0, 2),
        'dayOffset': slot.day_offset or 0,
        'orderBefore': round(slot.order_before or 0.0, 2),
        'fee': round(slot.fee or 0.0, 2), 'capacity': slot.capacity or 0,
        'active': bool(slot.active),
    }


def area_row(area):
    return {
        'id': area.id, 'pincode': area.pincode or '', 'name': area.name or '',
        'quick': bool(area.quick), 'express': bool(area.express),
        'eta': area.eta or '', 'active': bool(area.active),
    }


def shop_row(shop):
    lat, lng = shop.latitude, shop.longitude
    pinned = bool(lat or lng)
    return {
        'id': shop.id, 'name': shop.name or '',
        'code': shop.warehouse_id.code or '',
        'company': shop.warehouse_id.company_id.name or '',
        'quick': bool(shop.qe_quick),
        'quickKm': round(shop.qe_quick_km or 0.0, 2),
        'lat': lat if pinned else None, 'lng': lng if pinned else None,
        'unready': bool(shop.qe_quick and not shop._qe_ready()),
    }


# ------------------------------------------------------------------ the models

class DeliveryRuleQe(models.Model):
    _inherit = 'mart369.delivery.rule'

    @api.model
    def _mart369_rules(self):
        if not qe_on(self.env):
            return super()._mart369_rules()
        return qe_rules(self.env)

    @api.model
    def _mart369_qe_copy_across(self):
        """Move the website's own delivery settings into his, once - his page:
        "Moving your records across". Nothing he already has is duplicated,
        so running it again adds nothing. Returns what it did, for the log."""
        env = self.env
        if not qe_on(env):
            return {}
        done = {'areas': 0, 'rules': 0, 'slots': 0, 'shops': 0, 'products': 0}

        Area = env['sa.qe.service.area'].sudo().with_context(active_test=False)
        for area in env['mart369.service.area'].sudo().with_context(active_test=False).search([]):
            pin = Area._qe_clean(area.pincode)
            if not pin or Area.search_count([('pincode', '=', pin)]):
                continue
            Area.create({'pincode': pin, 'name': area.name or False,
                         'quick': area.quick, 'express': area.express,
                         'eta': area.eta or False, 'active': area.active})
            done['areas'] += 1

        Rule = env['sa.qe.delivery.rule'].sudo().with_context(active_test=False)
        for rule in self.sudo().with_context(active_test=False).search([]):
            mode = THEIRS.get(rule.mode)
            if not mode:
                continue
            values = {'label': rule.label, 'eta': rule.eta, 'min_order': rule.min_order,
                      'free_above': rule.free_above, 'fee': rule.fee}
            theirs = Rule.search([('mode', '=', mode)], limit=1)
            if theirs:
                theirs.write(values)        # one rule per mode: write that one
            else:
                Rule.create(dict(values, mode=mode))
            done['rules'] += 1

        Slot = env['sa.qe.delivery.slot'].sudo().with_context(active_test=False)
        for slot in env['mart369.delivery.slot'].sudo().with_context(active_test=False).search([]):
            mode = THEIRS.get(slot.mode)
            name = slot.label or ' '.join(x for x in (slot.top, slot.sub) if x) or slot.key
            if not mode or not name or Slot.search_count([('mode', '=', mode), ('name', '=', name)]):
                continue
            Slot.create({'sequence': slot.sequence, 'name': name, 'mode': mode,
                         'kind': slot.kind, 'from_hour': slot.from_hour,
                         'to_hour': slot.to_hour, 'order_before': slot.order_before or 24.0,
                         'day_offset': slot.day_offset, 'fee': slot.fee,
                         'capacity': slot.capacity, 'active': slot.active})
            done['slots'] += 1

        Shop = env['sa.delivery.shop'].sudo().with_context(active_test=False)
        for warehouse in env['stock.warehouse'].sudo().search([]):
            if not (warehouse.mart369_quick or warehouse.mart369_lat or warehouse.mart369_lng):
                continue
            shop = Shop.search([('warehouse_id', '=', warehouse.id)], limit=1)
            if not shop:
                continue
            values = {'qe_quick': bool(warehouse.mart369_quick),
                      'qe_quick_km': warehouse.mart369_quick_km or 0.0}
            if warehouse.mart369_lat or warehouse.mart369_lng:
                values.update(latitude=warehouse.mart369_lat, longitude=warehouse.mart369_lng)
            shop.write(values)
            done['shops'] += 1

        Template = env['product.template'].sudo().with_context(active_test=False)
        if 'qe_delivery_text' in Template._fields:
            for product in Template.search([('mart_delivery_text', '!=', False),
                                            ('qe_delivery_text', '=', False)]):
                product.with_context(mart369_qe_text=True).qe_delivery_text = \
                    product.mart_delivery_text
                done['products'] += 1

        # Staff edit delivery in the console (now his records) or in his
        # Store menus; the website's own Odoo screens would edit copies that
        # nothing reads any more.
        for xmlid in ('mart369_cart.menu_mart369_delivery_desk',
                      'mart369_cart.menu_mart369_delivery_rules',
                      'mart369_cart.menu_mart369_service_areas',
                      'mart369_cart.menu_mart369_slots'):
            menu = env.ref(xmlid, raise_if_not_found=False)
            if menu:
                menu.sudo().active = False
        return done

    def mart369_admin_list(self):
        """The staff console's Delivery screen, from his records."""
        if not qe_on(self.env):
            return super().mart369_admin_list()
        env = self.env
        Rule = env['sa.qe.delivery.rule'].sudo().with_context(active_test=False)
        Slot = env['sa.qe.delivery.slot'].sudo().with_context(active_test=False)
        Area = env['sa.qe.service.area'].sudo().with_context(active_test=False)
        Shop = env['sa.delivery.shop'].sudo().with_context(active_test=False)
        rules, slots, areas, shops = Rule.search([]), Slot.search([]), Area.search([]), Shop.search([])
        kinds = Slot._fields['kind'].selection
        return {
            'rules': [rule_row(r) for r in rules],
            'slots': [slot_row(s) for s in slots],
            'areas': [area_row(a) for a in areas],
            'branches': [shop_row(s) for s in shops],
            'modes': [{'key': QUICK, 'label': 'Quick'}, {'key': EXPRESS, 'label': 'Express'}],
            'kinds': [{'key': key, 'label': label} for key, label in kinds],
            'currency': env['mart369.serializable']._mart369_currency(),
            'counts': {
                'rules': len(rules.filtered('active')),
                'slots': len(slots.filtered('active')),
                'areas': len(areas.filtered('active')),
                'branches': len(shops.filtered('qe_quick')),
            },
        }


class ServiceAreaQe(models.Model):
    _inherit = 'mart369.service.area'

    @api.model
    def _mart369_match(self, pin):
        """His area for this pincode (longest prefix), read by the website's
        serviceability answer and the cart unchanged: same quick / express /
        eta fields."""
        if not qe_on(self.env):
            return super()._mart369_match(pin)
        return self.env['sa.qe.service.area']._qe_match(pin)


class DeliverySlotQe(models.Model):
    _inherit = 'mart369.delivery.slot'

    @api.model
    def _mart369_slots(self):
        """His slots that are open now, as the checkout's chips."""
        if not qe_on(self.env):
            return super()._mart369_slots()
        out = {QUICK: [], EXPRESS: []}
        for slot in self.env['sa.qe.delivery.slot'].sudo().search([]):
            mode = OURS.get(slot.mode)
            if mode in out and slot._qe_is_open():
                out[mode].append(slot_chip(slot))
        return out


class CartQe(models.AbstractModel):
    _inherit = 'mart369.cart'

    @api.model
    def _mart369_express_only(self, product):
        if super()._mart369_express_only(product):
            return True
        return bool(qe_on(self.env) and 'qe_delivery_text' in product._fields
                    and product.qe_delivery_text)

    @api.model
    def _mart369_where(self, address):
        """His shops instead of our warehouses; his areas without a pin."""
        if not qe_on(self.env):
            return super()._mart369_where(address)
        where = {'branches': None, 'area_quick': None, 'reason': ''}
        if not address:
            return where
        ready = self.env['sa.delivery.shop'].sudo().search(
            [('qe_quick', '=', True)]).filtered(lambda s: s._qe_ready())
        lat, lng = address.partner_latitude, address.partner_longitude
        if ready and (lat or lng):
            where['branches'] = ready._qe_in_reach(lat, lng)
            if not where['branches']:
                where['reason'] = 'far'
            return where
        area = self.env['sa.qe.service.area']._qe_match(address.zip)
        if area:
            where['area_quick'] = bool(area.quick)
            if not area.quick:
                where['reason'] = 'area'
        return where

    @api.model
    def _mart369_mode_of(self, product, qty=1, where=None, variant=None):
        if not qe_on(self.env):
            return super()._mart369_mode_of(product, qty, where=where, variant=variant)
        none = self.env['sa.delivery.shop']
        if self._mart369_express_only(product):
            return EXPRESS, none
        where = where or {}
        if where.get('branches') is not None:
            item = variant or product.product_variant_id
            for shop, __ in where['branches']:
                if shop._qe_has_stock(item, qty):
                    return QUICK, shop
            return EXPRESS, none
        if where.get('area_quick') is not None:
            return (QUICK if where['area_quick'] else EXPRESS), none
        return QUICK, none

    @api.model
    def _mart369_order_mode(self, present):
        """His rule: an order is Quick only when every line is."""
        return QUICK if present.get(QUICK) and not present.get(EXPRESS) else EXPRESS

    @api.model
    def _mart369_fees(self, rules, present, sub, gross, slot_fee):
        """One fee per order, his formula (`_qe_refresh_amounts`): the order's
        rule fee while the goods are under its free-above, plus the slot's."""
        if not qe_on(self.env):
            return super()._mart369_fees(rules, present, sub, gross, slot_fee)
        fees = 0.0
        if present.get(QUICK) or present.get(EXPRESS):
            rule = rules.get(self._mart369_order_mode(present))
            if rule and gross < (rule.free_above or 0.0):
                fees += rule.fee or 0.0
        return fees + max(0.0, slot_fee or 0.0)

    @api.model
    def _mart369_blocked(self, rules, present, sub, gross):
        if not qe_on(self.env):
            return super()._mart369_blocked(rules, present, sub, gross)
        rule = rules.get(QUICK)
        return bool(self._mart369_order_mode(present) == QUICK and rule
                    and gross < (rule.min_order or 0.0))


class SaleOrderQe(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _mart369_mode_of_bill(self, bill):
        """His rule: Quick only when nothing in the basket is Express."""
        if not qe_on(self.env):
            return super()._mart369_mode_of_bill(bill)
        sub = bill.get('sub') or {}
        return QUICK if sub.get('quick') and not sub.get('all') else EXPRESS

    @api.model
    def _mart369_qe_slot(self, key):
        """His slot for a 'qe:<id>' key, or None for any other key."""
        key = (key or '').strip()
        if not (qe_on(self.env) and key.startswith(SLOT_PREFIX)):
            return None
        try:
            slot_id = int(key[len(SLOT_PREFIX):])
        except ValueError:
            return self.env['sa.qe.delivery.slot']
        return self.env['sa.qe.delivery.slot'].sudo().browse(slot_id).exists()

    @api.model
    def _mart369_slot_for(self, body):
        slot = self._mart369_qe_slot(body.get('slot_key'))
        if slot is None:
            return super()._mart369_slot_for(body)
        if not slot or not slot.active:
            return self.env['sa.qe.delivery.slot'], 0.0
        if not slot._qe_is_open():
            raise UserError(_('That delivery window has just filled up or closed. '
                              'Please pick another.'))
        return slot, slot.fee or 0.0

    @api.model
    def _mart369_is_qe_slot(self, slot):
        return bool(slot) and slot._name == 'sa.qe.delivery.slot'

    @api.model
    def _mart369_slot_key(self, slot):
        if self._mart369_is_qe_slot(slot):
            return '%s%d' % (SLOT_PREFIX, slot.id)
        return super()._mart369_slot_key(slot)

    @api.model
    def _mart369_slot_label(self, slot):
        if self._mart369_is_qe_slot(slot):
            return slot.name or ''
        return super()._mart369_slot_label(slot)

    @api.model
    def _mart369_slot_day(self, slot):
        if self._mart369_is_qe_slot(slot):
            return slot._qe_day()
        return super()._mart369_slot_day(slot)

    @api.model
    def _mart369_due_at(self, slot, mode):
        if self._mart369_is_qe_slot(slot):
            due = slot._qe_due(slot._qe_day())
            if due:
                return due
            slot = None
        return super()._mart369_due_at(slot, mode)

    def _mart369_fee_lines(self, bill):
        """The delivery fee is his line (`_mart369_after_item_lines`)."""
        if qe_on(self.env):
            return []
        return super()._mart369_fee_lines(bill)

    def _mart369_after_item_lines(self, bill):
        """The goods are on the order: his decision fields, his slot, and his
        single fee line - marked as the website's fee too, so the bill, the
        receipt and points-earning treat it as delivery, not as an item."""
        result = super()._mart369_after_item_lines(bill)
        if not qe_on(self.env):
            return result
        order = self.sudo()
        slot = order._mart369_qe_slot(order.mart369_slot_key)
        order.write({
            'qe_decided': True,
            'qe_mode': THEIRS.get(order.mart369_mode, 'express'),
            'qe_slot_id': slot.id if slot else False,
        })
        order._qe_apply_fee()
        order.order_line.filtered(lambda l: l.qe_kind == 'fee').write({'mart369_kind': 'fee'})
        return result


class ProductTemplateQe(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        """A product with its own delivery promise is Express on WhatsApp too."""
        res = super().write(vals)
        if ('mart_delivery_text' in vals and 'qe_delivery_text' in self._fields
                and not self.env.context.get('mart369_qe_text')):
            for product in self:
                if (product.qe_delivery_text or '') != (product.mart_delivery_text or ''):
                    product.with_context(mart369_qe_text=True).qe_delivery_text = \
                        product.mart_delivery_text or False
        return res
