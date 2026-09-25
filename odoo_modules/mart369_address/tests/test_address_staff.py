"""Support staff and a customer's address book.

Staff see every address a customer keeps, add one, fix one, pick the default -
through the console's routes, the Odoo dialog and the Customers desk. They
never delete, and a shopper can reach none of it.
"""

import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}
LOOKUP = 'odoo.addons.mart369_address.models.address_rules.requests.get'


class _IndiaPost:
    def raise_for_status(self):
        pass

    def json(self):
        return [{'Status': 'Success', 'PostOffice': [
            {'Name': 'Begampur', 'District': 'Dindigul', 'State': 'Tamil Nadu'}]}]


@tagged('post_install', '-at_install')
class TestAddressStaff(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('auth_signup.invitation_scope', 'b2c')
        self.env.company.partner_id.country_id = self.env.ref('base.in')
        self.env['ir.config_parameter'].sudo().search([('key', '=like', 'mart369.pin.%')]).unlink()
        self.tn = self.env['res.country.state'].search([
            ('country_id.code', '=', 'IN'), ('name', '=', 'Tamil Nadu')], limit=1)
        self.Partner = self.env['res.partner']
        self.shopper = self._signup()
        self.customer = self.shopper.partner_id

    # ------------------------------------------------------------- plumbing

    def _req(self, method, path, payload=None):
        return self.opener.request(method, self.base_url() + path,
                                   data=json.dumps(payload) if payload is not None else None,
                                   headers=HEADERS)

    def _signup(self, email='ravi@example.com', phone='9486020356'):
        self._req('POST', '/369mart/auth/signup', {
            'name': 'Ravi Kumar', 'email': email, 'password': 'secret123', 'phone': phone})
        self._req('POST', '/369mart/auth/logout', {})
        return self.env['res.users'].search([('login', '=', email)])

    def _body(self, **over):
        body = {'label': 'Home', 'name': 'Ravi Kumar', 'phone': '9486020356',
                'line': '12, Lotus Apartments', 'area': 'Dindigul East', 'town': 'Dindigul',
                'pin': '624003', 'state_id': self.tn.id, 'country_id': 'IN'}
        body.update(over)
        return body

    # ---------------------------------------------------------------- fences

    def test_a_shopper_is_refused_every_staff_route(self):
        self.authenticate('ravi@example.com', 'secret123')
        uid = self.shopper.id
        for method, path, payload in (
            ('GET', '/369mart/admin/customers/%s/addresses' % uid, None),
            ('POST', '/369mart/admin/customers/%s/addresses' % uid, self._body()),
            ('PATCH', '/369mart/admin/addresses/1', {'line': 'x'}),
            ('POST', '/369mart/admin/addresses/1/default', {}),
        ):
            self.assertEqual(self._req(method, path, payload).status_code, 403, path)

    def test_staff_cannot_reach_a_staff_account_s_addresses(self):
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        response = self._req('GET', '/369mart/admin/customers/%s/addresses' % admin.id)
        self.assertEqual(response.status_code, 404)

    # ---------------------------------------------------------- the console

    def test_staff_see_add_fix_and_choose_the_default(self):
        self.authenticate('admin', 'admin')
        base = '/369mart/admin/customers/%s/addresses' % self.shopper.id

        home = self._req('POST', base, self._body())
        self.assertEqual(home.status_code, 201, home.text)
        work = self._req('POST', base, self._body(label='Work', line='3rd Floor, Tech Park',
                                                  area='Parrys Corner', town='Chennai', pin='600001'))
        self.assertEqual(work.status_code, 201, work.text)
        home_id, work_id = home.json()['address']['id'], work.json()['address']['id']

        book = self._req('GET', base).json()
        self.assertEqual([a['label'] for a in book['addresses']], ['Home', 'Work'])
        self.assertEqual(book['selected'], home_id, 'the first address is the default')
        self.assertEqual(book['removed'], 0)

        bad = self._req('PATCH', '/369mart/admin/addresses/%s' % work_id, {'phone': '12345'})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()['field'], 'phone', 'the same mobile check the app uses')

        fixed = self._req('PATCH', '/369mart/admin/addresses/%s' % work_id, {'landmark': 'Near the bus stand'})
        self.assertEqual(fixed.status_code, 200, fixed.text)
        self.assertEqual(fixed.json()['address']['landmark'], 'Near the bus stand')

        chosen = self._req('POST', '/369mart/admin/addresses/%s/default' % work_id, {})
        self.assertEqual(chosen.status_code, 200, chosen.text)
        self.assertEqual(self._req('GET', base).json()['selected'], work_id)

        notes = self.customer.message_ids.mapped('body')
        self.assertTrue(any('added by' in n for n in notes), 'staff changes land in the history')
        self.assertTrue(any('Default delivery address set to Work' in n for n in notes))

    # -------------------------------------------------------- the Odoo dialog

    def test_the_dialog_adds_for_the_customer(self):
        wizard = self.env['mart369.address.wizard'].with_context(
            default_customer_id=self.customer.id).create({
                'street': '12, Lotus Apartments', 'street2': 'Dindigul East',
                'city': 'Dindigul', 'zip': '624003', 'state_id': self.tn.id})
        self.assertEqual(wizard.name, 'Ravi Kumar', "a new address is the customer's own")
        self.assertEqual(wizard.country_id.code, 'IN')
        wizard.action_save()
        book = self.customer._mart369_book()
        self.assertEqual(len(book), 1)
        self.assertTrue(book.mart369_default)

    def test_the_dialog_only_offers_a_mobile_that_fits_the_country(self):
        Wizard = self.env['mart369.address.wizard'].with_context(default_customer_id=self.customer.id)
        opened = lambda: Wizard.new(Wizard.default_get(list(Wizard._fields)))  # noqa: E731
        self.customer.sudo().write({'country_id': False, 'phone': '+96891234567'})
        wizard = opened()
        self.assertEqual(wizard.country_id.code, 'IN')
        self.assertFalse(wizard.phone, 'an Omani mobile is not offered on an Indian address')

        self.customer.sudo().phone = '+919486020356'
        wizard = opened()
        self.assertEqual(wizard.phone, '+919486020356', "the customer's Indian mobile is")

        wizard.country_id = self.env.ref('base.om')
        wizard._onchange_country()
        self.assertFalse(wizard.phone, 'moving the address to Oman drops the +91 number')

    def test_the_dialog_refuses_what_the_app_refuses(self):
        address = self.customer.sudo()._mart369_add_address({
            'name': 'Ravi Kumar', 'street': '12, Lotus Apartments', 'street2': 'Dindigul East',
            'city': 'Dindigul', 'zip': '624003', 'phone': '+919486020356',
            'country_id': self.env.ref('base.in').id, 'state_id': self.tn.id})
        wizard = self.env['mart369.address.wizard'].with_context(default_address_id=address.id).create({})
        self.assertEqual(wizard.street, '12, Lotus Apartments', 'opens filled in')
        wizard.phone = '12345'
        with self.assertRaises(UserError):
            wizard.action_save()

    def test_the_dialog_fills_city_and_state_from_the_pincode(self):
        wizard = self.env['mart369.address.wizard'].with_context(
            default_customer_id=self.customer.id).new({'country_id': self.env.ref('base.in').id})
        with patch(LOOKUP, return_value=_IndiaPost()):
            wizard.zip = '624003'
            wizard._onchange_zip()
        self.assertEqual(wizard.city, 'Dindigul')
        self.assertEqual(wizard.state_id, self.tn)
        self.assertIn('Begampur', wizard.pin_found)

    # --------------------------------------------------------- the desks' data

    def test_the_customer_screens_read_the_address_book(self):
        for label, town in (('Home', 'Dindigul'), ('Work', 'Chennai')):
            self.customer.sudo()._mart369_add_address({
                'name': 'Ravi Kumar', 'mart369_label': label, 'street': '1 Road', 'street2': 'Area',
                'city': town, 'zip': '624003', 'phone': '+919486020356'})
        Users = self.env['res.users']
        row = self.shopper._mart369_admin_row()
        self.assertEqual(row['addressCount'], 2)
        self.assertEqual(row['area'], 'Dindigul', 'area is the default address town')
        detail = Users.mart369_admin_detail(self.shopper.id)
        self.assertEqual([a['label'] for a in detail['addresses']], ['Home', 'Work'])
        self.assertEqual(detail['removedAddresses'], 0)
        self.assertIn('Chennai', Users._mart369_admin_areas())
        found = Users.search(Users._mart369_admin_domain(area='Chennai'))
        self.assertIn(self.shopper, found, 'the Area filter finds a customer by any of their addresses')

        admin_row = self.customer._mart369_book()[:1]._mart369_admin_row()
        self.assertEqual(admin_row['customerUser'], self.shopper.id)
