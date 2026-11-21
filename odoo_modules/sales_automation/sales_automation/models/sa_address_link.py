# -*- coding: utf-8 -*-
"""The private address form link (owner, 21 Nov 2026).

When the group's address questions start adding a new address (a first-time
customer, or "➕ Add a new address"), the customer is also sent a link -
privately when WhatsApp shows their number - to a page with the same fields
as the 369 Mart shop's Delivery Address form. Filling it in saves the address
the same way the group questions do, puts it on the order and the group moves
on to the read-back. The group questions keep working beside it: whichever
finishes first wins and the other one stops.

The link works once, for a limited time (Settings > Delivery Address), and
only while that order's address questions are open. The token in the link is
the whole credential and is compared in constant time.
"""
import hmac
import logging
import re
import secrets
from datetime import timedelta

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

LABELS = ('home', 'work', 'other')


class SaAddressLink(models.Model):
    _name = 'sa.address.link'
    _description = 'Private address form link'
    _order = 'id desc'

    request_id = fields.Many2one('sa.group.request', 'Enquiry', required=True,
                                 ondelete='cascade', index=True)
    order_id = fields.Many2one(related='request_id.order_id', string='Order')
    requester_name = fields.Char(related='request_id.requester_name', string='Customer')
    token = fields.Char('Token', required=True, index=True, copy=False, groups='base.group_user',
                        default=lambda self: secrets.token_urlsafe(24))
    sent_to = fields.Selection([('private', 'Private chat'), ('group', 'Group')], 'Sent to',
                               readonly=True)
    expires_on = fields.Datetime('Works until', readonly=True)
    opened_on = fields.Datetime('First opened', readonly=True)
    open_count = fields.Integer('Opens', readonly=True, default=0)
    used_on = fields.Datetime('Filled in', readonly=True)
    used_ip = fields.Char('Filled in from (IP)', readonly=True)
    used_ua = fields.Char('Filled in with (browser)', readonly=True)
    address_id = fields.Many2one('res.partner', 'Address saved', readonly=True, ondelete='set null')
    active = fields.Boolean(default=True)
    # 21 Nov 2026: the form also changes a saved address (filled in with it),
    # and works from the menu's CHANGE ADDRESS, outside an order.
    mode = fields.Selection([('add', 'New address'), ('edit', 'Change an address')], 'For',
                            default='add', readonly=True)
    back = fields.Selection([('order', 'An order'), ('menu', 'Change address (menu)')], 'From',
                            default='order', readonly=True)
    target_id = fields.Many2one('res.partner', 'Address changed', readonly=True, ondelete='set null',
                                help="The saved address this form changes (Change an address).")

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    @api.model
    def _by_token(self, token):
        """The link for this token, compared in constant time. Empty otherwise."""
        token = (token or '').strip()
        if not token or len(token) < 16 or len(token) > 64 or not re.fullmatch(r'[A-Za-z0-9_-]+', token):
            return self.browse()
        candidate = self.sudo().with_context(active_test=False).search([('token', '=', token)], limit=1)
        if candidate and hmac.compare_digest(str(candidate.token), token):
            return candidate
        return self.browse()

    def _alive(self):
        """Still fillable: not used, not expired, and the address questions it
        answers are still open (not finished in the group, not cancelled; for
        an order, the order not cancelled either)."""
        self.ensure_one()
        req = self.request_id.sudo()
        if not (self.active and not self.used_on and self.expires_on
                and self.expires_on > fields.Datetime.now() and req.sa_book_step):
            return False
        if self.mode == 'edit' and not self.target_id.exists():
            return False
        if self.back == 'order':
            return bool(req.order_id and req.order_id.state != 'cancel')
        return True

    def _url(self):
        self.ensure_one()
        return self.env['wa.auto.reply'].sudo()._sa_public_link('/wa/address/%s' % self.sudo().token)

    def _minutes_left(self):
        self.ensure_one()
        if not self.expires_on:
            return 0
        return max(0, int((self.expires_on - fields.Datetime.now()).total_seconds() // 60))

    def _note_open(self):
        self.ensure_one()
        vals = {'open_count': self.open_count + 1}
        if not self.opened_on:
            vals['opened_on'] = fields.Datetime.now()
        self.sudo().write(vals)

    # ------------------------------------------------------------------
    # What the page shows
    # ------------------------------------------------------------------
    # The form, the same as the 369 Mart shop's Delivery Address form
    # (components/home/AddressForm.jsx): Home / Work / Other, country, full
    # name, mobile, alternate mobile, pincode, house, road / area, city,
    # state, landmark and the map pin - with its required fields and its
    # messages. Where the shop's address module is installed its own rules
    # check and save the address (mart369_address/models/address_rules.py),
    # so both doors behave the same; elsewhere the same rules live here.
    # ------------------------------------------------------------------
    def _shop(self):
        """The shop's address rules, when that module is installed."""
        partner = self.env['res.partner'].sudo()
        return partner if hasattr(partner, '_mart369_address_values') else None

    def _customer(self):
        return self.request_id.sudo()._sa_book_customer()

    @api.model
    def _phone_rule(self, country):
        """{'dial': '+91', 'length': 10} - from the phone library when it knows
        the country, else the dial code alone (any 6-15 digits)."""
        dial = ('+%s' % country.phone_code) if country.phone_code else ''
        try:
            import phonenumbers
            example = phonenumbers.example_number_for_type(
                (country.code or '').upper(), phonenumbers.PhoneNumberType.MOBILE)
            return {'dial': dial, 'length': len(phonenumbers.national_significant_number(example))}
        except Exception:  # noqa: BLE001 - unknown country or no library
            return {'dial': dial, 'length': 0}

    def _meta(self, country=None):
        """What the form needs for one country: dial code, digit counts,
        states, every country for the picker (the likely ones first)."""
        self.ensure_one()
        shop = self._shop()
        customer = self._customer()
        if shop is not None and hasattr(shop, '_mart369_form_meta'):
            try:
                return shop._mart369_form_meta(country=country or None, parent=customer)
            except Exception:  # noqa: BLE001 - our own below
                _logger.info("Address link %s: shop form rules unavailable", self.id, exc_info=True)
        Country = self.env['res.country'].sudo()
        chosen = Country.browse()
        if country:
            chosen = (Country.search([('code', '=', str(country).upper())], limit=1)
                      if not str(country).isdigit() else Country.browse(int(country)).exists())
        default = self.request_id.sudo()._sa_book_country({})
        chosen = chosen or default
        suggested = []
        for near in (default, Country.search([('code', '=', 'IN')], limit=1), self.env.company.country_id):
            if near.code and near.code not in suggested:
                suggested.append(near.code)
        india = (chosen.code or '').upper() == 'IN'
        return {
            'ok': True,
            'suggested': suggested,
            'country': {'id': chosen.id, 'code': chosen.code or '', 'name': chosen.name or ''},
            'countries': [{'id': c.id, 'code': c.code, 'name': c.name,
                           'dial': '+%s' % c.phone_code if c.phone_code else ''}
                          for c in Country.search([], order='name')],
            'phone': self._phone_rule(chosen),
            'pin_length': 6 if india else 0,
            'pin_lookup': india,
            'states': [{'id': s.id, 'name': s.name, 'code': s.code}
                       for s in chosen.state_ids.sorted('name')],
        }

    @staticmethod
    def _national(phone, dial):
        """+919800011111 -> 9800011111 when the dial code is +91."""
        digits = re.sub(r'\D', '', phone or '')
        code = re.sub(r'\D', '', dial or '')
        if code and digits.startswith(code) and len(digits) > len(code) + 5:
            digits = digits[len(code):]
        return digits.lstrip('0') if code else digits

    def _form_context(self):
        """Everything the page opens with, read under sudo for this one link."""
        self.ensure_one()
        req = self.request_id.sudo()
        customer = self._customer()
        target = self.target_id.sudo() if self.mode == 'edit' else self.env['res.partner']
        meta = self._meta(target.country_id.code if target and target.country_id else None)
        dial = (meta.get('phone') or {}).get('dial') or ''
        phone = (target.phone if target else '') or customer.phone or req.requester_phone or ''
        if phone and dial and str(phone).startswith('+') and not str(phone).startswith(dial):
            phone = ''          # a number of another country is no use in front of this prefix
        values = {
            'label': 'Home',
            'country': meta['country']['code'],
            'name': ((target.name if target else '') or customer.name or req.requester_name or '').strip(),
            'phone': self._national(phone, dial),
        }
        if target:
            # Change an address: the form opens with it, every field filled in.
            label = target._sa_label()
            values.update({
                'label': label if label.lower() in LABELS else 'Other',
                'alt': self._national(target._sa_alt(), dial),
                'pin': re.sub(r'\D', '', target.zip or ''),
                'line': target.street or '', 'area': target.street2 or '',
                'landmark': target._sa_landmark(), 'town': target.city or '',
                'state_id': str(target.state_id.id or ''),
                'lat': ('%.6f' % target.partner_latitude) if target.partner_latitude else '',
                'lng': ('%.6f' % target.partner_longitude) if target.partner_longitude else '',
            })
        return {
            'ref': req._sa_book_ref(),
            'meta': meta,
            'edit': bool(target),
            'menu': self.back == 'menu',
            'values': values,
        }

    def _pincode(self, pin):
        """City, state and post-office areas for a pincode (India), the way
        the shop's form fills itself in."""
        self.ensure_one()
        pin = re.sub(r'\D', '', pin or '')
        shop = self._shop()
        if shop is not None and hasattr(shop, '_mart369_pincode_lookup'):
            try:
                return shop._mart369_pincode_lookup(pin)
            except Exception:  # noqa: BLE001
                return {'ok': False}
        if not re.fullmatch(r'\d{6}', pin):
            return {'ok': False}
        india = self.env['res.country'].sudo().search([('code', '=', 'IN')], limit=1)
        got = self.request_id.sudo()._sa_pincode_lookup(pin, india)
        if not got.get('city'):
            return {'ok': False}
        state = self.env['res.country.state'].sudo().browse(got.get('state_id') or 0).exists()
        return {'ok': True, 'pin': pin, 'town': got['city'], 'state_id': state.id or False,
                'state': state.name or '', 'areas': []}

    def _spot(self, pin):
        """Where a pincode roughly is, so the map opens there."""
        if 'mart369.postcode' not in self.env:
            return {'known': False}
        try:
            return self.env['mart369.postcode'].sudo()._mart369_spot((pin or '')[:12])
        except Exception:  # noqa: BLE001
            return {'known': False}

    def _search_place(self, text, country=None):
        """Places matching what was typed in the map's search box, for the map
        to move to: [{'name', 'lat', 'lng'}], at most five. OpenStreetMap's
        free search (Nominatim) with a generic app name - no personal details
        leave with it; it asks for about one search a second, which a person
        typing and pressing Search never comes near."""
        text = (text or '').strip()[:120]
        if len(text) < 3:
            return {'ok': True, 'places': []}
        params = {'format': 'jsonv2', 'q': text, 'limit': 5, 'addressdetails': 0}
        code = (country or '').strip().lower()
        if re.fullmatch(r'[a-z]{2}', code):
            params['countrycodes'] = code
        try:
            reply = requests.get('https://nominatim.openstreetmap.org/search', params=params, timeout=6,
                                 headers={'User-Agent': 'whatsapp-address-form/1.0', 'Accept-Language': 'en'})
            reply.raise_for_status()
            rows = reply.json() or []
        except Exception as err:  # noqa: BLE001 - the map still works by dragging
            _logger.info("Address link %s: place search failed: %s", self.id, err)
            return {'ok': False, 'places': []}
        places = []
        for row in rows[:5]:
            try:
                places.append({'name': row.get('display_name') or '',
                               'lat': float(row['lat']), 'lng': float(row['lon'])})
            except (KeyError, TypeError, ValueError):
                continue
        return {'ok': True, 'places': places}

    def _pin_check(self, pin, lat, lng):
        """Do the pincode and the map pin point to the same place? Only warns."""
        if 'mart369.postcode' not in self.env:
            return {'known': False}
        try:
            return self.env['mart369.postcode'].sudo()._mart369_pin_check(
                (pin or '')[:12], float(lat), float(lng))
        except Exception:  # noqa: BLE001
            return {'known': False}

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------
    def _body(self, post):
        """The posted form in the shop form's own shape."""
        get = lambda k, n=120: (post.get(k) or '').strip()[:n] if isinstance(post.get(k), str) else ''
        label = get('label', 10).capitalize()
        body = {
            'label': label if label.lower() in LABELS else 'Home',
            'country_id': get('country', 3).upper(),
            'name': get('name', 80),
            'phone': re.sub(r'\D', '', get('phone', 20)),
            'alt': re.sub(r'\D', '', get('alt', 20)),
            'pin': re.sub(r'\D', '', get('pin', 12)),
            'line': get('line'), 'area': get('area'), 'landmark': get('landmark'),
            'town': get('town', 60), 'state_id': get('state_id', 10),
        }
        lat, lng = get('lat', 20), get('lng', 20)
        try:
            flat, flng = float(lat), float(lng)
            if -90 <= flat <= 90 and -180 <= flng <= 180 and (flat or flng):
                body.update({'lat': flat, 'lng': flng})
        except ValueError:
            pass
        return body

    def _check(self, post):
        """(body, {field: message}) - the shop form's checks, word for word,
        then the shop's own server rules where they are installed."""
        self.ensure_one()
        body = self._body(post)
        meta = self._meta(body['country_id'] or None)
        body['country_id'] = meta['country']['code'] or body['country_id']
        phone_len = (meta.get('phone') or {}).get('length') or 0
        pin_len = meta.get('pin_length') or 0
        ok = (lambda v: len(v) == phone_len) if phone_len else (lambda v: bool(re.fullmatch(r'\d{6,15}', v)))
        x = {}
        if not body['name']:
            x['name'] = _("Enter the receiver's name")
        if not ok(body['phone']):
            x['phone'] = (_("Enter a %s-digit mobile number") % phone_len) if phone_len \
                else _("Enter a valid mobile number")
        if body['alt'] and not ok(body['alt']):
            x['alt'] = (_("Enter a %s-digit number, or leave it empty") % phone_len) if phone_len \
                else _("Enter a valid number")
        if body['alt'] and body['alt'] == body['phone']:
            x['alt'] = _("Use a different number, or leave it empty")
        if (len(body['pin']) != pin_len) if pin_len else not re.fullmatch(r'\d{3,10}', body['pin']):
            x['pin'] = (_("Enter a %s-digit postcode") % pin_len) if pin_len else _("Enter a valid postcode")
        if not body['line']:
            x['line'] = _("Enter the house no., building or apartment")
        if not body['area']:
            x['area'] = _("Enter the street or area")
        if not body['town']:
            x['town'] = _("Enter the city, district or town")
        state_ids = [s['id'] for s in meta.get('states') or []]
        if state_ids and (not body['state_id'].isdigit() or int(body['state_id']) not in state_ids):
            x['state'] = _("Pick a state")
        if x:
            return body, x
        shop = self._shop()
        if shop is not None:
            values, err = shop._mart369_address_values(dict(body), address=self._shop_target(),
                                                       parent=self._customer())
            if err:
                message, fld = err
                fld = {'city': 'town', 'state_id': 'state', 'country_id': 'country'}.get(fld, fld)
                return body, {fld if fld in ('name', 'phone', 'alt', 'pin', 'line', 'area', 'town',
                                             'state', 'country') else 'form': message}
        return body, {}

    def _shop_target(self):
        """The address being changed, as the shop's rules see it: a saved
        address under the customer. The customer's own contact (an old 'home'
        kept on the contact itself) is checked as a new address instead."""
        self.ensure_one()
        target = self.target_id.sudo() if self.mode == 'edit' else self.env['res.partner']
        if target and target == self._customer():
            return self.env['res.partner']
        return target

    def _save_address(self, body):
        """The checked form -> an address in the customer's book: a new one,
        or the saved one this form changes."""
        self.ensure_one()
        req = self.request_id.sudo()
        customer = self._customer()
        target = self.target_id.sudo().exists() if self.mode == 'edit' else self.env['res.partner']
        shop = self._shop()
        if shop is not None:
            values, _err = shop._mart369_address_values(dict(body), address=self._shop_target(),
                                                       parent=customer)
            pin = {k: values.pop(k) for k in ('partner_latitude', 'partner_longitude') if k in values}
            if target and target == customer:
                # the customer's own contact: changed in place, keeping who they are
                values = {k: v for k, v in values.items() if k not in ('name', 'phone')}
                customer.write(values)
                addr = customer
            elif target:
                # the shop's rule: an address an order went to is copied, not rewritten
                if hasattr(target, '_mart369_revise'):
                    addr = target._mart369_revise(values)
                else:
                    target.write(values)
                    addr = target
            else:
                probe = self.env['res.partner'].new({'street': values.get('street'),
                                                     'street2': values.get('street2'), 'zip': values.get('zip')})
                same = req._sa_address_book(customer).filtered(
                    lambda a: a != customer and req._sa_addr_dedupe_key(a) == req._sa_addr_dedupe_key(probe))[:1]
                if same and hasattr(same, '_mart369_revise'):
                    addr = same._mart369_revise(values)
                else:
                    addr = customer._mart369_add_address(values)
            if pin:
                addr.write(pin)     # after the address lines: Odoo clears a pin written before them
            return addr
        # Without the shop: the WhatsApp address book's own save, same fields.
        country = self.env['res.country'].sudo().search([('code', '=', body['country_id'])], limit=1)
        dial = ('+%s' % country.phone_code) if country.phone_code else ''
        vals = {'label': body['label'], 'line': body['line'], 'area': body['area'],
                'landmark': body['landmark'], 'zip': body['pin'], 'city': body['town'],
                'country_id': country.id or req._sa_book_country({}).id,
                'alt': (dial + body['alt']) if body['alt'] else ''}
        if body['state_id'].isdigit():
            vals['state_id'] = int(body['state_id'])
        if body.get('lat'):
            vals.update({'lat': body['lat'], 'lng': body['lng']})
        if target:
            addr = req._sa_book_save_edit({'target': target.id, 'vals': vals})
        else:
            addr = req._sa_book_create({'vals': vals})
        if addr != customer:
            addr.write({'name': body['name'], 'phone': dial + body['phone']})
        return addr

    def _submit(self, post, ip='', ua=''):
        """Save the form. Returns (address, errors); errors when nothing was
        saved. The group is told and moves on, exactly as when the last group
        question is answered."""
        self.ensure_one()
        link = self.sudo()
        body, errors = link._check(post)
        if errors:
            return self.env['res.partner'], errors
        req = link.request_id
        addr = link._save_address(body)
        st = req._sa_book_state()
        st.update({'back': link.back or st.get('back') or 'order', 'mode': link.mode or 'add',
                   'vals': {}, 'target': addr.id})
        link.write({'used_on': fields.Datetime.now(), 'used_ip': (ip or '')[:64],
                    'used_ua': (ua or '')[:250], 'address_id': addr.id})
        _logger.info("Sales Automation: enquiry %s - address %s %s on the form link %s",
                     req.id, addr.id, 'changed' if link.mode == 'edit' else 'filled in', link.id)
        said = _("✅ Address updated from the form:\n%s") if link.mode == 'edit' \
            else _("✅ Address saved from the form:\n%s")
        if st['back'] == 'order':
            req._say(said % addr._sa_addr_title())
        # from the menu, the finish line itself says "Delivery address set"
        req._sa_book_finish(addr, st)
        return addr, {}

class SaSalesGroupInvite(models.Model):
    _inherit = 'sa.sales.group'

    invite_url = fields.Char(
        'Group Invite Link',
        help="The group's invite link (WhatsApp > group info > Invite via link), "
             "like https://chat.whatsapp.com/AbCd... The \"Back to WhatsApp group\" "
             "button on the pages sent privately (address form) opens this group. "
             "Empty: the button opens WhatsApp.")

    invite_checked_on = fields.Datetime('Invite Link Checked', readonly=True)
    invite_error = fields.Char(
        'Invite Link Problem', readonly=True,
        help="Why the last try to get the invite link from WhatsApp failed.")
    invite_hint = fields.Char(compute='_compute_invite_hint')

    @api.depends('invite_url')
    def _compute_invite_hint(self):
        for group in self:
            if (group.invite_url or '').strip().startswith('https://chat.whatsapp.com/'):
                group.invite_hint = _("The “Back to WhatsApp group” button opens this group.")
            else:
                group.invite_hint = _("Empty: the button opens WhatsApp. Press Get invite link "
                                      "(the shop's number must be a group admin), or paste the link.")

    def _sa_back_url(self):
        """Where "Back to WhatsApp group" goes: this group, or WhatsApp itself."""
        url = (self[:1].invite_url or '').strip()
        if url.startswith('https://chat.whatsapp.com/'):
            return url
        return 'whatsapp://'

    def _sa_invite_from_gateway(self):
        """(url, error) - the group's invite link asked from WhatsApp. Only a
        group admin gets one, so a refusal usually means the shop's number is
        not an admin. Never raises."""
        self.ensure_one()
        session = self.session_id.sudo()
        if not session or not self.group_jid or not session.instance_name:
            return '', _("This group has no WhatsApp session linked.")
        try:
            body = session._gateway_call(
                'GET', '/group/inviteCode/%s?groupJid=%s' % (session.instance_name, self.group_jid),
                timeout=8)
        except Exception as err:  # noqa: BLE001 - said on the screen instead
            return '', str(getattr(err, 'args', [err])[0] if getattr(err, 'args', None) else err)[:300]
        body = body if isinstance(body, dict) else {}
        url = str(body.get('inviteUrl') or '')
        code = str(body.get('inviteCode') or '')
        if not url.startswith('https://chat.whatsapp.com/') and code:
            url = 'https://chat.whatsapp.com/%s' % code
        if url.startswith('https://chat.whatsapp.com/'):
            return url, ''
        return '', _("WhatsApp gave no invite link.")

    def action_sa_get_invite_link(self):
        """Get invite link: ask WhatsApp for each group's link and keep it, or
        say plainly why it could not be had."""
        found = failed = 0
        for group in self.filtered(lambda g: g.group_type == 'customer'):
            url, error = group._sa_invite_from_gateway()
            vals = {'invite_checked_on': fields.Datetime.now()}
            if url:
                vals.update({'invite_url': url, 'invite_error': False})
                found += 1
            else:
                vals['invite_error'] = _(
                    "WhatsApp did not give the invite link. Make the shop's number (session %(session)s) "
                    "an admin of this group and try again, or paste the link from Group info > "
                    "Invite via link.\n%(why)s",
                    session=group.session_id.name or '-', why=error or '')[:500]
                failed += 1
            group.sudo().write(vals)
        if failed and not found:
            kind, title = 'warning', _("No invite link")
        elif failed:
            kind, title = 'warning', _("Some invite links missing")
        else:
            kind, title = 'success', _("Invite link saved")
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': title, 'type': kind, 'sticky': bool(failed),
                'message': _("%(found)s found, %(failed)s not given by WhatsApp. "
                             "A group without one: make the shop's number an admin, or paste the link.",
                             found=found, failed=failed),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }


class SaGroupRequestAddressLink(models.Model):
    _inherit = 'sa.group.request'

    sa_addr_link_ids = fields.One2many('sa.address.link', 'request_id', 'Address form links')
    sa_book_step = fields.Selection(selection_add=[('form', 'Waiting for the address form')])

    def _sa_addr_link_live(self):
        self.ensure_one()
        links = self.env['sa.address.link'].sudo().search(
            [('request_id', '=', self.id), ('used_on', '=', False)])
        return links.filtered(lambda l: l._alive())[:1]

    def _sa_addr_links_close(self):
        """The address was decided another way: the open links stop working."""
        links = self.env['sa.address.link'].sudo().search(
            [('request_id', 'in', self.ids), ('used_on', '=', False)])
        if links:
            links.write({'active': False})

    def _sa_addr_link_wanted(self, st):
        """The form is used for this address step: switched on, and either an
        order's address or the menu's CHANGE ADDRESS."""
        self.ensure_one()
        if not self._settings().address_link_enabled:
            return False
        back = st.get('back')
        return back == 'menu' or (back == 'order' and bool(self.order_id))

    def _sa_addr_link_words(self, link):
        """(what it is for, ' for order #ref' or '') - for the messages."""
        ref = self._sa_book_ref()
        order = (_(" for order *#%s*") % ref) if link.back == 'order' else ''
        if link.mode == 'edit':
            label = link.target_id.sudo()._sa_label() if link.target_id else _("saved")
            return _("change your *%s* address") % label, order
        return _("fill your delivery address"), order

    def _sa_addr_link_send(self, mode='add', target=None, back='order'):
        """The link: privately when we can write to the customer, otherwise
        in the group marked for them."""
        self.ensure_one()
        target = target or self.env['res.partner']
        if not self.env['sa.outbox.guard'].sudo().claim(
                'addrlink|%s|%s|%s' % (self.id, mode, target.id or 0), 120):
            return False
        minutes = max(5, self._settings().address_link_minutes or 30)
        link = self.env['sa.address.link'].sudo().create({
            'request_id': self.id, 'mode': mode, 'back': back,
            'target_id': target.id or False,
            'expires_on': fields.Datetime.now() + timedelta(minutes=minutes),
        })
        try:
            url = link._url()
        except Exception:
            link.unlink()   # never leave a link nobody was given
            raise
        what, order = self._sa_addr_link_words(link)
        phone = self._sa_dm_target()
        sent = False
        if phone:
            head = (_("✏️ Change your *%s* address") % link.target_id.sudo()._sa_label()) \
                if mode == 'edit' else _("\U0001F3E0 Your delivery address")
            text = _("%(head)s%(order)s\n\nFill it in here \U0001F449 %(url)s\n\n"
                     "_Only for you · works once · %(min)s min_",
                     head=head, order=order, url=url, min=minutes)
            try:
                sent = bool(self.group_id.session_id.send_message(phone, text))
            except Exception as err:  # noqa: BLE001 - the group gets the link instead
                _logger.info("Sales Automation: enquiry %s - private address link not sent: %s",
                             self.id, err)
        if sent:
            link.write({'sent_to': 'private'})
            self._sa_mark_private()
            # Form only (owner, 21 Nov 2026): no "or answer here" and no poll after it.
            self._say(_("\U0001F4E9 I've sent you a form in your *private chat* to %(what)s%(order)s "
                        "\U0001F512", what=what, order=order))
        else:
            link.write({'sent_to': 'group'})
            who = (self.requester_name or '').strip() or _("you")
            self._say(_("\U0001F4DD A form to %(what)s \U0001F449 %(url)s\n\n"
                        "_Only for %(who)s · works once · %(min)s min_\n\n"
                        "Or answer here \U0001F447", what=what, url=url, who=who, min=minutes))
        return link

    def _sa_addr_form_wait(self, st, link):
        """The link went privately: the group waits for the form, no questions."""
        editing = link.mode == 'edit' and link.target_id
        st.update({'mode': link.mode or 'add', 'vals': {}, 'bad': '', 'trail': [],
                   'target': link.target_id.id if editing else False})
        if editing:
            st['target_label'] = link.target_id.sudo()._sa_label()
        self._sa_book_set(step='form', state=st, sa_book_asked_on=fields.Datetime.now())
        return True

    def _sa_addr_form_questions(self, st):
        """No private chat after all: the group questions, as the book starts them."""
        target = self.env['res.partner'].sudo().browse(st.get('target') or 0).exists()
        if st.get('mode') == 'edit' and target:
            return super(SaGroupRequestAddressLink, self)._sa_book_start_edit(st, target)
        return super(SaGroupRequestAddressLink, self)._sa_book_start_add(st)

    def _sa_addr_form_remind(self):
        """Something was said in the group while the form is out: point at the
        private chat again, with a new link when the old one has run out."""
        self.ensure_one()
        st = self._sa_book_state()
        live = self._sa_addr_link_live()
        if live:
            self.sudo().write({'sa_book_asked_on': fields.Datetime.now()})
            what, order = self._sa_addr_link_words(live)
            return self._say(_("\U0001F512 Please use the form in your *private chat* to %(what)s%(order)s.",
                               what=what, order=order))
        self._sa_addr_links_close()
        target = self.env['res.partner'].sudo().browse(st.get('target') or 0).exists()
        mode = 'edit' if st.get('mode') == 'edit' and target else 'add'
        link = None
        try:
            link = self._sa_addr_link_send(mode, target if mode == 'edit' else None,
                                           st.get('back') or 'order')
        except Exception:  # noqa: BLE001 - the group questions instead
            _logger.exception("Sales Automation: enquiry %s - new address link failed", self.id)
        if link and link.sent_to == 'private':
            return self._sa_addr_form_wait(st, link)
        return self._sa_addr_form_questions(st)

    def _sa_addr_link_route(self, st, mode, target=None):
        """Use the form for this step. True when the group now waits for it;
        None when the group questions go on as before."""
        self.ensure_one()
        if not self._sa_addr_link_wanted(st):
            return None
        target = target or self.env['res.partner']
        back = st.get('back') or 'order'
        live = self._sa_addr_link_live()
        if live and (live.mode, live.target_id.id or False, live.back) != (mode, target.id or False, back):
            self._sa_addr_links_close()     # a link for another address, or another job
            live = None
        link = live
        if not link:
            try:
                link = self._sa_addr_link_send(mode, target, back)
            except Exception:  # noqa: BLE001 - the group questions still go out
                _logger.exception("Sales Automation: enquiry %s - address link failed", self.id)
        if link and link.sent_to == 'private':
            return self._sa_addr_form_wait(st, link)
        return None

    # ---- hooks into the address book ----
    def _sa_book_start_add(self, st):
        """➕ Add a new address - in an order or from CHANGE ADDRESS."""
        if self._sa_addr_link_route(st, 'add'):
            return True
        return super()._sa_book_start_add(st)

    def _sa_book_start_edit(self, st, addr):
        """✏️ Edit an address: the form, filled in with it."""
        if addr and self._sa_addr_link_route(st, 'edit', addr):
            return True
        return super()._sa_book_start_edit(st, addr)

    def _sa_book_ask(self, note=''):
        if self.sa_book_step == 'form':
            return self._sa_addr_form_remind()
        return super()._sa_book_ask(note=note)

    def _sa_book_take(self, text):
        if self.sa_book_step == 'form':
            if self._sa_is_cancel(text or ''):
                return self._sa_book_cancel()
            return self._sa_addr_form_remind()
        return super()._sa_book_take(text)

    def _sa_book_finish(self, addr, st):
        self._sa_addr_links_close()
        return super()._sa_book_finish(addr, st)

    def _sa_book_cancel(self):
        self._sa_addr_links_close()
        return super()._sa_book_cancel()
