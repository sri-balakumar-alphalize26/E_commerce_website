"""WhatsApp connector - a thin HTTP client for an Evolution API gateway.

Nothing WhatsApp-specific runs inside Odoo any more. There is no client object,
no socket, no QR, no background thread and no ownership election - all of which
existed only because the WhatsApp library used to live in the Odoo process.
Every one of them was a failure mode: a session could only be used by the one
worker that happened to hold it, the heartbeat had to arbitrate between
workers, and a QR had to be scanned separately for every database.

Pairing now happens once, on the gateway. Sending is an ordinary HTTP request,
so every worker can send, and a restart changes nothing.

The four send methods keep the exact signatures the consuming modules already
call - whatsapp_email, whatsapp_broadcast, spa_online_booking, kra_kpi_module,
whatsapp_employee_tracker, crm_call_recorder, pdc_management and
nexgenn_wa_reporting - so nothing outside this module had to change:

    send_message(phone, message)
    send_image(phone, image_data, caption='')
    send_document(phone, file_data, filename, caption='', mimetype='...')
    send_buttons(phone, body, buttons, include_numbers=True)
    send_odoo_report(phone, report_xmlid, record, caption='')

`status` also keeps its old values, because other modules filter sessions with
domain="[('status', '=', 'connected')]".
"""

import base64
import logging
import uuid

import psycopg2
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.tools import config

from . import send_memo

_logger = logging.getLogger(__name__)

# The gateway is a separate process, possibly on a separate box. A dead or slow
# one must never hold an Odoo worker: fail the connection fast, allow a little
# longer for a reply that is on its way.
GW_TIMEOUT = (5, 30)

# How long a fetched connection state is trusted before asking the gateway
# again. Without this, every get_connected_session() - which the POS calls on
# each screen - would add a network round trip.
STATE_TTL = 60

# Evolution's connection states mapped onto the status values this module has
# always exposed.
_STATE_MAP = {
    'open': 'connected',
    'connecting': 'connecting',
    'close': 'disconnected',
    'closed': 'disconnected',
    'refused': 'error',
    # Panel-side verdicts (26 Sep 2026): the QR was scanned with a phone other
    # than the ONE the administrator authorized, the instance is gone, or no
    # number is assigned to this database at all.
    'wrong_number': 'wrong_number',
    'missing': 'error',
    'none': 'disconnected',
}

# Evolution rejects more than three reply buttons outright. Past that we do not
# even try - the numbered-text form carries any number of options.
MAX_REPLY_BUTTONS = 3


# How many times the outbox will try a message before writing it off.
MAX_SEND_ATTEMPTS = 20


class WhatsAppBlocked(UserError):
    """The gateway refused this message on policy, not on capacity.

    An opt-out, blocked content, or the daily cap. None of them improve by
    waiting, so a message that raises this is marked `blocked` and never
    retried - unlike `WhatsAppQueued`, which is exactly what retrying is for.
    """


class WhatsAppQueued(UserError):
    """The gateway could not take the message now; it is queued for retry.

    A subclass of UserError so every existing caller - the wizard, the mixin,
    the fallback chains - keeps behaving exactly as before and still shows the
    same sentence. What it adds is the ability to tell "this will arrive
    shortly" apart from "this can never be sent", which is the difference
    between waiting and sending something else instead.
    """


# What this process was told last: {(database, session): (write_date, values)}.
_STATE_MEMO = {}

# A state that did not change is written again only this often.
STATE_WRITE = 300


# The same text typed by a person (context wa_typed): a double press, not more.
TYPED_REPEAT = 10


def _state_direct(env):
    """Tests have one connection: the state is written directly."""
    return config['test_enable'] and not env.context.get('wa_own_cursor')


def _write_state(registry, session_id, vals):
    """In a transaction of its own; somebody else on the row: not now."""
    try:
        with registry.cursor() as cr:
            cr.execute('SELECT status, error_message, state_checked FROM whatsapp_session WHERE id = %s', [session_id])
            row = cr.fetchone()
            if not row:
                return
            same = row[0] == vals['status'] and (row[1] or False) == (vals['error_message'] or False)
            if same and row[2] and 0 <= (vals['state_checked'] - row[2]).total_seconds() < STATE_WRITE:
                return
            cr.execute('SELECT 1 FROM whatsapp_session WHERE id = %s FOR NO KEY UPDATE SKIP LOCKED', [session_id])
            if cr.fetchone():
                names = sorted(vals)
                cr.execute('UPDATE whatsapp_session SET %s WHERE id = %%s' % ', '.join('"%s" = %%s' % n for n in names),
                           [vals[n] or None for n in names] + [session_id])
    except Exception as err:  # noqa: BLE001 - the state is asked again in a moment
        _logger.info("WhatsApp: state of %s not saved now: %s", session_id, err)


