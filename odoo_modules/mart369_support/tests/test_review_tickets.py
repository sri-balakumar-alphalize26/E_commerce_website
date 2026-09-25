"""A one- or two-star rating opens a support ticket (models/review_tickets.py)."""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReviewTickets(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Rating = self.env['rating.rating']
        self.product = self.env['product.template'].create({'name': 'Ticket Mouse', 'list_price': 10.0})
        self.partner = self.env['res.partner'].create({'name': 'Unhappy'})

    def test_a_one_star_review_opens_a_ticket_with_what_they_wrote(self):
        row = self.Rating._mart369_write_review(
            self.partner, self.product, {'stars': 1, 'title': 'Broke', 'text': 'Died in a day'})
        ticket = row.mart369_ticket_id
        self.assertTrue(ticket, 'a ticket is opened')
        self.assertEqual(ticket.partner_id, self.partner)
        self.assertIn('1-star', ticket.subject)
        self.assertIn('Died in a day', ' '.join(ticket.message_ids.mapped('body')))
        self.assertEqual(self.Rating.mart369_admin_list()['reviews'][0]['ticket'] if False else
                         row._mart369_admin_serialize()['ticket'], ticket.name)

    def test_editing_does_not_open_a_second_ticket(self):
        row = self.Rating._mart369_write_review(self.partner, self.product, {'stars': 2, 'text': 'meh'})
        first = row.mart369_ticket_id
        self.Rating._mart369_write_review(self.partner, self.product, {'stars': 1, 'text': 'worse'})
        self.assertEqual(row.mart369_ticket_id, first)

    def test_a_good_review_opens_nothing(self):
        row = self.Rating._mart369_write_review(self.partner, self.product, {'stars': 4, 'text': 'ok'})
        self.assertFalse(row.mart369_ticket_id)
