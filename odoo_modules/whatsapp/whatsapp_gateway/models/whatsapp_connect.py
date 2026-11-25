"""Connect a number: one screen instead of the panel, a key, a session, an
employee session and the group list (23 Nov 2026).

A database can have several WhatsApp numbers, one session each, each with its
own key. The administrator picks the country and types the number; this asks
the panel for that number's key with the key of a session the database has
already, makes the session, shows the QR and goes on when it is connected. The
panel decides whether a database may add numbers at all, and how many.

Other modules add to it: whatsapp_employee_tracker the employee,
sales_automation the groups.
"""
import logging
import re

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import config

try:
    import phonenumbers
except ImportError:                     # length 6-15 for every country then
    phonenumbers = None

_logger = logging.getLogger(__name__)

PENDING = 'pending-'


class WhatsAppConnect(models.AbstractModel):
    _name = 'whatsapp.connect'
    _description = 'Connect a WhatsApp number'

    # ------------------------------------------------------------ who
    @api.model
    def _check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only an administrator can connect a WhatsApp number."))

    @api.model
    def _save(self):
        """What the panel made must not be lost by something that fails later."""
        self.env.flush_all()
        if not config['test_enable']:
            self.env.cr.commit()

    # ------------------------------------------------------------ numbers
    @api.model
    def _rule(self, country):
        """{'dial': '971', 'min': 9, 'max': 9, 'zero': False, 'example': '50...'}"""
        code = (country.code or '').upper()
        rule = {'dial': str(country.phone_code or ''), 'min': 6, 'max': 15, 'zero': False, 'example': '',
                'amin': 4, 'amax': 15}
        if not phonenumbers or code not in phonenumbers.SUPPORTED_REGIONS:
            return rule
        meta = phonenumbers.PhoneMetadata.metadata_for_region(code)
        lengths = []
        for desc in (meta.mobile, meta.general_desc):
            lengths = [n for n in (desc.possible_length or ()) if n > 0] if desc else []
            if lengths:
                break
        rule['dial'] = str(phonenumbers.country_code_for_region(code))
        if lengths:
            rule.update(min=min(lengths), max=max(lengths))
        # landlines too, where a contact's phone is typed
        every = [n for n in (meta.general_desc.possible_length or ()) if n > 0] if meta.general_desc else []
        rule.update(amin=min(every + [rule['min']]), amax=max(every + [rule['max']]))
        example = phonenumbers.example_number_for_type(code, phonenumbers.PhoneNumberType.MOBILE)
        if example:
            rule['example'] = phonenumbers.national_significant_number(example)
            rule['zero'] = rule['example'].startswith('0')
        return rule

    @api.model
    def _countries(self):
        rows = []
        for country in self.env['res.country'].sudo().search([('phone_code', '!=', 0)]):
            rows.append(dict(self._rule(country), id=country.id, code=country.code, name=country.name))
        return sorted(rows, key=lambda r: r['name'])

    @api.model
    def _number(self, country, typed, landline=False):
        """The whole number, digits only with the country code - or UserError."""
        if not country:
            raise UserError(_("Choose the country."))
        rule = self._rule(country)
        if landline:
            rule = dict(rule, min=rule['amin'], max=rule['amax'])
        text = (typed or '').strip()
        if re.search(r'[^0-9\s]', text):
            raise UserError(_("Type the number with digits only."))
        text = re.sub(r'\D', '', text)
        if len(text) > rule['max'] and text.startswith(rule['dial']):
            text = text[len(rule['dial']):]
        if not rule['zero']:
            text = text.lstrip('0')
        if not rule['min'] <= len(text) <= rule['max']:
            wanted = str(rule['max']) if rule['min'] == rule['max'] else '%s-%s' % (rule['min'], rule['max'])
            raise UserError(_("A number in %(country)s has %(wanted)s digits after +%(dial)s; %(n)s were typed.",
                              country=country.name, wanted=wanted, dial=rule['dial'], n=len(text)))
        whole = rule['dial'] + text
        if phonenumbers and (country.code or '').upper() in phonenumbers.SUPPORTED_REGIONS:
            try:
                parsed = phonenumbers.parse('+' + whole, None)
            except phonenumbers.NumberParseException as err:
                raise UserError(_("+%s is not a phone number.", whole)) from err
            if not phonenumbers.is_valid_number(parsed):
                raise UserError(_("+%(n)s is not a valid number in %(country)s. Please check it.",
                                  n=whole, country=country.name))
            whole = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164).lstrip('+')
        return whole

    # ------------------------------------------------------------ a phone box
    # Any employee's screen: nothing but the countries and the library's word.
    @api.model
    def _check_staff(self):
        if not self.env.user._is_internal():
            raise AccessError(_("Only for employees."))

    @api.model
    def phone_countries(self):
        self._check_staff()
        country = self.env.company.country_id
        return {'countries': self._countries(), 'country': country.id if country.phone_code else False}

    @api.model
    def phone_check(self, country_id, number, landline=False):
        self._check_staff()
        try:
            whole = self._number(self.env['res.country'].sudo().browse(int(country_id or 0)).exists(), number,
                                 landline=landline)
        except UserError as err:
            return {'ok': False, 'error': str(err.args[0])}
        return {'ok': True, 'pretty': self._pretty(whole)}

    @api.model
    def phone_split(self, values):
        """{saved value: {country, national, pretty}}; {} for what is not surely one
        whole number - that stays a plain box and is never rewritten."""
        self._check_staff()
        return {value: self._split(value) for value in {str(v) for v in (values or [])[:500]}}

    @api.model
    def _split(self, value):
        text = (value or '').strip()
        if not phonenumbers or not re.fullmatch(r'\+?[0-9\s().\-]+', text):
            return {}
        digits = re.sub(r'\D', '', text)
        if not 6 <= len(digits) <= 15:
            return {}
        try:
            whole = phonenumbers.parse('+' + digits, None)
        except phonenumbers.NumberParseException:
            return {}
        if not phonenumbers.is_valid_number(whole):
            return {}
        if not text.startswith('+'):
            # "9876543210" without its code must not become another country's
            code = (self.env.company.country_id.code or '').upper()
            if code in phonenumbers.SUPPORTED_REGIONS:
                try:
                    if phonenumbers.is_valid_number(phonenumbers.parse(digits, code)) \
                            and not digits.startswith(str(phonenumbers.country_code_for_region(code))):
                        return {}
                except phonenumbers.NumberParseException:
                    pass
        pretty = phonenumbers.format_number(whole, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        region = phonenumbers.region_code_for_number(whole)
        country = self.env['res.country'].sudo().search([('code', '=', region)], limit=1) if region else False
        national = phonenumbers.national_significant_number(whole)
        if not country or self._rule(country)['dial'] + national != digits:
            return {'pretty': pretty}
        return {'country': country.id, 'national': national, 'pretty': pretty}

    @api.model
    def _pretty(self, digits):
        """"+971 50 123 4567"."""
        digits = ''.join(c for c in str(digits or '') if c.isdigit())
        if not digits:
            return ''
        if phonenumbers:
            try:
                return phonenumbers.format_number(
                    phonenumbers.parse('+' + digits, None), phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            except phonenumbers.NumberParseException:
                pass
        return '+' + digits

    # ------------------------------------------------------------ the panel
    @api.model
    def _sessions(self):
        sessions = self.env['whatsapp.session'].sudo().search([('active', '=', True), ('gateway_api_key', '!=', False)])
        return sessions.sorted(lambda s: (s.status != 'connected', s.id))

    @api.model
    def _askers(self):
        """Who may ask the panel: the numbers that are on, then those turned off
        in Odoo. The panel lets such a key ask and add, never send."""
        off = self.env['whatsapp.session'].sudo().search([
            ('active', '=', False), ('removed', '=', False), ('gateway_api_key', '!=', False)])
        return self._sessions() + off.filtered(lambda s: not s.gateway_api_key.startswith('removed-'))

    @staticmethod
    def _last_line(err):
        text = str(err.args[0] if getattr(err, 'args', None) else err)
        return text.strip().split('\n')[-1]

    @api.model
    def _panel_numbers(self):
        """(numbers it may have, numbers it has, why not, free ones)."""
        why = ''
        for session in self._askers():
            try:
                body = session._gateway_call('GET', '/v1/numbers', timeout=(5, 15)) or {}
            except UserError as err:
                why = why or self._last_line(err)
                continue
            return (int(body.get('may_add') or 0), body.get('numbers') or [], '',
                    [n for n in body.get('free') or [] if n.get('authorized_number')])
        return 0, [], why, []

    @api.model
    def _from_panel(self, numbers, free):
        """What the panel has ready: added there for this database and not in
        Odoo yet, and what no database uses."""
        here = set(self.env['whatsapp.session'].sudo().with_context(active_test=False).search(
            [('removed', '=', False)]).mapped('authorized_number'))
        ready = [n for n in numbers if n.get('in_use') is False and n.get('authorized_number')
                 and n['authorized_number'] not in here]
        return ready + [n for n in free if n['authorized_number'] not in {r['authorized_number'] for r in ready}]

    @api.model
    def _free_numbers(self):
        """Numbers of the vendor, linked in the panel, that Odoo does not have."""
        _may, numbers, _why, free = self._panel_numbers()
        return self._from_panel(numbers, free)

    @api.model
    def _without_owner(self):
        """Hook: sessions of this database that nobody has been given yet."""
        return self.env['whatsapp.session']

    @api.model
    def _scanned(self, free):
        rows = [{'id': 's%s' % s.id, 'session_id': s.id, 'number': s.authorized_number,
                 'pretty': self._pretty(s.authorized_number) or s.name, 'label': s.name,
                 'connected': s.status == 'connected', 'here': True} for s in self._without_owner()]
        here = {r['number'] for r in rows}
        rows += [{'id': 'f%s' % n['authorized_number'], 'session_id': False, 'number': n['authorized_number'],
                  'pretty': self._pretty(n['authorized_number']), 'label': n.get('label') or '',
                  'connected': n.get('state') == 'open', 'here': False}
                 for n in free if n['authorized_number'] not in here]
        return sorted(rows, key=lambda r: not r['connected'])

    @api.model
    def _ask_panel(self, number, label):
        """The setup key of a new number of this database."""
        if not self._askers():
            raise UserError(_("This database has no WhatsApp session yet. Paste its first key from the panel."))
        why = ''
        for session in self._askers():
            try:
                body = session._gateway_call('POST', '/v1/numbers', {'number': number, 'label': label},
                                             timeout=(5, 60)) or {}
            except UserError as err:
                why = why or self._last_line(err)
                continue
            if body.get('key'):
                return body['key']
        raise UserError(_("Not added in the panel: %s", why))

    # ------------------------------------------------------------ the screen
    @api.model
    def start(self, session_id=None):
        self._check_admin()
        # a list that cannot be read must not close the screen
        may, numbers, why, free = self._panel_numbers()
        has_session = bool(self._askers())
        if has_session and why:
            self._keep_try('open', '', why)
        country = self.env.company.country_id
        return {
            'countries': self._countries(),
            'country': country.id if country.phone_code else False,
            'companies': [{'id': c.id, 'name': c.name} for c in self.env.companies],
            'company': self.env.company.id,
            'has_session': has_session, 'database': self.env.cr.dbname,
            'has_groups': 'sa.sales.group' in self.env,
            'may_add': may, 'used': len(numbers),
            'can_add': bool(has_session and may > len(numbers)),
            'scanned': self._scanned(self._from_panel(numbers, free if may > len(numbers) else []) if has_session and may else []),
            'why': why if has_session else '',
            'session': self.state(session_id) if session_id and not self._is_off(session_id) else False,
            'off': self._off_row(session_id) if session_id and self._is_off(session_id) else False,
        }

    @api.model
    def _is_off(self, session_id):
        session = self.env['whatsapp.session'].sudo().browse(int(session_id or 0)).exists()
        return bool(session and not session.active and not session.removed)

    @api.model
    def _off_row(self, session_id):
        """A number that is off: picked already, with the question about it."""
        session = self.env['whatsapp.session'].sudo().browse(int(session_id))
        number = ''.join(c for c in (session.authorized_number or '') if c.isdigit())
        return {'id': 'o%s' % session.id, 'off_session_id': session.id, 'session_id': False, 'number': number,
                'pretty': self._pretty(number) or session.name, 'label': session.name, 'connected': False,
                'owner': self._owner(session)[1], 'ask_on': self._ask_on(session, number)}

    @api.model
    def _ask_on(self, session, number):
        return {'number': self._pretty(number) or session.name, 'name': session.name, 'owner': self._owner(session)[1],
                'waiting': len(session._waiting_messages())}

    @api.model
    def check_number(self, country_id, number):
        """"+971 50 123 4567", or what is wrong with it."""
        self._check_admin()
        try:
            whole = self._number(self.env['res.country'].sudo().browse(int(country_id or 0)).exists(), number)
        except UserError as err:
            return {'ok': False, 'error': str(err.args[0])}
        return {'ok': True, 'pretty': self._pretty(whole)}

    @api.model
    def look(self, country_id, number):
        """Is it here, or in the panel, already? {'where', 'text', 'ok', 'key'}:
        ok - it can be connected; key - only with its key from the panel."""
        self._check_admin()
        try:
            whole = self._number(self.env['res.country'].sudo().browse(int(country_id or 0)).exists(), number)
        except UserError as err:
            return {'where': 'bad', 'ok': False, 'text': str(err.args[0])}
        session = self._session_of(whole)
        if session:
            if session.status == 'connected':
                return {'where': 'here', 'ok': False, 'text': _("Already connected: %s", session.name)}
            return {'where': 'here', 'ok': True, 'text': _("Already in this database, go on to scan")}
        off = self._off_session(whole)
        if off:
            return {'where': 'off', 'ok': True, 'owner': self._owner(off)[1],
                    'text': _("Turned off here, you can turn it on: %s", off.name)}
        body, why = {}, ''
        for asked in self._askers():
            try:
                body = asked._gateway_call('GET', '/v1/numbers?check=%s' % whole, timeout=(3, 8)) or {}
            except UserError as err:
                why = why or self._last_line(err)
                _logger.info("Connect a number: the panel was not asked: %s", self._last_line(err))
                continue
            why = ''
            break
        where = body.get('check')
        if where == 'here' and body.get('in_use'):
            return {'where': 'here', 'ok': True, 'key': True,
                    'text': _("The panel has it in use for this database already; its key is needed.")}
        answer = {
            'new': (True, _("New number, it will be added to this database")),
            'free': (True, _("Already in the panel and free, it will be used")),
            'here': (True, _("Already in the panel for this database, it will be used")),
            'off': (False, _("It is turned off for this database in the panel.")),
            'elsewhere': (False, self._elsewhere()),
        }.get(where)
        if not answer:
            if why:
                self._keep_try('number', whole, why)
                return {'where': '', 'ok': True, 'text': _("Could not check in the panel: %s", why)}
            return {'where': '', 'ok': True, 'text': _("Could not check in the panel now; checked again on Next") if self._askers() else ''}
        if where == 'elsewhere':
            self._keep_try('number', whole, answer[1])
        return {'where': where, 'ok': answer[0], 'text': answer[1]}

    @api.model
    def _elsewhere(self):
        return _("Used by another database. Remove it there first, or assign it to this database in the panel.")

    @api.model
    def _keep_try(self, step, number, error, apart=False):
        """A failed try, for the list. Apart: what follows is undone, this is not."""
        Try = self.env['whatsapp.connect.try'].sudo()
        try:
            if apart and not config['test_enable']:
                with self.env.registry.cursor() as cr:
                    Try.with_env(Try.env(cr=cr))._keep(step, number, error)
            else:
                with self.env.cr.savepoint():
                    Try._keep(step, number, error)
        except Exception as err:  # noqa: BLE001 - the list never stops the screen
            _logger.warning("Connect a number: a failed try was not kept: %s", err)

    @api.model
    def _typed(self, vals):
        """The number of a try, as far as it can be told."""
        digits = ''.join(c for c in str(vals.get('free_number') or '') if c.isdigit())
        if digits:
            return digits
        session = self.env['whatsapp.session'].sudo().browse(
            int(vals.get('off_session_id') or vals.get('session_id') or 0)).exists()
        if session:
            return session.authorized_number or ''
        try:
            return self._number(self.env['res.country'].sudo().browse(int(vals.get('country_id') or 0)).exists(),
                                vals.get('number'))
        except UserError:
            return ''

    @api.model
    def add(self, vals):
        """Step 1: the number, its key and its session."""
        self._check_admin()
        vals = dict(vals or {})
        number = self._typed(vals)
        try:
            return self._add_number(vals)
        except UserError as err:
            self._keep_try('number', number, str(err.args[0] if err.args else err), apart=True)
            raise

    @api.model
    def _add_number(self, vals):
        if vals.get('session_id'):
            return self._give(vals)
        if vals.get('off_session_id'):
            session = self.env['whatsapp.session'].sudo().browse(int(vals['off_session_id'])).exists()
            if not session or session.removed:
                raise UserError(_("That number is no longer there. Open the screen again."))
            if session.active:
                return self._first_state(session, vals)
            number = ''.join(c for c in (session.authorized_number or '') if c.isdigit())
            if not number:
                raise UserError(_("%s has no number yet. Use Connect a number.", session.name))
            other = session._same_number_on()
            if other:
                raise UserError(_("%(number)s is already connected: %(session)s.", number=self._pretty(number), session=other.name))
            if not vals.get('turn_on'):
                return {'ask_on': self._ask_on(session, number)}
            vals['company'] = session.company_id or self.env.company
            return self._turn_on_here(session, number, vals)
        free = ''.join(c for c in str(vals.get('free_number') or '') if c.isdigit())
        if free:
            if free not in {n['authorized_number'] for n in self._free_numbers()}:
                raise UserError(_("%s is no longer free. Open the screen again.", self._pretty(free)))
            vals.pop('key', None)
        country = self.env['res.country'].sudo().browse(int(vals.get('country_id') or 0)).exists()
        number = free or self._number(country, vals.get('number'))
        session = self._session_of(number)
        if session:
            state = self.state(session.id)
            if state['connected']:
                raise UserError(_("%(number)s is already connected: %(session)s.",
                                  number=self._pretty(number), session=session.name))
            return state                    # left halfway: go on with it
        off = self._off_session(number)
        if off and not vals.get('turn_on'):
            return {'ask_on': self._ask_on(off, number)}
        company = self.env['res.company'].browse(int(vals.get('company_id') or 0)).exists() or self.env.company
        if company not in self.env.companies and company != self.env.company:
            raise AccessError(_("You cannot use that company."))
        vals['company'] = company
        if off:
            return self._turn_on_here(off, number, vals)
        self._before(vals, number)
        label = (vals.get('label') or '').strip()[:60] or self._label(vals, number)
        key = (vals.get('key') or '').strip() or self._ask_panel(number, label)
        session = self._make_session(label, key, number, company, vals)
        self._after(vals, session, number)
        if not vals.get('key'):
            self._save()
        try:
            self._load(session)
        except UserError as err:
            other = re.search(r'it is the key of database (.+?), but this is', self._last_line(err))
            if not vals.get('key') or not other:
                raise
            raise UserError(_(
                "This key is for database %(other)s. Open %(here)s in the panel, assign the number there and copy the key from that page.",
                other=other.group(1), here=self.env.cr.dbname)) from err
        return self._first_state(session, vals)

    # ------------------------------------------------------------ one that is off
    @api.model
    def _owner(self, session):
        """Hook: (id, name) of who has this number."""
        return False, ''

    @api.model
    def _panel_says(self, number):
        for session in self._askers():
            try:
                return session._gateway_call('GET', '/v1/numbers?check=%s' % number, timeout=(3, 8)) or {}
            except UserError as err:
                _logger.info("Connect a number: the panel was not asked: %s", self._last_line(err))
        return {}

    @api.model
    def _turn_on_here(self, session, number, vals):
        """On again. What waited is never sent. An entry without a key of its
        own gets a new one; its groups stay off then."""
        session._drop_waiting()
        says = self._panel_says(number)
        own_key = says.get('check') in (None, 'off') or (says.get('check') == 'here' and says.get('in_use'))
        if own_key and not session._key_of_another():
            session._turn_on()
            if not self._owner(session)[0]:
                self._before(vals, number)
                self._after(vals, session, number)
            return self._first_state(session, vals)
        if says.get('check') == 'elsewhere':
            raise UserError("%s: %s" % (self._pretty(number), self._elsewhere()))
        owner = self._owner(session)[0]
        if owner:
            vals['employee_id'] = owner
        self._new_key(session, number, vals['company'], vals)
        return self._first_state(session, vals)

    @api.model
    def _new_key(self, session, number, company, vals=None):
        session._number_off(removed=True)
        if vals is not None:
            self._before(vals, number)
        key = self._ask_panel(number, session.name)
        session.write({'gateway_api_key': key, 'instance_name': PENDING + number, 'authorized_number': number,
                       'company_id': company.id, 'active': True, 'removed': False, 'status': 'disconnected'})
        if vals is not None:
            self._after(vals, session, number)
        self._save()
        self._load(session)

    @api.model
    def _give(self, vals):
        """A number that is here already gets its owner."""
        session = self.env['whatsapp.session'].sudo().browse(int(vals['session_id'])).exists()
        if not session or session not in self._without_owner():
            raise UserError(_("That number has been given to somebody already."))
        number = session.authorized_number or ''
        company = session.company_id or self.env.company
        vals['company'] = company
        self._before(vals, number)
        self._after(vals, session, number)
        return self.state(session.id)

    @api.model
    def _session_of(self, number):
        return self.env['whatsapp.session'].sudo().search(
            [('active', '=', True), ('authorized_number', '=', number)], limit=1)

    @api.model
    def _off_session(self, number):
        return self.env['whatsapp.session'].sudo().search(
            [('active', '=', False), ('removed', '=', False), ('authorized_number', '=', number)], limit=1)

    @api.model
    def _label(self, vals, number):
        return self._pretty(number)

    @api.model
    def _before(self, vals, number):
        """Hook: refuse before anything is made."""

    @api.model
    def _after(self, vals, session, number):
        """Hook: what belongs to the new session."""

    @api.model
    def _may_return(self, session, vals):
        """Hook: may this removed session of the same number be used again?"""
        return True

    @api.model
    def _make_session(self, label, key, number, company, options=None):
        others = self._sessions()
        vals = {
            'name': label, 'gateway_api_key': key, 'company_id': company.id,
            'instance_name': PENDING + number, 'authorized_number': number,
            # one mail account per database: the first session's
            'use_email': not others, 'route_odoo_mail': not others,
        }
        if others and not key.startswith('wa1_'):
            vals['gateway_url'] = others[0].gateway_url
        Session = self.env['whatsapp.session'].sudo()
        for old in Session.search([('active', '=', False), ('removed', '=', True),
                                   ('authorized_number', '=', number)], order='id desc'):
            if self._may_return(old, options or {}):
                old.write(dict(vals, active=True, removed=False))     # with its history
                return old
        return Session.create(vals)

    @api.model
    def _load(self, session):
        """The panel's word on this session: its number, and where its
        incoming messages go."""
        wanted = session.authorized_number
        config_ = session._fetch_panel_config()
        got = ((config_ or {}).get('whatsapp') or {}).get('authorized_number') or ''
        if wanted and got and wanted != got:
            # the wrong key was pasted: nothing of it is kept
            raise UserError(_("That key belongs to %(got)s, not to %(wanted)s.",
                              got=self._pretty(got), wanted=self._pretty(wanted)))

    @api.model
    def _first_state(self, session, vals):
        """The scan step opens at once; the QR is asked for right after."""
        if not (vals or {}).get('quick'):
            return self.state(session.id)
        out = {'id': session.id, 'name': session.name, 'number': self._pretty(session.authorized_number),
               'company': session.company_id.name or '', 'connected': False, 'status': session.status, 'qr': '', 'error': '',
               'wrong': False, 'first': True}
        out.update(self._state_extra(session))
        return out

    @api.model
    def state(self, session_id):
        """Step 2: connected, or the QR to scan."""
        self._check_admin()
        session = self.env['whatsapp.session'].sudo().browse(int(session_id or 0)).exists()
        if not session:
            raise UserError(_("That WhatsApp session is no longer there."))
        error = ''
        try:
            if (session.instance_name or '').startswith(PENDING):
                self._load(session)
            session._refresh_state(force=True)
        except UserError as err:
            error = self._last_line(err)
        out = {'id': session.id, 'name': session.name, 'number': self._pretty(session.authorized_number),
               'company': session.company_id.name or '', 'connected': session.status == 'connected',
               'status': session.status, 'qr': '', 'error': error, 'wrong': session.status == 'wrong_number'}
        out.update(self._state_extra(session))
        if not out['connected'] and not error:
            try:
                body = session._gateway_call('GET', '/v1/qr', timeout=(5, 30)) or {}
                qr = str(body.get('qr') or '')
                out['qr'] = qr if qr.startswith('data:image/') else ''
                out['wrong'] = body.get('state') == 'wrong_number'
                if not session.active:
                    out['error'] = _("This number is turned off. Turn it on first.")
                elif not out['qr']:
                    out['error'] = {
                        'open': _("The panel says this number is connected already. If it does not go on, press Load Settings on its page."),
                        'missing': _("The gateway does not know this number. Use Full reset on its page."),
                        'unreachable': _("The WhatsApp gateway cannot be reached now."),
                    }.get(body.get('state'), '')
            except UserError as err:
                out['error'] = self._last_line(err)
        if out['wrong'] or out['error']:
            self._keep_try('scan', session.authorized_number, out['error'] or _("Scanned with another phone"))
        return out

    @api.model
    def check_connection(self):
        """[(ok, text)]: can the panel be asked, may numbers be added, how many are left."""
        self._check_admin()
        askers = self._askers()
        if not askers:
            return [(False, _("This database has no WhatsApp number yet. Its first key comes from the panel."))]
        lines, body = [], None
        for session in askers:
            try:
                answer = session._gateway_call('GET', '/v1/numbers', timeout=(5, 15)) or {}
            except UserError as err:
                lines.append((False, "%s: %s" % (session.name, self._last_line(err))))
                continue
            body = answer if body is None else body
        if body is None:
            return [(False, _("The panel could not be asked."))] + lines
        may, used = int(body.get('may_add') or 0), len(body.get('numbers') or [])
        lines.insert(0, (True, _("The panel answers.")))
        if not may:
            lines.append((False, _("Adding numbers from our software is off for this database. The panel administrator allows it.")))
        else:
            lines.append((may > used, _("%(used)s of %(may)s numbers used, %(left)s left.",
                                        used=used, may=may, left=max(0, may - used))))
        return lines

    @api.model
    def _state_extra(self, session):
        """Hook: {'employee': ...}"""
        return {}

    @api.model
    def groups(self, session_id):
        """Step 3, hook: the groups to choose from. Nothing here."""
        self._check_admin()
        return {'available': False, 'groups': []}

    @api.model
    def finish(self, session_id, group_ids=None):
        """Hook: switch the chosen groups on; what is ready and what is not."""
        self._check_admin()
        state = self.state(session_id)
        return {'lines': [{'ok': state['connected'], 'text': _("Connected: %s", state['number'])}]}
