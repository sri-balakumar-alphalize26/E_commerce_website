# -*- coding: utf-8 -*-
"""Ordering from a vendor after the sale order (owner, 24 Nov 2026): the popup
knows every price of the enquiry, also one that came after the order, and
recommends the lowest. Any vendor can be chosen. Automatic does the same by
itself, and stops for a person whenever something is not plain."""
import logging
from datetime import datetime, timedelta

import psycopg2
import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

from .sa_boards import iso

_logger = logging.getLogger(__name__)

DAY = 24 * 60
ONCE = 90 * 86400           # the same order to the same vendor: never again


class SaAiSettingsSupply(models.Model):
    _inherit = 'sa.ai.settings'

    supply_mode = fields.Selection([('manual', 'Manual'), ('auto', 'Automatic')], string='Who Orders From the Vendor',
                                   default='manual', required=True)
    supply_auto_start = fields.Selection([('paid', 'Has paid'), ('signed', 'Has signed')], string='Start When the Customer',
                                         default='paid', required=True)
    supply_auto_wait = fields.Integer('Wait for Late Prices (minutes)', default=10)
    supply_auto_margin = fields.Float('Lowest Margin to Order Automatically (%)', default=10.0)
    supply_auto_limit = fields.Float('Order by Itself Up To', default=500.0)
    supply_auto_days = fields.Integer('Goods Here After (days)', default=1)
    supply_customer_days = fields.Integer('Deliver to the Customer After (days)', default=0)
    supply_auto_since = fields.Datetime(readonly=True, copy=False, help="Orders from before are never ordered by themselves.")

    def write(self, vals):
        if vals.get('supply_mode') == 'auto':
            if any(rec.supply_mode != 'auto' for rec in self):
                vals = dict(vals, supply_auto_since=fields.Datetime.now())
        return super().write(vals)

    def _easy_problems(self, names):
        out = super()._easy_problems(names)
        if 'supply_auto_wait' in names and not 0 <= self.supply_auto_wait <= DAY:
            out.append(_("Wait for a cheaper late price? Type 0 to 1440 minutes (a day)."))
        if 'supply_auto_margin' in names and not 0 <= self.supply_auto_margin <= 500:
            out.append(_("How much must be left to order by itself? Type 0 to 500 percent."))
        if 'supply_auto_limit' in names and self.supply_auto_limit < 0:
            out.append(_("Biggest order without asking you? Type 0 (no limit) or more."))
        if 'supply_auto_days' in names and not 0 <= self.supply_auto_days <= 60:
            out.append(_("When are the goods here? Type 0 to 60 days."))
        if 'supply_customer_days' in names and not 0 <= self.supply_customer_days <= 60:
            out.append(_("Deliver to the customer after: type 0 to 60 days."))
        return out


class SaGroupRequestSupply(models.Model):
    _inherit = 'sa.group.request'

    def _sa_supply_price_open(self, partner):
        """Asked at the counter after the sale order: a day, until it is ordered."""
        self.ensure_one()
        if not partner or not self.order_id:
            return False
        since = fields.Datetime.now() - timedelta(days=1)
        return any(job.sa_delivery_state == 'awaiting_shop' and not job.sa_supply_waiting and partner in job.sa_supply_vendor_ids
                   and job.sa_supply_asked_on and job.sa_supply_asked_on > since for job in self.order_id.sudo().picking_ids)


