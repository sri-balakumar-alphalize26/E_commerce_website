# -*- coding: utf-8 -*-
"""The customer's address book, in the WhatsApp group (owner, 7 Oct 2026).

What the customer sees:

* one saved address - it is used, and shown in the details check as before;
* two or more - every address written out in full and numbered, then
  "➕ Add a new address" and "✏️ Edit an address" as the last two numbers;
* a new address is asked one short question at a time, with the fields the
  369 Mart shop uses: Home / Work / Other, house / flat, road / area,
  landmark, pincode (an Indian pincode fills the city and state), state,
  alternate number and the map location;
* every choice is a poll to tap, and also works typed as its number; every
  optional question ends with "1. ⏭ Skip". CANCEL stays a word on purpose,
  so a stray digit can never cancel an order.

One address book with the shop: an address is a contact under the customer
(the shop's `mart369_address` keeps them as `type='other'`, the default one
as `delivery`). When that module is installed its label, landmark and
alternate-phone fields are written too, so an address saved here shows in the
shop app and the other way round. Without it the same values live in our own
fields.

This runs as its own little conversation (`sa_book_step`), separate from the
name / details ladder: the ladder hands over when it reaches the address and
gets control back with the chosen address on the order. The private-chat
ladder (`auto_reply_hooks`) is untouched.
"""
import json
import logging
import re
from datetime import timedelta

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

SKIP_WORDS = {'1', 'skip', 'no', 'none', 'nil', 'na', 'n/a', '-', 'nothing', 'no landmark',
              'illa', 'illai', 'vendam', 'no need', 'not needed', 'later', 'remove', 'delete'}
_ICONS = {'home': '\U0001F3E0', 'work': '\U0001F4BC'}
_PIN_ICON = '\U0001F4CD'
_ADD = '➕'
_EDIT = '✏️'
_DONE = '✅'


def _plain(name):
    """'Jammu & Kashmir' and 'Jammu and Kashmir' are the same state."""
    return re.sub(r'[^a-z]', '', (name or '').lower().replace('&', 'and'))


def _key(text):
    return re.sub(r'[^a-z0-9]+', '', (text or '').lower())


class ResPartnerAddressBook(models.Model):
    _inherit = 'res.partner'

    sa_addr_label = fields.Char(
        'Address Label',
        help="What the customer calls this address on WhatsApp - Home, Work, "
             "Parents. Shared with the 369 Mart shop's Address type when "
             "that module is installed.")
    sa_alt_phone = fields.Char(
        'Alternate Phone',
        help="A second number for the rider to try, given on WhatsApp.")

    # ---- reading, ours first then the shop's ----
    def _sa_shop_book(self):
        return 'mart369_label' in self._fields

    def _sa_label(self):
        self.ensure_one()
        own = self.sa_addr_label or (self.mart369_label if self._sa_shop_book() else '')
        return (own or '').strip() or _("Home")

    def _sa_landmark(self):
        self.ensure_one()
        own = self.sa_delivery_note if 'sa_delivery_note' in self._fields else ''
        if not own and self._sa_shop_book():
            own = self.mart369_landmark
        return (own or '').strip()

    def _sa_alt(self):
        self.ensure_one()
        own = self.sa_alt_phone or (self.mart369_alt_phone if self._sa_shop_book() else '')
        return (own or '').strip()

    def _sa_icon(self):
        self.ensure_one()
        return _ICONS.get(self._sa_label().lower(), _PIN_ICON)

    def _sa_addr_text(self):
        """No. 12, Green Park Apartments, MG Road, near bus stand, Chennai,
        Tamil Nadu 600001 - nothing said twice (old addresses were typed as
        one line that already holds the city and pincode)."""
        self.ensure_one()
        parts, seen = [], ''
        landmark = self._sa_landmark()
        if landmark and not landmark.lower().startswith(('near', 'opp', 'behind', 'next to', 'beside')):
            landmark = _("near %s") % landmark
        for piece in (self.street, self.street2, landmark,
                      self.city, ' '.join(x for x in (self.state_id.name, self.zip) if x)):
            piece = (piece or '').strip().strip(',')
            if piece and piece.lower() not in seen:
                parts.append(piece)
                seen += ' ' + piece.lower()
        return ', '.join(parts)

    def _sa_addr_short(self):
        """House + area, cut for a poll option: "14, Bypass Road"."""
        self.ensure_one()
        return ', '.join(x for x in (self.street, self.street2) if x)[:45]

    def _sa_addr_title(self):
        """One line for a list: 🏠 Home - No. 12, Green Park ..."""
        self.ensure_one()
        # The receiver's name too, as the website's address cards show it.
        who = self._sa_receiver_name()
        return '%s %s - %s%s' % (self._sa_icon(), self._sa_label(),
                                 ('%s, ' % who) if who else '', self._sa_addr_text())


