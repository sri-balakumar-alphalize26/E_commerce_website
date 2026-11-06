"""Cash on delivery, and the limit the browser cannot argue with.

The app checks COD_LIMIT = 5000 in the browser (Checkout.jsx:576) against `payable`,
the amount left after the wallet is applied. Both halves of that are client-side: a
caller can claim any wallet figure it likes and drag the payable amount under the
limit.

Here the limit is the cash provider's own `maximum_amount`, which Odoo applies when
it decides which providers a basket may use, and the amount a cash payment carries is
the cash actually to be collected.
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMart369CodLimit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Cash Customer'})
        cls.cod = cls.env.ref('delivery.payment_provider_cod')
        cls.wallet_provider = cls.env.ref('mart369_payment.payment_provider_wallet')
        cls.currency = cls.env.company.currency_id
        cls.cod.write({'state': 'test'})

        # delivery refuses cash unless the order's carrier allows it, and it needs
        # the order to find out - so a cash test needs a carrier and an order.
        product = cls.env['product.product'].create({
            'name': '369 Delivery', 'type': 'service', 'list_price': 30,
        })
        cls.carrier = cls.env['delivery.carrier'].create({
            'name': '369 Quick',
            'delivery_type': 'fixed',
            'product_id': product.id,
            'allow_cash_on_delivery': True,
        })
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'carrier_id': cls.carrier.id,
        })

    def _cod_for(self, amount):
        return self.env['payment.provider']._mart369_provider_for(
            'cod', self.partner, amount, self.currency, order=self.order)

    # ------------------------------------------------------------- the limit

    def test_the_cod_limit_is_configuration_and_not_a_constant(self):
        self.assertEqual(self.cod.maximum_amount, 5000,
                         "COD_LIMIT lives on the provider, where an operator can change it")

    def test_cash_on_delivery_is_offered_below_the_limit(self):
        self.assertTrue(self._cod_for(4999), 'a basket under the limit may pay cash')

    def test_cash_on_delivery_is_refused_above_the_limit(self):
        self.assertFalse(self._cod_for(5001),
                         'Odoo itself refuses a provider above its maximum')

    def test_raising_the_limit_is_configuration_not_code(self):
        self.cod.write({'maximum_amount': 9000})
        self.assertTrue(self._cod_for(8000),
                        'the new limit takes effect with no code change')

    def test_the_limit_is_measured_on_the_cash_to_be_collected(self):
        """A 6,000 basket with 2,000 of wallet leaves 4,000 of cash, which is allowed.

        The number that matters is what the rider collects, not what the basket came
        to - the same rule the app intends and cannot enforce, because the browser
        decides both halves of it.
        """
        self.assertFalse(self._cod_for(6000), 'the whole basket is over the limit')
        self.assertTrue(self._cod_for(4000), 'but the cash actually due is not')

    def test_a_disabled_provider_is_never_offered(self):
        self.cod.write({'state': 'disabled'})
        self.assertFalse(self._cod_for(100),
                         'a provider an operator turned off cannot take money')

    def test_cash_is_refused_when_the_carrier_does_not_allow_it(self):
        self.carrier.write({'allow_cash_on_delivery': False})
        self.assertFalse(self._cod_for(100),
                         "delivery's own rule still applies through our lookup")

    # ------------------------------------------------------- the method mapping

    def test_the_five_app_methods_each_map_to_a_payment_method(self):
        # active_test=False: Odoo ships its generic methods inactive and turns them
        # on when a provider that supports them is enabled, so an ordinary search
        # would not see UPI at all.
        Method = self.env['payment.method'].sudo().with_context(active_test=False)
        for code in ('upi', 'card', 'netbanking', 'cod', 'wallet'):
            self.assertTrue(
                Method.search_count([('mart369_app_code', '=', code)]),
                "the app's %s key has nowhere to go in Odoo" % code)

    def test_cash_and_wallet_can_never_be_tokenised(self):
        for xmlid in ('delivery.payment_method_cash_on_delivery',
                      'mart369_payment.payment_method_wallet'):
            method = self.env.ref(xmlid)
            self.assertFalse(method.support_tokenization,
                             'there is nothing to save for %s' % method.name)

    def test_an_unknown_app_method_resolves_to_nothing(self):
        self.assertFalse(
            self.env['payment.provider']._mart369_provider_for(
                'crypto', self.partner, 100, self.currency, order=self.order),
            'an invented method must not fall back to some provider')

    def test_the_wallet_provider_ships_disabled(self):
        provider = self.env.ref('mart369_payment.payment_provider_wallet')
        self.assertTrue(provider.mart369_is_wallet, 'and it knows what it is')
        self.assertFalse(provider.mart369_is_cod)
