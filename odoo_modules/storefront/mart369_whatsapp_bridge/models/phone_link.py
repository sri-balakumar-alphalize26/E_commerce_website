"""One proven number, one customer - the WhatsApp side of signing in.

mart369_auth decides *who may sign in* with a mobile number and a code; it
knows nothing about WhatsApp. This plugs WhatsApp into its three hooks:

* **the postman** - the code travels as a WhatsApp message from the shop's
  number, and the answer says honestly whether it went, queued or could not;
* **who owns the number** - besides storefront accounts, the customer who only
  ever ordered on WhatsApp: they sign in with no sign-up, their login made on
  the very record that holds their orders;
* **after the number is proven** - every other WhatsApp contact with that
  number is joined into the account, one at a time: its orders, its address
  (into the storefront's book, the old orders still pointing at the doorstep
  they really went to), its points and wallet, its chats.

Joining is Odoo's own contact merge (base.partner.merge) - every row that
points at a contact follows it - with what the merge cannot know done first:
the address kept, the one-delivery-address rule kept, two wallets added up
rather than one deleted on the unique index. Never joined: staff, a company,
a rider or a shop, a supplier-only contact, anyone with a login.
"""

import logging
import re

from odoo import _, api, fields, models

from odoo.addons.whatsapp_gateway.models.whatsapp_session import WhatsAppQueued

_logger = logging.getLogger(__name__)

try:
    import phonenumbers
except ImportError:  # pragma: no cover - phone_validation depends on it
    phonenumbers = None

ADDRESS_FIELDS = ('street', 'street2', 'city', 'zip', 'state_id', 'country_id')


