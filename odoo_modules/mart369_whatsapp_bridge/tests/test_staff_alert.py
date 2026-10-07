"""A staff sign-in reaches every Owner on WhatsApp - and never blocks it."""

from unittest.mock import patch

from odoo.tests import tagged

from .common import Mart369BridgeCase

OWNER_PHONE = '+96890000077'
CHROME = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')


@tagged('post_install', '-at_install')
class TestStaffAlert(Mart369BridgeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].sudo()
        owner = cls.env.ref('mart369_roles.group_owner')
        internal = cls.env.ref('base.group_user')
        cls.owner = Users.create({
            'name': 'Alert Owner',
            'login': 'alert.owner@369mart.test',
            'group_ids': [(4, owner.id), (4, internal.id)],
        })
        cls.owner.partner_id.phone = OWNER_PHONE
        # An Owner with no mobile has nowhere to be told.
        cls.owner_no_phone = Users.create({
            'name': 'Alert Owner No Phone',
            'login': 'alert.owner.nophone@369mart.test',
            'group_ids': [(4, owner.id), (4, internal.id)],
        })
        cls.staff = Users.create({
            'name': 'Alert Staff',
            'login': 'alert.staff@369mart.test',
            'group_ids': [(4, internal.id)],
        })

    def _to_owner(self):
        """Only what reached this test's Owner: the database's own Owners
        (the admin) may have mobiles of their own."""
        digits = OWNER_PHONE.lstrip('+')
        return [body for phone, body in self.wa_sent if phone == digits]

    def test_owner_hears_who_when_where(self):
        self.staff._mart369_on_staff_sign_in('email and password', '203.0.113.9', CHROME)
        sent = self._to_owner()
        self.assertEqual(len(sent), 1)
        body = sent[0]
        self.assertIn('Alert Staff', body)
        self.assertIn('alert.staff@369mart.test', body)
        self.assertIn('email and password', body)
        self.assertIn('203.0.113.9', body)
        self.assertIn('Chrome on Windows', body)

    def test_unknown_address_and_device_still_tell(self):
        self.staff._mart369_on_staff_sign_in('mobile code and password')
        sent = self._to_owner()
        self.assertEqual(len(sent), 1)
        self.assertIn('unknown address', sent[0])

    def test_archived_owner_is_not_told(self):
        self.owner.active = False
        self.staff._mart369_on_staff_sign_in('email and password', '203.0.113.9', CHROME)
        self.assertFalse(self._to_owner())

    def test_owner_without_mobile_is_skipped(self):
        owners = self.env.ref('mart369_roles.group_owner').all_user_ids.filtered(
            lambda u: u.active and not u.share)
        with_mobile = owners.filtered(lambda u: u.partner_id.phone)
        self.assertIn(self.owner_no_phone, owners - with_mobile)
        self.staff._mart369_on_staff_sign_in('email and password', '203.0.113.9', CHROME)
        # One message per Owner with a mobile; the one without adds nothing.
        self.assertEqual(len(self.wa_sent), len(with_mobile))

    def test_no_session_sends_nothing(self):
        # Faked, not switched off: the running server shares those sessions.
        Notify = self.env.registry['mart369.whatsapp']
        with patch.object(Notify, '_mart369_session',
                          lambda self: self.env['whatsapp.session']):
            self.staff._mart369_on_staff_sign_in('email and password', '203.0.113.9', CHROME)
        self.assertFalse(self.wa_sent)

    def test_gateway_down_never_blocks_the_sign_in(self):
        Session = self.env.registry['whatsapp.session']

        def down(self, phone, message):
            raise ConnectionError('gateway offline')

        with patch.object(Session, 'send_message', down):
            # Returns normally: the staff member is let in regardless.
            self.staff._mart369_on_staff_sign_in('email and password', '203.0.113.9', CHROME)
        self.assertFalse(self._to_owner())
