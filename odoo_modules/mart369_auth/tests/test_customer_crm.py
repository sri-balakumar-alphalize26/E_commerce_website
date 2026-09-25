"""Tags and staff notes on a customer (models/customer_crm.py)."""

import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, new_test_user


@tagged('post_install', '-at_install')
class TestCustomerCrm(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal = cls.env.ref('base.group_portal')
        cls.ravi = cls.env['res.users'].create({
            'name': 'Zz Crm Ravi', 'login': 'zz_crm_ravi@example.com',
            'password': 'zz_crm_ravi@example.com',
            'group_ids': [(6, 0, [portal.id])],
        })
        cls.suresh = cls.env['res.users'].create({
            'name': 'Zz Crm Suresh', 'login': 'zz_crm_suresh@example.com',
            'group_ids': [(6, 0, [portal.id])],
        })
        cls.staff = new_test_user(
            cls.env, login='zz_crm_staff', password='zz_crm_staff',
            groups='base.group_user,website.group_website_designer')
        cls.Users = cls.env['res.users']

    # ---------------------------------------------------------------- tags

    def test_tags_are_made_by_name_and_replaced(self):
        tags = self.Users.mart369_admin_set_tags(self.ravi.id, ['Zz VIP', 'zz cash only'])
        self.assertEqual(sorted(t['name'] for t in tags), ['Zz VIP', 'zz cash only'])
        # The same name, any case, is the same tag - not a second one.
        again = self.Users.mart369_admin_set_tags(self.ravi.id, ['zz vip'])
        self.assertEqual([t['name'] for t in again], ['Zz VIP'])
        self.assertEqual(self.env['res.partner.category'].search_count([('name', '=ilike', 'zz vip')]), 1)

    def test_rows_carry_tags_and_the_list_filters_by_one(self):
        vip = self.Users.mart369_admin_set_tags(self.ravi.id, ['Zz VIP'])[0]
        page = self.Users.mart369_admin_list(q='Zz Crm', tag=vip['id'])
        names = [r['name'] for r in page['rows']]
        self.assertEqual(names, ['Zz Crm Ravi'])
        self.assertEqual(page['rows'][0]['tags'][0]['name'], 'Zz VIP')
        self.assertIn('Zz VIP', [t['name'] for t in page['tags']])
        everyone = self.Users.mart369_admin_list(q='Zz Crm')
        self.assertEqual(len(everyone['rows']), 2)

    # --------------------------------------------------------------- notes

    def test_a_note_is_signed_and_listed_newest_first(self):
        Users = self.Users.with_user(self.staff)
        Users.mart369_admin_add_note(self.ravi.id, 'Gate locked, ring the watchman')
        notes = Users.mart369_admin_add_note(self.ravi.id, 'Wants delivery after 6 pm')
        self.assertEqual([n['text'] for n in notes],
                         ['Wants delivery after 6 pm', 'Gate locked, ring the watchman'])
        self.assertEqual(notes[0]['author'], self.staff.name)
        self.assertTrue(notes[0]['mine'])
        # The detail reads wallets too, which a bare test user cannot; read it as admin.
        detail = self.Users.mart369_admin_detail(self.ravi.id)
        self.assertEqual(len(detail['notes']), 2)
        # Another customer's drawer does not show them.
        self.assertEqual(self.Users.mart369_admin_detail(self.suresh.id)['notes'], [])

    def test_an_empty_note_is_refused(self):
        with self.assertRaises(UserError):
            self.Users.with_user(self.staff).mart369_admin_add_note(self.ravi.id, '   ')

    def test_only_the_author_or_an_admin_removes_a_note(self):
        other = new_test_user(self.env, login='zz_crm_staff2',
                              groups='base.group_user,website.group_website_designer')
        notes = self.Users.with_user(self.staff).mart369_admin_add_note(self.ravi.id, 'Mine')
        with self.assertRaises(AccessError):
            self.Users.with_user(other).mart369_admin_delete_note(self.ravi.id, notes[0]['id'])
        left = self.Users.with_user(self.staff).mart369_admin_delete_note(self.ravi.id, notes[0]['id'])
        self.assertEqual(left, [])

    def test_the_detail_has_a_whatsapp_number(self):
        self.ravi.partner_id.phone = '+968 9271 0769'
        detail = self.Users.mart369_admin_detail(self.ravi.id)
        self.assertTrue(detail['waPhone'].isdigit())

    # ---------------------------------------------------------------- lock

    def test_a_shopper_is_refused(self):
        with self.assertRaises(AccessError):
            self.Users.with_user(self.suresh).mart369_admin_add_note(self.ravi.id, 'sneaky')
        self.authenticate('zz_crm_ravi@example.com', 'zz_crm_ravi@example.com')
        response = self.url_open(
            '/369mart/admin/customers/%s/notes' % self.ravi.id,
            data=json.dumps({'text': 'sneaky'}),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 403)

    def test_staff_routes_add_a_note_and_tags(self):
        self.authenticate('zz_crm_staff', 'zz_crm_staff')
        headers = {'Content-Type': 'application/json'}
        r = self.url_open('/369mart/admin/customers/%s/notes' % self.ravi.id,
                          data=json.dumps({'text': 'Over the route'}), headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['notes'][0]['text'], 'Over the route')
        r = self.url_open('/369mart/admin/customers/%s/tags' % self.ravi.id,
                          data=json.dumps({'tags': ['Zz Route Tag']}), headers=headers,
                          method='PATCH')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['tags'][0]['name'], 'Zz Route Tag')

    def test_the_console_route_filters_by_tag(self):
        """The console sends `tag` to the list route, which the parent route
        does not take - it travels on the context, and must arrive."""
        vip = self.Users.mart369_admin_set_tags(self.ravi.id, ['Zz Route VIP'])[0]
        self.authenticate('admin', 'admin')
        r = self.url_open('/369mart/admin/customers?q=Zz%%20Crm&tag=%s' % vip['id'])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([row['name'] for row in r.json()['rows']], ['Zz Crm Ravi'])

    def test_only_the_author_edits_a_note_and_it_keeps_its_signature(self):
        other = new_test_user(self.env, login='zz_crm_staff3',
                              groups='base.group_user,website.group_website_designer')
        notes = self.Users.with_user(self.staff).mart369_admin_add_note(self.ravi.id, 'Frist draft')
        with self.assertRaises(AccessError):
            self.Users.with_user(other).mart369_admin_edit_note(self.ravi.id, notes[0]['id'], 'Mine now')
        with self.assertRaises(UserError):
            self.Users.with_user(self.staff).mart369_admin_edit_note(self.ravi.id, notes[0]['id'], '  ')
        edited = self.Users.with_user(self.staff).mart369_admin_edit_note(
            self.ravi.id, notes[0]['id'], 'First draft')
        self.assertEqual(edited[0]['text'], 'First draft')
        self.assertEqual(edited[0]['author'], self.staff.name)
        self.assertEqual(edited[0]['at'], notes[0]['at'])