def _digits(number):
    return ''.join(c for c in (number or '') if c.isdigit())


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ------------------------------------------------------------ the postman

    @api.model
    def _mart369_send_login_code(self, phone, code):
        if 'whatsapp.session' not in self.env:
            return 'none'
        session = self.env['mart369.whatsapp']._mart369_session()
        if not session:
            return 'none'
        body = _("Your 369 Mart code is *%(code)s*\n\n"
                 "It expires in 10 minutes. Don't share it with anyone - "
                 "369 Mart will never ask you for it.", code=code)
        try:
            sent = session.send_message(_digits(phone), body)
        except WhatsAppQueued:
            return 'queued'
        except Exception:  # noqa: BLE001 - the caller says so, in words
            _logger.exception('bridge: could not send a sign-in code to %s', phone)
            return 'offline'
        return 'sent' if sent else 'offline'

    # ------------------------------------------------- who owns this number

    @api.model
    def _mart369_same_number(self, stored, phone):
        """Is `stored` (however it was typed) the proven E.164 `phone`?

        Same digits; or the national number alone - typed without a country
        code, maybe with a leading 0 - read as the number's own country. Never
        a bare last-nine-digits guess: an Omani mobile has eight.
        """
        mine = _digits(phone)
        theirs = _digits(stored)
        if not theirs or not mine:
            return False
        if theirs == mine:
            return True
        national = ''
        if phonenumbers:
            try:
                national = phonenumbers.national_significant_number(
                    phonenumbers.parse('+' + mine))
            except phonenumbers.NumberParseException:
                national = ''
        return bool(national) and theirs.lstrip('0') == national \
            and not (stored or '').strip().startswith('+')

    @api.model
    def _mart369_wa_customers(self, phone):
        """Contacts carrying this number that a login could take or that can
        be joined: top-level, no user, and not anyone the guards protect.
        Customers with orders first, then the newest."""
        tail = _digits(phone)[-5:]
        if len(tail) < 5:
            return self.browse()
        Partner = self.sudo().with_context(active_test=False)
        found = Partner.search([
            ('parent_id', '=', False),
            '|', ('phone', 'ilike', tail), ('phone_sanitized', 'ilike', tail),
        ])
        found = found.filtered(
            lambda p: p.active and not p.with_context(active_test=False).user_ids
            and (self._mart369_same_number(p.phone, phone)
                 or _digits(p.phone_sanitized) == _digits(phone)))
        found = found.filtered(lambda p: p._mart369_joinable())
        return found.sorted(lambda p: (-(p.customer_rank or 0), -p.id))

    def _mart369_joinable(self):
        """Never folded into a customer account: a company, staff, a rider, a
        shop, a supplier who never bought, or anyone with a login."""
        self.ensure_one()
        env = self.env
        if self.with_context(active_test=False).user_ids:
            return False
        if self.supplier_rank and not self.customer_rank:
            return False
        if env['res.company'].sudo().search_count([('partner_id', '=', self.id)]):
            return False
        if 'hr.employee' in env and env['hr.employee'].sudo().with_context(
                active_test=False).search_count([('work_contact_id', '=', self.id)]):
            return False
        for model in ('sa.delivery.partner', 'sa.delivery.shop'):
            if model in env and 'partner_id' in env[model]._fields and env[model].sudo(
                    ).with_context(active_test=False).search_count(
                    [('partner_id', '=', self.id)]):
                return False
        return True

    @api.model
    def _mart369_phone_owner(self, phone):
        partner, user = super()._mart369_phone_owner(phone)
        if user:
            return partner, user
        return self._mart369_wa_customers(phone)[:1], user

    # ------------------------------------------------------- after the proof

    def _mart369_after_phone_verified(self):
        """Join every WhatsApp contact with this number into this account,
        and put this record's own WhatsApp address into its book."""
        self.ensure_one()
        result = super()._mart369_after_phone_verified() or {}
        customer = self.commercial_partner_id.sudo()
        customer._mart369_book_own_address()
        merged = 0
        for src in customer._mart369_wa_customers(customer.phone) - customer:
            try:
                with self.env.cr.savepoint():
                    customer._mart369_join_one(src)
                merged += 1
            except Exception:  # noqa: BLE001 - one bad contact stops nothing
                _logger.exception('bridge: could not join contact %s into %s',
                                  src.id, customer.display_name)
        result.update(customer._mart369_link_counts())
        result['merged'] = merged
        return result

    def _mart369_link_counts(self):
        """What the customer now sees: their WhatsApp orders and addresses."""
        self.ensure_one()
        orders = self.env['sale.order'].sudo().search_count([
            ('partner_id', 'child_of', self.id),
            ('mart369_channel', '=', 'whatsapp'),
            ('state', '!=', 'cancel'),
        ])
        return {'orders': orders, 'addresses': len(self._mart369_book())}

    # ------------------------------------------------------------- the book

    @api.model
    def _mart369_addr_words(self, values):
        """The words that place an address, as a set: lower case, no
        punctuation, without its PIN and without the state, the country or
        'india' - which every address in the book shares anyway.

        'beach road,kollam,691001' and 'Beach Road, beach, kollam, Kerala
        691001' give {beach, road, kollam} and {beach, road, kollam}.
        """
        def name_of(value):
            return (value.name or '') if hasattr(value, 'name') else ''
        pin = (values.get('zip') or '').strip()
        text = ' '.join(str(values.get(f) or '') for f in ('street', 'street2', 'city'))
        drop = {'india', pin.lower()}
        for field in ('state_id', 'country_id'):
            drop.update(re.findall(r'[a-z0-9]+', name_of(values.get(field)).lower()))
        return {w for w in re.findall(r'[a-z0-9]+', text.lower()) if w not in drop}

    @api.model
    def _mart369_same_place(self, new, old):
        """Is the address in `new` already said by `old`? Same PIN (or one
        has none), and every word of `new` is in `old` - so 'beach road
        kollam' is the saved Home, while '12 beach road' and '14 beach road'
        stay two addresses."""
        new_pin = (new.get('zip') or '').strip()
        old_pin = (old.get('zip') or '').strip()
        if new_pin and old_pin and new_pin != old_pin:
            return False
        mine = self._mart369_addr_words(new)
        return bool(mine) and mine <= self._mart369_addr_words(old)

    @staticmethod
    def _mart369_strip_pin(street, pin):
        """'beach road,kollam,691001' with PIN 691001 -> 'beach road,kollam':
        the PIN typed into the chat is shown once, as the PIN."""
        street = (street or '').strip()
        pin = (pin or '').strip()
        if not pin or not street:
            return street
        cleaned = re.sub(r'[\s,;-]*\b%s\b' % re.escape(pin), '', street)
        return cleaned.strip(' ,;-') or street

    @api.model
    def _mart369_label_for(self, partner):
        """What a copied address is called: the senior's naming - the label
        the customer gave it on WhatsApp, else the shop's, else "Home". Never
        the channel's name: the customer calls it Home or Work, not WhatsApp.
        """
        if partner:
            try:
                if hasattr(partner, '_sa_label'):
                    label = (partner._sa_label() or '').strip()
                    if label and label != 'WhatsApp':
                        return label
            except Exception:  # noqa: BLE001 - a name is never worth a lost address
                _logger.info('bridge: no WhatsApp label for %s', partner.id)
            own = (partner.mart369_label or '').strip()
            if own and own != 'WhatsApp':
                return own
        return _('Home')

    def _mart369_book_add_once(self, values, label=None, make_default=False, source=None):
        """An address into this customer's book - unless the book already
        holds the same place (`_mart369_same_place`), which is then the one
        returned. Named after `source` (the contact it came from), else this
        customer, the senior's way (`_mart369_label_for`)."""
        self.ensure_one()
        customer = self.sudo()
        label = label or self._mart369_label_for(source or customer)
        values = dict(values)
        values['street'] = self._mart369_strip_pin(values.get('street'), values.get('zip'))
        for address in customer._mart369_book():
            if self._mart369_same_place(values, {f: address[f] for f in ADDRESS_FIELDS}):
                if make_default and not address.mart369_default:
                    address._mart369_set_default()
                return address
        clean = {}
        for field in ADDRESS_FIELDS:
            value = values.get(field)
            if value:
                clean[field] = value.id if hasattr(value, 'id') else value
        address = customer.with_context(mart369_joining=True)._mart369_add_address(dict(
            clean,
            name=customer.name,
            phone=customer.phone or '',
            mart369_label=label,
        ))
        if make_default and not address.mart369_default:
            address._mart369_set_default()
        return address

    def _mart369_book_tidy(self):
        """Fold addresses in this customer's book that are the same place.

        Only groups the WhatsApp copy made (one of them labelled WhatsApp).
        Of each group the most detailed one stays (then the default, then the
        oldest), and becomes the default if any of the group was. The others
        are archived the way the storefront archives a replaced address, so
        an old order still shows where it went. A WhatsApp address that also
        carries its PIN inside the street gets it removed.
        """
        self.ensure_one()
        customer = self.sudo()
        book = customer._mart369_book()
        for address in book.filtered(lambda a: a.mart369_label == 'WhatsApp' and a.zip):
            street = self._mart369_strip_pin(address.street, address.zip)
            if street != (address.street or ''):
                # A plain write: when it is the default, the customer's own
                # lines follow (res_partner.py).
                address.street = street
        seen = []
        folded = self.browse()
        for address in book:
            here = {f: address[f] for f in ADDRESS_FIELDS}
            group = next((g for g in seen if self._mart369_same_place(here, g[0])
                          or self._mart369_same_place(g[0], here)), None)
            if group is None:
                seen.append([here, address])
            else:
                group.append(address)
        for group in seen:
            members = self.browse([a.id for a in group[1:]])
            # Only what the WhatsApp copy made: two places a customer saved
            # on purpose (Home and Work at one door) are theirs to keep.
            if len(members) < 2 or 'WhatsApp' not in members.mapped('mart369_label'):
                continue
            keeper = members.sorted(lambda a: (
                -len(self._mart369_addr_words({f: a[f] for f in ADDRESS_FIELDS})),
                not a.mart369_default, a.id))[:1]
            was_default = any(members.mapped('mart369_default'))
            rest = members - keeper
            rest.write({'active': False, 'type': 'other', 'mart369_default': False})
            folded |= rest
            if was_default and not keeper.mart369_default:
                keeper._mart369_set_default()
        return folded

    def _mart369_book_own_address(self):
        """A WhatsApp customer's address lives on their record; the website
        reads the book. Copy it in, once."""
        self.ensure_one()
        if not (self.street or self.zip):
            return self.browse()
        return self._mart369_book_add_once({f: self[f] for f in ADDRESS_FIELDS})

    # -------------------------------------------------------------- joining

    def _mart369_join_one(self, src):
        """Fold one WhatsApp contact into this account."""
        self.ensure_one()
        src = src.sudo()
        cr = self.env.cr
        orders = self.env['sale.order'].sudo().search_count(
            [('partner_id', '=', src.id)])
        # 1. Its doorstep joins the book; its orders keep pointing at it.
        address = (self._mart369_book_add_once({f: src[f] for f in ADDRESS_FIELDS}, source=src)
                   if (src.street or src.zip) else self.browse())
        if address:
            # Plain SQL, as the merge itself does: a delivered order is locked
            # against ORM writes, and these are history, not edits.
            cr.execute('UPDATE sale_order SET partner_shipping_id = %s '
                       'WHERE partner_shipping_id = %s', (address.id, src.id))
            cr.execute('UPDATE stock_picking SET partner_id = %s '
                       'WHERE partner_id = %s', (address.id, src.id))
            self.env['sale.order'].invalidate_model(['partner_shipping_id'])
            self.env['stock.picking'].invalidate_model(['partner_id'])
        # 2. One delivery address per customer, the storefront's rule.
        src.child_ids.filtered(lambda c: c.type == 'delivery').with_context(
            mart369_joining=True).write({'type': 'other', 'mart369_default': False})
        # 3. Points and wallet are added up, never deleted on a unique index.
        self._mart369_combine_cards(src)
        # 4. Odoo's own merge: every row pointing at `src` now points here.
        name = src.display_name
        self.env['base.partner.merge.automatic.wizard'].sudo().with_context(
            mart369_joining=True)._merge([src.id, self.id], self, extra_checks=False)
        self.message_post(body=_(
            "Joined the WhatsApp contact %(name)s after the customer proved "
            "%(phone)s: %(orders)s order(s) moved here.",
            name=name, phone=self.phone or '', orders=orders))
        return True

    def _mart369_combine_cards(self, src):
        self.ensure_one()
        env = self.env
        if 'loyalty.card' in env and hasattr(env['loyalty.card'], '_mart369_program'):
            Card = env['loyalty.card'].sudo()
            try:
                program = Card._mart369_program()
            except Exception:  # noqa: BLE001 - no wallet programme, no wallet
                program = None
            if program:
                theirs = Card.search([('program_id', '=', program.id),
                                      ('partner_id', '=', src.id)], limit=1)
                mine = Card.search([('program_id', '=', program.id),
                                    ('partner_id', '=', self.id)], limit=1)
                if theirs and mine:
                    # The movements travel with the money, so the account's
                    # ledger still adds up to its balance (the wallet's own
                    # write guard is lifted for exactly that).
                    env['loyalty.history'].sudo().search(
                        [('card_id', '=', theirs.id)]).write({'card_id': mine.id})
                    moved = theirs.points
                    mine.with_context(mart369_wallet_move=True).points = mine.points + moved
                    theirs.with_context(mart369_wallet_move=True).points = 0.0
                    # Emptied, and gone before the merge: the one-wallet index
                    # is a partial index the merge cannot see, so it would
                    # try to move this card onto the account and fail.
                    theirs.unlink()
        if 'pos.loyalty.card' in env:
            Card = env['pos.loyalty.card'].sudo()
            theirs = Card.search([('partner_id', '=', src.id), ('is_deleted', '=', False)])
            mine = Card.search([('partner_id', '=', self.id), ('is_deleted', '=', False)],
                               order='state asc, id', limit=1)
            if theirs and mine:
                env['pos.loyalty.history'].sudo().search(
                    [('card_id', 'in', theirs.ids)]).write({'card_id': mine.id})
                theirs.write({'is_deleted': True, 'deleted_date': fields.Datetime.now()})

    # ---------------------------------------------------------- the safety net

    @api.model
    def _cron_mart369_join_duplicates(self):
        """A WhatsApp contact made since the last run for a proven number -
        some flows of the selling stack still match numbers loosely - is
        joined into the account."""
        since = fields.Datetime.subtract(fields.Datetime.now(), hours=1)
        fresh = self.sudo().search([
            ('parent_id', '=', False), ('user_ids', '=', False),
            ('create_date', '>=', since), ('phone', '!=', False),
        ])
        for src in fresh:
            accounts = self.sudo().search([
                ('mart369_phone_verified', '=', True),
                ('user_ids', '!=', False),
                ('phone', 'ilike', _digits(src.phone)[-5:]),
            ]).filtered(lambda a: self._mart369_same_number(src.phone, a.phone))
            if len(accounts) != 1 or not src._mart369_joinable():
                continue
            try:
                with self.env.cr.savepoint():
                    accounts._mart369_join_one(src)
            except Exception:  # noqa: BLE001
                _logger.exception('bridge: cron could not join contact %s', src.id)
