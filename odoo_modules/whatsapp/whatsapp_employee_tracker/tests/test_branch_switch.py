"""The top-right branch switch (26 Nov 2026): only the switched-on branches' people."""
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestBranchSwitch(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env['wa.employee.session'].search([]).write({'active': False})
        self.ruwi = self.env['res.company'].create({'name': 'Zz Ruwi'})
        self.sohar = self.env['res.company'].create({'name': 'Zz Sohar'})
        self.cards = {}
        for i, (name, co) in enumerate([('Ra', self.ruwi), ('Rb', self.ruwi), ('Sa', self.sohar), ('Sb', self.sohar)]):
            phone = '96890000000%d' % i
            number = self.env['whatsapp.session'].sudo().create({
                'name': name, 'gateway_api_key': 'test ' + phone, 'authorized_number': phone,
                'instance_name': 'co-' + phone, 'status': 'connected', 'company_id': co.id})
            employee = self.env['hr.employee'].create({'name': 'Zz ' + name, 'company_id': co.id})
            self.cards[name] = self.env['wa.employee.session'].create({
                'employee_id': employee.id, 'session_id': number.id, 'auto_reply_company_id': self.env.company.id})
        self.boss = new_test_user(self.env, login='zz_branch_boss', company_id=self.ruwi.id,
                                  company_ids=[(6, 0, (self.ruwi + self.sohar).ids)],
                                  groups='base.group_user,whatsapp_employee_tracker.group_wa_tracker_manager')

    def _seen(self, *companies):
        env = self.env(user=self.boss, context={'allowed_company_ids': [c.id for c in companies]})
        names = {c.id: 'Zz ' + n for n, c in self.cards.items()}
        return {names[i] for i in env['wa.employee.session'].search([]).ids}

    def test_switch_shows_the_branch(self):
        self.assertEqual(self.cards['Ra'].company_id, self.ruwi)
        self.assertEqual(self._seen(self.ruwi), {'Zz Ra', 'Zz Rb'})
        self.assertEqual(self._seen(self.sohar), {'Zz Sa', 'Zz Sb'})
        self.assertEqual(self._seen(self.ruwi, self.sohar), {'Zz Ra', 'Zz Rb', 'Zz Sa', 'Zz Sb'})

    def test_the_number_decides(self):
        """The Company on the WhatsApp number, not the Order Company; a change moves at once."""
        self.cards['Ra'].session_id.sudo().company_id = self.sohar
        self.assertEqual(self._seen(self.sohar), {'Zz Ra', 'Zz Sa', 'Zz Sb'})
        self.assertEqual(self._seen(self.ruwi), {'Zz Rb'})
        self.assertEqual(self.cards['Ra'].auto_reply_company_id, self.env.company, 'orders unchanged')
