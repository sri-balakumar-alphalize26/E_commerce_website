# -*- coding: utf-8 -*-
"""Sales groups and enquiries follow the branch switch (top right).

Ruwi and Sohar each have two customer groups with one enquiry each. Ticking
one branch shows only its groups and enquiries; a group with no Company is
shared and shows everywhere. Only an administrator can move a group to
another branch. Background work (an incoming group message) still sees every
branch. Nothing is sent."""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBranchSwitchGroups(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ruwi = env['res.company'].create({'name': 'Zz Ruwi'})
        cls.sohar = env['res.company'].create({'name': 'Zz Sohar'})
        cls.session = env['whatsapp.session'].create({
            'name': 'SA branch test', 'gateway_api_key': 'x',
            'instance_name': 'sa-branch-test'})
        Group = env['sa.sales.group']
        Request = env['sa.group.request']
        cls.groups = {cls.ruwi: Group, cls.sohar: Group}
        cls.requests = {cls.ruwi: Request, cls.sohar: Request}
        n = 0
        for company in (cls.ruwi, cls.sohar):
            for _i in range(2):
                n += 1
                group = Group.create({
                    'name': 'Zz %s %s' % (company.name, n),
                    'group_jid': '1203630000000099%02d@g.us' % n,
                    'session_id': cls.session.id, 'group_type': 'customer',
                    'company_id': company.id})
                cls.groups[company] |= group
                cls.requests[company] |= Request.create({
                    'group_id': group.id, 'requester_phone': '9198000999%02d' % n,
                    'raw_text': 'zz part %s' % n, 'state': 'new'})
        cls.shared = Group.create({
            'name': 'Zz Shared Vendors', 'group_jid': '120363000000009999@g.us',
            'session_id': cls.session.id, 'group_type': 'vendor',
            'company_id': False})
        both = [(6, 0, (cls.ruwi | cls.sohar).ids)]
        cls.manager = env['res.users'].create({
            'name': 'Zz Branch Manager', 'login': 'zz_sa_branch_manager',
            'company_id': cls.ruwi.id, 'company_ids': both,
            'group_ids': [(4, env.ref('sales_automation.group_sa_manager').id)]})
        cls.admin = env['res.users'].create({
            'name': 'Zz Branch Admin', 'login': 'zz_sa_branch_admin',
            'company_id': cls.ruwi.id, 'company_ids': both,
            'group_ids': [(4, env.ref('base.group_system').id)]})
        cls.mine = cls.groups[cls.ruwi] | cls.groups[cls.sohar] | cls.shared

    def _seen(self, *companies, user=None):
        env = self.env(user=user or self.manager,
                       context=dict(self.env.context,
                                    allowed_company_ids=[c.id for c in companies]))
        groups = env['sa.sales.group'].search([('id', 'in', self.mine.ids)])
        requests = env['sa.group.request'].search([
            ('group_id', 'in', self.mine.ids)])
        return set(groups.ids), set(requests.ids)

    def test_ruwi_only(self):
        groups, requests = self._seen(self.ruwi)
        self.assertEqual(groups, set((self.groups[self.ruwi] | self.shared).ids))
        self.assertEqual(requests, set(self.requests[self.ruwi].ids))

    def test_sohar_only(self):
        groups, requests = self._seen(self.sohar)
        self.assertEqual(groups, set((self.groups[self.sohar] | self.shared).ids))
        self.assertEqual(requests, set(self.requests[self.sohar].ids))

    def test_both(self):
        groups, requests = self._seen(self.ruwi, self.sohar)
        self.assertEqual(groups, set(self.mine.ids))
        self.assertEqual(requests,
                         set((self.requests[self.ruwi] | self.requests[self.sohar]).ids))

    def test_shared_group_shows_everywhere(self):
        for companies in ((self.ruwi,), (self.sohar,), (self.ruwi, self.sohar)):
            self.assertIn(self.shared.id, self._seen(*companies)[0])

    def test_admin_moves_a_group(self):
        group = self.groups[self.ruwi][:1]
        request = self.requests[self.ruwi].filtered(lambda r: r.group_id == group)
        group.with_user(self.admin).with_context(
            allowed_company_ids=[self.ruwi.id, self.sohar.id]).write(
            {'company_id': self.sohar.id})
        groups, requests = self._seen(self.sohar)
        self.assertIn(group.id, groups)
        self.assertIn(request.id, requests)
        groups, requests = self._seen(self.ruwi)
        self.assertNotIn(group.id, groups)
        self.assertNotIn(request.id, requests)

    def test_manager_cannot_move_a_group(self):
        group = self.groups[self.ruwi][:1].with_user(self.manager).with_context(
            allowed_company_ids=[self.ruwi.id, self.sohar.id])
        with self.assertRaises(UserError):
            group.write({'company_id': self.sohar.id})
        self.assertFalse(group.sa_can_move_branch)
        self.assertTrue(group.with_user(self.admin).sa_can_move_branch)

    def test_incoming_message_for_another_branch(self):
        """A message in a Sohar group still reaches it with only Ruwi ticked."""
        group = self.groups[self.sohar][:1]
        group.write({'group_type': 'vendor', 'enabled': True})
        message = self.env['whatsapp.message'].sudo().create({
            'session_id': self.session.id, 'phone': group.group_jid,
            'message': 'zz 25 OMR', 'direction': 'incoming', 'status': 'received',
            'wa_message_id': 'INBRANCH1', 'group_jid': group.group_jid,
            'participant_phone': '919800099999'})
        seen = []
        with patch.object(self.env.registry['sa.vendor.quote'], '_capture',
                          lambda self, msg, grp: seen.append(grp.id) or True):
            self.env['sa.group.request'].with_user(self.manager).with_context(
                allowed_company_ids=[self.ruwi.id])._on_group_message(message)
        self.assertEqual(seen, [group.id])
