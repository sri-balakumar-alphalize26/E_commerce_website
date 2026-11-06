"""The staff side of the bot answers, and the pattern that failed in silence.

These are the words the shop says before a person sees the customer, so the
things worth pinning are the ones that go wrong without saying so.

**A broken pattern.** The bot catches `re.error` while matching, logs a warning
and moves to the next rule - right at answering time, because one bad rule must
not take the panel down, but it means a rule that never matches, for ever, with
a green Save behind it. It is refused on write now.

**Order is meaning.** The bot takes the first match, so a broad rule moved above
a narrow one silently swallows it: the narrow rule still exists, still looks
fine, and never fires again. Reordering is its own action for that reason, and
a new answer goes last.

**Switched off is not deleted.** Somebody wrote it for a reason.
"""

import json

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase

HEADERS = {'Content-Type': 'application/json'}
LIST = '/369mart/admin/answers'


@tagged('post_install', '-at_install')
class TestBotPattern(TransactionCase):
    """The constraint, and what it protects."""

    def setUp(self):
        super().setUp()
        self.Rule = self.env['mart369.bot.rule']

    def test_a_pattern_that_will_not_compile_is_refused(self):
        """The bug. It used to save happily and never match again."""
        with self.assertRaises(ValidationError):
            self.Rule.create({'title': 'Broken', 'pattern': '[unclosed',
                              'kind': 'static', 'reply': 'x'})

    def test_it_is_refused_on_edit_too(self):
        rule = self.Rule.create({'title': 'Fine', 'pattern': r'\bhello\b',
                                 'kind': 'static', 'reply': 'x'})
        with self.assertRaises(ValidationError):
            rule.pattern = '(unbalanced'

    def test_the_message_says_what_is_wrong_with_it(self):
        """A regular expression is not obvious, so the error carries what
        Python said rather than a shrug."""
        try:
            self.Rule.create({'title': 'Broken', 'pattern': '*bad',
                              'kind': 'static', 'reply': 'x'})
        except ValidationError as exc:
            self.assertIn('bot can match', str(exc))
        else:
            self.fail('a bad pattern was accepted')

    def test_a_good_pattern_still_saves(self):
        rule = self.Rule.create({
            'title': 'Opening hours', 'pattern': r'\b(open|hours)\b',
            'kind': 'static', 'reply': 'Seven to eleven.'})
        self.assertTrue(rule.id)