class SaGroupRequestAddressBook(models.Model):
    _inherit = 'sa.group.request'

    sa_book_step = fields.Selection([
        ('choose', 'Choosing an address'),
        ('edit_pick', 'Choosing the address to edit'),
        ('edit_field', 'Choosing what to change'),
        ('label', 'Home / Work / Other'),
        ('label_other', 'Name of the address'),
        ('line', 'House / flat / building'),
        ('area', 'Road / area / colony'),
        ('landmark', 'Landmark'),
        ('pin', 'Pincode'),
        ('city', 'City / town'),
        ('state', 'State'),
        ('alt', 'Alternate number'),
        ('location', 'Map location'),
    ], 'Address Book Step', copy=False, readonly=True,
        help="Where the address questions in the group have got to.")
    sa_book_json = fields.Text(copy=False, readonly=True)
    sa_book_asked_on = fields.Datetime(copy=False, readonly=True)
    sa_book_done = fields.Boolean(
        copy=False, readonly=True,
        help="The address of this order was chosen (or added) in the group.")

    _SA_BOOK_TTL_H = 6

    # ------------------------------------------------------------------
    # The book
    # ------------------------------------------------------------------
    def _sa_address_book(self, customer):
        """Every address of the customer: home (the contact itself, when it
        has a street) then the delivery / other contacts under it - the shop's
        default first, then oldest first. Both types: a second 'delivery'
        child used to push the first one out of the list."""
        customer = customer.sudo()
        if not customer:
            return customer
        kids = customer.child_ids.filtered(
            lambda c: c.active and c.type in ('delivery', 'other') and c.street)
        if customer._sa_shop_book():
            kids = kids.sorted(lambda c: (not c.mart369_default, c.id))
        else:
            kids = kids.sorted('id')
        # The shop copies the default address onto the contact as well: the
        # same place twice. The saved address wins - it carries the label,
        # landmark and alternate number; the contact copy has none of them.
        seen, saved = set(), customer.browse()
        for kid in kids:
            k = self._sa_addr_dedupe_key(kid)
            if k not in seen:
                seen.add(k)
                saved |= kid
        if customer.street and self._sa_addr_dedupe_key(customer) not in seen:
            return customer | saved
        return saved

    @staticmethod
    def _sa_addr_dedupe_key(addr):
        return '%s|%s|%s' % (_key(addr.street), _key(addr.street2), _key(addr.zip))

    def _sa_saved_addresses(self, partner):
        return self._sa_address_book(partner)

    def _sa_book_customer(self):
        self.ensure_one()
        if self.order_id and self.order_id.partner_id:
            return self.order_id.partner_id.sudo()
        return self._sa_address_partner()

    def _sa_profile_complete(self, partner):
        """A customer whose addresses all live in the shop's book (none on the
        contact itself) is complete too - they would otherwise be asked their
        name on every order."""
        if super()._sa_profile_complete(partner):
            return True
        if not partner or not partner._sa_real_name():
            return False
        return bool(self._sa_address_book(partner).filtered('zip'))

    def _sa_use_address(self, order, addr):
        """Point the order (and its open delivery jobs) at `addr`. The name
        and phone of the customer fill an address that has none - an address
        the shop saved for someone else ("deliver to Ravi") keeps its own."""
        order = order.sudo()
        main = order.partner_id
        if addr != main:
            fill = {}
            if not addr.name:
                fill['name'] = main.name
            if not addr.phone:
                fill['phone'] = main.phone
            if fill:
                addr.write(fill)
        if order.partner_shipping_id != addr:
            order.write({'partner_shipping_id': addr.id})
        jobs = order.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel') and p.picking_type_code == 'outgoing'
            and p.partner_id != addr)
        if jobs:
            jobs.write({'partner_id': addr.id})
        return addr

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def _sa_book_state(self):
        self.ensure_one()
        try:
            return json.loads(self.sa_book_json or '{}') or {}
        except ValueError:
            return {}

    def _sa_book_set(self, step=None, state=None, **extra):
        vals = dict(extra)
        if step is not None:
            vals['sa_book_step'] = step or False
        if state is not None:
            vals['sa_book_json'] = json.dumps(state) if state else False
        self.sudo().write(vals)

    def _sa_book_ref(self):
        self.ensure_one()
        return self.ref_code or (self.order_id.name if self.order_id else '') or str(self.id)

    # ------------------------------------------------------------------
    # Asking
    # ------------------------------------------------------------------
    def _sa_book_options_send(self, body, options, intro=''):
        """A numbered choice: a poll to tap, the same numbers typed also work.
        `intro` is long text (the full addresses, the states) sent first:
        a poll question is kept short so WhatsApp shows it whole."""
        self.ensure_one()
        titles = ['%d %s' % (i, o['title']) for i, o in enumerate(options, 1)]
        if not intro and len(body) > 230:
            intro, body = body, _("Tap one \U0001F447")
        if intro:
            self._say(intro)
        if 2 <= len(options) <= 10:
            return self._ask(body, [{'id': 'sa_book_%s' % o['key'], 'title': t[:100]}
                                    for o, t in zip(options, titles)])
        lines = '\n'.join('%d. %s' % (i, o['title']) for i, o in enumerate(options, 1))
        return self._say('%s\n\n%s\n\n%s' % (body, lines, _("Reply with the number.")))

    def _sa_book_pick(self, text, options, digits=True):
        """The option `text` is: its number (when `digits`), a tapped poll
        title, or a word. `digits=False` on the questions whose answer is
        typed - a house number "1" is a house number, not option 1."""
        answer = (text or '').strip()
        low = answer.lower().strip(' .!*')
        if re.fullmatch(r'\d{1,2}', low):
            if not digits:
                return None
            n = int(low)
            return options[n - 1]['key'] if 1 <= n <= len(options) else None
        k = _key(answer)
        for i, o in enumerate(options, 1):
            if k and (k == _key('%d %s' % (i, o['title'])) or k == _key(o['title'])):
                return o['key']
        m = re.match(r'^\s*(\d{1,2})\s+\S', answer)
        if m and 1 <= int(m.group(1)) <= len(options) and _key(answer) == _key(
                '%s %s' % (m.group(1), options[int(m.group(1)) - 1]['title']))[:len(_key(answer))]:
            return options[int(m.group(1)) - 1]['key']
        for o in options:
            if low in o.get('words', ()):
                return o['key']
        return None

    def _sa_book_back_opt(self):
        return {'key': 'back', 'title': _("\u2B05\uFE0F Back"), 'words': ('back', 'go back', 'previous')}

    def _sa_book_choose_options(self, book, back):
        opts = [{'key': 'a%d' % a.id, 'title': '%s %s - %s' % (a._sa_icon(), a._sa_label(),
                                                                a._sa_addr_short())}
                for a in book[:10]]
        opts.append({'key': 'add', 'title': _("%s Add a new address") % _ADD,
                     'words': ('new', 'add', 'add new', 'new address')})
        opts.append({'key': 'edit', 'title': _("%s Edit an address") % _EDIT,
                     'words': ('edit', 'change', 'edit address')})
        opts.append(self._sa_book_back_opt())
        return opts

    _SA_EDIT_FIELDS = [
        ('label', '\U0001F3F7 Home / Work name'),
        ('line', '\U0001F3E2 House / flat'),
        ('area', '\U0001F6E3 Road / area'),
        ('landmark', '\U0001F4CD Landmark'),
        ('pin', '\U0001F4EE Pincode'),
        ('alt', '\U0001F4DE Alternate number'),
        ('location', '\U0001F5FA Location'),
        ('done', '✅ Done'),
    ]

    def _sa_book_edit_options(self):
        return [{'key': k, 'title': _(t), 'words': (('done', 'ok', 'save', 'finish') if k == 'done' else ())}
                for k, t in self._SA_EDIT_FIELDS] + [self._sa_book_back_opt()]

    _SA_TYPED_STEPS = ('label_other', 'line', 'area', 'pin', 'city', 'state')
    _SA_OPTIONAL_STEPS = ('landmark', 'alt', 'location')

    def _sa_book_label_options(self, with_back):
        opts = [{'key': 'home', 'title': _("\U0001F3E0 Home"), 'words': ('home', 'house')},
                {'key': 'work', 'title': _("\U0001F4BC Work"), 'words': ('work', 'office')},
                {'key': 'other', 'title': _("\U0001F4CD Other"), 'words': ('other', 'others')}]
        return opts + ([self._sa_book_back_opt()] if with_back else [])

    def _sa_book_edit_pick_options(self, book):
        return [{'key': 'a%d' % a.id, 'title': '%s %s - %s' % (a._sa_icon(), a._sa_label(),
                                                               a._sa_addr_short())}
                for a in book[:11]] + [self._sa_book_back_opt()]

    def _sa_book_step_options(self, step, st, book=None):
        """The tap options of a step. Typed questions get them too: Back and
        Stop (or Skip on the optional ones), so nobody has to type a word to
        move around."""
        editing = st.get('mode') == 'edit'
        if book is None:
            book = self._sa_address_book(self._sa_book_customer())
        back = self._sa_book_back_opt()
        if step == 'choose':
            return self._sa_book_choose_options(book, st.get('back'))
        if step == 'edit_pick':
            return self._sa_book_edit_pick_options(book)
        if step == 'edit_field':
            return self._sa_book_edit_options()
        if step == 'label':
            return self._sa_book_label_options(bool(book) or editing)
        if step in self._SA_OPTIONAL_STEPS:
            if editing:
                first = {'location': _("\u23ED Keep it as it is"),
                         }.get(step) or (_("\U0001F5D1 Remove it") if self._sa_book_current(st, step)
                                         else _("\u23ED Skip"))
            else:
                first = _("\u23ED Skip")
            return [{'key': 'skip', 'title': first, 'words': tuple(SKIP_WORDS)}, back]
        if editing:
            return [back, {'key': 'done', 'title': _("\u2705 Done"), 'words': ('done', 'save')}]
        stop = (_("\u2716\uFE0F Stop adding") if book else _("\U0001F504 Start over"))
        return [back, {'key': 'stop', 'title': stop, 'words': ('stop', 'start over')}]

    def _sa_book_ask(self, note=''):
        """Put the question for the current step in the group - always as a
        poll with a way back. `note` (or context `sa_reask_note`) is put on
        top when the same question comes back, with an invisible ending so
        the gateway's five-minute duplicate filter lets it through."""
        self.ensure_one()
        st = self._sa_book_state()
        step = self.sa_book_step
        self.sudo().write({'sa_book_asked_on': fields.Datetime.now()})
        note = note or self.env.context.get('sa_reask_note') or ''
        top_note = ('%s\n\n' % note) if note else ''
        tail = ('\u200b' * (fields.Datetime.now().second % 9 + 1)) if note else ''
        bad = (st.get('bad') or '').strip()[:40]
        sorry = _("Sorry, I can't use *%s*.\n\n") % bad if bad else ''
        ref = self._sa_book_ref()
        customer = self._sa_book_customer()
        book = self._sa_address_book(customer)
        editing = st.get('mode') == 'edit'
        head = (_("\u270F\uFE0F *Changing %s*") % st.get('target_label', '')) if editing \
            else _("%(add)s *New address* \u00b7 #%(ref)s", add=_ADD, ref=ref)
        opts = self._sa_book_step_options(step, st, book)
        lines_of = lambda recs: '\n'.join('%d. %s' % (i, a._sa_addr_title()) for i, a in enumerate(recs, 1))

        if step == 'choose':
            extra = '\n'.join('%d. %s' % (i, o['title'])
                              for i, o in enumerate(opts, 1) if o['key'] in ('add', 'edit', 'back'))
            if st.get('back') == 'order':
                top = _("\U0001F3E0 Where should order *#%s* be delivered?") % ref
            else:
                top = _("\U0001F4CD *Your saved addresses*\n(pick one to change it)")
            intro = '%s%s%s\n\n%s\n%s' % (top_note, sorry, top, lines_of(book[:10]), extra)
            body = (_("Tap one \U0001F447 (you sent *%s*)") % bad) if bad \
                else _("Tap one \U0001F447 (or reply with the number)")
            return self._sa_book_options_send(body + tail, opts, intro=intro)
        if step == 'edit_pick':
            intro = '%s%s%s\n\n%s' % (top_note, sorry, _("\u270F\uFE0F Which address do you want to change?"),
                                       lines_of(book[:11]))
            body = (_("Tap the one to change \U0001F447 (you sent *%s*)") % bad) if bad \
                else _("Tap the one to change \U0001F447")
            return self._sa_book_options_send(body + tail, opts, intro=intro)
        if step == 'edit_field':
            done = (_("\u2714 %s updated.\n\n") % st['last']) if st.get('last') else ''
            intro = '%s%s%s%s\n\n%s' % (top_note, sorry, done, head, self._sa_book_preview(st))
            return self._sa_book_options_send(_("What do you want to change? \U0001F447") + tail, opts,
                                              intro=intro)
        if step == 'label':
            return self._sa_book_options_send(
                '%s%s%s\n\n%s%s' % (top_note, sorry, head,
                                      _("\U0001F3F7 Is this address Home, Work or something else?"), tail),
                opts)
        texts = {
            'label_other': _("What should we call this address? (like *Parents* or *Shop*)"),
            'line': _("\U0001F3E2 House / flat / building?\n(like *Flat 12, Park View Apartments*)"),
            'area': _("\U0001F6E3 Street or area?\n(like *Main Street, City Centre*)"),
            'landmark': _("\U0001F4CD A landmark the rider can see?\n(like *next to the pharmacy*)"),
            'pin': _("\U0001F4EE Postcode?"),
            'city': _("\U0001F3D9 City / town?"),
            'state': _("\U0001F5FA Which state? Reply with its number or name from the list above."),
            'alt': _("\U0001F4DE Another number to call if %s doesn't answer?") % (customer.phone or _("yours")),
            'location': _("\U0001F4CD Share your location so the rider finds the door: "
                          "tap \U0001F4CE \u2192 *Location* \u2192 *Send your current location*."),
        }
        if step == 'pin' and bad:
            sorry = _("*%(bad)s* is not a postcode here - I need %(hint)s.\n\n",
                      bad=bad, hint=self._sa_pincode_hint(self._sa_book_pin_partner(st)))
        typed = _("\n\n\u270D\uFE0F Type your answer, or tap below \U0001F447") \
            if step in self._SA_TYPED_STEPS or step in ('landmark', 'alt') else \
            _("\n\n\U0001F447 Or tap below")
        intro = ''
        if step == 'state':
            states = self._sa_book_country(st).state_ids.sorted('name')
            intro = '%s%s%s\n\n%s' % (top_note, sorry, head,
                                       '\n'.join('%d. %s' % (i, x.name) for i, x in enumerate(states, 1)))
            top_note = sorry = ''
        body = '%s%s%s\n\n%s%s%s' % (top_note, sorry, '' if intro else head, texts.get(step, ''), typed, tail)
        return self._sa_book_options_send(body.strip(), opts, intro=intro)

    # ------------------------------------------------------------------
    # Draft helpers
    # ------------------------------------------------------------------
    def _sa_book_target(self, st):
        return self.env['res.partner'].sudo().browse(st.get('target') or 0).exists()

    def _sa_book_current(self, st, field):
        """The value shown / edited: the draft over the address being edited."""
        vals = st.get('vals') or {}
        if field in vals:
            return vals[field]
        target = self._sa_book_target(st)
        if not target:
            return False
        return {'label': target._sa_label(), 'line': target.street, 'area': target.street2,
                'landmark': target._sa_landmark(), 'alt': target._sa_alt(), 'city': target.city,
                'zip': target.zip, 'state_id': target.state_id.id,
                'country_id': target.country_id.id}.get(field)

    def _sa_book_country(self, st):
        Country = self.env['res.country'].sudo()
        cid = (st.get('vals') or {}).get('country_id') or self._sa_book_current(st, 'country_id')
        country = Country.browse(cid).exists() if cid else Country
        if not country:
            customer = self._sa_book_customer()
            country = customer.country_id or self._sa_pin_country(customer) or self.env.company.country_id
        return country

    def _sa_book_pin_partner(self, st):
        """A throw-away contact carrying the draft's country, so the existing
        postcode rules (`_sa_find_pincode` & co.) judge the pincode."""
        customer = self._sa_book_customer()
        return self.env['res.partner'].new({
            'country_id': self._sa_book_country(st).id, 'phone': customer.phone})

    def _sa_book_preview(self, st):
        """The address as it stands with the draft applied."""
        target = self._sa_book_target(st)
        vals = st.get('vals') or {}
        state = self.env['res.country.state'].sudo().browse(vals.get('state_id') or 0).exists()
        lines = [
            '%s %s' % (_ICONS.get((self._sa_book_current(st, 'label') or '').lower(), _PIN_ICON),
                       self._sa_book_current(st, 'label') or _("Home")),
            self._sa_book_current(st, 'line') or '',
            self._sa_book_current(st, 'area') or '',
        ]
        lm = self._sa_book_current(st, 'landmark')
        if lm:
            lines.append(lm if lm.lower().startswith(('near', 'opp', 'behind', 'next to', 'beside'))
                         else _("near %s") % lm)
        city = vals.get('city', target.city if target else '')
        zipc = vals.get('zip', target.zip if target else '')
        sname = state.name if state else (target.state_id.name if target else '')
        lines.append(' '.join(x for x in (city and city + ',', sname, zipc) if x))
        alt = self._sa_book_current(st, 'alt')
        if alt:
            lines.append(_("\U0001F4DE also %s") % alt)
        has_pin = vals.get('lat') or (target and target.partner_latitude)
        lines.append(_("\U0001F5FA Location: %s") % (_("saved") if has_pin else _("not shared")))
        return '\n'.join(x for x in lines if x)

    # ------------------------------------------------------------------
    # Opening and closing
    # ------------------------------------------------------------------
    def _sa_book_open(self, back, force_list=False):
        """`back` = 'order' (the details ladder of this order) or 'menu'
        (Change address from the welcome-back menu)."""
        self.ensure_one()
        customer = self._sa_book_customer()
        book = self._sa_address_book(customer)
        st = {'back': back, 'vals': {}}
        if not book:
            return self._sa_book_start_add(st)
        if len(book) == 1 and not force_list:
            return self._sa_book_finish(book, st)
        self._sa_book_set(step='choose', state=st)
        return self._sa_book_ask()

    def _sa_book_start_add(self, st):
        st.update({'mode': 'add', 'vals': {}, 'target': False, 'bad': '', 'trail': []})
        self._sa_book_set(step='label', state=st)
        return self._sa_book_ask()

    def _sa_book_start_edit(self, st, addr):
        st.update({'mode': 'edit', 'vals': {}, 'target': addr.id, 'bad': '', 'trail': [],
                   'last': '', 'target_label': addr._sa_label()})
        self._sa_book_set(step='edit_field', state=st)
        return self._sa_book_ask()

    def _sa_book_finish(self, addr, st):
        """The address is decided: on the order and back to the details
        check, or (from the menu) a thank-you and the menu."""
        self.ensure_one()
        self._sa_book_set(step=False, state={})
        if st.get('back') == 'order' and self.order_id:
            order = self.order_id.sudo()
            self._sa_use_address(order, addr)
            vals = {'profile_step': 'confirm', 'sa_details_fix': False, 'sa_book_done': True,
                    'profile_retry': 0, 'profile_last_bad': False}
            if st.get('mode') in ('add', 'edit') or addr._sa_landmark():
                vals['sa_note_step'] = 'done'
            if st.get('from_form') and self.sa_details_pending and self.state == 'order_created':
                # The customer has just read every line of it on the address
                # form: no "please check your details" - straight to the sign
                # link, exactly as YES on that check does (21 Nov 2026).
                vals.update({'profile_step': 'done', 'sa_note_step': 'done', 'profile_restarted': False,
                             'sa_details_pending': False})
                self.write(vals)
                self._sa_details_confirmed_contact(order.partner_id)
                return self._sa_details_done(order)
            self.write(vals)
            return self._sa_details_ask(order)
        # CHANGE ADDRESS from the menu: this address is the default from now
        # on - the shop app's own default when it is installed - and an order
        # still on its way out goes there too.
        customer = self._sa_book_customer()
        if addr != customer and hasattr(addr, '_mart369_set_default'):
            try:
                addr._mart369_set_default()
            except Exception as err:  # noqa: BLE001 - the choice still stands
                _logger.info("Address book: shop default not moved: %s", err)
        order = self.order_id.sudo() if self.order_id else None
        if order and order.state not in ('done', 'cancel') and not any(
                p.state == 'done' for p in order.picking_ids):
            self._sa_use_address(order, addr)
        self._say(_("%(ok)s Delivery address set:\n%(title)s\n\nYour next deliveries go there.",
                    ok=_DONE, title=addr._sa_addr_title()))
        return self._sa_nav('more') if hasattr(self, '_sa_nav') else True

    def _sa_book_cancel(self):
        self.ensure_one()
        st = self._sa_book_state()
        self._sa_book_set(step=False, state={})
        if st.get('back') == 'order' and self.order_id:
            self.write({'profile_step': 'done', 'sa_details_pending': False, 'sa_details_fix': False})
            return self._sa_cancel_deal()
        self._say(_("No problem - nothing was changed."))
        return True

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------
    def _sa_book_partner_vals(self, vals, partner):
        """Draft keys -> partner fields (ours + the shop's when installed)."""
        out, shop = {}, partner._sa_shop_book()
        mapping = {'line': 'street', 'area': 'street2', 'city': 'city', 'zip': 'zip',
                   'state_id': 'state_id', 'country_id': 'country_id'}
        for k, f in mapping.items():
            if k in vals:
                out[f] = vals[k] or False
        if 'label' in vals:
            out['sa_addr_label'] = vals['label'] or False
            if shop:
                out['mart369_label'] = vals['label'] or 'Home'
        if 'landmark' in vals:
            out['sa_delivery_note'] = vals['landmark'] or False
            if shop:
                out['mart369_landmark'] = vals['landmark'] or False
        if 'alt' in vals:
            out['sa_alt_phone'] = vals['alt'] or False
            if shop:
                out['mart369_alt_phone'] = vals['alt'] or False
        return out

    def _sa_book_write(self, addr, vals):
        """Address fields first, the map pin after: Odoo clears a contact's
        pin whenever an address field is written without it."""
        data = self._sa_book_partner_vals(vals, addr)
        if data:
            addr.sudo().write(data)
        if vals.get('lat') and vals.get('lng'):
            addr.sudo().write({'partner_latitude': vals['lat'], 'partner_longitude': vals['lng']})
        return addr

    def _sa_book_create(self, st):
        """A new address. Home on the contact itself while it has none (and
        the shop is not installed - the shop's book only lists the contacts
        under the customer); otherwise a contact under the customer. Typed
        the same as one already saved: that one is used."""
        self.ensure_one()
        customer = self._sa_book_customer()
        vals = dict(st.get('vals') or {})
        vals.setdefault('country_id', self._sa_book_country(st).id)
        probe = self.env['res.partner'].new({'street': vals.get('line'), 'street2': vals.get('area'),
                                             'zip': vals.get('zip')})
        same = self._sa_address_book(customer).filtered(
            lambda a: self._sa_addr_dedupe_key(a) == self._sa_addr_dedupe_key(probe))[:1]
        if same:
            return self._sa_book_write(same, {k: v for k, v in vals.items()
                                              if k in ('label', 'landmark', 'alt', 'lat', 'lng') and v})
        shop = customer._sa_shop_book()
        if not customer.street and not shop:
            return self._sa_book_write(customer, vals)
        addr = self.env['res.partner'].sudo().create({
            'parent_id': customer.id, 'type': 'other' if shop else 'delivery',
            'name': customer.name, 'phone': customer.phone,
        })
        self._sa_book_write(addr, vals)
        if shop and hasattr(addr, '_mart369_set_default') and not customer.child_ids.filtered(
                lambda c: c.active and c.mart369_default):
            addr._mart369_set_default()
        _logger.info("Sales Automation: enquiry %s - address %s added for %s",
                     self.id, addr.id, customer.name)
        return addr

    def _sa_move_open_orders(self, old, new):
        """An edited address became a new record: WhatsApp orders nobody has
        signed yet go to the new one (S00012 kept the archived 13a). Signed
        and confirmed orders keep the address they were signed with."""
        if not old or not new or old == new:
            return
        orders = self.env['sale.order'].sudo().search([
            ('partner_shipping_id', '=', old.id), ('state', 'in', ('draft', 'sent')),
            ('signed_on', '=', False)])
        for order in orders.filtered(lambda o: o._sa_group_enquiry()):
            order._sa_group_enquiry()._sa_use_address(order, new)
            order._sa_addr_redecide()

    def _sa_address_in_use(self, addr):
        """A confirmed order or a finished delivery already went there."""
        order = self.order_id
        dom = [('partner_shipping_id', '=', addr.id), ('state', 'in', ('sale', 'done'))]
        if order:
            dom.append(('id', '!=', order.id))
        if self.env['sale.order'].sudo().search_count(dom, limit=1):
            return True
        return bool(self.env['stock.picking'].sudo().search_count(
            [('partner_id', '=', addr.id), ('state', '=', 'done')], limit=1))

    def _sa_book_save_edit(self, st):
        """The shop's rule: an address an order already went to is not
        rewritten - the change becomes a fresh copy the customer uses from now
        on, and the old one is archived for the old orders. The customer's own
        contact (home) is always changed in place."""
        self.ensure_one()
        target = self._sa_book_target(st)
        vals = st.get('vals') or {}
        if not target or not vals:
            return target
        customer = self._sa_book_customer()
        moving = any(k in vals for k in ('line', 'area', 'city', 'zip', 'state_id', 'country_id'))
        if target != customer and moving and self._sa_address_in_use(target):
            shop = target._sa_shop_book()
            was_default = shop and target.mart369_default
            fresh = target.copy({'name': target.name, 'parent_id': target.parent_id.id,
                                 'type': 'other' if shop else 'delivery'})
            self._sa_book_write(fresh, vals)
            self._sa_move_open_orders(target, fresh)
            off = {'active': False}
            if shop:
                off.update({'mart369_default': False, 'type': 'other'})
            target.write(off)
            if was_default and hasattr(fresh, '_mart369_set_default'):
                fresh._mart369_set_default()
            return fresh
        return self._sa_book_write(target, vals)

    # ------------------------------------------------------------------
    # Pincode -> city, state (India Post, free, cached)
    # ------------------------------------------------------------------
    @api.model
    def _sa_pincode_lookup(self, pin, country):
        if (country.code or '').upper() != 'IN' or not re.fullmatch(r'\d{6}', pin or ''):
            return {}
        params = self.env['ir.config_parameter'].sudo()
        key = 'sa.pin.%s' % pin
        cached = params.get_param(key)
        if cached:
            try:
                return json.loads(cached)
            except ValueError:
                pass
        try:
            reply = requests.get('https://api.postalpincode.in/pincode/%s' % pin, timeout=5,
                                 headers={'User-Agent': 'Mozilla/5.0 (WhatsApp order address)'})
            reply.raise_for_status()
            found = (reply.json() or [{}])[0]
        except Exception as err:  # noqa: BLE001 - offline or slow: the city is asked instead
            _logger.info("Pincode lookup %s failed: %s", pin, err)
            return {}
        offices = (found.get('PostOffice') or []) if found.get('Status') == 'Success' else []
        if not offices:
            return {}
        first = offices[0]
        wanted = _plain(first.get('State'))
        state = country.state_ids.filtered(lambda s: _plain(s.name) == wanted)[:1]
        out = {'city': first.get('District') or first.get('Block') or '', 'state_id': state.id or False}
        params.set_param(key, json.dumps(out))
        return out

    # ------------------------------------------------------------------
    # Answers
    # ------------------------------------------------------------------
    def _sa_book_back(self, st):
        """⬅️ Back from wherever the customer is."""
        self.ensure_one()
        step = self.sa_book_step
        editing = st.get('mode') == 'edit'
        book = self._sa_address_book(self._sa_book_customer())

        def to(next_step):
            st['bad'] = ''
            self._sa_book_set(step=next_step, state=st)
            return self._sa_book_ask()

        if step == 'choose':
            if st.get('back') == 'order' and self.order_id:
                ship = self.order_id.partner_shipping_id
                keep = ship if ship in book else book[:1]
                if keep:
                    return self._sa_book_finish(keep, dict(st, mode=None))
            self._sa_book_set(step=False, state={})
            return self._sa_nav('main') if hasattr(self, '_sa_nav') else True
        if step in ('edit_pick', 'edit_field'):
            st.update({'mode': None, 'vals': {}, 'target': False, 'trail': [], 'last': ''})
            return to('choose')
        if step == 'location' and st.get('mode') == 'add' and st.get('target'):
            return self._sa_book_start_edit(st, self._sa_book_target(st))
        if editing:
            return to('edit_field')
        trail = st.get('trail') or []
        if trail:
            return to(trail.pop())
        if book:
            st.update({'mode': None, 'vals': {}})
            return to('choose')
        return to('label')

    def _sa_book_take(self, text):
        """One answer in, the next question (or the end) out."""
        self.ensure_one()
        st = self._sa_book_state()
        step = self.sa_book_step
        answer = (text or '').strip()
        low = answer.lower().strip(' .!*')
        vals = st.setdefault('vals', {})
        editing = st.get('mode') == 'edit'
        customer = self._sa_book_customer()
        book = self._sa_address_book(customer)

        def go(next_step):
            if not editing and next_step != step and step not in ('choose', 'edit_pick', 'edit_field'):
                st.setdefault('trail', []).append(step)
            st['bad'] = ''
            self._sa_book_set(step=next_step, state=st)
            return self._sa_book_ask()

        def bad():
            st['bad'] = answer[:60]
            self._sa_book_set(state=st)
            return self._sa_book_ask()

        def after_field(next_step):
            """In the edit flow every answered field goes back to the menu."""
            if editing:
                st['last'] = dict(self._SA_EDIT_FIELDS).get(st.get('field') or step, step)
                st['bad'] = ''
                self._sa_book_set(step='edit_field', state=st)
                return self._sa_book_ask()
            return go(next_step)

        # the tap options of this step first: Back / Stop / Done / Skip
        opts = self._sa_book_step_options(step, st, book)
        typed_step = step in self._SA_TYPED_STEPS
        pick = self._sa_book_pick(answer, opts, digits=not typed_step)
        if pick == 'back':
            return self._sa_book_back(st)
        if pick == 'stop':
            st.update({'vals': {}, 'trail': []})
            if book:
                st['mode'] = None
                st['bad'] = ''
                self._sa_book_set(step='choose', state=st)
                return self._sa_book_ask()
            return self._sa_book_start_add(st)
        if pick == 'done' and editing and step != 'edit_field':
            addr = self._sa_book_save_edit(st)
            return self._sa_book_finish(addr, st)
        if pick != 'skip' and self._sa_is_cancel(answer):
            return self._sa_book_cancel()

        if step == 'choose':
            if not pick:
                return bad()
            if pick == 'add':
                return self._sa_book_start_add(st)
            if pick == 'edit':
                if len(book) == 1:
                    return self._sa_book_start_edit(st, book)
                return go('edit_pick')
            addr = book.filtered(lambda a: 'a%d' % a.id == pick)
            # from the menu a tap means "deliver there from now on" (the
            # shop app does the same); Edit has its own button
            return self._sa_book_finish(addr, st)
        if step == 'edit_pick':
            if not pick:
                return bad()
            return self._sa_book_start_edit(st, book.filtered(lambda a: 'a%d' % a.id == pick))
        if step == 'edit_field':
            if not pick:
                return bad()
            if pick == 'done':
                addr = self._sa_book_save_edit(st)
                return self._sa_book_finish(addr, st)
            st['field'] = pick
            st['bad'] = ''
            self._sa_book_set(step=pick, state=st)
            return self._sa_book_ask()
        if step == 'label':
            if not pick:
                return bad()
            if pick == 'other':
                return go('label_other')
            vals['label'] = _("Home") if pick == 'home' else _("Work")
            return after_field('line')
        if step == 'label_other':
            if len(answer) < 2 or not any(c.isalpha() for c in answer):
                return bad()
            vals['label'] = answer[:30]
            return after_field('line')
        if step == 'line':
            if len(answer) < 1 or len(answer) > 120 or not any(c.isalnum() for c in answer):
                return bad()
            vals['line'] = answer[:120]
            return after_field('area')
        if step == 'area':
            if sum(c.isalpha() for c in answer) < 3:
                return bad()
            vals['area'] = answer[:120]
            return after_field('landmark')
        if step == 'landmark':
            vals['landmark'] = '' if pick == 'skip' else answer[:120]
            return after_field('pin')
        if step == 'pin':
            probe = self._sa_book_pin_partner(st)
            named = self._sa_country_in_address(answer)
            if named and named != self._sa_book_country(st):
                vals['country_id'] = named.id
                vals.pop('state_id', None)
                probe = self._sa_book_pin_partner(st)
                if not self._sa_pincode_wanted(probe):
                    return go('city')
                self._say(_("Thanks - *%(country)s* it is. I need %(hint)s.",
                            country=named.name, hint=self._sa_pincode_hint(probe)), addressed=False)
                self._sa_book_set(state=st)
                return True
            if not self._sa_pincode_wanted(probe):
                return go('city')
            found = self._sa_find_pincode(answer, probe)
            if not found:
                return bad()
            vals['zip'] = found
            country = self._sa_book_country(st)
            vals['country_id'] = country.id
            got = self._sa_pincode_lookup(found.replace(' ', ''), country)
            if got.get('city'):
                vals['city'] = got['city']
                if got.get('state_id'):
                    vals['state_id'] = got['state_id']
                state = self.env['res.country.state'].sudo().browse(vals.get('state_id') or 0).exists()
                self._say(_("\U0001F4EE %(pin)s - %(place)s \u2714", pin=found,
                            place=', '.join(x for x in (got['city'], state.name) if x)), addressed=False)
                if country.state_ids and not vals.get('state_id'):
                    return go('state')
                return after_field('alt')
            return go('city')
        if step == 'city':
            if sum(c.isalpha() for c in answer) < 2:
                return bad()
            vals['city'] = answer[:60]
            if self._sa_book_country(st).state_ids:
                return go('state')
            return after_field('alt')
        if step == 'state':
            states = self._sa_book_country(st).state_ids.sorted('name')
            chosen = self.env['res.country.state']
            if re.fullmatch(r'\d{1,3}', low) and 1 <= int(low) <= len(states):
                chosen = states[int(low) - 1]
            else:
                chosen = states.filtered(lambda s: _plain(s.name) == _plain(answer)
                                         or (s.code or '').lower() == low)[:1]
            if not chosen:
                return bad()
            vals['state_id'] = chosen.id
            return after_field('alt')
        if step == 'alt':
            if pick == 'skip':
                vals['alt'] = ''
            else:
                digits = re.sub(r'\D', '', answer)
                if not 7 <= len(digits) <= 15:
                    return bad()
                vals['alt'] = ('+' + digits) if answer.strip().startswith('+') else digits
            if editing:
                return after_field('edit_field')
            # the address is complete: save it, then the optional pin
            addr = self._sa_book_create(st)
            st.update({'target': addr.id, 'vals': {}})
            if addr.partner_latitude or addr.partner_longitude:
                return self._sa_book_finish(addr, st)
            return go('location')
        if step == 'location':
            if pick == 'skip':
                if editing:
                    return after_field('edit_field')
                return self._sa_book_finish(self._sa_book_target(st), st)
            return bad()
        return None

    def _sa_book_take_pin(self, lat, lng):
        """A WhatsApp location while the address questions are open: it
        belongs to the address being added or changed."""
        self.ensure_one()
        st = self._sa_book_state()
        step = self.sa_book_step
        if st.get('mode') == 'add' and st.get('target'):
            target = self._sa_book_target(st)
            target.write({'partner_latitude': lat, 'partner_longitude': lng})
            self._say(_("\U0001F4CD Location saved - thank you!"), addressed=False)
            return self._sa_book_finish(target, st)
        st.setdefault('vals', {}).update({'lat': lat, 'lng': lng})
        self._sa_book_set(state=st)
        self._say(_("\U0001F4CD Location noted."), addressed=False)
        if step == 'location' and st.get('mode') == 'edit':
            st['bad'] = ''
            self._sa_book_set(step='edit_field', state=st)
        return self._sa_book_ask()

    # ------------------------------------------------------------------
    # Hooks into the details ladder
    # ------------------------------------------------------------------
    def _sa_group_details_start(self, order):
        self.write({'sa_book_done': False, 'sa_book_step': False, 'sa_book_json': False})
        return super()._sa_group_details_start(order)

    def _sa_default_address(self, customer, order=None):
        """The address an order goes to unless the customer says otherwise:
        the one they set as default, else the one of their latest order, else
        the first saved one. Only addresses a rider can use."""
        book = self._sa_address_book(customer).filtered(
            lambda a: (a.street or '').strip() and (a.zip or not self._sa_pincode_wanted(a)))
        if not book:
            return book
        if customer._sa_shop_book():
            default = book.filtered(lambda a: a != customer and a.mart369_default)[:1]
            if default:
                return default
        dom = [('partner_id', '=', customer.id), ('state', '!=', 'cancel'),
               ('partner_shipping_id', 'in', book.ids)]
        if order:
            dom.append(('id', '!=', order.id))
        last = self.env['sale.order'].sudo().search(dom, order='id desc', limit=1)
        return last.partner_shipping_id or book[:1]

    def _sa_details_known(self, order):
        """Name known and an address saved: no address poll, no landmark
        question, no read-back (owner, 23 Nov 2026). The order takes the
        default; the sign page shows it with Change / Edit / Add."""
        order = order.sudo()
        customer = order.partner_id.sudo()
        if not customer or not self._sa_profile_complete(customer):
            return False
        addr = self._sa_default_address(customer, order)
        if not addr:
            return False
        self._sa_use_address(order, addr)
        self.write({'profile_step': 'done', 'sa_book_done': True, 'sa_note_step': 'done',
                    'sa_details_fix': False, 'sa_details_pending': False})
        self._sa_details_confirmed_contact(customer)
        return True

    NOTE_SKIP = '1 \u23ED Skip'
    NOTE_BACK = '2 \u2B05\uFE0F Back'
    DETAILS_POLL = [('yes', 'DETAILS_YES'), ('no', 'DETAILS_NO'), ('cancel', 'DETAILS_CANCEL')]
    FIX_POLL = [('name', 'FIX_NAME'), ('address', 'FIX_ADDRESS'), ('back', 'FIX_BACK')]

    def _sa_details_ask(self, order):
        """The address part of the ladder is the address book; the polls get
        their numbers; the landmark question ends with "1. ⏭ Skip"."""
        self.ensure_one()
        # every details question counts as asked now - the landmark and the
        # change menu do not pass `_sa_profile_question` (30-minute window,
        # sa_group_details._sa_details_waiting)
        self.sudo().write({'profile_asked_on': fields.Datetime.now()})
        if self.sa_book_step:
            return self._sa_book_ask()
        # brought back after an old poll was tapped: a note on top, and an
        # invisible ending so the gateway's duplicate filter lets it through
        note = self.env.context.get('sa_reask_note') or ''
        top = ('%s\n\n' % note) if note else ''
        tail = ('​' * (fields.Datetime.now().second % 9 + 1)) if note else ''
        fix = self.sa_details_fix
        if fix == 'menu':
            self._ask(top + _("✏️ What would you like to change?") + tail,
                      [{'id': 'sa_fix_%s' % k, 'title': '%d %s' % (i, getattr(self, attr))}
                       for i, (k, attr) in enumerate(self.FIX_POLL, 1)])
            return True
        if not self.profile_step:
            # the name given at the welcome is not asked again (sa_customer_name.py)
            self.profile_step = self._sa_profile_first_step(order.partner_id)
        step = self.profile_step
        if fix == 'address' or (fix != 'name' and not self.sa_book_done
                                and step in ('address', 'pin', 'confirm')):
            return self._sa_book_open('order', force_list=(fix == 'address'))
        if step == 'confirm' and not fix and self.sa_note_step in (False, 'ask'):
            self.write({'sa_note_step': 'ask'})
            self._ask(top + _("\U0001F4CD Order *#%(ref)s*: any landmark, flat number or gate note "
                              "for the delivery person?\n\n\u270D\uFE0F Type it, or tap below \U0001F447",
                              ref=self.ref_code or order.name) + tail,
                      [{'id': 'sa_note_skip', 'title': self.NOTE_SKIP},
                       {'id': 'sa_note_back', 'title': self.NOTE_BACK}])
            return True
        if step == 'confirm':
            reply, _kind = self._sa_profile_question(order)
            body = reply.replace(
                _("Reply *YES* to confirm, *NO* to change them, or *CANCEL* to stop."),
                _("Tap one:")).rstrip()
            self._ask(top + body + tail, [{'id': 'sa_det_%s' % k, 'title': '%d %s' % (i, getattr(self, attr))}
                             for i, (k, attr) in enumerate(self.DETAILS_POLL, 1)])
            return True
        return super()._sa_details_ask(order)

    def _sa_profile_summary(self, partner):
        """The details check shows the address of THIS order in full."""
        self.ensure_one()
        order = self.order_id.sudo()
        addr = partner
        if order and order.partner_id == partner:
            ship = order.partner_shipping_id
            if ship and (ship == partner or ship.parent_id == partner):
                addr = ship
        phone = partner.phone or '-'
        alt = addr._sa_alt() if addr else ''
        if alt:
            phone = '%s / %s' % (phone, alt)
        # Delivering to somebody else: say who, as the website does.
        who = partner.name or '-'
        receiver = addr._sa_real_name() if addr and addr != partner else ''
        if receiver and receiver != (partner.name or '').strip():
            who = _("%(receiver)s (for %(customer)s)", receiver=receiver, customer=partner.name or '-')
        return _("\U0001F4CB *Please check your details*\n\n"
                 "\U0001F464 %(name)s\n"
                 "%(icon)s %(label)s - %(addr)s\n"
                 "\U0001F4F1 %(phone)s\n\n"
                 "Reply *YES* to confirm, *NO* to change them, "
                 "or *CANCEL* to stop.",
                 name=who, icon=addr._sa_icon(), label=addr._sa_label(),
                 addr=addr._sa_addr_text() or '-', phone=phone)

    def _sa_take_details(self, text):
        """Numbers typed on the change menu; "1" on the landmark question is
        Skip; the landmark also goes to the shop's field."""
        self.ensure_one()
        if self.sa_book_step:
            return self._sa_book_take(text)
        answer = (text or '').strip()
        low = answer.lower().strip(' .!*')
        if self.sa_details_fix == 'menu' and low in ('1', '2', '3'):
            return self._sa_details_change({'1': 'name', '2': 'address', '3': 'back'}[low])
        noting = self.sa_note_step == 'ask' and self.profile_step == 'confirm'
        if noting and (low in ('2', 'back') or _key(answer) == _key(self.NOTE_BACK)):
            # ⬅️ Back on the landmark question: to the address list
            self.write({'sa_note_step': False})
            return self._sa_details_change('address')
        if noting and (low in SKIP_WORDS or _key(answer) == _key(self.NOTE_SKIP)):
            text = 'skip'
        res = super()._sa_take_details(text)
        if noting and self.sa_note_step == 'done' and self.order_id:
            ship = (self.order_id.partner_shipping_id or self.order_id.partner_id).sudo()
            if ship._sa_shop_book():
                ship.write({'mart369_landmark': ship.sa_delivery_note or False})
        return res

    _SA_REASK = '\U0001F446 That one is already done - here is where we are:'

    def _sa_answer_poll(self, text):
        """A tap on one of our polls. A tap that is one of the CURRENT
        question's options is taken; an older poll brings the current question
        back (never "please type"). The numbered titles of the details polls
        are matched without their number, so a poll sent before still works."""
        self.ensure_one()
        if self.sa_book_step:
            st = self._sa_book_state()
            if self._sa_book_pick(text, self._sa_book_step_options(self.sa_book_step, st)):
                return self._sa_book_take(text)
            return self._sa_book_ask(note=_(self._SA_REASK))
        if self.sa_details_pending and self.state == 'order_created':
            if self.sa_note_step == 'ask' and self.profile_step == 'confirm':
                k = _key(text)
                if k in (_key(self.NOTE_SKIP), _key(self.NOTE_BACK)):
                    return self._sa_take_details(text)
            stripped = re.sub(r'^\s*\d{1,2}\s+', '', text or '')
            if stripped != (text or ''):
                return super()._sa_answer_poll(stripped)
        return super()._sa_answer_poll(text)

    def _sa_tell_poll_spent(self, text):
        """An already-answered poll tapped again: show where the customer is,
        as a poll to tap - not "type it"."""
        self.ensure_one()
        note = _(self._SA_REASK)
        try:
            if self.sa_book_step:
                self._sa_book_ask(note=note)
                return True
            if self.sa_details_pending and self.state == 'order_created' and self.order_id:
                self.with_context(sa_reask_note=note)._sa_details_ask(self.order_id.sudo())
                return True
            if self.sa_menu_json and hasattr(self, '_sa_nav'):
                self._say(_("\u2705 That choice was already made.\u200b"))
                self._sa_nav('main')
                return True
            self._say(_("\u2705 That choice was already made."))
        except Exception as err:  # noqa: BLE001 - a note, never a failure
            _logger.info("Sales Automation: poll-spent re-ask failed: %s", err)
        return False

    def _sa_ask_new_address(self):
        """Change of address from the welcome-back menu: the address book."""
        self.ensure_one()
        if not self._sa_address_partner():
            return super()._sa_ask_new_address()
        return self._sa_book_open('menu', force_list=True)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    @api.model
    def _sa_book_waiting(self, group, message):
        """This sender's enquiry with address questions open (asked in the
        last few hours - an abandoned one must not swallow later messages)."""
        digits = ''.join(c for c in (message.participant_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = message.participant_lid or ''
        since = fields.Datetime.now() - timedelta(hours=self._SA_BOOK_TTL_H)
        dom = [('group_id', '=', group.id), ('sa_book_step', '!=', False),
               ('sa_book_asked_on', '>=', since)]
        if tail and lid:
            dom += ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        elif tail:
            dom += [('requester_phone', 'like', tail)]
        elif lid:
            dom += [('requester_lid', '=', lid)]
        else:
            return self.browse()
        return self.sudo().search(dom, order='sa_book_asked_on desc, id desc', limit=1)

    @api.model
    def _on_group_message(self, message):
        group = self.env['sa.sales.group'].sudo().search([
            ('session_id', '=', message.session_id.id), ('group_jid', '=', message.group_jid),
            ('enabled', '=', True)], limit=1)
        text = (message.message or '').strip()
        if group and text and group.group_type != 'vendor' and not self.env.context.get('sa_poll_ref'):
            waiting = self._sa_book_waiting(group, message)
            if waiting:
                trig = message.wa_message_id or ('row%s' % message.id)
                pin = self._SA_PIN_RE.match(text)
                if pin:
                    return waiting.with_context(sa_trigger_msg=trig)._sa_book_take_pin(
                        float(pin.group(1)), float(pin.group(2)))
                if not self._sa_is_greeting(text):
                    return waiting.with_context(sa_trigger_msg=trig)._sa_book_take(text)
        return super()._on_group_message(message)