class WhatsAppSession(models.Model):
    _name = 'whatsapp.session'
    _description = 'WhatsApp Session'
    _rec_name = 'name'

    name = fields.Char(
        'Session Name', required=True, default='Default',
        help='A friendly name for this WhatsApp session',
    )

    # --- where to send, and as whom ---------------------------------
    gateway_url = fields.Char(
        'Gateway URL', required=True, default='http://127.0.0.1:8085',
        groups='base.group_system',
        help='Base URL of the Evolution API server, with no trailing slash.',
    )
    gateway_api_key = fields.Char(
        'API Key', required=True,
        groups='base.group_system',
        help="The gateway's AUTHENTICATION_API_KEY. Sent as the apikey header.",
    )
    instance_name = fields.Char(
        'Instance', required=True, default='nexgenn-main',
        groups='base.group_system',
        help='Which WhatsApp number on the gateway this session sends through.',
    )
    use_whatsapp = fields.Boolean(
        'WhatsApp', default=True,
        help="Untick to stop this database sending WhatsApp. The number stays "
             "connected for the vendor's other databases.")
    use_email = fields.Boolean(
        'Email', default=True,
        help="Untick to stop this database sending email through the gateway. "
             "369ai then falls back to its own SMTP settings, where the "
             "unsubscribe list and blocked words do not apply.")
    tenant_label = fields.Char(
        'Signed As',
        help='Client company name appended to outgoing messages. The number is '
             'shared between tenants, so without this the recipient cannot tell '
             'which business is writing to them.',
    )

    route_odoo_mail = fields.Boolean(
        'Send all 369ai email through the gateway', default=True,
        help="Every email 369ai sends - notifications, invoices, POS receipts - "
             "goes out on this vendor's mail account and is held to the same "
             "unsubscribe list, blocked words and caps as WhatsApp.\n\n"
             "Turn this off and modules fall back to 369ai's own SMTP settings, "
             "where none of those rules apply.",
    )

    # --- receiving ---------------------------------------------------
    webhook_secret = fields.Char(
        'Webhook Secret', copy=False, default=lambda self: uuid.uuid4().hex,
        groups='base.group_system',
        help='Random path segment that authenticates the gateway when it posts '
             'an incoming message. Regenerating it stops the old URL working.',
    )
    webhook_url = fields.Char(
        'Webhook URL', compute='_compute_webhook_url', groups='base.group_system',
        help='Where the gateway posts incoming messages. Register it with '
             'the button - it carries this database in a header.',
    )

    # --- protecting a shared number ---------------------------------
    throttled_until = fields.Datetime(
        'Throttled Until', copy=False, readonly=True,
        help="Set when the gateway answered HTTP 429. Sends are held until "
             "this passes instead of being retried into the same limit.",
    )
    send_delay_ms = fields.Integer(
        'Send Delay (ms)', default=1200,
        help='Pause the gateway applies between messages. Sending as fast as '
             'the API allows is what makes a number look automated.',
    )
    daily_cap = fields.Integer(
        'Daily Cap', default=0,
        help='Maximum outgoing messages per day from this database. 0 = no cap. '
             'Stops one tenant exhausting a number shared with others.',
    )
    dedupe_minutes = fields.Integer(
        'Duplicate Window (min)', default=5,
        help='Drop an identical message to the same number sent again inside '
             'this many minutes. 0 = send every time.',
    )
    allow_bulk = fields.Boolean(
        'Allow Bulk Sending', default=False,
        help='Required by whatsapp_broadcast. Bulk sending to lists is the '
             'single likeliest way to get a shared number banned, so it is off '
             'until deliberately enabled.',
    )

    # --- state, read from the gateway -------------------------------
    status = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('waiting_qr', 'Scan QR Code'),
        ('connected', 'Connected'),
        ('wrong_number', 'Wrong Phone Scanned'),
        ('error', 'Error'),
    ], string='Status', default='disconnected', readonly=True)
    phone_number = fields.Char('Connected Phone', readonly=True,
                              groups='base.group_system')
    # Fixed by the panel, shown here so nobody wonders which number and which
    # sender address this database is allowed to use. Never typed in Odoo.
    authorized_number = fields.Char(
        'Authorized Number', readonly=True, copy=False,
        help="The ONE phone number the panel allows this database to pair. "
             "A QR scanned with any other phone is logged out again.")
    authorized_email = fields.Char(
        'Sender Email', readonly=True, copy=False,
        help="Every email from this database goes out from this address, "
             "set on the panel. 369ai cannot replace it.")
    state_checked = fields.Datetime('State Checked', readonly=True, copy=False,
                                   groups='base.group_system')
    error_message = fields.Text('Last Error', readonly=True)

    is_activated = fields.Boolean(
        'Activated', compute='_compute_is_activated',
        help="Set up and able to send. The details behind it belong to the "
             "server, not to this database.")

    active = fields.Boolean(default=True)
    message_ids = fields.One2many(
        'whatsapp.message', 'session_id', string='Messages',
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )
    message_count = fields.Integer(
        compute='_compute_message_count', string='Messages',
    )

    # ----------------------------------------------------------
    # Computed
    # ----------------------------------------------------------
    def _compute_message_count(self):
        counts = dict(self.env['whatsapp.message']._read_group(
            [('session_id', 'in', self.ids)], ['session_id'], ['__count'],
        ))
        for rec in self:
            rec.message_count = counts.get(rec, 0)

    @api.depends('status')
    def _compute_is_activated(self):
        for rec in self:
            rec.is_activated = rec.status == 'connected'

    def _compute_webhook_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', '')
        for rec in self:
            rec.webhook_url = '%s/whatsapp/webhook/%s' % (
                base.rstrip('/'), rec.webhook_secret or '')

    # ----------------------------------------------------------
    # Self-setup
    # ----------------------------------------------------------
    @api.model
    def _decode_setup_key(self, value):
        """Return (gateway_url, token) from a setup key, or (None, None).

        A setup key is `wa1_` followed by base64url of "<panel url>|<token>".
        Anything else is treated as a plain token so a hand-configured session
        keeps working.
        """
        raw = (value or '').strip()
        if not raw.startswith('wa1_'):
            return None, None
        payload = raw[4:]
        # base64url without padding is what the panel emits; add it back rather
        # than requiring the panel to pad, which some encoders drop.
        payload += '=' * (-len(payload) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload.encode()).decode('utf-8')
        except (ValueError, UnicodeDecodeError):
            return None, None
        if '|' not in decoded:
            return None, None
        url, token = decoded.split('|', 1)
        url, token = url.strip().rstrip('/'), token.strip()
        if not url.startswith(('http://', 'https://')) or not token:
            return None, None
        return url, token

    def _apply_setup_key(self):
        """Unpack a pasted setup key into the fields it configures."""
        for session in self:
            url, token = self._decode_setup_key(session.gateway_api_key)
            if url:
                session.gateway_url = url
                session.gateway_api_key = token
        return True

    def action_fetch_config(self):
        """Ask the panel what this database should be using.

        Which number, the name it signs as, whether email is set up. Typing
        those by hand in every database is how they drift out of step with the
        panel - and the panel is the side that actually decides them.
        """
        self.ensure_one()
        self._apply_setup_key()
        config = self._fetch_panel_config()
        self._sync_mail_from(config)
        self._refresh_state(force=True)

        email = config.get('email') or {}
        wa = config.get('whatsapp') or {}
        message = _(
            "Vendor: %(vendor)s\nSends on: %(instance)s (%(state)s)\n"
            "Authorized number: %(number)s\nSigns as: %(label)s\n%(email)s",
            vendor=config.get('vendor') or '?',
            instance=config.get('instance') or _("no number assigned"),
            state=wa.get('state') or '?',
            number=('+' + wa['authorized_number']) if wa.get('authorized_number') else _("not set"),
            label=config.get('tenant_label') or '?',
            email=(_("Email: %s") % email.get('from')) if email.get('configured')
                  else _("Email: no mail account set up for this database yet"),
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _("Configured from the panel"), 'message': message,
                       'type': 'success', 'sticky': True},
        }

    def _fetch_panel_config(self):
        """GET /v1/config, telling the panel where this database's webhook
        is. The panel points the number's incoming messages at itself and
        forwards them to every database on that number, so the address only
        has to be known here."""
        self.ensure_one()
        config = self._gateway_call(
            'GET', '/v1/config', timeout=(5, 20),
            extra_headers={'X-Odoo-Webhook': self.webhook_url or ''}) or {}
        self._apply_panel_config(config)
        return config

    @api.constrains('gateway_api_key', 'active')
    def _check_key_once(self):
        """One key is one number. The panel sends a key's incoming messages to
        one session only: the same key in a second session would take the first
        one's messages (23 Nov 2026)."""
        for session in self.sudo():
            key = (session.gateway_api_key or '').strip()
            if not session.active or not key:
                continue
            mine = self._decode_setup_key(key)[1] or key
            for other in self.sudo().search([('active', '=', True), ('id', '!=', session.id),
                                             ('gateway_api_key', '!=', False)]):
                theirs = (other.gateway_api_key or '').strip()
                if (self._decode_setup_key(theirs)[1] or theirs) == mine:
                    raise ValidationError(_(
                        "This key already belongs to session '%(name)s'%(number)s. Every number has its own "
                        "key: copy the key of the new number from the panel.",
                        name=other.name,
                        number=(' (+%s)' % other.authorized_number) if other.authorized_number else ''))

    def _apply_panel_config(self, config):
        """What the panel decided for this database, copied onto the record
        so it can be read without a round trip. All read-only in the form."""
        self.ensure_one()
        instance = (config or {}).get('instance') or ''
        if instance:
            twin = self.sudo().search([('active', '=', True), ('id', '!=', self.id),
                                       ('instance_name', '=', instance)], limit=1)
            if twin:
                raise UserError(_(
                    "The panel gives this key the number of session '%s'. Every number has its own key and "
                    "its own session.", twin.name))
            if instance != self.instance_name:
                self._check_number_change(instance)
        wa = (config or {}).get('whatsapp') or {}
        email = (config or {}).get('email') or {}
        vals = {}
        if (config or {}).get('instance') and config['instance'] != self.instance_name:
            vals['instance_name'] = config['instance']
        if (config or {}).get('tenant_label') and config['tenant_label'] != self.tenant_label:
            vals['tenant_label'] = config['tenant_label']
        number = (wa.get('authorized_number') or '').strip()
        if number != (self.authorized_number or ''):
            vals['authorized_number'] = number
        address = (email.get('from') or '').strip() if email.get('configured') else ''
        if address != (self.authorized_email or ''):
            vals['authorized_email'] = address
        if vals:
            self.sudo().write(vals)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        sessions = super().create(vals_list)
        sessions._apply_setup_key()
        return sessions

    def _number_changed(self, old, new):
        """Hook: this session was the number `old` and is `new` now (digits)."""

    def write(self, vals):
        digits = lambda t: ''.join(c for c in (t or '') if c.isdigit())  # noqa: E731
        before = {s.id: digits(s.authorized_number) for s in self} if 'authorized_number' in vals else {}
        result = super().write(vals)
        for session in self if before else ():
            new = digits(session.authorized_number)
            if before[session.id] and new and new != before[session.id]:
                session._number_changed(before[session.id], new)
        # Only when the key itself was touched, or unpacking on every write
        # would fight with the values it just wrote.
        if 'gateway_api_key' in vals:
            self._apply_setup_key()
        return result

    # ----------------------------------------------------------
    # Talking to the gateway
    # ----------------------------------------------------------
    def _gateway_call(self, method, path, payload=None, timeout=GW_TIMEOUT, extra_headers=None):
        """One request to the gateway. Raises UserError with something a human
        can act on - never a bare requests traceback in the UI."""
        self.ensure_one()
        if not self.gateway_url or not self.gateway_api_key:
            raise UserError(_(
                "WhatsApp session '%(name)s' has no gateway URL or API key set.",
                name=self.name,
            ))
        url = '%s/%s' % (self.gateway_url.rstrip('/'), path.lstrip('/'))
        headers = {
            'apikey': self.gateway_api_key,
            'Content-Type': 'application/json',
            # Say which server and database this is. The panel accepts a key
            # only from the one server address and database name it was issued
            # to, so these are not decoration - a key copied into a different
            # database, or a database moved to a different server, is refused
            # until an administrator registers it.
            'X-Odoo-Db': self.env.cr.dbname,
            'X-Odoo-Url': self.env['ir.config_parameter'].sudo().get_param(
                'web.base.url', ''),
        }
        if extra_headers:
            headers.update(extra_headers)
        memo = key = None
        if method == 'POST' and path.startswith(('/message/', '/email/')):
            # a conflict with somebody else's change shows now, not after sending
            self.env.flush_all()
            memo = send_memo.current(self.env)
            if memo is not None:
                key = send_memo.send_key(self, path, payload)
                found, answer = memo.take(key)
                if found:
                    _logger.info("WhatsApp: this request sent it before it was repeated - not sent again")
                    return answer
        try:
            response = requests.request(
                method, url, headers=headers, json=payload, timeout=timeout)
        except requests.exceptions.RequestException as err:
            raise UserError(_(
                "Cannot reach the gateway at %(url)s.\n%(err)s",
                url=self.gateway_url, err=err,
            )) from err

        if response.status_code >= 400:
            detail = ''
            blocked_error = ''
            try:
                body = response.json()
                # `detail` first: the panel puts the sentence that names
                # the vendor and says what to do there, while `error` is only
                # the short category.
                detail = (body.get('detail') or body.get('message')
                          or body.get('error') or '')
                if isinstance(detail, (list, dict)):
                    detail = str(detail)
                blocked_error = body.get('error') or ''
            except ValueError:
                detail = (response.text or '')[:300]
            if response.status_code == 429:
                # The panel answers 429 for two unrelated things: genuine rate
                # limiting, and a policy refusal - an opt-out, blocked content,
                # or the daily cap. Waiting fixes the first and never the
                # second, and treating a cap breach as congestion is how "daily
                # cap reached (500/500)" spent an afternoon looking like a
                # network fault while every reply queued silently.
                if str(blocked_error).lower() == 'blocked':
                    _logger.warning(
                        "WhatsApp gateway refused a send on session '%s': %s",
                        self.name, detail or 'blocked')
                    raise WhatsAppBlocked(detail or _('The gateway refused it.'))
                # Retry-After is the gateway's own answer to "when?", so prefer
                # it over a number we invented. 60 s is the fallback.
                try:
                    wait = int(response.headers.get('Retry-After') or 60)
                except (TypeError, ValueError):
                    wait = 60
                wait = max(5, min(wait, 900))
                self.sudo().throttled_until = fields.Datetime.add(
                    fields.Datetime.now(), seconds=wait)
                _logger.warning(
                    "WhatsApp gateway rate-limited session '%s'; holding sends "
                    "for %ss.", self.name, wait)
            raise UserError(_(
                "The gateway refused the request (HTTP %(code)s).\n%(detail)s",
                code=response.status_code, detail=detail,
            ))
        try:
            answer = response.json()
        except ValueError:
            answer = {}
        if memo is not None:
            memo.put(key, answer)
        return answer

    def _check_number_change(self, instance):
        """Hook: may this session become another number?"""

    def action_connect_screen(self):
        """The QR of this session's own number (administrators)."""
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'whatsapp_gateway.connect', 'name': _("Connect a number"),
                'params': {'session_id': self.id}}

    def action_check_again(self):
        """Ask the panel now; a status says it, not a scan."""
        self.ensure_one()
        self._refresh_state(force=True)
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    def action_check_connection(self):
        lines = self.env['whatsapp.connect'].check_connection()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _("Check connection"), 'sticky': True,
            'type': 'success' if all(ok for ok, _text in lines) else 'warning',
            'message': '\n'.join(text for _ok, text in lines)}}

    def action_connect_new(self):
        return {'type': 'ir.actions.client', 'tag': 'whatsapp_gateway.connect', 'name': _("Connect a number")}

    def _refresh_state(self, force=False):
        """Ask the gateway whether the number is actually linked.

        The old code inferred this from in-process dictionaries, which is why
        the column could claim 'connected' long after the owning worker had
        died. There is now a single authority - the gateway - and this is how
        we ask it.
        """
        now = fields.Datetime.now()
        for session in self:
            if not force and session.state_checked:
                age = (now - session.state_checked).total_seconds()
                if age < STATE_TTL:
                    continue
            if not force and session._state_known(now):
                continue
            vals = {'state_checked': now}
            try:
                body = session._gateway_call(
                    'GET', '/instance/connectionState/%s' % session.instance_name,
                    timeout=(5, 10))
                state = ((body or {}).get('instance') or {}).get('state') or ''
                vals['status'] = _STATE_MAP.get(state, 'disconnected')
                # The panel says why a number cannot be used (wrong phone
                # scanned, nothing assigned, instance missing) in `detail`.
                vals['error_message'] = (body or {}).get('detail') or False
                # a link that drops for a moment is not one to scan again:
                # only what is closed at the next look too is disconnected
                if state == 'close' and session.status == 'connected' and not vals['error_message']:
                    vals['status'] = 'connecting'
            except UserError as err:
                # Unreachable or unknown instance. Say so on the record rather
                # than leaving a stale 'connected' behind for callers to trip on.
                vals['status'] = 'error'
                vals['error_message'] = str(err)
            session._save_state(vals)
        return True

    def _state_key(self):
        return self.env.cr.dbname, self.id

    def _state_known(self, now):
        """This process asked less than STATE_TTL ago: its answer, unless
        somebody wrote the number since."""
        self.ensure_one()
        if _state_direct(self.env):
            return False
        written, vals = _STATE_MEMO.get(self._state_key(), (None, None))
        if not vals or written != self.sudo().write_date or not 0 <= (now - vals['state_checked']).total_seconds() < STATE_TTL:
            return False
        self._state_into_cache(vals)
        return True

    def _state_into_cache(self, vals):
        session = self.sudo()
        for name, value in vals.items():
            session._fields[name]._update_cache(session, session._fields[name].convert_to_cache(value, session))

    def _save_state(self, vals):
        """Into the database after this transaction, in a moment of its own.
        Written with the message's own transaction, the status job and every
        other message collided on this one row and the message was sent again
        (23 Nov 2026). Written beside it while it still ran, the message of this
        very transaction collided with it: enquiry 1GG was dropped (24 Nov)."""
        self.ensure_one()
        session = self.sudo()
        if _state_direct(self.env):
            session.write(vals)
            return
        _STATE_MEMO[self._state_key()] = (session.write_date, dict(vals))
        cr = self.env.cr
        waiting = cr.cache.setdefault('whatsapp_gateway.state', {})
        if not waiting:
            registry = self.env.registry

            # the values stay with the function: postcommit.data is emptied by
            # a rollback before postrollback runs
            def after():
                todo = dict(waiting)
                waiting.clear()
                for session_id, state in todo.items():
                    _write_state(registry, session_id, state)
            cr.postcommit.add(after)
            cr.postrollback.add(after)
        waiting[session.id] = dict(vals)
        self._state_into_cache(vals)

    # ----------------------------------------------------------
    # The screens show the gateway's answer, not an old saved one
    # ----------------------------------------------------------
    def _refresh_state_for_screen(self):
        """At most once a minute (STATE_TTL). A screen always opens: a failure
        here only leaves the last saved status showing."""
        try:
            with self.env.cr.savepoint():
                self._refresh_state()
        except Exception as err:  # noqa: BLE001
            _logger.info("WhatsApp: status refresh for the screen skipped: %s", err)

    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        self.search(domain, offset=offset, limit=limit, order=order)._refresh_state_for_screen()
        return super().web_search_read(
            domain, specification, offset=offset, limit=limit, order=order, count_limit=count_limit)

    def web_read(self, specification):
        self._refresh_state_for_screen()
        return super().web_read(specification)

    # Odoo runs these two on a read-only connection (@api.readonly on the
    # originals), where saving the fresh status would fail.
    web_search_read._readonly = False
    web_read._readonly = False

    @api.model
    def get_connected_session(self, preferred_id=None):
        """The session that can actually send right now.

        Returns an empty recordset when nothing is linked; the caller decides
        what to do about that.
        """
        sessions = self.sudo().search([('active', '=', True)])
        sessions._refresh_state()
        connected = sessions.filtered(lambda s: s.status == 'connected')
        if preferred_id:
            try:
                preferred = connected.filtered(lambda s: s.id == int(preferred_id))
            except (TypeError, ValueError):
                preferred = self.browse()
            if preferred:
                return preferred[:1]
        return connected[:1]

    def action_test_connection(self):
        """Button on the form: prove the URL, the key and the instance."""
        self.ensure_one()
        self._refresh_state(force=True)
        if self.status == 'connected':
            body = self._gateway_call('GET', '/instance/fetchInstances')
            phone = ''
            for entry in (body if isinstance(body, list) else []):
                inst = entry.get('instance') or entry
                if inst.get('name') == self.instance_name or \
                        inst.get('instanceName') == self.instance_name:
                    phone = inst.get('ownerJid') or inst.get('owner') or ''
                    break
            if phone:
                self.sudo().phone_number = phone.split('@')[0]
            message = _("Connected. Sending as %s.", self.phone_number or self.instance_name)
            kind = 'success'
        else:
            message = _(
                "Gateway reached but instance '%(inst)s' is %(state)s. "
                "Pair it once on the gateway, then test again.",
                inst=self.instance_name, state=self.status,
            )
            kind = 'warning'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _("WhatsApp Gateway"), 'message': message,
                       'type': kind, 'sticky': False},
        }

    def _sync_mail_from(self, config=None):
        """Point Odoo's sender at the vendor's mail account on the gateway.

        Without `mail.default.from` and `mail.catchall.domain` Odoo will not
        compose a message at all, and the failure looks like a mail server
        problem when it is really a missing setting. Reading them from the panel
        keeps one answer in one place.
        """
        self.ensure_one()
        if config is None:
            try:
                config = self._fetch_panel_config()
            except UserError:
                return False
        else:
            self._apply_panel_config(config)
        email = ((config or {}).get('email') or {})
        address = (email.get('from') or '').strip()
        if not email.get('configured') or '@' not in address:
            return False
        local, domain = address.rsplit('@', 1)
        params = self.env['ir.config_parameter'].sudo()
        changed = []
        for key, value in (('mail.default.from', local),
                           ('mail.catchall.domain', domain)):
            if params.get_param(key) != value:
                params.set_param(key, value)
                changed.append('%s=%s' % (key, value))
        # Without this the author of every message is OdooBot, and Odoo shows
        # odoobot@example.com as the sender in the chatter even though the
        # gateway sends from the vendor's account.
        company = self.env.company.sudo()
        if not (company.email or '').strip():
            company.email = address
            changed.append('company.email=%s' % address)

        # OdooBot authors most automated messages, and Odoo derives the From
        # from the author. Its shipped address is a placeholder on a domain
        # that does not exist, so it appears as the sender of everything until
        # it is replaced. Only touched while it is still that placeholder.
        bot = self.env.ref('base.partner_root', raise_if_not_found=False)
        if bot and (bot.email or '').strip().lower().endswith('@example.com'):
            bot.sudo().email = address
            changed.append('odoobot=%s' % address)
        if changed:
            _logger.info("Mail sender taken from the gateway: %s", ', '.join(changed))
        return True

    @api.model
    def mail_from(self):
        """The address this database should send email as, or ''.

        Asked of the gateway once and cached in the usual Odoo parameters, so
        every module can call it without a network round trip and a database
        that was only ever handed a setup key still knows the answer.
        """
        params = self.env['ir.config_parameter'].sudo()
        session = self.sudo().search(
            [('active', '=', True), ('use_email', '=', True), ('gateway_api_key', '!=', False)],
            limit=1)
        if session:
            # The panel decides the sender for this database. company.email is
            # whatever somebody typed in Odoo and is deliberately NOT a fallback.
            if session.authorized_email:
                return session.authorized_email
            if session._sync_mail_from() and session.authorized_email:
                return session.authorized_email
            local = params.get_param('mail.default.from')
            domain = params.get_param('mail.catchall.domain')
            return '%s@%s' % (local, domain) if local and domain else ''
        local = params.get_param('mail.default.from')
        domain = params.get_param('mail.catchall.domain')
        if local and domain:
            return '%s@%s' % (local, domain)
        return self.env.company.email or ''

    def action_view_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("WhatsApp Messages"),
            'res_model': 'whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id},
        }

    def action_send_message_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Send WhatsApp Message"),
            'res_model': 'whatsapp.send.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_id': self.id},
        }

    # ----------------------------------------------------------
    # Protecting the number
    # ----------------------------------------------------------
    @staticmethod
    def _clean_phone(phone):
        """Remove formatting. Evolution wants digits only, no leading '+'."""
        if not phone:
            return ''
        for ch in ('+', ' ', '-', '(', ')'):
            phone = phone.replace(ch, '')
        return phone

    def _sign(self, message):
        """Left to the gateway - Odoo no longer adds the name itself.

        Both sides used to append one. That did not double up only because the
        gateway skips its own label when the text already contains it, which
        holds right up until the two names differ - and then every message
        carries both. The gateway is the side that knows which vendor a database
        belongs to, and it applies the name where no Odoo can get it wrong, so
        it signs alone. `tenant_label` is kept as a read-only mirror of what the
        panel is configured to use.
        """
        return message

    def _policy_block(self, phone, message):
        """Why this message must not go out, or None to send it.

        These checks exist because the number is shared: anything that gets it
        banned takes down every tenant at once, with no appeal for an
        unofficial client.
        """
        self.ensure_one()
        Message = self.env['whatsapp.message'].sudo()

        if self.env['whatsapp.optout'].sudo().is_opted_out(phone):
            return _("%s has opted out of WhatsApp messages.") % phone

        if self.daily_cap > 0:
            today = fields.Datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0)
            sent_today = Message.search_count([
                ('session_id', '=', self.id),
                ('direction', '=', 'outgoing'),
                ('status', 'in', ('sent', 'delivered', 'read')),
                ('create_date', '>=', today),
            ])
            if sent_today >= self.daily_cap:
                return _(
                    "Daily cap of %(cap)s messages reached (%(sent)s sent today).",
                    cap=self.daily_cap, sent=sent_today,
                )

        if self.dedupe_minutes > 0 and message:
            typed = self.env.context.get('wa_typed')
            cutoff = fields.Datetime.subtract(
                fields.Datetime.now(), **({'seconds': TYPED_REPEAT} if typed else {'minutes': self.dedupe_minutes}))
            duplicate = Message.search_count([
                ('session_id', '=', self.id),
                ('direction', '=', 'outgoing'),
                ('phone', '=', phone),
                ('message', '=', message),
                ('status', 'in', ('sent', 'delivered', 'read')),
                ('create_date', '>=', cutoff),
            ])
            if duplicate and typed:
                return _("The same message was sent just now. Wait %s seconds to send it again.", TYPED_REPEAT)
            if duplicate:
                return _(
                    "Identical message already sent to %(phone)s in the last "
                    "%(mins)s minutes.", phone=phone, mins=self.dedupe_minutes,
                )
        return None

    def _log(self, phone, message, status, wa_message_id=False, retry=None):
        vals = {
            'session_id': self.id,
            'phone': phone,
            'message': message,
            'direction': 'outgoing',
            'status': status,
            'wa_message_id': wa_message_id or False,
        }
        # `retry` carries what a document needs to be sent again as a document.
        if retry:
            vals.update(retry)
        Message = self.env['whatsapp.message'].sudo()
        if status != 'sent':
            return Message.create(vals)
        # It has left. What the database refuses now must neither lose its row
        # nor leave the caller in a broken transaction (Ref 1GG, 24 Nov 2026).
        memo = send_memo.current(self.env)
        if memo and wa_message_id and memo.rows.get(wa_message_id):
            return Message.browse(memo.rows[wa_message_id])
        self.env.flush_all()
        try:
            with self.env.cr.savepoint(flush=False):
                message = Message.create(vals)
                self.env.flush_all()
                return message
        except psycopg2.OperationalError as err:
            _logger.info("WhatsApp: message to %s is written on its own (%s)", phone, str(err).split('\n')[0])
            self.env.invalidate_all(flush=False)
        with self.env.registry.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '3s'")
            message_id = Message.with_env(api.Environment(cr, self.env.uid, dict(self.env.context))).sudo().create(vals).id
        if memo and wa_message_id:
            memo.rows[wa_message_id] = message_id
        return Message.browse(message_id)

    def _retry_soon(self):
        """Ask the retry cron to run now instead of on its 5-minute tick.

        A gateway blip used to cost the customer five minutes even when the
        gateway came back a second later.
        """
        if self.throttled_until and self.throttled_until > fields.Datetime.now():
            return  # the cron would find nothing it is allowed to send
        cron = self.env.ref('whatsapp_gateway.ir_cron_whatsapp_sync',
                            raise_if_not_found=False)
        if cron:
            try:
                cron.sudo()._trigger()
            except Exception:  # noqa: BLE001 - never fail a send over this
                _logger.warning("Could not trigger the WhatsApp retry cron.")

    # ----------------------------------------------------------
    # Sending
    # ----------------------------------------------------------
    def _send_payload(self, endpoint, payload, phone, log_text,
                      queue_on_failure=True, retry=None):
        """POST one message and record the outcome.

        On an unreachable gateway the message is kept as 'pending' *and* the
        error is raised: the caller gets a clear failure, and nothing is lost -
        _cron_sync_status retries pending messages once the gateway is back.

        queue_on_failure=False is for an attempt that has a fallback behind it.
        Queuing every layer of a fallback chain is how one menu turns into
        three queued copies, all of which are then delivered.
        """
        self.ensure_one()
        # Check first, because an unpaired instance answers a send with a bare
        # HTTP 500 - technically a failure, but it tells whoever pressed the
        # button nothing about what is wrong or where to fix it. This costs
        # nothing in the normal case: _refresh_state caches for STATE_TTL.
        self._refresh_state()
        if self.status != 'connected':
            why = ''
            if self.status == 'wrong_number':
                why = _("The QR was scanned with the wrong phone; only %(n)s is allowed. "
                        "Scan again in the panel with that phone.\n\n",
                        n=('+' + self.authorized_number) if self.authorized_number else _("the authorized number"))
            elif self.error_message:
                why = self.error_message + "\n\n"
            if queue_on_failure:
                self._log(phone, log_text, 'pending', retry=retry)
                self._retry_soon()
                raise WhatsAppQueued(_(
                    "WhatsApp is not connected for session '%(name)s'.\n\n%(why)s"
                    "The message is queued and will go out once the connection "
                    "is back.",
                    name=self.name, why=why,
                ))
            raise UserError(_(
                "WhatsApp is not connected for session '%(name)s'.\n\n"
                "The number is paired on the gateway, not in 369ai - check "
                "instance '%(inst)s' at %(url)s.\n"
                "The message is queued and will go out once the connection "
                "is back.",
                name=self.name, inst=self.instance_name, url=self.gateway_url,
            ))
        try:
            body = self._gateway_call(
                'POST', '/message/%s/%s' % (endpoint, self.instance_name), payload)
        except WhatsAppBlocked as err:
            # Refused on policy. Queuing it would retry something that is meant
            # not to go, and hide the reason behind a pending row.
            self._log(phone, log_text, 'blocked')
            raise
        except UserError as err:
            if queue_on_failure:
                self._log(phone, log_text, 'pending', retry=retry)
                self._retry_soon()
                raise WhatsAppQueued(str(err)) from err
            raise
        wa_id = ((body or {}).get('key') or {}).get('id') or ''
        self._log(phone, log_text, 'sent', wa_id)
        _logger.info("WhatsApp %s sent to %s via %s", endpoint, phone,
                     self.instance_name)
        return True

    def send_message(self, phone, message):
        """Send a text message. The signature every consuming module calls."""
        self.ensure_one()
        if not self.use_whatsapp:
            _logger.info("WhatsApp is switched off for session '%s'.", self.name)
            return False
        phone_clean = self._clean_phone(phone)
        if not phone_clean:
            raise UserError(_("No phone number provided."))

        body = self._sign(message)
        reason = self._policy_block(phone_clean, body)
        if reason:
            _logger.info("WhatsApp to %s blocked: %s", phone_clean, reason)
            self._log(phone_clean, body, 'blocked')
            return False

        return self._send_payload('sendText', {
            'number': phone_clean,
            'text': body,
            'delay': self.send_delay_ms,
        }, phone_clean, body)

    def _send_media(self, phone, data, mediatype, filename='', caption='',
                    mimetype='', log_text='', retry=None):
        """Shared by send_image and send_document."""
        self.ensure_one()
        phone_clean = self._clean_phone(phone)
        if not phone_clean:
            raise UserError(_("No phone number provided."))

        if isinstance(data, bytes):
            data = base64.b64encode(data).decode()
        elif isinstance(data, str) and data.startswith('data:'):
            data = data.split(',', 1)[-1]

        reason = self._policy_block(phone_clean, '')
        if reason:
            _logger.info("WhatsApp media to %s blocked: %s", phone_clean, reason)
            self._log(phone_clean, log_text, 'blocked')
            return False

        payload = {
            'number': phone_clean,
            'mediatype': mediatype,
            'media': data,
            'delay': self.send_delay_ms,
        }
        if caption:
            payload['caption'] = self._sign(caption)
        if filename:
            payload['fileName'] = filename
        if mimetype:
            payload['mimetype'] = mimetype
        return self._send_payload('sendMedia', payload, phone_clean, log_text,
                                  retry=retry)

    def send_image(self, phone, image_data, caption=''):
        """Send an image."""
        return self._send_media(
            phone, image_data, 'image', caption=caption,
            log_text=("\U0001F4F7 Image: %s" % caption) if caption else "\U0001F4F7 Image")

    def send_document(self, phone, file_data, filename,
                      caption='', mimetype='application/pdf', retry=None):
        """Send a document (PDF, Excel, ...)."""
        log_text = "\U0001F4CE %s" % filename + (" - %s" % caption if caption else "")
        return self._send_media(
            phone, file_data, 'document', filename=filename, caption=caption,
            mimetype=mimetype, log_text=log_text, retry=retry)

    def send_odoo_report(self, phone, report_xmlid, record, caption=''):
        """Render a QWeb PDF and send it."""
        self.ensure_one()
        try:
            pdf_content, _content_type = self.env[
                'ir.actions.report'
            ]._render_qweb_pdf(report_xmlid, record.ids)
        except Exception as err:
            raise UserError(_("Failed to generate report: %s") % err) from err
        filename = "%s.pdf" % (record.display_name or 'document')
        # Remember what this was, so a retry can send the PDF rather than a
        # sentence describing it.
        return self.send_document(phone, pdf_content, filename, caption, retry={
            'retry_report_xmlid': report_xmlid,
            'retry_res_model': record._name,
            'retry_res_id': record.id,
            'retry_filename': filename,
            'retry_caption': caption or '',
        })

    def send_buttons(self, phone, body, buttons, include_numbers=True):
        """Send tappable quick-reply buttons, falling back to numbered text.

        Tappable buttons are unreliable on the unofficial WhatsApp Web protocol
        regardless of which library sends them, and Evolution rejects more than
        three outright. The numbered form is therefore the path that always
        works; buttons are the enhancement, not the mechanism. Callers pass
        include_numbers=False only when they are confident.
        """
        self.ensure_one()
        phone_clean = self._clean_phone(phone)
        if not phone_clean:
            raise UserError(_("No phone number provided."))

        numbered = "\n".join(
            "%d. %s" % (i, b['title']) for i, b in enumerate(buttons, 1))
        text_body = body
        if include_numbers and buttons:
            text_body = "%s\n\n%s\n\n%s" % (
                body, numbered,
                _("Tap a button, reply with the number, or type what you need."))

        if len(buttons) <= MAX_REPLY_BUTTONS:
            payload = {
                'number': phone_clean,
                'title': '',
                'description': self._sign(text_body),
                'buttons': [{
                    'type': 'reply',
                    'displayText': b['title'],
                    'id': b['id'],
                } for b in buttons],
                'delay': self.send_delay_ms,
            }
            try:
                # queue_on_failure=False: the numbered fallback below will
                # queue if it needs to. Queuing here as well is how one menu
                # becomes two deliveries.
                return self._send_payload(
                    'sendButtons', payload, phone_clean, body,
                    queue_on_failure=False)
            except UserError as err:
                _logger.info(
                    "WhatsApp buttons rejected for %s (%s) - sending as text.",
                    phone_clean, err)
        else:
            _logger.info(
                "WhatsApp: %s options is more than the %s tappable buttons "
                "allowed - sending as numbered text.",
                len(buttons), MAX_REPLY_BUTTONS)

        # Numbered fallback. Force the numbers on: without buttons to tap,
        # an unnumbered list leaves the recipient nothing to reply with.
        if not include_numbers and buttons:
            text_body = "%s\n\n%s" % (body, numbered)
        try:
            return self.send_message(phone_clean, text_body)
        except UserError:
            # send_message has already queued it, so it is not lost. The
            # exception is swallowed on purpose: callers that keep their own
            # text fallback - wa.report.engine.send_wa_buttons is one - treat a
            # raise as "buttons failed, send the menu myself", and queue a
            # second copy of a menu that is already waiting to go out.
            _logger.info(
                "WhatsApp: menu for %s queued; not raising, so the caller "
                "does not queue it again.", phone_clean)
            return False

    # ----------------------------------------------------------
    # Email, through the same gateway
    # ----------------------------------------------------------
    def send_email(self, to, subject, body_html='', body_text='',
                   cc=None, bcc=None, reply_to=None, attachments=None):
        """Send one email through the gateway.

        Same key, same server address, same database name as WhatsApp - and so
        the same unsubscribe list, blocked words and caps. A customer who asked
        this vendor to stop should not have to ask again on the other channel,
        which is exactly what happens when the two run through separate systems.

        The vendor's mail credentials live on the gateway and are never sent
        here, so a database cannot read them or send as anybody else.

        attachments: [{'filename', 'content' (base64 str or bytes), 'mimetype'}]
        Returns True when accepted, False when a rule stopped it.
        """
        self.ensure_one()
        if not self.use_email:
            _logger.info("Gateway email is switched off for session '%s'.", self.name)
            return False
        recipient = (to or '').strip()
        if not recipient:
            raise UserError(_("No email address provided."))

        payload = {
            'to': recipient,
            'subject': subject or '',
            'body_html': body_html or '',
            'body_text': body_text or '',
        }
        if cc:
            payload['cc'] = cc
        if bcc:
            payload['bcc'] = bcc
        if reply_to:
            payload['reply_to'] = reply_to
        if attachments:
            prepared = []
            for item in attachments:
                content = item.get('content')
                if isinstance(content, bytes):
                    content = base64.b64encode(content).decode()
                prepared.append({
                    'filename': item.get('filename') or 'attachment',
                    'content': content or '',
                    'mimetype': item.get('mimetype') or '',
                })
            payload['attachments'] = prepared

        try:
            body = self._gateway_call('POST', '/email/send', payload,
                                      timeout=(5, 60))
        except UserError as err:
            # A rule doing its job - an unsubscribe, a blocked word or a cap -
            # is not a fault. Raising would have callers retry something that
            # must not be retried.
            if 'Blocked' in str(err):
                _logger.info("Email to %s blocked: %s", recipient, err)
                return False
            raise
        self.env['whatsapp.message'].sudo().create({
            'session_id': self.id,
            'channel': 'email',
            'phone': recipient,
            'message': '%s\n\n%s' % (subject or '', body_text or body_html or ''),
            'direction': 'outgoing',
            'status': 'sent',
            'wa_message_id': (body or {}).get('id', ''),
        })
        _logger.info("Email sent to %s (%s)", recipient, (body or {}).get('id', ''))
        return True

    # ----------------------------------------------------------
    # Retry + housekeeping
    # ----------------------------------------------------------
    def _flush_outbox(self, limit=50):
        """Retry messages left pending by an unreachable gateway."""
        self.ensure_one()
        if self.status != 'connected':
            return 0
        if self.throttled_until and self.throttled_until > fields.Datetime.now():
            # Retrying now would only extend the limit and burn the cron run.
            return 0
        queued = self.env['whatsapp.message'].sudo().search([
            ('session_id', '=', self.id),
            ('direction', '=', 'outgoing'),
            ('status', '=', 'pending'),
        ], order='id', limit=limit)
        sent = 0
        for msg in queued:
            try:
                if msg.retry_report_xmlid and msg.retry_res_model and msg.retry_res_id:
                    body = self._resend_document(msg)
                else:
                    body = self._gateway_call(
                        'POST', '/message/sendText/%s' % self.instance_name, {
                            'number': msg.phone,
                            'text': msg.message or '',
                            'delay': self.send_delay_ms,
                        })
            except WhatsAppBlocked as err:
                # Refused on policy - it will be refused every time.
                msg.write({'status': 'blocked'})
                _logger.warning("WhatsApp outbox: %s refused: %s",
                                msg.phone, err)
                continue
            except UserError as err:
                # Count the attempt. Without a cap a message that can never
                # send is retried for ever, and each attempt costs a call to
                # the gateway - four dead test messages once held every live
                # send on this server for four days.
                msg.retry_count += 1
                if msg.retry_count >= MAX_SEND_ATTEMPTS:
                    msg.write({'status': 'failed'})
                    _logger.warning(
                        "WhatsApp outbox: giving up on message %s after %s "
                        "attempts: %s", msg.id, msg.retry_count, err)
                else:
                    _logger.warning(
                        "WhatsApp outbox: %s still failing (attempt %s/%s): %s",
                        msg.phone, msg.retry_count, MAX_SEND_ATTEMPTS, err)
                break  # gateway is down; leave the rest queued
            except Exception as err:  # noqa: BLE001
                # A record that has gone, or a report that will not render, is
                # not a gateway problem: retrying it every five minutes for ever
                # never helps and hides the rows that would.
                _logger.exception("WhatsApp outbox: giving up on message %s: %s",
                                  msg.id, err)
                msg.write({'status': 'failed'})
                continue
            msg.write({
                'status': 'sent',
                'wa_message_id': ((body or {}).get('key') or {}).get('id') or '',
            })
            sent += 1
        if sent:
            _logger.info("WhatsApp outbox: flushed %s message(s).", sent)
        return sent

    def _resend_document(self, msg):
        """Re-render and re-send a pending document, as a document.

        This is the whole point of the retry_* fields. Sending `msg.message`
        instead - which is what happened before - delivers the log line
        ("PDF invoice.pdf - Thank you...") and leaves the customer without the
        file, while the row is written 'sent' and nobody is any the wiser.
        """
        self.ensure_one()
        record = self.env[msg.retry_res_model].browse(msg.retry_res_id).exists()
        if not record:
            raise ValueError("source record %s,%s is gone"
                             % (msg.retry_res_model, msg.retry_res_id))
        pdf_content, _content_type = self.env[
            'ir.actions.report'
        ]._render_qweb_pdf(msg.retry_report_xmlid, record.ids)
        payload = {
            'number': msg.phone,
            'mediatype': 'document',
            'media': base64.b64encode(pdf_content).decode(),
            'mimetype': 'application/pdf',
            'fileName': msg.retry_filename or 'document.pdf',
            'delay': self.send_delay_ms,
        }
        if msg.retry_caption:
            payload['caption'] = self._sign(msg.retry_caption)
        return self._gateway_call(
            'POST', '/message/sendMedia/%s' % self.instance_name, payload)

    @api.model
    def _cron_sync_status(self):
        """Refresh every session's state and retry anything queued."""
        for session in self.sudo().search([('active', '=', True)]):
            session._refresh_state(force=True)
            # Also re-reads the sender address, so changing the vendor's mail
            # account in the panel reaches every database on its own.
            if session.gateway_api_key:
                session._sync_mail_from()
            if session.status == 'connected':
                session._flush_outbox()
        return True