@tagged('post_install', '-at_install')
class TestBotAdminModel(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Rule = self.env['mart369.bot.rule']

    def _rule(self, **over):
        values = {'title': 'A rule', 'pattern': r'\bthing\b',
                  'kind': 'static', 'reply': 'Some words'}
        values.update(over)
        return self.Rule.create(values)

    # ------------------------------------------------------------- order

    def test_a_new_answer_goes_last(self):
        """A rule the bot tries first has to be put there deliberately -
        placing one high takes matches off whatever sat above it."""
        highest = self.Rule.with_context(active_test=False).search(
            [], order='sequence desc', limit=1).sequence or 0
        row = self.Rule.mart369_admin_save(values={
            'title': 'Newcomer', 'pattern': r'\bnewcomer\b',
            'kind': 'static', 'reply': 'x'})
        self.assertGreater(row['sequence'], highest)

    def test_reordering_puts_them_in_the_order_given(self):
        a = self._rule(title='First', pattern=r'\ba\b')
        b = self._rule(title='Second', pattern=r'\bb\b')
        self.Rule.mart369_admin_reorder([b.id, a.id])
        self.assertLess(b.sequence, a.sequence)

    def test_reordering_something_that_is_gone_is_refused(self):
        a = self._rule()
        with self.assertRaises(Exception):
            self.Rule.mart369_admin_reorder([a.id, 99999999])

    def test_the_list_keeps_the_order_the_bot_reads_them_in(self):
        """Sorted any other way, the screen stops showing which rule wins."""
        rows = self.Rule.mart369_admin_list(tab='all', limit=100)['answers']
        sequences = [r['sequence'] for r in rows]
        self.assertEqual(sequences, sorted(sequences))

    # ------------------------------------------------------------ reading

    def test_each_tab_asks_for_what_it_says(self):
        off = self._rule(title='Switched off one')
        self.Rule.mart369_admin_switch(off.id, False)
        ids = lambda **kw: [r['id'] for r
                            in self.Rule.mart369_admin_list(limit=100, **kw)['answers']]
        self.assertIn(off.id, ids(tab='off'))
        self.assertNotIn(off.id, ids(tab='on'))
        self.assertIn(off.id, ids(tab='all'))

    def test_the_row_says_whether_the_words_are_the_answer(self):
        """Only `static` answers with what is typed in `reply`; every other
        kind runs a handler, and editing the words does something different."""
        plain = self._rule(kind='static')
        clever = self._rule(title='Wallet one', pattern=r'\bwallet\b', kind='wallet')
        self.assertTrue(plain._mart369_admin_row()['answersItself'])
        self.assertFalse(clever._mart369_admin_row()['answersItself'])

    def test_the_tiles_count_everything_not_the_filtered_rows(self):
        self._rule(title='Findable rule', pattern=r'\bfindable\b')
        wide = self.Rule.mart369_admin_list(tab='all', limit=100)
        narrow = self.Rule.mart369_admin_list(tab='all', q='Findable', limit=100)
        self.assertEqual(wide['counts'], narrow['counts'])
        self.assertLess(len(narrow['answers']), len(wide['answers']))

    # ------------------------------------------------------------ writing

    def test_an_answer_without_something_to_match_on_is_refused(self):
        with self.assertRaises(Exception):
            self.Rule.mart369_admin_save(values={
                'title': 'No pattern', 'pattern': '  ', 'kind': 'static'})

    def test_switching_off_keeps_the_answer(self):
        rule = self._rule()
        self.Rule.mart369_admin_switch(rule.id, False)
        self.assertFalse(rule.active)
        self.assertTrue(rule.exists(), 'off, not gone')
        self.Rule.mart369_admin_switch(rule.id, True)
        self.assertTrue(rule.active)

    def test_chips_arrive_as_a_list_and_are_stored_as_text(self):
        row = self.Rule.mart369_admin_save(values={
            'title': 'Chippy', 'pattern': r'\bchippy\b', 'kind': 'static',
            'reply': 'x', 'chips': ['Talk to an agent', 'See offers']})
        self.assertEqual(row['chips'], ['Talk to an agent', 'See offers'])


@tagged('post_install', '-at_install')
class TestBotAdminRoutes(HttpCase):

    def setUp(self):
        super().setUp()
        self.rule = self.env['mart369.bot.rule'].create({
            'title': 'Route test', 'pattern': r'\broutetest\b',
            'kind': 'static', 'reply': 'x'})
        self.shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper',
            'login': 'mart369_bot_shopper',
            'password': 'mart369_bot_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    def _send(self, method, path, payload=None):
        return self.url_open(path, data=json.dumps(payload or {}),
                             headers=HEADERS, method=method)

    def test_a_shopper_is_refused_every_route(self):
        """These are the shop's own words. A customer must not rewrite them."""
        self.authenticate('mart369_bot_shopper', 'mart369_bot_shopper')
        self.assertEqual(self.url_open(LIST).status_code, 403)
        self.assertEqual(self.url_open(LIST + '/counts').status_code, 403)
        self.assertEqual(self._send('POST', LIST, {'title': 'x'}).status_code, 403)
        self.assertEqual(
            self._send('PATCH', '%s/%s' % (LIST, self.rule.id),
                       {'active': False}).status_code, 403)
        self.assertTrue(self.rule.active, 'and nothing moved')

    def test_staff_write_one_and_switch_it_off(self):
        self.authenticate('admin', 'admin')
        made = self._send('POST', LIST, {
            'title': 'From the console', 'pattern': r'\bconsole\b',
            'kind': 'static', 'reply': 'Hello from the console.'})
        self.assertEqual(made.status_code, 201)
        rule_id = made.json()['answer']['id']

        off = self._send('PATCH', '%s/%s' % (LIST, rule_id), {'active': False})
        self.assertEqual(off.status_code, 200)
        self.assertFalse(off.json()['answer']['active'])

    def test_a_bad_pattern_comes_back_named_to_the_field(self):
        """So the screen can put the message under the box it is about."""
        self.authenticate('admin', 'admin')
        response = self._send('POST', LIST, {
            'title': 'Broken', 'pattern': '[unclosed', 'kind': 'static',
            'reply': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'pattern')

    def test_there_is_no_way_to_delete_an_answer(self):
        self.authenticate('admin', 'admin')
        response = self._send('DELETE', '%s/%s' % (LIST, self.rule.id))
        self.assertNotEqual(response.status_code, 200)
        self.assertTrue(self.rule.exists())

    def test_order_is_not_read_as_an_id(self):
        """'order' and 'counts' sit where an id goes, so route order matters."""
        self.authenticate('admin', 'admin')
        payload = self.url_open(LIST + '/counts').json()
        self.assertTrue(payload['ok'])
        self.assertIn('on', payload['counts'])
        self.assertNotIn('answers', payload)
