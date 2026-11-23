"""Nothing is sent twice (23 Nov 2026).

Odoo repeats a web request from the start when two of them wrote the same row.
The database forgets the first try; WhatsApp does not: one tap on a product went
out three times. What a request has sent is remembered on the request itself:
the repeat gets the stored answer instead of sending again. So that it says the
same again, codes, tokens and order numbers made in the first try are taken
over - they were never used by anybody else."""
import json

from odoo import models
from odoo.http import request

KEY = 'whatsapp.send.memo'


class SendMemo:
    def __init__(self):
        self.sent, self.used = {}, {}
        self.made, self.at = {}, {}
        self.attempt = 0

    def again(self):
        """The transaction was undone: the request starts from its beginning."""
        self.attempt += 1
        self.used.clear()
        self.at.clear()

    def take(self, key):
        n = self.used.get(key, 0)
        stored = self.sent.get(key, [])
        if n < len(stored):
            self.used[key] = n + 1
            return True, stored[n]
        return False, None

    def put(self, key, answer):
        self.sent.setdefault(key, []).append(answer)
        self.used[key] = self.used.get(key, 0) + 1

    def value(self, kind, maker):
        """The nth value of this kind: the one of the first try, else a new one."""
        n = self.at.get(kind, 0)
        self.at[kind] = n + 1
        made = self.made.setdefault(kind, [])
        if n < len(made):
            return made[n]
        made.append(maker())
        return made[n]


def current(env):
    """The memo of the running web request, or None (jobs, shell)."""
    if not request or getattr(request, 'httprequest', None) is None:
        return None
    try:
        if request.env.cr is not env.cr and request.env.cr.dbname != env.cr.dbname:
            return None
    except Exception:  # noqa: BLE001 - no database on this request
        return None
    environ = request.httprequest.environ
    memo = environ.get(KEY)
    if memo is None:
        memo = environ[KEY] = SendMemo()
    if memo.again not in getattr(env.cr.postrollback, '_funcs', ()):
        env.cr.postrollback.add(memo.again)
    return memo


def send_key(session, path, payload):
    return '%s|%s|%s' % (session.id, path, json.dumps(payload, sort_keys=True, default=str))


class IrSequenceMemo(models.Model):
    _inherit = 'ir.sequence'

    def _next(self, sequence_date=None):
        # 'standard' numbers are never handed out again: taking over the one of
        # the undone try is safe. 'no_gap' gives its number back itself.
        if self.implementation != 'standard':
            return super()._next(sequence_date=sequence_date)
        memo = current(self.env)
        if memo is None:
            return super()._next(sequence_date=sequence_date)
        return memo.value('seq|%s|%s' % (self.id, sequence_date or ''), lambda: super(IrSequenceMemo, self)._next(sequence_date=sequence_date))
