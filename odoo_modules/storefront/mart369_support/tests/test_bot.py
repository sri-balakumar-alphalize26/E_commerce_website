"""The bot.

Two things are load-bearing and easy to break without noticing:

* the reply object is exactly `{text, actions?, chips?, agent?}` - the panel
  rebuilds its message from those four and silently drops anything else;
* `agentReply` is a **bare string** - returning a dict puts "[object Object]"
  on the customer's screen.

The rest is about the bot no longer saying things that are not true.
"""

from odoo.tests import tagged

from odoo.addons.mart369_order.tests.common import Mart369OrderFixtures
from odoo.tests import TransactionCase

REPLY_FIELDS = {'text', 'actions', 'chips', 'agent'}


@tagged('post_install', '-at_install')
class TestMart369Bot(Mart369OrderFixtures, TransactionCase):

    def _ask(self, text):
        return self.env['mart369.bot']._mart369_reply(self.partner, text)

    # ------------------------------------------------------------ the shape

    def test_every_reply_fits_the_shape_the_panel_reads(self):
        """Anything outside these four is dropped at SupportBot.jsx:169."""
        for question in ('hello', 'where is my order', 'refund', 'cancel',
                         'delivery charges', 'coupons', 'wallet', 'talk to an agent',
                         'something nobody planned for'):
            reply = self._ask(question)
            self.assertTrue(set(reply) <= REPLY_FIELDS,
                            '%r returned %s' % (question, set(reply) - REPLY_FIELDS))
            self.assertTrue(reply.get('text'), '%r said nothing' % question)

    def test_chips_are_plain_strings_the_bot_can_match_again(self):
        """Tapping a chip re-sends its text, so a chip the rules cannot match
        is a dead end."""
        reply = self._ask('hello')
        for chip in reply.get('chips', []):
            self.assertIsInstance(chip, str)
            answer = self._ask(chip)
            self.assertTrue(answer.get('text'))

    def test_an_action_is_a_label_and_a_go_pair(self):
        reply = self._ask('wallet')
        for action in reply.get('actions', []):
            self.assertEqual(set(action), {'label', 'go'})
            self.assertTrue(1 <= len(action['go']) <= 2)

    def test_the_agent_reply_is_a_bare_string(self):
        """SupportBot.jsx:167 does not unwrap it."""
        answer = self.env['mart369.bot']._mart369_agent_reply(self.partner, None, 'hi')
        self.assertIsInstance(answer, str)

    # -------------------------------------------------- no longer made up

    def test_delivery_charges_come_from_the_real_rules(self):
        """They used to be typed into a string and had already drifted."""
        rule = self.env['mart369.delivery.rule'].sudo().search(
            [('mode', '=', 'quick')], limit=1)
        rule.write({'fee': 42.0, 'free_above': 777.0})
        text = self._ask('delivery charges')['text']
        self.assertIn('42', text)
        self.assertIn('777', text)

    def test_coupon_codes_come_from_the_real_coupons(self):
        self.env['mart369.coupon'].sudo().create({
            'code': 'BOTTEST', 'title': 'A test code', 'kind': 'flat',
            'value': 10.0, 'min_spend': 50.0,
        })
        self.assertIn('BOTTEST', self._ask('coupon codes')['text'])

    def test_a_coupon_that_has_expired_is_not_offered(self):
        self.env['mart369.coupon'].sudo().create({
            'code': 'GONE', 'title': 'Finished', 'kind': 'flat', 'value': 10.0,
            'ends_on': '2020-01-01',
        })
        self.assertNotIn('GONE', self._ask('coupon codes')['text'])

    def test_the_wallet_balance_is_this_customers_own(self):
        card = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner)
        card._mart369_move(150.0, 'add', 'Test top-up')
        self.assertIn('150', self._ask('wallet balance')['text'])

    # ------------------------------------------------------------- orders

    def test_it_can_answer_about_an_order_by_number(self):
        # A realistic reference: the app builds them from digits
        # (payment.js:75), and the pattern requires digits precisely so that
        # someone typing "369mart" is not taken to be naming an order.
        order = self._place(ref='369M-240916')
        self._pay(order)
        text = self._ask('what about %s' % order.mart369_ref)['text']
        self.assertIn(order.mart369_ref, text)
        self.assertIn('confirmed', text)

    def test_the_shop_s_own_name_is_not_read_as_an_order_number(self):
        reply = self._ask('is 369mart open on sunday')
        self.assertNotIn('order #', reply['text'].lower())

    def test_another_customers_order_number_is_not_found(self):
        """The bot only ever reads the orders of whoever is asking."""
        order = self._place(ref='369M-240917')
        self._pay(order)
        reply = self.env['mart369.bot']._mart369_reply(
            self.other.partner_id, 'where is %s' % order.mart369_ref)
        self.assertNotIn(order.mart369_ref, reply['text'])

    def test_tracking_names_an_order_that_is_really_on_its_way(self):
        order = self._place()
        self._pay(order)
        reply = self._ask('where is my order')
        self.assertIn(order.mart369_ref, reply['text'])
        self.assertTrue(reply.get('actions'))

    def test_with_nothing_on_the_way_it_says_so(self):
        reply = self._ask('where is my order')
        self.assertIn('no orders', reply['text'].lower())

    # ------------------------------------------------- the thing it must not say

    def test_the_bot_never_says_the_delivery_code(self):
        """The order page's bot printed it into the chat. mart369_order made it
        server-issued and hashed; a support answer is not a reason to undo that."""
        order = self._place()
        self._pay(order)
        code = order._mart369_issue_otp()
        for question in ('where is my order', 'otp', 'delivery code',
                         order.mart369_ref, 'talk to an agent'):
            reply = self._ask(question)
            self.assertNotIn(code, reply.get('text', ''),
                             '%r leaked the delivery code' % question)

    # ------------------------------------------------------------ matching

    def test_asking_for_a_person_sets_the_agent_flag(self):
        self.assertTrue(self._ask('talk to an agent').get('agent'))

    def test_the_word_called_no_longer_hands_them_to_an_agent(self):
        """The old rule matched a bare "call", so "you called me about my
        refund" was handed over instead of answered."""
        reply = self._ask('you called me about my refund')
        self.assertFalse(reply.get('agent'))
        self.assertIn('refund', reply['text'].lower())

    def test_an_unknown_question_offers_the_topics(self):
        reply = self._ask('purple monkey dishwasher')
        self.assertTrue(reply.get('chips'))

    def test_a_rule_with_a_broken_pattern_does_not_break_the_panel(self):
        """Answering must survive a pattern that will not compile.

        Writing one is refused now (`_check_pattern`), so this breaks the rule
        in SQL instead - which is how such a row really comes to exist: data
        that predates the constraint, an import, a direct write. The guard in
        the matcher is for those, and it is still needed: refusing new ones
        does not repair the old.
        """
        rule = self.env['mart369.bot.rule'].sudo().create({
            'sequence': 1, 'title': 'Broken', 'pattern': 'placeholder',
            'kind': 'static', 'reply': 'never seen',
        })
        self.env.cr.execute(
            "UPDATE mart369_bot_rule SET pattern = %s WHERE id = %s",
            ('([unclosed', rule.id))
        rule.invalidate_recordset(['pattern'])

        reply = self._ask('hello')
        self.assertTrue(reply.get('text'))
        self.assertNotIn('never seen', reply['text'])
