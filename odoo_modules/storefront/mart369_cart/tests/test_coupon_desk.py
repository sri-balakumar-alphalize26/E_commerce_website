"""The coupons desk's way in, which is not the console's.

The console writes over HTTP (`/369mart/admin/coupons`, covered by
test_admin_coupons.py). The Odoo desk writes over the ORM, through
`mart369_admin_save` and `mart369_admin_delete` on the model. Two doors into
the same cupboard, so the rules have to hold at both - and until this file
existed only one of them was ever opened by a test.

The one worth the most here is the savepoint. A refused write that is still in
the transaction gives the operator the worst of both answers: an error message
*and* the bad value saved. Worse, it poisons the cursor, so the next statement
comes back "current transaction is aborted" - which the operator meets as a
second, unrelated-looking failure while trying to correct the first. Get it
wrong, fix it, save is exactly what somebody does, so that sequence is tested
rather than a single refusal in isolation.
"""

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCouponDeskWrites(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Coupon = self.env['mart369.coupon'].with_context(active_test=False)
        self.coupon = self.Coupon.create({
            'code': 'DESKTEST',
            'title': 'Ten off',
            'kind': 'flat',
            'value': 10.0,
        })

    # --------------------------------------------------------------- saving

    def test_a_new_code_is_created_and_comes_back_upper_cased(self):
        row = self.Coupon.mart369_admin_save(False, {
            'code': 'deskmade', 'title': 'Made by the desk',
            'kind': 'flat', 'value': 15.0,
        })
        self.assertEqual(row['code'], 'DESKMADE')
        self.assertEqual(row['value'], 15.0)
        self.assertTrue(self.Coupon.search([('code', '=', 'DESKMADE')]))

    def test_the_row_it_returns_is_the_one_the_screen_draws(self):
        """The desk redraws from this, so it has to be the admin shape -
        camelCase keys and `live` included, not the model's own field names."""
        row = self.Coupon.mart369_admin_save(self.coupon.id, {'title': 'Renamed'})
        self.assertEqual(row['title'], 'Renamed')
        for key in ('id', 'code', 'maxOff', 'minSpend', 'limitTotal',
                    'usedCount', 'live'):
            self.assertIn(key, row)

    def test_switching_one_off_is_one_save(self):
        row = self.Coupon.mart369_admin_save(self.coupon.id, {'active': False})
        self.assertFalse(row['active'])
        # Off is never live, whatever its dates say.
        self.assertFalse(row['live'])

    def test_a_code_without_a_title_is_refused(self):
        with self.assertRaises(ValidationError):
            self.Coupon.mart369_admin_save(False, {
                'code': 'NOTITLE', 'kind': 'flat', 'value': 5.0})

    def test_a_window_that_ends_before_it_starts_is_refused(self):
        with self.assertRaises(ValidationError):
            self.Coupon.mart369_admin_save(self.coupon.id, {
                'starts_on': '2026-12-01', 'ends_on': '2026-01-01'})

    def test_a_duplicate_code_is_refused_with_a_sentence(self):
        with self.assertRaises(ValidationError) as caught:
            self.Coupon.mart369_admin_save(False, {
                'code': 'desktest', 'title': 'Clash', 'kind': 'flat', 'value': 5.0})
        # Names the code, because that is the one thing to change.
        self.assertIn('DESKTEST', str(caught.exception))

    def test_renaming_a_code_onto_another_one_is_refused(self):
        other = self.Coupon.create({
            'code': 'OTHER', 'title': 'Other', 'kind': 'flat', 'value': 1.0})
        with self.assertRaises(ValidationError):
            self.Coupon.mart369_admin_save(other.id, {'code': 'DESKTEST'})

    def test_a_coupon_that_is_not_there_is_refused(self):
        with self.assertRaises(ValidationError):
            self.Coupon.mart369_admin_save(999999, {'title': 'Ghost'})

    def test_the_desk_cannot_write_how_often_a_code_has_been_used(self):
        """`used_count` is the shop's tally of what customers did. A screen
        that could set it could hand a spent code back to everybody.

        It is dropped before the write rather than rejected by name, so asking
        for it *alone* leaves nothing to do and is refused as such. Either way
        the tally stands.
        """
        self.coupon.used_count = 4
        with self.assertRaises(ValidationError):
            self.Coupon.mart369_admin_save(self.coupon.id, {'used_count': 0})
        self.coupon.invalidate_recordset()
        self.assertEqual(self.coupon.used_count, 4)

    def test_it_is_dropped_rather_than_carried_along_with_a_real_edit(self):
        """The sharper version: smuggled in beside a field that *is* writable,
        the rest of the save must go through and the tally still not move."""
        self.coupon.used_count = 4
        row = self.Coupon.mart369_admin_save(
            self.coupon.id, {'title': 'Renamed', 'used_count': 0})
        self.assertEqual(row['title'], 'Renamed')
        self.assertEqual(row['usedCount'], 4)
        self.coupon.invalidate_recordset()
        self.assertEqual(self.coupon.used_count, 4)

    # --------------------------------------------- refused means undone

    def test_a_refused_percentage_is_not_saved_anyway(self):
        """The model refuses a percentage over 100. Without the savepoint the
        write is still in the transaction when the error is caught, so the
        operator is told no and the bad number is kept."""
        self.coupon.write({'kind': 'percent', 'value': 10.0})
        with self.assertRaises(ValidationError):
            self.Coupon.mart369_admin_save(self.coupon.id, {'value': 150.0})
        self.coupon.invalidate_recordset()
        self.assertEqual(self.coupon.value, 10.0)

    def test_a_refused_new_coupon_leaves_nothing_behind(self):
        before = self.Coupon.search_count([])
        with self.assertRaises(ValidationError):
            self.Coupon.mart369_admin_save(False, {
                'code': 'HALFMADE', 'title': 'Half made',
                'kind': 'percent', 'value': 500.0})
        self.assertEqual(self.Coupon.search_count([]), before)
        self.assertFalse(self.Coupon.search([('code', '=', 'HALFMADE')]))

    def test_the_transaction_still_works_after_a_refusal(self):
        """Get it wrong, fix it, save - what an operator actually does.

        A poisoned cursor fails the *second* statement, so a single-assertion
        test of the refusal would pass while the screen was still unusable.
        """
        self.coupon.write({'kind': 'percent', 'value': 10.0})
        with self.assertRaises(ValidationError):
            self.Coupon.mart369_admin_save(self.coupon.id, {'value': 150.0})

        row = self.Coupon.mart369_admin_save(self.coupon.id, {'value': 25.0})
        self.assertEqual(row['value'], 25.0)
        self.coupon.invalidate_recordset()
        self.assertEqual(self.coupon.value, 25.0)

    # ------------------------------------------------------------- deleting

    def test_an_unused_code_can_be_deleted(self):
        spare = self.Coupon.create({
            'code': 'SPARE', 'title': 'Spare', 'kind': 'flat', 'value': 1.0})
        self.assertTrue(self.Coupon.mart369_admin_delete(spare.id))
        self.assertFalse(spare.exists())

    def test_a_code_somebody_has_used_is_kept(self):
        """It belongs to the orders that used it now. The desk offers delete
        anyway and says this in the confirmation, rather than hiding a button
        somebody would go looking for."""
        self.coupon.used_count = 2
        with self.assertRaises(ValidationError) as caught:
            self.Coupon.mart369_admin_delete(self.coupon.id)
        self.assertIn('Switch it off instead', str(caught.exception))
        self.assertTrue(self.coupon.exists())

    def test_deleting_one_that_is_not_there_is_refused(self):
        with self.assertRaises(ValidationError):
            self.Coupon.mart369_admin_delete(999999)
