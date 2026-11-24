# -*- coding: utf-8 -*-
"""The counter's side of an enquiry that is waiting for a vendor choice.

The model and the parking live in `sales_automation`; only the screen's API
is here, because only this module has the bus and the screen.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaGroupRequest(models.Model):
    _inherit = 'sa.group.request'

    # ------------------------------------------------------------------
    # Telling the screen
    # ------------------------------------------------------------------
    def _sa_enquiry_notify(self):
        """Push, do not poll. Same shape as the packing screen's notify."""
        for request in self:
            try:
                self.env['bus.bus']._sendone(
                    'sa_store_0', 'sa_enquiry/refresh', {'id': request.id})
            except Exception as err:  # noqa: BLE001 - a screen that missed a
                _logger.warning(      # nudge still redraws on its next action
                    "Sales Automation: could not notify the enquiry desk "
                    "about %s: %s", request.id, err)
        return True

    # ------------------------------------------------------------------
    # What the screen shows
    # ------------------------------------------------------------------
    @api.model
    def sa_enquiry_queue(self):
        """Every enquiry waiting for somebody to choose its vendors."""
        now = fields.Datetime.now()
        waiting = self.sudo().search(
            [('state', '=', 'awaiting_vendor_pick')],
            order='shop_pick_deadline asc, id asc')
        rows = []
        for request in waiting:
            # Snapshot plus whatever the category names right now: somebody
            # adding the right supplier while the card sits on the counter is
            # the most likely moment for one to be added, and a list that
            # cannot show them makes the screen useless at exactly that point.
            candidates = request.shop_pick_vendor_ids
            try:
                live, _flag = request._sa_vendor_candidates()
                candidates = candidates | live
            except Exception as err:  # noqa: BLE001 - the snapshot is enough
                _logger.warning(      # to keep the counter working
                    "Sales Automation: could not refresh the vendor list for "
                    "enquiry %s: %s", request.id, err)
            vendors = []
            for partner in candidates:
                phone = (partner.phone or '').strip()
                vendors.append({
                    'id': partner.id,
                    'name': partner.name or '',
                    'phone': phone,
                    # Shown but not tickable: _start_sourcing would try to
                    # message a blank number and only log the failure.
                    'ok': bool(phone),
                })
            vendors.sort(key=lambda v: (not v['ok'], v['name'].lower()))
            left = 0
            if request.shop_pick_deadline:
                left = int((request.shop_pick_deadline - now).total_seconds())
            waited = 0
            if request.create_date:
                # max(0, ...): floor division turned a card a fraction of a
                # second old into "-1 min", which reads as broken.
                waited = max(0, int(
                    (now - request.create_date).total_seconds() // 60))
            product = request.product_id
            rows.append({
                'id': request.id,
                'ref': request.ref_code or str(request.id),
                'product': (product.name or request.ai_search_term
                            or request.raw_text or ''),
                'qty': int(request.qty or 0),
                'customer': request.requester_name or request.requester_phone or '',
                'phone': request.requester_phone or '',
                'group': request.group_id.name or '',
                'category': product.categ_id.complete_name or '',
                'no_categ': bool(request.shop_pick_no_categ),
                'waiting': waited,
                'seconds_left': max(0, left),
                'vendors': vendors,
            })
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        stalled = self._sa_stalled_rows(now)
        return {
            'rows': rows,
            'tracking': self._sa_tracking_rows(now),
            'stalled': stalled,
            # Counted and rung separately: the two alarms answer different
            # questions and one must not silence the other.
            'stalled_ringing': len(stalled),
            'stalled_ring': max(3, settings.stalled_ring_seconds or 30),
            'stalled_repeat': max(30, (settings.stalled_repeat_minutes or 2)
                                  * 60),
            'stalled_max_minutes': max(0, settings.stalled_alarm_minutes or 0),
            'ringing': len(rows),
            'ring': max(3, settings.enquiry_ring_seconds or 30),
            'repeat': max(3, settings.enquiry_repeat_seconds or 10),
            'max_minutes': max(0, settings.enquiry_alarm_minutes or 0),
        }

    @api.model
    def sa_alarm_state(self):
        """Counts and cadence only - small enough to poll from every screen.

        The background alarm runs on every page of the web client, so this is
        deliberately not `sa_enquiry_queue`: no vendor lists, no message
        threads, no per-card work. Two counts and the numbers needed to ring.
        """
        now = fields.Datetime.now()
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        picks = self.sudo().search([('state', '=', 'awaiting_vendor_pick')])
        # The furthest deadline, not the nearest: the alarm should keep going
        # while any card still has time to be decided.
        seconds_left = 0
        for request in picks:
            if request.shop_pick_deadline:
                seconds_left = max(seconds_left, int(
                    (request.shop_pick_deadline - now).total_seconds()))
        return {
            'pick': len(picks),
            'pick_seconds_left': max(0, seconds_left),
            'stalled': self.sudo().search_count(
                [('state', '=', 'sourcing'), '|', '|', ('sa_price_stalled', '=', True), ('sa_price_choice_pending', '=', True),
                 ('sa_vendor_choice_pending', '=', True)]),
            'ring': max(3, settings.enquiry_ring_seconds or 30),
            'repeat': max(3, settings.enquiry_repeat_seconds or 10),
            'stalled_ring': max(3, settings.stalled_ring_seconds or 30),
            'stalled_repeat': max(30, (settings.stalled_repeat_minutes or 2)
                                  * 60),
            'stalled_max_minutes': max(0, settings.stalled_alarm_minutes or 0),
        }

    @api.model
    def _sa_stalled_rows(self, now, limit=30):
        """Enquiries where every vendor stayed silent.

        These need a person, not more waiting: somebody phones the supplier
        and types the number in. The row carries the vendors that were asked
        so the price can be attributed, and the public link so it can be
        finished on a phone away from the counter.
        """
        stalled = self.sudo().search(
            [('state', '=', 'sourcing'), '|', '|', ('sa_price_stalled', '=', True), ('sa_price_choice_pending', '=', True),
                 ('sa_vendor_choice_pending', '=', True)],
            order='sa_price_asked_on asc, id asc', limit=limit)
        rows = []
        for request in stalled:
            asked = request.sourcing_vendor_ids
            replied = set(request.quote_ids.mapped('partner_id').ids)
            vendors = [{'id': p.id, 'name': p.name or '', 'ok': True}
                       for p in asked]
            vendors.sort(key=lambda v: v['name'].lower())
            yes, no, silent = request._sa_vendor_lists()
            seller, hint = request._sa_price_hint()
            since = request.sa_price_asked_on or request.create_date
            waited = 0
            if since:
                waited = max(0, int((now - since).total_seconds() // 60))
            rows.append({
                'id': request.id,
                'ref': request.ref_code or str(request.id),
                'product': (request.product_id.name or request.ai_search_term
                            or request.raw_text or ''),
                'qty': int(request.qty or 0),
                'customer': (request.requester_name
                             or request.requester_phone or ''),
                'group': request.group_id.name or '',
                'silent': silent[:6],
                'said_yes': yes[:6],
                'held': request._sa_held_lines()[:6],
                'held_why': request._sa_held_why(),
                'said_no': no[:6],
                'hint_cost': hint,
                'hint_vendor': seller.partner_id.name if seller else '',
                'vendors': vendors,
                # Vendor price differs from the product page: approve one.
                'choice': ({
                    'page': request.sa_price_page,
                    'vendor': request.sa_price_vendor,
                    'cost': request.vendor_price,
                    'vendor_name': (request.sa_price_choice_quote_id.vendor_name
                                    or request.sa_price_choice_quote_id.partner_id.name
                                    or request.best_quote_id.vendor_name or ''),
                } if request.sa_price_choice_pending else None),
                'no_vendors': not asked and not request.sa_price_choice_pending and not request.sa_vendor_choice_pending,
                'categ': request.product_id.categ_id.display_name or '',
                'waiting': waited,
                'margin': request._sa_margin(),
                'currency': (request.currency_id.name
                             or self.env.company.currency_id.name or ''),
                'link': request._sa_price_entry_url() or '',
            })
        return rows

    @api.model
    def _sa_tracking_rows(self, now, limit=30):
        """Enquiries already put to vendors, and how they are going.

        The card used to disappear the moment the vendors were asked, which
        is exactly when the shop starts wondering who has answered.
        """
        sent = self.sudo().search([
            ('state', 'in', ('sourcing', 'quoted', 'negotiating')),
            # An enquiry nobody answered stays `sourcing` on purpose, so
            # without this it would sit in both halves of the screen at once
            # - counted twice, and shown as "waiting for suppliers" when the
            # waiting is over and it is a person who is needed.
            ('sa_price_stalled', '=', False),
        ], order='sourcing_deadline desc, id desc', limit=limit)
        rows = []
        for request in sent:
            asked = request.sourcing_vendor_ids
            quotes = request.quote_ids
            replied_ids = set(quotes.mapped('partner_id').ids)
            best = quotes.filtered('is_best')[:1] or quotes.sorted('price')[:1]
            left = 0
            if request.sourcing_deadline:
                left = int((request.sourcing_deadline - now).total_seconds())
            rows.append({
                'id': request.id,
                'ref': request.ref_code or str(request.id),
                'product': (request.product_id.name or request.ai_search_term
                            or request.raw_text or ''),
                'customer': (request.requester_name
                             or request.requester_phone or ''),
                'state': request.state,
                'asked': len(asked),
                'replied': len(quotes),
                'waiting_on': [p.name for p in asked
                               if p.id not in replied_ids][:6],
                'best_price': best.price if best else 0.0,
                'best_vendor': best.partner_id.name or best.vendor_name or ''
                               if best else '',
                'quoted_price': request.quoted_price or 0.0,
                'currency': request.currency_id.name or '',
                'seconds_left': max(0, left),
                'closed': left <= 0,
            })
        return rows

    @api.model
    def sa_enquiry_detail(self, request_id):
        """Everything that happened on one enquiry, for the detail panel."""
        request = self.sudo().browse(int(request_id))
        if not request.exists():
            raise UserError(_("That enquiry is no longer there."))
        now = fields.Datetime.now()

        quote_by_partner = {}
        for quote in request.quote_ids:
            quote_by_partner.setdefault(quote.partner_id.id, quote)

        vendors = []
        # Everyone asked, whether or not they bothered to answer - a silent
        # supplier is information too.
        pool = request.sourcing_vendor_ids or request.shop_pick_vendor_ids
        for partner in pool:
            quote = quote_by_partner.get(partner.id)
            vendors.append({
                'id': partner.id,
                'name': partner.name or '',
                'phone': (partner.phone or '').strip(),
                'replied': bool(quote),
                'price': quote.price if quote else 0.0,
                'delay_days': quote.delay_days if quote else None,
                'minutes': quote.response_minutes if quote else None,
                'text': (quote.raw_text or '')[:300] if quote else '',
                'is_best': bool(quote and quote.is_best),
                'at': (quote.create_date.isoformat() + 'Z') if quote else '',
            })
        # Answered first, cheapest first within that.
        vendors.sort(key=lambda v: (not v['replied'], v['price'] or 0))

        # A quote from somebody who was never on the list still counts.
        known = {v['id'] for v in vendors}
        for quote in request.quote_ids:
            if quote.partner_id.id in known:
                continue
            vendors.append({
                'id': quote.partner_id.id or 0,
                'name': quote.partner_id.name or quote.vendor_name or '',
                'phone': quote.vendor_phone or '',
                'replied': True,
                'price': quote.price,
                'delay_days': quote.delay_days,
                'minutes': quote.response_minutes,
                'text': (quote.raw_text or '')[:300],
                'is_best': bool(quote.is_best),
                'at': quote.create_date.isoformat() + 'Z',
            })

        # ---- the conversation, scoped to THIS enquiry -------------------
        Msg = self.env['whatsapp.message'].sudo()
        phone = (request.requester_phone or '').strip()
        ref = (request.ref_code or '').strip()
        started = request.create_date or now

        # The window closes where this person's next enquiry in the same
        # group opens; otherwise one customer asking three times would see
        # all three conversations in each history.
        following = self.sudo().search([
            ('id', '!=', request.id),
            ('group_id', '=', request.group_id.id),
            ('requester_phone', '=', request.requester_phone),
            ('create_date', '>', started),
        ], order='create_date asc', limit=1)
        ends = following.create_date if following else fields.Datetime.add(
            now, minutes=1)

        vendor_phones = set()
        for partner in (request.sourcing_vendor_ids
                        | request.shop_pick_vendor_ids):
            digits = (partner.phone or '').strip()
            if digits:
                vendor_phones.add(digits[-9:])
        for quote in request.quote_ids:
            digits = (quote.vendor_phone or '').strip()
            if digits:
                vendor_phones.add(digits[-9:])

        # What is actually recorded as belonging to this enquiry.
        found = Msg.search([('sa_request_id', '=', request.id)],
                           order='id asc', limit=200)
        found |= request.message_id
        found |= request.quote_ids.mapped('message_id')
        if ref:
            # Our own text carries "_Ref FT_" and a vendor answers "#FT 450",
            # so the code identifies a message even when nothing tagged it.
            found |= Msg.search([
                ('message', 'ilike', '#%s' % ref),
                ('create_date', '>=', started),
            ], order='id asc', limit=60)
            found |= Msg.search([
                ('message', 'ilike', 'Ref %s' % ref),
                ('create_date', '>=', started),
            ], order='id asc', limit=60)

        if not found:
            # Enquiries from before messages were tagged. A window is a guess
            # - two enquiries seconds apart cannot be separated by it - so it
            # is used only when there is nothing better.
            if phone:
                found |= Msg.search([
                    ('phone', 'like', phone[-9:]),
                    ('create_date', '>=', started),
                    ('create_date', '<=', ends),
                ], order='id asc', limit=60)
            for tail in vendor_phones:
                found |= Msg.search([
                    ('phone', 'like', tail),
                    ('create_date', '>=', started),
                    ('create_date', '<=', ends),
                ], order='id asc', limit=30)

        def _side(msg):
            """customer / us / vendor."""
            tail = (msg.phone or '')[-9:]
            if tail and tail in vendor_phones:
                return 'vendor' if msg.direction == 'incoming' else 'us'
            return 'customer' if msg.direction == 'incoming' else 'us'

        def _who_name(msg):
            tail = (msg.phone or '')[-9:]
            if tail and tail in vendor_phones:
                for partner in (request.sourcing_vendor_ids
                                | request.shop_pick_vendor_ids):
                    if (partner.phone or '').strip()[-9:] == tail:
                        return partner.name or ''
            return ''

        messages, vendor_messages = [], []
        for msg in found.sorted('id'):
            tail = (msg.phone or '')[-9:]
            entry = {
                'who': _side(msg),
                'name': _who_name(msg),
                'direction': msg.direction,
                'phone': msg.phone or '',
                'text': (msg.message or '')[:400],
                'status': msg.status or '',
                'at': msg.create_date.isoformat() + 'Z',
            }
            if tail and tail in vendor_phones:
                vendor_messages.append(entry)
            else:
                messages.append(entry)

        return {
            'id': request.id,
            'ref': request.ref_code or str(request.id),
            'product': (request.product_id.name or request.ai_search_term
                        or request.raw_text or ''),
            'asked_text': request.raw_text or '',
            'qty': int(request.qty or 0),
            'state': request.state,
            'drop_reason': request.drop_reason or '',
            'customer': request.requester_name or phone,
            'phone': phone,
            'group': request.group_id.name or '',
            'category': request.product_id.categ_id.complete_name or '',
            'no_categ': bool(request.shop_pick_no_categ),
            'currency': request.currency_id.name or '',
            'quoted_price': request.quoted_price or 0.0,
            'agreed_price': request.agreed_price or 0.0,
            'vendor_price': request.vendor_price or 0.0,
            'chosen_by': request.shop_pick_user_id.name or '',
            'auto_sent': bool(request.shop_pick_auto),
            'elapsed_seconds': max(0, int((now - started).total_seconds())),
            'seconds_left': max(0, int(
                (request.sourcing_deadline - now).total_seconds()))
                if request.sourcing_deadline else 0,
            'vendors': vendors,
            'messages': messages,
            'vendor_messages': vendor_messages,
        }

    # ------------------------------------------------------------------
    # What the screen's buttons do
    # ------------------------------------------------------------------
    @api.model
    def sa_enquiry_act(self, request_id, action, vendor_ids=None,
                       cost=None, days=0, choice=None):
        """One entry point for every button, like sa_store_act."""
        request = self.sudo().browse(int(request_id))
        if not request.exists():
            raise UserError(_("That enquiry is no longer there."))
        if action == 'approve_price':
            # Above the state guard for the same reason as set_price: the
            # enquiry is still `sourcing` while the counter decides.
            if not request.sa_price_choice_pending:
                return self.sa_enquiry_queue()   # somebody got there first
            request._sa_apply_price_choice(choice or 'page', sell=cost,
                                           source=_("counter screen"))
            _logger.info("Sales Automation: enquiry %s price approved at the "
                         "counter (%s) by %s", request.id, choice,
                         self.env.user.name)
            request._sa_enquiry_notify()
            return self.sa_enquiry_queue()
        if action == 'set_price':
            # Deliberately above the guard below. A stalled enquiry is still
            # `sourcing` - that is what keeps every existing lookup working -
            # so the guard would reject the one action this section exists
            # for. Validation lives in `_sa_apply_manual_price`, shared with
            # the public link, so a price typed here and one typed there
            # cannot diverge.
            if not request.sa_price_stalled:
                return self.sa_enquiry_queue()   # somebody got there first
            picked = [int(v) for v in (vendor_ids or []) if v]
            request._sa_apply_manual_price(
                cost, vendor_id=(picked[0] if picked else None),
                days=days, source=_("counter screen"))
            _logger.info("Sales Automation: enquiry %s priced at the counter "
                         "by %s", request.id, self.env.user.name)
            request._sa_enquiry_notify()
            return self.sa_enquiry_queue()

        if request.state != 'awaiting_vendor_pick':
            # Somebody else got there first, or the timeout did. Not an
            # error - just redraw so the card disappears.
            return self.sa_enquiry_queue()

        if action == 'skip':
            # Nobody to ask: held for a typed price, not dropped.
            request._sa_nobody_to_ask()
            _logger.info("Sales Automation: enquiry %s skipped at the counter "
                         "by %s - waits for a price", request.id,
                         self.env.user.name)
        elif action in ('send', 'send_all'):
            offered = request.shop_pick_vendor_ids
            try:
                live, _flag = request._sa_vendor_candidates()
                offered = offered | live
            except Exception:  # noqa: BLE001
                pass
            if action == 'send_all':
                chosen = offered
            else:
                wanted = [int(v) for v in (vendor_ids or [])]
                # Intersected with what was actually offered: the screen must
                # not be able to message a partner this enquiry never showed.
                chosen = offered.filtered(
                    lambda partner: partner.id in wanted)
            chosen = chosen.filtered(lambda partner: (partner.phone or '').strip())
            if not chosen:
                raise UserError(
                    _("Choose at least one vendor with a phone number."))
            request.write({
                'shop_pick_user_id': self.env.uid,
                'shop_pick_done_on': fields.Datetime.now(),
                'shop_pick_auto': False,
            })
            request._start_sourcing(chosen)
            _logger.info("Sales Automation: enquiry %s - %s asked %d vendor(s) "
                         "from the counter", request.id, self.env.user.name,
                         len(chosen))
        else:
            raise UserError(_("Unknown action %s.", action))

        request._sa_enquiry_notify()
        return self.sa_enquiry_queue()
