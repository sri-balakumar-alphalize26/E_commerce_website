"""The figures on the dashboard's cards, as they are now (24 Nov 2026)."""
import logging
import time
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

NOT_SENT = ('pending', 'failed', 'blocked')
FIGURES = ('total_messages', 'total_sent', 'total_received', 'unique_contacts')
# Asking the panel may take seconds per number when it is down; the rest is
# asked the next time the screen refreshes.
ASK_SECONDS = 4
# A chat without a reply this long is not called waiting any more.
WAIT_HOURS = 48
# What the assistant wrote, as in wa.response.time.stat.
NOT_THE_BOT = """NOT EXISTS (
    SELECT 1 FROM wa_auto_reply ar
     WHERE ar.conversation_id = l.conversation_id
       AND TRIM(COALESCE(ar.reply_message, '')) = TRIM(COALESCE(l.message_text, ''))
       AND ABS(EXTRACT(EPOCH FROM (ar.create_date - l.message_date))) < 60)"""


class EmployeeSessionFigures(models.Model):
    _inherit = 'wa.employee.session'

    number_pretty = fields.Char('WhatsApp Number', compute='_compute_number_pretty')
    has_replies = fields.Boolean(compute='_compute_response_time')
    has_score = fields.Boolean(compute='_compute_quality_score')

    @api.depends('phone_number', 'own_number')
    def _compute_number_pretty(self):
        pretty = self.env['whatsapp.connect'].sudo()._pretty
        for rec in self:
            rec.number_pretty = (pretty(rec.own_number) if rec.own_number else '') or rec.phone_number or ''

    # ------------------------------------------------------------ counting
    def _figures(self, since=None):
        """{id: (sent, received, people)}: the messages, and what was typed on
        the phone, in one go for all the cards."""
        ids = tuple(i for i in self.ids if isinstance(i, int))
        if not ids:
            return {}
        self.env['whatsapp.message'].flush_model()
        self.env['wa.communication.log'].flush_model()
        self.env.cr.execute("""
            SELECT owner,
                   count(*) FILTER (WHERE direction = 'outgoing'),
                   count(*) FILTER (WHERE direction = 'incoming'),
                   count(DISTINCT right(regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g'), 9))
                       FILTER (WHERE regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g') != '')
              FROM (SELECT employee_session_id AS owner, direction, phone, create_date AS at
                      FROM whatsapp_message
                     WHERE employee_session_id IN %(ids)s
                       AND (direction = 'incoming' OR COALESCE(status, '') NOT IN %(not_sent)s)
                     UNION ALL
                    SELECT employee_session_id, direction, phone, message_date
                      FROM wa_communication_log
                     WHERE employee_session_id IN %(ids)s AND message_id IS NULL) AS m
             WHERE %(since)s::timestamp IS NULL OR at >= %(since)s::timestamp
             GROUP BY owner""", {'ids': ids, 'not_sent': NOT_SENT, 'since': since})
        return {row[0]: row[1:] for row in self.env.cr.fetchall()}

    def _reply_status(self):
        """{id: {'last', 'waiting', 'oldest', 'waits'}} (25 Nov 2026).

        last: when the employee last wrote something - on the phone, or in Odoo
        with their own login. Not a manager's reply and not the assistant's.
        waiting: private chats whose customer wrote after the last reply of any
        person; oldest: the first message still without one; waits: the same
        for each chat, {last 9 digits: when}."""
        result = {rec.id: {'last': False, 'waiting': 0, 'oldest': False, 'waits': {}} for rec in self}
        ids = tuple(i for i in self.ids if isinstance(i, int))
        if not ids:
            return result
        for model in ('whatsapp.message', 'wa.communication.log', 'wa.auto.reply', 'wa.employee.session', 'hr.employee'):
            self.env[model].flush_model()
        values = {'ids': ids, 'not_sent': NOT_SENT, 'since': fields.Datetime.now() - timedelta(hours=WAIT_HOURS)}
        self.env.cr.execute("""
            SELECT owner, max(at)
              FROM (SELECT l.employee_session_id AS owner, l.message_date AS at
                      FROM wa_communication_log l
                     WHERE l.employee_session_id IN %(ids)s AND l.message_id IS NULL AND l.direction = 'outgoing'
                       AND """ + NOT_THE_BOT + """
                     UNION ALL
                    SELECT m.employee_session_id, m.create_date
                      FROM whatsapp_message m
                      JOIN wa_employee_session s ON s.id = m.employee_session_id
                      JOIN hr_employee e ON e.id = s.employee_id AND e.user_id = m.create_uid
                     WHERE m.employee_session_id IN %(ids)s AND m.direction = 'outgoing'
                       AND COALESCE(m.status, '') NOT IN %(not_sent)s) AS wrote
             GROUP BY owner""", values)
        for owner, last in self.env.cr.fetchall():
            result[owner]['last'] = last
        self.env.cr.execute("""
            WITH said AS (
                SELECT m.employee_session_id AS owner, right(regexp_replace(m.phone, '[^0-9]', '', 'g'), 9) AS who,
                       m.direction, m.create_date AS at
                  FROM whatsapp_message m
                  LEFT JOIN res_users u ON u.id = m.create_uid
                 WHERE m.employee_session_id IN %(ids)s AND m.create_date >= %(since)s
                   AND COALESCE(m.phone, '') NOT LIKE '%%@g.us%%'
                   AND (m.direction = 'incoming'
                        OR (COALESCE(m.status, '') NOT IN %(not_sent)s AND u.id != 1 AND u.share IS NOT TRUE AND u.active))
                 UNION ALL
                SELECT l.employee_session_id, right(regexp_replace(l.phone, '[^0-9]', '', 'g'), 9), l.direction, l.message_date
                  FROM wa_communication_log l
                 WHERE l.employee_session_id IN %(ids)s AND l.message_id IS NULL AND l.message_date >= %(since)s
                   AND l.is_group_message IS NOT TRUE AND COALESCE(l.phone, '') NOT LIKE '%%@g.us%%'
                   AND (l.direction = 'incoming' OR """ + NOT_THE_BOT + """)),
            replied AS (
                SELECT owner, who, max(at) AS at FROM said WHERE direction = 'outgoing' GROUP BY owner, who)
            SELECT said.owner, said.who, min(said.at)
              FROM said
              LEFT JOIN replied ON replied.owner = said.owner AND replied.who = said.who
             WHERE said.direction = 'incoming' AND said.who != '' AND (replied.at IS NULL OR said.at > replied.at)
             GROUP BY said.owner, said.who""", values)
        for owner, who, at in self.env.cr.fetchall():
            row = result[owner]
            row['waits'][who] = at
            row['waiting'] += 1
            row['oldest'] = min(row['oldest'] or at, at)
        return result

    def _reply_today(self):
        """{id: (replies, average minutes)} of today: the first reply of a person
        to each customer message, as on the dashboard."""
        ids = tuple(i for i in self.ids if isinstance(i, int))
        if not ids:
            return {}
        self.env['wa.communication.log'].flush_model()
        self.env['wa.auto.reply'].flush_model()
        self.env.cr.execute("""
            SELECT owner, count(*), avg(minutes)
              FROM (SELECT employee_session_id AS owner, min(response_minutes) AS minutes, min(reply_date) AS at
                      FROM wa_response_time_stat
                     WHERE employee_session_id IN %s
                     GROUP BY employee_session_id, conversation_id, customer_msg_date) AS first_reply
             WHERE at >= %s
             GROUP BY owner""", [ids, self._today_start()])
        return {owner: (count, float(average or 0)) for owner, count, average in self.env.cr.fetchall()}

    def _totals(self):
        figures = self._figures()
        result = {}
        for rec in self:
            sent, received, people = figures.get(rec.id, (0, 0, 0))
            result[rec.id] = dict(zip(FIGURES, (sent + received, sent, received, people)))
        return result

    @api.depends('session_id')
    def _compute_stats(self):
        totals = self._totals()
        for rec in self:
            for name, value in totals[rec.id].items():
                rec[name] = value

    def _refresh_totals(self):
        """The stored totals, written only where they differ."""
        totals = self._totals()
        for rec in self:
            vals = {name: value for name, value in totals[rec.id].items() if rec[name] != value}
            if vals:
                rec.sudo().write(vals)

    @api.model
    def _today_start(self):
        """Midnight of the user's own day, in UTC."""
        try:
            zone = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        except pytz.UnknownTimeZoneError:
            zone = pytz.utc
        here = pytz.utc.localize(fields.Datetime.now()).astimezone(zone)
        midnight = zone.localize(here.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None))
        return midnight.astimezone(pytz.utc).replace(tzinfo=None)

    @api.depends_context('tz', 'uid')
    def _compute_today_stats(self):
        figures = self._figures(self._today_start())
        for rec in self:
            rec.today_sent, rec.today_received = figures.get(rec.id, (0, 0, 0))[:2]

    def _compute_response_time(self):
        """A person's first reply to each customer message; the bot's replies
        and what was written after the first reply do not count."""
        ids = tuple(i for i in self.ids if isinstance(i, int))
        average = {}
        if ids:
            self.env['wa.communication.log'].flush_model()
            self.env['wa.auto.reply'].flush_model()
            self.env.cr.execute("""
                SELECT owner, avg(minutes)
                  FROM (SELECT employee_session_id AS owner, min(response_minutes) AS minutes
                          FROM wa_response_time_stat
                         WHERE employee_session_id IN %s
                         GROUP BY employee_session_id, conversation_id, customer_msg_date) AS first_reply
                 GROUP BY owner""", [ids])
            average = dict(self.env.cr.fetchall())
        for rec in self:
            rec.has_replies = rec.id in average
            rec.avg_response_minutes = round(float(average.get(rec.id) or 0), 1)

    def _compute_quality_score(self):
        super()._compute_quality_score()
        Score = self.env['wa.quality.score']
        for rec in self:
            rec.has_score = isinstance(rec.id, int) and bool(
                Score.search_count([('employee_session_id', '=', rec.id)], limit=1))

    # ------------------------------------------------------------ the screen
    def _refresh_for_screen(self):
        """A screen always opens: a failure leaves what was saved last."""
        until = time.monotonic() + ASK_SECONDS
        sessions = self.sudo().filtered('active').session_id
        for session in sessions.sorted(lambda s: s.state_checked or datetime.min):
            if time.monotonic() > until:
                break
            session._refresh_state_for_screen()
        try:
            with self.env.cr.savepoint():
                self._refresh_totals()
                self.env.flush_all()
        except Exception as err:  # noqa: BLE001
            self.env.invalidate_all(flush=False)
            _logger.info("WA Tracker: the dashboard shows the last totals: %s", err)

    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        self.search(domain, offset=offset, limit=limit, order=order)._refresh_for_screen()
        return super().web_search_read(
            domain, specification, offset=offset, limit=limit, order=order, count_limit=count_limit)

    # the fresh totals are saved, so not on a read-only connection
    web_search_read._readonly = False
