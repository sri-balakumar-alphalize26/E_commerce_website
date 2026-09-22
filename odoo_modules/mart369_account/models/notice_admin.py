"""What the app's own admin console reads and writes for notifications.

A notice is a line that appears in every customer's notification list. So this
is a writing screen - marketing owns the words - but a narrow one: staff write
a notice, choose when it runs, and retire it. Nothing here deletes one, because
a notice somebody has already read is part of what they were told.

Two things kept apart on purpose.

**The shopper's serializer is not widened.** `_mart369_serialize()` is what a
customer's own feed receives; whether a notice is scheduled, expired or
switched off is a staff question, and the shape here answers it.

**A notice's state is worked out, not stored.** There is no status field: live,
scheduled and expired all fall out of `publish_at`, `until` and `active`, and
inventing a fourth column to hold what those three already say is how the two
stop agreeing. The tabs below are the same three dates read as domains.
"""

import logging

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .notification import TYPE_CHOICES

_logger = logging.getLogger(__name__)

KINDS = dict(TYPE_CHOICES)

# What a screen may set. A notice's own words and its window, and nothing else
# - `active` is reached through the retire route, which says what it does.
WRITABLE = ('name', 'text', 'kind', 'publish_at', 'until', 'go_view', 'go_param')

MAX_ROWS = 100


def _tabs(now):
    """The domains behind the tabs, built against one `now`.

    A function rather than a constant because every one of them is a
    comparison with the clock, and a module-level dict would freeze the
    moment the server booted.
    """
    return {
        'live': [('active', '=', True), ('publish_at', '<=', now),
                 '|', ('until', '=', False), ('until', '>=', now)],
        'scheduled': [('active', '=', True), ('publish_at', '>', now)],
        'expired': [('active', '=', True), ('until', '!=', False),
                    ('until', '<', now)],
        'off': [('active', '=', False)],
        'all': [],
    }


