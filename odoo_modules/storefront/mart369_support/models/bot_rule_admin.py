"""What the app's own admin console reads and writes for the bot answers.

These are the words the shop says to a customer before a person sees them, so
this is the most editable of the staff screens: create, reword, reorder and
switch off. It is also the one where a mistake is quietest.

Three things worth knowing.

**Order is meaning.** The bot tries rules in `sequence` and the first match
wins, so a broad pattern moved above a narrow one silently swallows it - the
narrow rule still exists, still looks fine on the screen, and never fires
again. That is why reordering is a first-class action here rather than a
column somebody edits by hand.

**A pattern is a regular expression, and a broken one used to fail silently.**
`_check_pattern` on the model now refuses it on save; this file never
second-guesses that, it just lets the error through with the field named.

**Switched off is not deleted.** A rule nobody wants today is a rule somebody
wrote for a reason, and `active` keeps it findable. Nothing here deletes one.
"""

import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

from .bot_rule import KIND_CHOICES

_logger = logging.getLogger(__name__)

KINDS = dict(KIND_CHOICES)

# What a screen may set. Everything a rule is, in other words - this is an
# editing screen, and the allow-list is here to name the fields rather than to
# hold anything back.
WRITABLE = ('title', 'pattern', 'kind', 'reply', 'reply_alt', 'chips',
            'action_label', 'action_view', 'action_param', 'sequence')

MAX_ROWS = 100