class StockPickingSupply(models.Model):
    _inherit = 'stock.picking'

    sa_supply_due_on = fields.Datetime('Needed From Vendor By', readonly=True, copy=False,
                                       help="What the vendor was told. The customer's promise is another field.")
    sa_supply_day = fields.Date('Vendor Brings It On', readonly=True, copy=False)
    sa_supply_by = fields.Selection([('person', 'By Hand'), ('auto', 'Automatic')], 'Ordered From Vendor', readonly=True, copy=False)
    sa_supply_reason = fields.Char('Why This Vendor', readonly=True, copy=False)
    sa_supply_sent_on = fields.Datetime('Order Sent to Vendor On', readonly=True, copy=False)
    sa_supply_sent_to_id = fields.Many2one('res.partner', 'Order Sent To', readonly=True, copy=False)
    sa_supply_send_note = fields.Char('Order Message', readonly=True, copy=False)
    sa_supply_auto_stop = fields.Char('Needs You Because', readonly=True, copy=False)
    sa_supply_auto_tries = fields.Integer(readonly=True, copy=False)

    # ------------------------------------------------------------ day and time
    def _sa_supply_zone(self):
        self.ensure_one()
        return pytz.timezone(self.env['sa.delivery.partner']._sa_company_tz(self.company_id or self.env.company) or 'UTC')

    def _sa_supply_now(self):
        """Today and now, from the server, in the company's time zone."""
        local = pytz.UTC.localize(fields.Datetime.now()).astimezone(self._sa_supply_zone())
        return {'date': local.strftime('%Y-%m-%d'), 'time': local.strftime('%H:%M')}

    def _sa_supply_due(self, promised):
        """('YYYY-MM-DD', UTC datetime or False) of 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'."""
        self.ensure_one()
        text = str(promised or '').strip()
        if not text:
            return False, False
        try:
            if len(text) == 10:
                day = fields.Date.to_date(text)
                if day < min(fields.Date.context_today(self), fields.Date.to_date(self._sa_supply_now()['date'])):
                    raise UserError(_("That day is over. Choose today or a later day."))
                return text, False
            when = self._sa_supply_zone().localize(datetime.strptime(text[:16], '%Y-%m-%d %H:%M')).astimezone(pytz.UTC).replace(tzinfo=None)
        except ValueError:
            raise UserError(_("That is not a day and time."))
        if when < fields.Datetime.now() - timedelta(minutes=5):
            raise UserError(_("That time is over. Choose now or later."))
        return text[:10], when

    @api.model
    def _sa_supply_customer_days(self):
        return min(60, max(0, self.env['sa.ai.settings'].sudo().get_settings().supply_customer_days or 0))

    def _sa_supply_customer_day(self, vendor_day, customer_date):
        """'YYYY-MM-DD' for the customer: what was typed, else so many days
        after the vendor's day (Configuration)."""
        self.ensure_one()
        if not customer_date:
            return fields.Date.to_string(fields.Date.to_date(vendor_day) + timedelta(days=self._sa_supply_customer_days())) if vendor_day else False
        day, _when = self._sa_supply_due(str(customer_date).strip()[:10])
        if vendor_day and day < vendor_day:
            raise UserError(_("The customer cannot get it before the vendor brings it."))
        return day

    def _sa_supply_due_words(self):
        if not self.sa_supply_due_on:
            return self.sa_supply_day.strftime('%a %d %b %Y') if self.sa_supply_day else ''
        local = pytz.UTC.localize(self.sa_supply_due_on).astimezone(self._sa_supply_zone())
        return '%s, %s' % (local.strftime('%a %d %b %Y'), local.strftime('%I:%M %p').lstrip('0'))

    # ------------------------------------------------------------ the prices
    def _sa_supply_prices(self):
        """Every vendor's price of this order's enquiry, and the recommended one."""
        self.ensure_one()
        order = self.sale_id
        request = order._sa_group_enquiry() if order else False
        out = {'cards': [], 'recommended': False, 'chosen': False, 'qty': 0, 'unit': 0.0, 'sell': 0.0, 'currency': '', 'why': ''}
        currency = self.sa_currency_id or self.company_id.currency_id
        out['currency'] = currency.name or ''
        if not request:
            out['why'] = _("This order did not come from an enquiry with vendor prices.")
            return out
        request = request.sudo()
        out['cards'] = request._sa_vendor_cards()
        best = request.best_quote_id
        if best:
            out['chosen'] = {'vendor': best.partner_id.name or best.vendor_name or '', 'vendor_id': best.partner_id.id or 0, 'price': best.price}
        moves = self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        many = self.env['sa.group.request'].sudo().search_count([('order_id', '=', order.id)]) > 1
        if len(moves.product_id) != 1 or many:
            out['why'] = _("This order has several products, so nothing is recommended.")
            return out
        if moves.product_id.product_tmpl_id != request.product_id:
            out['why'] = _("The order's product is not the one the vendors were asked for.")
            return out
        out['qty'] = sum(moves.mapped('product_uom_qty'))
        lines = order.order_line.filtered(lambda l: l.product_id == moves.product_id)
        today = fields.Date.context_today(self)
        out['sell'] = order.currency_id._convert(sum(lines.mapped('price_subtotal')), currency, self.company_id, today)
        priced = [c for c in out['cards'] if c['state'] == 'price']
        for card in priced:
            quote = self.env['sa.vendor.quote'].sudo().browse(card['quote_id'])
            unit = quote.currency_id._convert(quote.price, currency, self.company_id, today) if quote.currency_id else quote.price
            card['total'] = currency.round(unit * out['qty'])
        if not priced:
            out['why'] = _("No vendor has given a price.")
            return out
        top = priced[0]             # already in the order of the rank key
        words = _("lowest price")
        if out['chosen'] and top['vendor_id'] != out['chosen']['vendor_id'] and top['price'] < out['chosen']['price'] - 0.00005:
            words = _("%(less)s less than %(who)s", less='%.2f' % (out['chosen']['price'] - top['price']), who=out['chosen']['vendor'])
        elif len(priced) == 1:
            words = _("the only price")
        elif out['chosen'] and top['vendor_id'] == out['chosen']['vendor_id']:
            words = _("chosen for the customer's price, still the lowest")
        partner = self.env['res.partner'].sudo().browse(top['vendor_id'] or 0)
        out['recommended'] = {'quote_id': top['quote_id'], 'vendor_id': top['vendor_id'], 'vendor': top['vendor'], 'unit': top['price'],
                              'total': top['total'], 'why': words, 'late': top['late'],
                              'phone': bool(partner.exists() and (partner.phone or '').strip())}
        return out

    @api.model
    def sa_store_supply_options(self, job_id):
        data = super().sa_store_supply_options(job_id)
        job = self.sudo().browse(int(job_id))
        data['prices'] = job._sa_supply_prices()
        data['now'] = dict(job._sa_supply_now(), customer_days=job._sa_supply_customer_days())
        # asked again here, in this popup
        data['asked'] = [{'id': p.id, 'name': p.name or ''} for p in job.sa_supply_vendor_ids]
        # who gave a price can be chosen, also one no category names
        have = {v['id'] for v in data['vendors']}
        for card in data['prices']['cards']:
            partner = self.env['res.partner'].sudo().browse(card['vendor_id'] or 0)
            if card['vendor_id'] and card['vendor_id'] not in have:
                data['vendors'].append({'id': partner.id, 'name': partner.name or '', 'phone': (partner.phone or '').strip(),
                                        'ok': bool((partner.phone or '').strip())})
                have.add(card['vendor_id'])
        return data

    # ------------------------------------------------------------ asking more vendors
    def _sa_supply_request(self):
        """The enquiry of this job when it is for its one product, else empty."""
        self.ensure_one()
        Request = self.env['sa.group.request'].sudo()
        order = self.sale_id
        request = order._sa_group_enquiry() if order else Request
        moves = self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        if not request or moves.product_id.product_tmpl_id != request.sudo().product_id or len(moves.product_id) != 1 \
                or Request.search_count([('order_id', '=', order.id)]) > 1:
            return Request
        return request.sudo()

    @api.model
    def sa_store_supply_ask(self, job_id, vendor_ids):
        """With the price link, so the price comes by itself; where that cannot
        be (several products, links off) the question as text, as before."""
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        wanted = [int(v) for v in (vendor_ids or []) if v]
        request = job._sa_supply_request()
        linked = self.env['res.partner']
        if request and hasattr(request, '_sa_ask_vendor_confirm') and request._sa_confirm_settings().confirm_vendor_enabled:
            session = job._sa_session()
            if not session:
                raise UserError(_("No WhatsApp session is connected."))
            offered = job._sa_supply_vendors()[0]
            guard = self.env['sa.outbox.guard'].sudo()
            qty = sum(job.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')).mapped('product_uom_qty'))
            for partner in offered.filtered(lambda p: p.id in wanted and (p.phone or '').strip()):
                if not guard.claim('supplyask|%s|%s' % (job.id, partner.phone), 3600):
                    linked |= partner
                    continue
                try:
                    with self.env.cr.savepoint():
                        if request._sa_ask_vendor_confirm(session, partner, request.product_id.name, qty, ''):
                            linked |= partner
                except psycopg2.OperationalError:
                    raise
                except Exception as err:  # noqa: BLE001 - one bad number is not a reason to skip the rest
                    _logger.warning("Store: could not ask %s about %s: %s", partner.name, job.sa_ref_code, err)
            if linked:
                request.write({'sourcing_vendor_ids': [(4, p.id) for p in linked]})
                job.write({'sa_supply_vendor_ids': [(4, p.id) for p in linked], 'sa_supply_asked_on': fields.Datetime.now()})
                job._sa_store_notify()
        rest = [v for v in wanted if v not in linked.ids]
        if rest:
            return super().sa_store_supply_ask(job.id, rest)
        return self.sa_store_queue(job.sa_shop_id.id)

    # ------------------------------------------------------------ the order to the vendor
    def _sa_supply_prepare(self):
        """What has to be there before the vendor is told (the purchase)."""
        return True

    def _sa_supply_number(self):
        """Our purchase number for the vendor, or ''."""
        return ''

    def _sa_supply_message(self, partner, cost, promised):
        self.ensure_one()
        lines = '\n'.join('• *%s* x %s' % (m.product_id.name, '%g' % m.product_uom_qty)
                          for m in self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')))
        amount, code = cost, (self.sa_currency_id or self.company_id.currency_id).name or ''
        # what they typed, in their own money, when that is the price taken
        for card in self._sa_supply_prices()['cards']:
            if card['vendor_id'] == partner.id and card.get('total') is not None and abs(card['total'] - cost) < 0.005:
                quote = self.env['sa.vendor.quote'].sudo().browse(card['quote_id'])
                if quote.sa_typed_amount and quote.sa_typed_currency:
                    qty = sum(self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')).mapped('product_uom_qty'))
                    amount, code = quote.sa_typed_amount * qty, quote.sa_typed_currency
        when = ''
        if self.sa_supply_due_on:
            when = _("\n*Needed by:* %s", self._sa_supply_due_words())
        elif promised:
            when = _("\n*Needed by:* %s", fields.Date.to_date(promised).strftime('%a %d %b %Y'))
        number = self._sa_supply_number()
        number = _("\nPurchase: *%s*", number) if number else ''
        return _("\U0001F6D2 *Order* — *#%(ref)s*%(number)s\n\n%(lines)s\n\n*Price:* %(cur)s %(amount).2f%(when)s\n\nPlease keep it for us. Thank you!",
                 ref=self.sa_ref_code or self.name, number=number, lines=lines, cur=code, amount=amount, when=when)

    def _sa_supply_send(self, partner, cost, promised=None):
        """The order to this vendor, once. True when it has left."""
        self.ensure_one()
        phone = (partner.phone or '').strip()
        if not phone:
            raise UserError(_("%s has no WhatsApp number.", partner.name or _("The vendor")))
        session = self._sa_session()
        if not session:
            raise UserError(_("No WhatsApp session is connected."))
        session._refresh_state()
        if session.status != 'connected':
            raise UserError(_("WhatsApp is not connected."))
        body = self._sa_supply_message(partner, cost, promised)
        if not self.env['sa.outbox.guard'].sudo().claim('supplyorder|%s|%s' % (self.id, partner.id), ONCE):
            raise UserError(_("This order was already sent to %s.", partner.name or ''))
        if not session.send_message(phone, body):
            raise UserError(_("WhatsApp did not take the message."))
        self.write({'sa_supply_sent_on': fields.Datetime.now(), 'sa_supply_sent_to_id': partner.id, 'sa_supply_send_note': False})
        return True

    @api.model
    def sa_store_supply_set(self, job_id, company_id=None, partner_id=None, cost=None, promised_date=None, send=False, by='person', reason='',
                            customer_date=None):
        # promised_date: the vendor's. customer_date: the customer's.
        job = self.sudo().browse(int(job_id))
        promised_date, due = job._sa_supply_due(promised_date)
        customer = job._sa_supply_customer_day(promised_date, customer_date)
        res = super().sa_store_supply_set(job_id, company_id=company_id, partner_id=partner_id, cost=cost, promised_date=customer)
        partner = job.sa_supply_partner_id
        job.write({'sa_supply_due_on': due, 'sa_supply_day': promised_date, 'sa_supply_by': by, 'sa_supply_reason': reason or False, 'sa_supply_auto_stop': False, 'sa_supply_send_note': False})
        job._sa_supply_prepare()
        if send and partner:
            try:
                with self.env.cr.savepoint():
                    job._sa_supply_send(partner, job.sa_supply_cost, promised_date)
            except psycopg2.OperationalError:
                raise
            except Exception as err:  # noqa: BLE001 - the order stays; the card says it
                _logger.warning("Store: order of %s not sent to %s: %s", job.sa_ref_code, partner.name, err)
                job.sa_supply_send_note = _("Not sent to %(who)s: %(why)s", who=partner.name or '', why=str(err)[:150])
        elif send:
            job.sa_supply_send_note = _("Not sent: no vendor was chosen.")
        return self.sa_store_queue(job.sa_shop_id.id) if send else res

    @api.model
    def sa_store_act(self, job_id, action, reason='', company_id=None, **kwargs):
        if action == 'supply_set':
            job = self.sudo().browse(int(job_id))
            if not job.exists():
                raise UserError(_("That order is no longer there."))
            return self.sa_store_supply_set(
                job.id, company_id=kwargs.get('company_id') or company_id, partner_id=kwargs.get('partner_id'), cost=kwargs.get('cost'),
                promised_date=kwargs.get('promised_date'), customer_date=kwargs.get('customer_date'), send=bool(kwargs.get('send')))
        return super().sa_store_act(job_id, action, reason=reason, company_id=company_id, **kwargs)

    def _sa_board_extra(self):
        return dict(super()._sa_board_extra(), supply_by=self.sa_supply_by or '', supply_why=self.sa_supply_reason or '',
                    supply_note=self.sa_supply_send_note or '', supply_stop=self.sa_supply_auto_stop or '',
                    supply_sent=iso(self.sa_supply_sent_on), supply_due=self._sa_supply_due_words(),
                    request_id=self.sale_id._sa_group_enquiry().id or 0 if self.sale_id else 0,
                    supply_asked_names=', '.join(self.sudo().sa_supply_vendor_ids.mapped('name')) if self.sa_delivery_state == 'awaiting_shop' else '')

    @api.depends('sa_supply_waiting', 'sa_supply_partner_id')
    def _compute_sa_stage_text(self):
        """Bought in: there is nothing to dispatch before the goods are here."""
        super()._compute_sa_stage_text()
        for job in self:
            if job.sa_supply_waiting and job.sa_delivery_state in ('awaiting_shop', 'preparing'):
                job.sa_stage_text = _("Waiting for the goods from %s - next: press Goods arrived when they are here",
                                      job.sa_supply_partner_id.name) if job.sa_supply_partner_id else _(
                    "Waiting for the goods - next: press Goods arrived when they are here")

    # ------------------------------------------------------------ by itself
    def _sa_supply_trigger(self, settings):
        """When the customer did what the setting waits for, or False."""
        self.ensure_one()
        order = self.sale_id
        request = order._sa_group_enquiry() if order else False
        if not request or order.state != 'sale':
            return False
        request = request.sudo()
        if settings.supply_auto_start == 'signed':
            return order.signed_on
        paid = order.transaction_ids.filtered(lambda t: t.state == 'done')
        if not paid or (self.sa_amount_due() or 0.0) > 0.005:
            return False
        return request.sa_paid_on or max(paid.mapped('last_state_change'))

    def _sa_supply_stop(self, why):
        self.ensure_one()
        self.write({'sa_supply_auto_stop': why[:200]})
        order = self.sale_id
        self.env['sa.notice']._tell('supply', _("Order from a vendor needs you"), _("%(ref)s: %(why)s", ref=self.sa_ref_code or self.name, why=why),
                                    'supply|%s' % self.id, request=order._sa_group_enquiry() if order else None, order=order)
        _logger.info("Store: %s is not ordered by itself: %s", self.sa_ref_code, why)
        self._sa_store_notify()

    def _sa_supply_auto_check(self, settings):
        """(prices, '') or (prices, why a person is needed)."""
        self.ensure_one()
        prices = self._sa_supply_prices()
        pick = prices['recommended']
        if not pick:
            return prices, prices['why'] or _("No vendor has given a price.")
        if not pick['vendor_id']:
            return prices, _("%s is not a contact.", pick['vendor'])
        if not pick['phone']:
            return prices, _("%s has no WhatsApp number.", pick['vendor'])
        if pick['total'] <= 0:
            return prices, _("The price is 0.")
        margin = (prices['sell'] - pick['total']) / pick['total'] * 100.0
        if margin < settings.supply_auto_margin - 0.005:
            return prices, _("The margin would be %(a).1f%%, below %(b).1f%%.", a=margin, b=settings.supply_auto_margin)
        if settings.supply_auto_limit and pick['total'] > settings.supply_auto_limit + 0.005:
            return prices, _("%(a).2f %(c)s is above %(b).2f.", a=pick['total'], b=settings.supply_auto_limit, c=prices['currency'])
        return prices, ''

    def _sa_supply_auto(self, settings):
        """One order. False: nothing to do now."""
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM stock_picking WHERE id = %s FOR UPDATE SKIP LOCKED', [self.id])
        if not self.env.cr.fetchone():
            return False
        self.invalidate_recordset()
        if self.sa_delivery_state != 'awaiting_shop' or self.sa_supply_waiting or self.sa_supply_auto_stop or self.state in ('done', 'cancel'):
            return False
        at = self._sa_supply_trigger(settings)
        if not at or not settings.supply_auto_since or at < settings.supply_auto_since \
                or at + timedelta(minutes=max(0, settings.supply_auto_wait)) > fields.Datetime.now():
            return False
        if any(c['ok'] for c in self.sa_store_company_options(self.id)):
            return False                    # our own stock comes first
        prices, why = self._sa_supply_auto_check(settings)
        if why:
            self._sa_supply_stop(why)
            return False
        pick = prices['recommended']
        partner = self.env['res.partner'].sudo().browse(pick['vendor_id'])
        quote = self.env['sa.vendor.quote'].sudo().browse(pick['quote_id'])
        day = fields.Date.context_today(self) + timedelta(days=quote.delay_days or settings.supply_auto_days)
        try:
            with self.env.cr.savepoint():       # not sent: nothing of it stays
                self.write({'sa_supply_partner_id': partner.id, 'sa_supply_cost': pick['total'], 'sa_supply_due_on': False,
                            'sa_supply_day': day})
                self._sa_supply_prepare()
                self._sa_supply_send(partner, pick['total'], day)
        except psycopg2.Error:
            raise
        except Exception as err:  # noqa: BLE001 - not sent: not ordered
            self._sa_supply_stop(_("Not sent to %(who)s: %(why)s", who=partner.name or '', why=str(err)[:120]))
            return False
        self.sa_store_supply_set(self.id, partner_id=partner.id, cost=pick['total'], promised_date=fields.Date.to_string(day),
                                 by='auto', reason=pick['why'])
        self.env['sa.notice']._tell('supply', _("Ordered from a vendor"), _("%(ref)s: %(who)s, %(sum).2f %(cur)s", ref=self.sa_ref_code or self.name,
                                    who=partner.name or '', sum=pick['total'], cur=prices['currency']), 'supplied|%s' % self.id, order=self.sale_id)
        return True

    @api.model
    def _cron_sa_supply_auto(self):
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        if settings.supply_mode != 'auto':
            return True
        test = config['test_enable']
        jobs = self.sudo().search([('sa_delivery_state', '=', 'awaiting_shop'), ('sa_supply_waiting', '=', False),
                                   ('sa_supply_auto_stop', '=', False), ('sale_id', '!=', False),
                                   ('create_date', '>=', fields.Datetime.now() - timedelta(days=30))], order='id', limit=100)
        for job_id in jobs.ids:
            job = self.sudo().browse(job_id)
            try:
                with self.env.cr.savepoint():
                    job._sa_supply_auto(settings)
                if not test:
                    self.env.cr.commit()
            except (psycopg2.OperationalError, psycopg2.errors.InFailedSqlTransaction) as err:
                if not test:
                    self.env.cr.rollback()
                self.env.invalidate_all()
                _logger.info("Store: %s is being changed by somebody, tried again (%s)", job_id, str(err).split('\n')[0])
            except Exception as err:  # noqa: BLE001 - one order stops none of the others
                _logger.exception("Store: automatic order of %s failed", job_id)
                self.env.invalidate_all()
                job._sa_supply_stop(_("It failed: %s", str(err)[:120]))
                if not test:
                    self.env.cr.commit()
        return True
