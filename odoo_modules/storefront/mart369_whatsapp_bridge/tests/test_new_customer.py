"""➕ New customer: added by staff with a mobile number.

The website then signs that number in with a code (no sign-up, no password),
and the WhatsApp bot knows the customer: name not asked again, the saved
address used - the bot's own flow unchanged.
"""

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import Mart369BridgeCase

MOBILE = '9876512345'
E164 = '+919876512345'


@tagged('post_install', '-at_install')
class TestNewCustomer(Mart369BridgeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.india = cls.env.ref('base.in')
        cls.state = cls.env['res.country.state'].search([('country_id', '=', cls.india.id)], limit=1)

    def _wizard(self, **vals):
        base = {'name': 'Asha Menon', 'country_id': self.india.id, 'mobile': MOBILE,
                'label': 'Home', 'line': 'Flat 12, Park View Apartments',
                'area': 'Main Street, City Centre', 'landmark': 'Next to the pharmacy',
                'town': 'Kochi', 'zip': '682001', 'state_id': self.state.id}
        base.update(vals)
        return self.env['mart369.new.customer'].create(base)

    def _create(self, **vals):
        action = self._wizard(**vals).action_create()
        return self.env['res.users'].browse(action['res_id'])

    # ------------------------------------------------------------ the account
    def test_a_login_on_the_number_with_the_number_trusted(self):
        user = self._create()
        partner = user.partner_id
        self.assertTrue(user.share)
        self.assertEqual(user.login, E164)
        self.assertEqual(partner.phone, E164)
        self.assertTrue(partner.mart369_phone_verified)
        self.assertTrue(partner.sa_name_confirmed_on)
        book = partner._mart369_book()
        self.assertEqual(len(book), 1)
        self.assertEqual(book.zip, '682001')
        self.assertEqual(book.mart369_landmark, 'Next to the pharmacy')
        self.assertTrue(book.mart369_default)

    def test_the_website_signs_the_number_in_without_a_password(self):
        user = self._create()
        partner, owner = self.env['res.partner']._mart369_phone_owner(E164)
        self.assertEqual(owner, user)
        # phone_api.py asks a password only of a login whose number is unproven
        self.assertFalse(bool(owner and not partner.mart369_phone_verified))

    # ----------------------------------------------------------- the WhatsApp bot
    def test_the_bot_knows_the_customer(self):
        user = self._create()
        partner = user.partner_id
        self.assertEqual(self.env['res.partner']._sa_phone_owner('919876512345')[:1], partner)
        req = self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id, 'requester_phone': '919876512345', 'raw_text': 'x'})
        self.assertEqual(req._sa_book_customer(), partner)
        self.assertEqual(req._sa_known_name(), 'Asha Menon')
        self.assertEqual(req._sa_profile_first_step(partner), 'confirm',
                         'name and address known: straight to the check')

    def test_without_an_address_the_bot_asks_only_the_address(self):
        user = self._create(line=False, area=False, landmark=False, town=False, zip=False, state_id=False)
        req = self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id, 'requester_phone': '919876512345', 'raw_text': 'x'})
        self.assertEqual(req._sa_profile_first_step(user.partner_id), 'address')

    # ------------------------------------------------------------- one person
    def test_a_number_that_already_signs_in_is_refused(self):
        self._create()
        with self.assertRaises(UserError):
            self._create(name='Someone Else')

    def test_the_whatsapp_contact_of_the_number_is_reused(self):
        chat = self.env['res.partner'].sudo().create({
            'name': 'WhatsApp Customer (+919876512345)', 'phone': E164, 'customer_rank': 1})
        user = self._create()
        self.assertEqual(user.partner_id, chat, 'the same contact, its orders kept')
        self.assertEqual(chat.name, 'Asha Menon', 'the placeholder name is replaced')

    # ------------------------------------------------------------- bad input
    def test_a_bad_postcode_makes_nothing(self):
        with self.assertRaises(UserError):
            self._create(zip='12')
        self.assertFalse(self.env['res.users'].with_context(active_test=False).search(
            [('login', '=', E164)]))

    def test_a_bad_mobile_makes_nothing(self):
        with self.assertRaises(UserError):
            self._create(mobile='12')

    # ------------------------------------------- the phone rule, every form's
    def test_the_rule_says_which_digits_a_mobile_starts_with(self):
        hint = self.env['res.partner']._mart369_phone_hint(region='IN')
        self.assertEqual((hint['dial'], hint['length'], hint['starts']), ('+91', 10, '6789'))
        self.assertEqual(self.env['res.partner']._mart369_phone_hint(region='OM')['starts'], '79')

    # ------------------------------------------------ the backend's own popup
    def test_the_popup_gets_the_form_and_adds_the_customer(self):
        Popup = self.env['mart369.new.customer']
        form = Popup.mart369_popup_form('IN')
        self.assertEqual(form['phone']['starts'], '6789')
        self.assertTrue(form['states'])
        r = Popup.mart369_popup_create({'name': 'Popup Person', 'mobile': MOBILE, 'country': 'IN'})
        self.assertTrue(r['ok'])
        self.assertTrue(r['view_id'])
        self.assertEqual(self.env['res.users'].browse(r['id']).login, E164)

    def test_the_popup_is_staff_only(self):
        shopper = self.env['res.users'].sudo().create({
            'name': 'Shopper', 'login': 'nc-shopper@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        with self.assertRaises(AccessError):
            self.env['mart369.new.customer'].with_user(shopper).mart369_popup_form('IN')

    # ------------------------------------------------- the admin console's door
    def _console(self, **body):
        base = {'name': 'Ravi Kumar', 'mobile': MOBILE, 'country': 'IN',
                'address': {'label': 'Work', 'line': 'Flat 3, Lake View', 'area': 'Main Street',
                            'landmark': 'Opposite the park', 'town': 'Kochi', 'pin': '682002',
                            'state_id': self.state.id}}
        base.update(body)
        return self.env['mart369.new.customer']._mart369_create_customer(base)

    def test_the_console_adds_the_same_customer(self):
        r = self._console()
        self.assertTrue(r['ok'])
        user = self.env['res.users'].browse(r['id'])
        self.assertEqual(user.login, E164)
        self.assertTrue(user.partner_id.mart369_phone_verified)
        self.assertEqual(user.partner_id._mart369_book().mart369_label, 'Work')

    def test_the_console_names_the_field_that_is_wrong(self):
        self.assertEqual(self._console(mobile='12')['field'], 'mobile')
        self.assertEqual(self._console(name='')['field'], 'name')
        bad = self._console(address={'line': 'x', 'area': 'y', 'town': 'Kochi', 'pin': '1',
                                     'state_id': self.state.id})
        self.assertFalse(bad['ok'])
        self.assertEqual(bad['field'], 'pin')
        no_landmark = self._console(address={'line': 'Flat 3', 'area': 'Main Street', 'town': 'Kochi',
                                             'pin': '682002', 'state_id': self.state.id})
        self.assertEqual(no_landmark['field'], 'landmark', 'staff save every line of an address')
        self.assertTrue(self._console(address=None)['ok'], 'the address is optional')
        self.assertEqual(self._console()['field'], 'mobile', 'the number is taken now')
