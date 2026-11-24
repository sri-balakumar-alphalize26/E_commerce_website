# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import fields
from odoo.addons.sales_automation.tests.test_only_listed import ListedCase


class BuyCase(ListedCase):
    """Ravi pays 100 for one speaker; vendors A to E were asked."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.settings = env['sa.ai.settings'].sudo().get_settings()
        cls.settings.write({'late_min_saving_amount': 20.0, 'pay_link_no_stock': 'sign'})
        cls.own = env.company.currency_id
        cls.speaker = env['product.template'].create({
            'name': 'Zz Buy Speaker', 'type': 'consu', 'is_storable': True, 'list_price': 100.0,
            'taxes_id': [(5,)]}).product_variant_id
        cls.vendors = {k: env['res.partner'].create({'name': 'Zz Vendor %s' % k, 'phone': '+9715000040%02d' % n})
                       for n, k in enumerate('ABCDE')}
        cls.ravi = env['res.partner'].create({'name': 'Zz Ravi', 'phone': '+919800066611'})
        cls.warehouse = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
        cls.paid = True
        p = patch.object(env.registry['sale.order'], '_sa_buy_paid', lambda self: cls.paid)
        p.start()
        cls.addClassCleanup(p.stop)

    def setUp(self):
        super().setUp()
        type(self).paid = True

    def _stock(self, qty, product=None):
        self.env['stock.quant']._update_available_quantity(product or self.speaker, self.warehouse.lot_stock_id, qty)

    def _ask(self, qty=1, price=100.0, order=None, product=None, **vals):
        product = product or self.speaker
        return self.env['sa.group.request'].create(dict({
            'group_id': self.group.id, 'requester_phone': '919800066611', 'requester_name': 'Zz Ravi', 'raw_text': 'speaker',
            'product_id': product.product_tmpl_id.id, 'state': 'order_created', 'qty': qty, 'quoted_price': price,
            'agreed_price': price, 'currency_id': self.own.id,
            'sourcing_vendor_ids': [(6, 0, [v.id for v in self.vendors.values()])],
            'order_id': order.id if order else False, 'sa_paid_on': fields.Datetime.now()}, **vals))

    def _order(self, qty=1, price=100.0, product=None, confirm=True):
        order = self.env['sale.order'].create({
            'partner_id': self.ravi.id, 'require_signature': False, 'require_payment': False,
            'order_line': [(0, 0, {'product_id': (product or self.speaker).id, 'product_uom_qty': qty,
                                   'price_unit': price, 'tax_ids': [(6, 0, [])]})]})
        if confirm:
            order.action_confirm()
        return order

    def _price(self, req, vendor, price, **vals):
        partner = self.vendors[vendor]
        return self.env['sa.vendor.quote'].create(dict({
            'request_id': req.id, 'partner_id': partner.id, 'vendor_name': partner.name, 'vendor_phone': partner.phone,
            'price': price, 'currency_id': self.own.id}, **vals))

    def _ravi(self, qty=1):
        """Paid; A's 80 was the price he was quoted from, B said 85."""
        order = self._order(qty)
        req = self._ask(qty, order=order)
        a = self._price(req, 'A', 80.0, is_best=True)
        self._price(req, 'B', 85.0)
        req.best_quote_id = a
        return order, req, a
