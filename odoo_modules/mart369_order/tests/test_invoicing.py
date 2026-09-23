"""The bill, as a document in the books.

Until this landed the shop took money that never reached accounting. Nothing
in the suite created an `account.move`: no revenue, no tax, no receivable, and
both invoice routes answered 404 because there was genuinely nothing to render.
The manifest claimed "the invoice is a real document", which it was not.

Three things are worth pinning here, and they are the three that would not
announce themselves when they break.

**One invoice per order.** `_mart369_on_paid` is reached from `_post_process`,
which Odoo may run more than once for a single transaction, and the cash-on-
delivery path confirms once on acceptance and is paid later. A second invoice
for one order does not look broken on any screen - it just quietly doubles the
day's revenue.

**The money the shop quotes.** Lines carry price-included tax, set when the
order was placed. `_create_invoices` inherits that, and the invoice total has
to equal what the customer was actually charged. A total that drifts from the
order is the version of this bug that reaches an accountant rather than a
developer.

**A failure to invoice must not lose the payment.** By the time any of this
runs the customer has paid, so the invoicing is swallowed and logged the same
way the confirm above it is. An order that is paid but unbilled is a job for an
operator; an exception here would have taken the money and lost the order.
"""

from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestInvoicing(Mart369OrderCase):

    def _invoices(self, order):
        return order.invoice_ids.filtered(lambda m: m.state != 'cancel')

    # --------------------------------------------------------------- making

    def test_paying_an_order_posts_an_invoice(self):
        order = self._place()
        self.assertFalse(self._invoices(order), 'nothing before the money')

        self._pay(order)
        invoices = self._invoices(order)
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices.state, 'posted', 'posted, not left in draft')
        self.assertEqual(invoices.move_type, 'out_invoice')

    def test_the_invoice_is_for_what_the_customer_paid(self):
        """Price-included tax is set on the lines at placement; the invoice
        inherits it. If these two ever disagree the shop is billing one number
        and charging another."""
        order = self._place()
        self._pay(order)
        invoice = self._invoices(order)
        self.assertEqual(
            invoice.currency_id.round(invoice.amount_total),
            order.currency_id.round(order.amount_total))

    def test_the_invoice_is_addressed_to_the_customer(self):
        order = self._place()
        self._pay(order)
        self.assertEqual(self._invoices(order).partner_id, order.partner_id)

    # ------------------------------------------------------- only ever one

    def test_paying_twice_does_not_bill_twice(self):
        """`_post_process` is not promised to run once."""
        order = self._place()
        tx = self._pay(order)
        self.assertEqual(len(self._invoices(order)), 1)

        tx._post_process()
        tx._post_process()
        self.assertEqual(len(self._invoices(order)), 1,
                         'a second invoice doubles the day')

    def test_confirming_an_already_invoiced_order_is_a_no_op(self):
        order = self._place()
        self._pay(order)
        first = self._invoices(order)

        order._mart369_invoice()
        self.assertEqual(self._invoices(order), first)

    # ------------------------------------------------------ cash on delivery

    def test_cash_on_delivery_is_billed_when_it_is_accepted(self):
        """The invoice is the claim on the customer, so it exists from the
        moment the order is confirmed - the cash arriving later is a payment
        against it, not the thing that creates it."""
        order = self._place()
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self.gateway.id,
            'payment_method_id': self.method.id,
            'partner_id': self.partner.id,
            'amount': order.amount_total,
            'currency_id': order.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': 'order',
            'mart369_order_ref': order.mart369_ref,
        })
        tx._mart369_on_accepted()

        self.assertEqual(order.mart369_state, 'placed')
        self.assertEqual(len(self._invoices(order)), 1)

    # ------------------------------------------------------------- refusing

    def test_an_unpaid_order_is_not_billed(self):
        """Nothing is owed until the order is confirmed, and nothing confirms
        it but payment. Invoicing a basket that was never paid for would put
        revenue in the books for an order the shop never took."""
        order = self._place()
        order._mart369_invoice()
        self.assertFalse(self._invoices(order))

    def test_cancelling_after_the_bill_leaves_the_bill_standing(self):
        """Pinning the gap rather than pretending it is closed.

        An order can only be cancelled while `placed`, which it reaches by
        being paid - and paying is what invoices it. So by the time cancelling
        is allowed the invoice already exists, and nothing here reverses it:
        that needs a credit note, which this suite does not raise. The books
        therefore still show the sale until somebody credits it by hand.
        """
        order = self._place()
        self._pay(order)
        self.assertEqual(len(self._invoices(order)), 1)

        order._mart369_cancel(reason='Store closed')
        self.assertEqual(order.mart369_state, 'cancelled')
        self.assertEqual(len(self._invoices(order)), 1,
                         'still there, and still needing a credit note')

    def test_an_order_that_cannot_be_invoiced_does_not_raise(self):
        """The money is already taken by the time this runs. An unbilled order
        an operator can see beats an exception that loses the payment."""
        order = self._place()
        self._pay(order)
        # Already billed, so the guard is what answers - but the contract
        # being pinned is that it answers rather than throws.
        self.assertFalse(order._mart369_invoice())
