"""The mobile rule follows whichever country Odoo has.

Nothing here hardcodes "+91, ten digits, starts 6-9" - that falls out of the
country, which is the whole point. Oman wants eight digits; the same code
enforces both.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestMart369Phone(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']

    def _country(self, code):
        return self.env['res.country'].search([('code', '=', code)], limit=1)

    def _use_country(self, code):
        """Point the company at a country, which is what the rule reads."""
        self.env.company.partner_id.country_id = self._country(code)

    # ------------------------------------------------------------- India

    def test_india_accepts_real_mobiles(self):
        self._use_country('IN')
        for number in ('7092090133', '9486020356', '6000000000', '8123456789'):
            ok, value = self.Partner._mart369_check_mobile(number)
            self.assertTrue(ok, '%s should be accepted: %s' % (number, value))
            self.assertEqual(value, '+91%s' % number, 'stored in E.164')

    def test_india_rejects_a_landline(self):
        """libphonenumber calls this *valid*, but it is a fixed line. Requiring
        the mobile type is the only thing that catches it."""
        self._use_country('IN')
        ok, why = self.Partner._mart369_check_mobile('1234567890')
        self.assertFalse(ok)
        self.assertIn('landline', why.lower())

    def test_india_rejects_wrong_prefix_and_length(self):
        self._use_country('IN')
        for number in ('5092090133', '912345678', '70920901334'):
            ok, _why = self.Partner._mart369_check_mobile(number)
            self.assertFalse(ok, '%s should be rejected' % number)

    # -------------------------------------------------------------- Oman

    def test_the_rule_moves_with_the_country(self):
        self._use_country('OM')
        ok, value = self.Partner._mart369_check_mobile('92123456')
        self.assertTrue(ok, value)
        self.assertEqual(value, '+96892123456', 'Oman mobiles are eight digits')

        ok, _why = self.Partner._mart369_check_mobile('7092090133')
        self.assertFalse(ok, 'an Indian number is not valid in Oman')

    # ------------------------------------------------------------ general

    def test_empty_is_allowed_only_when_optional(self):
        self._use_country('IN')
        self.assertEqual(self.Partner._mart369_check_mobile('', required=False), (True, ''))
        ok, _why = self.Partner._mart369_check_mobile('', required=True)
        self.assertFalse(ok)

    def test_hint_tells_the_form_what_to_show(self):
        self._use_country('IN')
        hint = self.Partner._mart369_phone_hint()
        self.assertEqual(hint['dial'], '+91')
        self.assertEqual(hint['length'], 10)
        self.assertTrue(hint['example'])

        self._use_country('OM')
        self.assertEqual(self.Partner._mart369_phone_hint()['dial'], '+968')
        self.assertEqual(self.Partner._mart369_phone_hint()['length'], 8)

    def test_password_hash_is_readable_only_as_the_stored_fingerprint(self):
        user = self.env['res.users'].create({
            'name': 'Hash Reader', 'login': 'hash.reader@example.com', 'password': 'secret123',
        })
        user.invalidate_recordset(['mart369_password_hash'])
        self.assertTrue(user.mart369_password_hash.startswith('$'),
                        'the column holds a hash, not a password')
        self.assertNotIn('secret123', user.mart369_password_hash)