class Mart369NoticeAdmin(models.Model):
    _inherit = 'mart369.notice'

    # --------------------------------------------------------- serializing

    def _mart369_state(self, now=None):
        """live / scheduled / expired / off, worked out from the dates."""
        self.ensure_one()
        now = now or fields.Datetime.now()
        if not self.active:
            return 'off'
        if self.publish_at and self.publish_at > now:
            return 'scheduled'
        if self.until and self.until < now:
            return 'expired'
        return 'live'

    def _mart369_admin_row(self, now=None):
        """One notice as the staff screens draw it."""
        self.ensure_one()
        now = now or fields.Datetime.now()
        return {
            'id': self.id,
            'title': self.name or '',
            'text': self.text or '',
            'kind': self.kind or 'offer',
            'kindLabel': KINDS.get(self.kind, self.kind or ''),
            'state': self._mart369_state(now),
            'from': int(self.publish_at.timestamp() * 1000) if self.publish_at else None,
            'until': int(self.until.timestamp() * 1000) if self.until else None,
            'goView': self.go_view or '',
            'goParam': self.go_param or '',
        }

    # ------------------------------------------------------------ reading

    @api.model
    def _mart369_admin_domain(self, tab=None, q=None, now=None):
        now = now or fields.Datetime.now()
        tabs = _tabs(now)
        domain = list(tabs.get(tab or 'live', tabs['live']))
        term = (q or '').strip()
        if term:
            domain += ['|', ('name', 'ilike', term), ('text', 'ilike', term)]
        return domain

    @api.model
    def mart369_admin_list(self, tab=None, q=None, limit=30, offset=0):
        """One page of the notices, and the tile counts above them."""
        now = fields.Datetime.now()
        domain = self._mart369_admin_domain(tab=tab, q=q, now=now)
        limit = max(1, min(int(limit or 30), MAX_ROWS))
        offset = max(0, int(offset or 0))

        # `active_test=False` throughout: 'off' is a tab, not a thing to hide,
        # and 'all' means all.
        books = self.with_context(active_test=False)
        rows = books.search(domain, limit=limit, offset=offset,
                            order='publish_at desc, id desc')

        payload = self.mart369_admin_counts()
        payload.update({
            'notices': [n._mart369_admin_row(now) for n in rows],
            'total': books.search_count(domain),
            'limit': limit,
            'offset': offset,
            # Shipped with the list so neither screen keeps its own copy of
            # what a kind is called.
            'kinds': [{'key': key, 'label': label} for key, label in TYPE_CHOICES],
        })
        return payload

    @api.model
    def mart369_admin_counts(self):
        """The tiles, and the number on each tab."""
        now = fields.Datetime.now()
        books = self.with_context(active_test=False)
        return {'counts': {key: books.search_count(where)
                           for key, where in _tabs(now).items()}}

    # ------------------------------------------------------------ writing

    @api.model
    def _mart369_admin_values(self, body):
        """The allow-listed fields, in the right types.

        Raises UserError naming the field, so the screen can put the message
        under the control the server is complaining about.
        """
        values = {}
        for field in WRITABLE:
            if field in body:
                values[field] = body[field] or False

        title = (values.get('name') or '').strip() if 'name' in values else None
        if title is not None and not title:
            raise UserError(self.env._('Give it a title.'))
        if 'name' in values:
            values['name'] = title

        text = (values.get('text') or '').strip() if 'text' in values else None
        if text is not None and not text:
            raise UserError(self.env._('Write what it should say.'))
        if 'text' in values:
            values['text'] = text

        if values.get('kind') and values['kind'] not in KINDS:
            raise UserError(self.env._('That is not a kind of notification.'))

        starts, ends = values.get('publish_at'), values.get('until')
        if starts and ends and str(ends) < str(starts):
            raise UserError(self.env._('It cannot stop before it starts.'))
        return values

    @api.model
    def mart369_admin_save(self, notice_id=None, values=None):
        """Write a notice, or change one. Returns the row back.

        Returned rather than trusted: whether it is live or scheduled depends
        on the clock, and the screen must not have to work that out.
        """
        prepared = self._mart369_admin_values(values or {})
        if notice_id:
            notice = self.browse(int(notice_id)).exists()
            if not notice:
                raise UserError(self.env._('That notification no longer exists.'))
            notice.write(prepared)
        else:
            for required in ('name', 'text'):
                if not prepared.get(required):
                    raise UserError(self.env._('Give it a title and some words.'))
            notice = self.create(prepared)
            _logger.info('369 Mart: notice %s written by %s',
                         notice.id, self.env.user.login)
        return notice._mart369_admin_row()

    @api.model
    def mart369_admin_retire(self, notice_id, retired=True):
        """Take a notice down, or put it back.

        Archived rather than deleted: a customer who has already read one was
        told something, and deleting the record does not untell them.
        """
        notice = self.with_context(active_test=False).browse(int(notice_id)).exists()
        if not notice:
            raise UserError(self.env._('That notification no longer exists.'))
        notice.write({'active': not retired})
        return notice._mart369_admin_row()

    # --------------------------------------------------------------- demo

    @api.model
    def _mart369_load_notice_demo(self):
        """A few notices to look at, one in each state.

        Called from `data/notice_demo.xml` rather than being records there,
        because two of them need dates relative to now - a scheduled one and a
        finished one - and an XML record would freeze those at whenever the
        module happened to be installed, so the example set would be wrong by
        the next morning.

        Does nothing once a demo notice exists, so a shop that has written its
        own never sprouts examples. The three real notices shipped in
        account_data.xml are left alone: they are content, not examples.
        """
        tagged = self.with_context(active_test=False).search_count(
            [('name', 'like', '[demo]')])
        if tagged:
            return False

        now = fields.Datetime.now()
        day = timedelta(days=1)
        rows = [
            # Live, and the kind that could never be delivered until now.
            {'name': 'Deliveries are running late today [demo]',
             'text': 'Heavy rain in Dindigul. Orders may arrive an hour late.',
             'kind': 'order', 'publish_at': now - day},
            {'name': 'Double cashback this week [demo]',
             'text': 'Pay from the 369 Wallet and get twice the usual back.',
             'kind': 'wallet', 'publish_at': now - day,
             'go_view': 'account', 'go_param': 'wallet'},
            # Scheduled: written now, shown on Friday.
            {'name': 'Weekend fruit sale starts Friday [demo]',
             'text': 'Up to 40% off on fresh picks, from Friday morning.',
             'kind': 'offer', 'publish_at': now + (2 * day),
             'until': now + (5 * day), 'go_view': 'offers'},
            # Finished: its window has closed, but nobody took it down.
            {'name': 'Onam offers have ended [demo]',
             'text': 'Thank you for shopping with us this season.',
             'kind': 'offer', 'publish_at': now - (10 * day),
             'until': now - (2 * day), 'go_view': 'offers'},
            # Taken down, which is a different thing from finished: somebody
            # pulled this one while it was still inside its window. One record
            # cannot be both, and using the expired one for both left the
            # Finished tab empty - which is what demo data exists to prevent.
            {'name': 'Free delivery week [demo]',
             'text': 'No delivery charge on any order, all week.',
             'kind': 'offer', 'publish_at': now - (3 * day)},
        ]

        made = self.create(rows)
        made[-1:].write({'active': False})

        _logger.info('369 Mart: seeded %s example notice(s)', len(made))
        return True