class Mart369BotRuleAdmin(models.Model):
    _inherit = 'mart369.bot.rule'

    # --------------------------------------------------------- serializing

    def _mart369_admin_row(self):
        """One answer as the staff screens draw it."""
        self.ensure_one()
        return {
            'id': self.id,
            'sequence': self.sequence,
            'title': self.title or '',
            'pattern': self.pattern or '',
            'kind': self.kind or 'static',
            'kindLabel': KINDS.get(self.kind, self.kind or ''),
            'reply': self.reply or '',
            'replyAlt': self.reply_alt or '',
            'chips': [c.strip() for c in (self.chips or '').split(',') if c.strip()],
            'actionLabel': self.action_label or '',
            'actionView': self.action_view or '',
            'actionParam': self.action_param or '',
            'active': bool(self.active),
            # `static` is the only kind that answers with the words on the
            # rule; every other one runs a handler and `reply` is a fallback.
            # Worth saying on the row, because it changes what editing `reply`
            # actually does.
            'answersItself': self.kind == 'static',
        }

    # ------------------------------------------------------------ reading

    @api.model
    def _mart369_admin_domain(self, tab=None, q=None):
        domain = []
        if tab == 'off':
            domain = [('active', '=', False)]
        elif tab == 'agent':
            domain = [('active', '=', True), ('kind', '=', 'agent')]
        elif tab and tab not in ('all', 'on'):
            domain = [('active', '=', True), ('kind', '=', tab)]
        elif tab == 'on' or not tab:
            domain = [('active', '=', True)]

        term = (q or '').strip()
        if term:
            domain += ['|', '|',
                       ('title', 'ilike', term),
                       ('pattern', 'ilike', term),
                       ('reply', 'ilike', term)]
        return domain

    @api.model
    def mart369_admin_list(self, tab=None, q=None, limit=30, offset=0):
        """The answers in the order the bot tries them, and the tiles."""
        domain = self._mart369_admin_domain(tab=tab, q=q)
        limit = max(1, min(int(limit or 30), MAX_ROWS))
        offset = max(0, int(offset or 0))

        # `active_test=False` throughout: switched off is a tab, not a thing
        # to hide. `_order` is 'sequence, id', which is the order the bot
        # itself reads them in - the screen must not sort them any other way
        # or it stops showing which rule wins.
        books = self.with_context(active_test=False)
        rows = books.search(domain, limit=limit, offset=offset)

        payload = self.mart369_admin_counts()
        payload.update({
            'answers': [r._mart369_admin_row() for r in rows],
            'total': books.search_count(domain),
            'limit': limit,
            'offset': offset,
            'kinds': [{'key': key, 'label': label} for key, label in KIND_CHOICES],
        })
        return payload

    @api.model
    def mart369_admin_counts(self):
        """The tiles, and the number on each tab."""
        books = self.with_context(active_test=False)
        on = [('active', '=', True)]
        return {
            'counts': {
                'on': books.search_count(on),
                'off': books.search_count([('active', '=', False)]),
                'agent': books.search_count(on + [('kind', '=', 'agent')]),
                'all': books.search_count([]),
            },
            # A rule whose pattern no longer compiles cannot match anything.
            # The constraint stops new ones, but a database may already hold
            # some, and nothing would otherwise say so.
            'broken': sum(1 for r in books.search([]) if not r._mart369_pattern_ok()),
        }

    def _mart369_pattern_ok(self):
        self.ensure_one()
        if not self.pattern:
            return False
        try:
            re.compile(self.pattern)
        except re.error:
            return False
        return True

    # ------------------------------------------------------------ writing

    @api.model
    def _mart369_admin_values(self, body):
        """The allow-listed fields, in the right types."""
        values = {}
        for field in WRITABLE:
            if field in body:
                values[field] = body[field] if body[field] is not None else False

        if 'chips' in values and isinstance(values['chips'], (list, tuple)):
            values['chips'] = ','.join(str(c).strip() for c in values['chips'] if str(c).strip())

        for field in ('title', 'pattern'):
            if field in values:
                values[field] = (values[field] or '').strip()

        if 'title' in values and not values['title']:
            raise UserError(self.env._('Give it a name, so somebody can find it.'))
        if 'pattern' in values and not values['pattern']:
            raise UserError(self.env._('Without something to match on, it never fires.'))
        if values.get('kind') and values['kind'] not in KINDS:
            raise UserError(self.env._('That is not an answer the bot knows how to give.'))
        if 'sequence' in values:
            values['sequence'] = int(values['sequence'] or 10)
        return values

    @api.model
    def mart369_admin_save(self, rule_id=None, values=None):
        """Write an answer, or change one.

        A bad pattern raises from the model's own constraint; it is let
        through rather than caught, because the message it carries names what
        is wrong with the expression.
        """
        prepared = self._mart369_admin_values(values or {})
        if rule_id:
            rule = self.with_context(active_test=False).browse(int(rule_id)).exists()
            if not rule:
                raise UserError(self.env._('That answer no longer exists.'))
            rule.write(prepared)
        else:
            for required in ('title', 'pattern'):
                if not prepared.get(required):
                    raise UserError(self.env._('It needs a name and something to match on.'))
            # New rules go last: a rule the bot tries first has to be put
            # there deliberately, because doing so takes matches off whatever
            # sat above it.
            if 'sequence' not in prepared:
                last = self.with_context(active_test=False).search(
                    [], order='sequence desc', limit=1)
                prepared['sequence'] = (last.sequence or 0) + 10
            rule = self.create(prepared)
            _logger.info('369 Mart: bot answer %s written by %s',
                         rule.id, self.env.user.login)
        return rule._mart369_admin_row()

    @api.model
    def mart369_admin_switch(self, rule_id, on=True):
        """Switch one on or off. Never deleted: somebody wrote it for a
        reason, and off keeps it findable."""
        rule = self.with_context(active_test=False).browse(int(rule_id)).exists()
        if not rule:
            raise UserError(self.env._('That answer no longer exists.'))
        rule.write({'active': bool(on)})
        return rule._mart369_admin_row()

    @api.model
    def mart369_admin_reorder(self, rule_ids):
        """Put the answers in this order.

        Order is meaning here - the bot takes the first match - so this is its
        own action rather than a number somebody edits on a row. Spaced by ten
        so a later insertion has somewhere to go.
        """
        if not rule_ids:
            raise UserError(self.env._('Nothing to reorder.'))
        rules = self.with_context(active_test=False).browse(
            [int(i) for i in rule_ids]).exists()
        if len(rules) != len(rule_ids):
            raise UserError(self.env._('One of those answers no longer exists.'))
        for position, rule in enumerate(rules, start=1):
            rule.sequence = position * 10
        return True

    # --------------------------------------------------------------- demo

    @api.model
    def _mart369_load_bot_demo(self):
        """Two extra answers, to show what an added one looks like.

        The thirteen shipped in `data/bot_rules.xml` are the shop's real
        answers. These two sit after them - deliberately last, because a new
        rule placed high would start swallowing matches from the ones above -
        and one is switched off so that tab is not empty.

        Does nothing once a demo answer exists.
        """
        books = self.with_context(active_test=False)
        if books.search_count([('title', 'like', '[demo]')]):
            return False

        last = books.search([], order='sequence desc', limit=1)
        start = (last.sequence or 0) + 10
        made = self.create([
            {'sequence': start, 'title': 'Opening hours [demo]',
             'pattern': r'\b(open|hours|timing|closed)\b', 'kind': 'static',
             'reply': 'We are open 7am to 11pm, every day including Sundays.',
             'chips': 'Talk to an agent'},
            {'sequence': start + 10, 'title': 'Bulk orders [demo]',
             'pattern': r'\b(bulk|wholesale|quantity|catering)\b',
             'kind': 'static',
             'reply': 'For large orders, tell us what you need and we will call you back.',
             'action_label': 'Talk to us', 'action_view': 'account',
             'action_param': 'support'},
        ])
        made[-1:].write({'active': False})
        _logger.info('369 Mart: seeded %s example bot answer(s)', len(made))
        return True
