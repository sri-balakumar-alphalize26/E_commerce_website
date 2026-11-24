# -*- coding: utf-8 -*-
"""Hand over without a rider, two ways (owner, 24 Nov 2026).

Store pickup: the customer is here, gets the code, and the counter types it.
Home delivery: one person (a rider, staff, or a typed number) gets a link and
does every step on it. The link is for one order and one person; it ends with
the delivery, with a change of person and with Not delivered."""
import hmac
import logging
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# 'accepted' = with a person, parcel still at the shop. Nothing rings for it
# and no rider can be called.
LINK_STATES = ('accepted', 'picked', 'dispatched', 'out_for_delivery')
STEPS = ('accept', 'parcel', 'start', 'reached')
AGAIN_SECONDS = 60


class StockPickingSelfLink(models.Model):
    _inherit = 'stock.picking'

    sa_self_way = fields.Selection([('collect', 'Store Pickup'), ('link', 'Home Delivery')], 'Handed Over By', readonly=True, copy=False)
    sa_self_name = fields.Char('Home Delivery Person', readonly=True, copy=False)
    sa_self_phone = fields.Char('Home Delivery WhatsApp', readonly=True, copy=False)
    sa_self_token = fields.Char(readonly=True, copy=False, groups='base.group_system')
    sa_self_link_on = fields.Datetime('Link Sent On', readonly=True, copy=False)
    sa_self_accepted_on = fields.Datetime('Link Accepted On', readonly=True, copy=False)
    sa_self_failed = fields.Char('Not Delivered Because', readonly=True, copy=False)
    sa_cash_by = fields.Char('Cash Received By (Home Delivery)', readonly=True, copy=False)

    # ------------------------------------------------------------ who
    @api.model
    def _sa_carrier_digits(self, value):
        """The whole number, digits only, or ''. A local one is of the company's country."""
        text = (value or '').strip()
        digits = ''.join(c for c in text if c.isdigit())
        if text.startswith('+'):
            return digits if 8 <= len(digits) <= 15 else ''
        if text.startswith('00'):
            return digits[2:] if 10 <= len(digits) <= 17 else ''
        try:
            return self.env['whatsapp.connect'].sudo()._number(self.env.company.country_id, digits)
        except UserError:
            return digits if 11 <= len(digits) <= 15 else ''

    @api.model
    def sa_store_carriers(self):
        """Riders and staff with a number. Never customers or vendors."""
        if not self.env.su and not self.env.user._is_internal():
            raise UserError(_("Only for the shop."))
        pretty = self.env['whatsapp.connect'].sudo()._pretty
        found, out = set(), []

        def add(kind, rec_id, name, number):
            digits = self._sa_carrier_digits(number)
            if digits and digits not in found:
                found.add(digits)
                out.append({'key': '%s-%s' % (kind, rec_id), 'kind': kind, 'name': name or '', 'phone': digits, 'pretty': pretty(digits)})
        for rider in self.env['sa.delivery.partner'].sudo().search([('active', '=', True)], order='name'):
            add('rider', rider.id, rider.name, rider.phone)
        for staff in self.env['hr.employee'].sudo().search([('company_id', 'in', [False] + self.env.companies.ids)], order='name'):
            add('staff', staff.id, staff.name, staff.mobile_phone or staff.work_phone)
        return out

    def _sa_carrier_of(self, kw):
        """(name, digits) of what the popup sent."""
        if kw.get('carrier'):
            row = next((r for r in self.sa_store_carriers() if r['key'] == kw['carrier']), None)
            if not row:
                raise UserError(_("That person is no longer in the list."))
            return row['name'], row['phone']
        country = self.env['res.country'].sudo().browse(int(kw.get('country_id') or 0)).exists()
        digits = self.env['whatsapp.connect'].sudo()._number(country, kw.get('number'))
        return (kw.get('name') or '').strip()[:60], digits

    # ------------------------------------------------------------ the link
    def _sa_self_url(self):
        self.ensure_one()
        return self.env['wa.auto.reply'].sudo()._sa_public_link('/wa/staff/%s?token=%s' % (self.id, self.sudo().sa_self_token))

    def _sa_self_token_ok(self, token):
        self.ensure_one()
        job = self.sudo()
        return bool(token and job.sa_self_token and job.sa_self_way == 'link' and job.sa_delivery_state in LINK_STATES
                    and job.state not in ('done', 'cancel') and hmac.compare_digest(job.sa_self_token.encode(), str(token).encode()))

    def _sa_self_message(self):
        self.ensure_one()
        lines = '\n'.join('• *%s* x %g' % (m.product_id.name, m.product_uom_qty)
                          for m in self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')))
        due = self._sa_self_due()
        money = _("Collect %(a).2f %(c)s", a=due, c=(self.sa_currency_id or self.company_id.currency_id).name or '') \
            if due > 0.005 else _("Paid, nothing to collect")
        return _("\U0001F6F5 *Delivery #%(ref)s*\n\n%(lines)s\n%(money)s\n\nOpen this link, it has every step:\n%(url)s\n\n"
                 "Only for you, do not forward it.", ref=self.sa_ref_code or self.name, lines=lines, money=money, url=self._sa_self_url())

    def _sa_self_send_link(self):
        """Last of all: not sent = raised, and nothing of it happened."""
        self.ensure_one()
        session = self._sa_session()
        if not session:
            raise UserError(_("No WhatsApp session is connected."))
        session._refresh_state()
        if session.status != 'connected':
            raise UserError(_("WhatsApp is not connected, so the link cannot be sent."))
        self.env.flush_all()
        body = self._sa_self_message()
        # the same words within minutes are refused by the gateway
        if not (session.send_message(self.sa_self_phone, body) or session.send_message(self.sa_self_phone, body + '​')):
            raise UserError(_("WhatsApp did not take the message. Nothing was changed."))

    def _sa_self_link_start(self, kw):
        self.ensure_one()
        name, phone = self._sa_carrier_of(kw)
        self._sa_self_lock()
        self.invalidate_recordset(['sa_self_way'])
        if not (self.sa_self_way == 'link' and self.sa_delivery_state == 'accepted'):       # else: another person
            problem = self._sa_self_problem()
            if problem:
                raise UserError(problem)
            if self.state != 'assigned':
                self.action_assign()
            if self.state != 'assigned':
                raise UserError(_("The goods of this order are not in stock."))
        now = fields.Datetime.now()
        with self.env.cr.savepoint():
            self.write({
                'sa_self_delivery': True, 'sa_self_way': 'link', 'sa_self_user_id': self.env.uid, 'sa_self_name': name,
                'sa_self_phone': phone, 'sa_self_token': secrets.token_urlsafe(24), 'sa_self_link_on': now,
                'sa_self_accepted_on': False, 'sa_self_failed': False, 'sa_delivery_state': 'accepted',
                'sa_shop_ready_on': self.sa_shop_ready_on or now, 'sa_shop_user_id': self.sa_shop_user_id.id or self.env.uid,
                'sa_packed_unpaid_on': False, 'sa_arrived_customer_on': False, 'sa_code_resends': 0, 'sa_code_sent_on': False})
            self._sa_self_send_link()
        self.message_post(body=_("Home delivery: the link was sent to %s.", self._sa_self_who()))
        self._sa_store_notify()

    def _sa_self_link_again(self):
        self.ensure_one()
        self._sa_self_lock()
        if self.sa_self_way != 'link' or self.sa_delivery_state not in LINK_STATES:
            raise UserError(_("No link is out for this order."))
        now = fields.Datetime.now()
        if self.sa_self_link_on and (now - self.sa_self_link_on).total_seconds() < AGAIN_SECONDS:
            raise UserError(_("It was sent a moment ago. Wait a minute."))
        with self.env.cr.savepoint():
            self.sa_self_link_on = now
            self._sa_self_send_link()

    def _sa_self_who(self):
        self.ensure_one()
        number = self.env['whatsapp.connect'].sudo()._pretty(self.sa_self_phone) if self.sa_self_phone else ''
        return self.sa_self_name or number or _("our staff")

    # ------------------------------------------------------------ the steps of the link
    def _sa_self_step(self, step):
        """One step; a second tap does nothing. Raises what to tell."""
        self.ensure_one()
        self._sa_self_lock()
        if self.sa_self_way != 'link' or self.sa_delivery_state not in LINK_STATES:
            raise UserError(_("This order is not out for home delivery."))
        state = self.sa_delivery_state
        if step == 'accept':
            if state == 'accepted' and not self.sa_self_accepted_on:
                self.sa_self_accepted_on = fields.Datetime.now()
        elif step == 'parcel':
            if state == 'accepted':
                if not self.sa_self_accepted_on:
                    raise UserError(_("Press Accept first."))
                self.with_context(sa_quiet=True).sa_set_state('picked')
        elif step == 'start':
            if state == 'accepted':
                raise UserError(_("Take the parcel first."))
            if state == 'picked':
                self.with_context(sa_quiet=True).sa_set_state('dispatched')
                link = self.sa_track_link_once()
                self._sa_tell_customer(_(
                    "\U0001F69A *%(who)s* has your order *#%(ref)s* and is on the way.%(tail)s", who=self.sa_self_name or _("Our staff"),
                    ref=self.sa_ref_code or '', tail=_("\n\nFollow it here:\n%s", link) if link else ''))
        elif step == 'reached':
            if state in ('accepted', 'picked'):
                raise UserError(_("Press Start first."))
            if not self.sa_arrived_customer_on:
                with self.env.cr.savepoint():       # no code sent: not reached
                    self.with_context(sa_quiet=True).sa_action_reached_customer()
        else:
            raise UserError(_("Unknown step."))
        self._sa_store_notify()

    def _sa_self_finish(self, code, cash):
        if self.sa_self_way == 'link' and not self.sa_arrived_customer_on:
            return _("Press Reached first: the code is sent then.")
        told = super()._sa_self_finish(code, cash)
        if not told:
            vals = {'sa_self_token': False}
            if self.sa_self_way == 'link' and self.env.context.get('sa_by_link') and self.sa_cash_taken:
                vals.update(sa_cash_user_id=False, sa_cash_by=self._sa_self_who())      # not the public user
            self.write(vals)
        return told

    def _sa_self_back(self, why=''):
        self.ensure_one()
        if self.sa_self_way != 'link':
            res = super()._sa_self_back()
            if not self.sa_self_delivery:
                self.sa_self_way = False
            return res
        self._sa_self_lock()
        if self.sa_delivery_state not in LINK_STATES:
            return True
        who = self._sa_self_who()
        words = _("%(who)s: %(why)s", who=who, why=why) if why else who
        self._sa_void_codes()
        self.write({
            'sa_delivery_state': 'ready', 'sa_self_delivery': False, 'sa_self_way': False, 'sa_self_user_id': False,
            'sa_self_token': False, 'sa_self_name': False, 'sa_self_phone': False, 'sa_self_accepted_on': False,
            'sa_arrived_customer_on': False, 'sa_picked_on': False, 'sa_dispatched_on': False, 'sa_out_on': False,
            'sa_self_failed': words[:200] if why else False})
        self.message_post(body=_("Not delivered (%s): back to packed. The link and the code no longer work.", words))
        self._sa_store_notify()
        return True

    # ------------------------------------------------------------ the counter
    @api.model
    def sa_store_act(self, job_id, action, reason='', company_id=None, **kwargs):
        if action not in ('self_collect', 'self_link', 'self_link_again', 'self_step'):
            return super().sa_store_act(job_id, action, reason=reason, company_id=company_id, **kwargs)
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        told = ''
        if action == 'self_collect':
            job._sa_self_start()
            job.write({'sa_self_way': 'collect', 'sa_self_failed': False})
        elif action == 'self_link':
            job._sa_self_link_start(kwargs)
            told = _("Link sent to %s.", job._sa_self_who())
        elif action == 'self_link_again':
            job._sa_self_link_again()
            told = _("Link sent again to %s.", job._sa_self_who())
        else:
            # the counter, for somebody whose phone does not work
            for step in STEPS[:STEPS.index('reached') + 1]:
                job._sa_self_step(step)
        data = self.sa_store_queue(job.sa_shop_id.id)
        data['self_told'] = told
        return data

    def _sa_tell_rider(self, body):
        if self.sa_self_way == 'link' and self.sa_self_phone and not self.sa_delivery_partner_id:
            session = self._sa_session()
            try:
                return bool(session and session.send_message(self.sa_self_phone, body))
            except Exception as err:  # noqa: BLE001 - the job matters more
                _logger.warning("Store: could not tell the home delivery person about %s: %s", self.sa_ref_code, err)
                return False
        return super()._sa_tell_rider(body)

    def _sa_carrier_name(self):
        if self.sa_self_way == 'link':
            return self.sa_self_name or _("our staff")
        if self.sa_self_way == 'collect':
            return _("our staff, at the store")
        return super()._sa_carrier_name()

    def _sa_payment_status(self):
        out = super()._sa_payment_status()
        if out['key'] == 'cash' and self.sudo().sa_cash_by:
            out['how'] = _("by %s, not booked yet", self.sudo().sa_cash_by)
        return out

    def _sa_board_extra(self):
        out = super()._sa_board_extra()
        job = self.sudo()
        link = job.sa_self_way == 'link' and job.sa_delivery_state in LINK_STATES
        out.update(self_way=job.sa_self_way or '', self_failed=job.sa_self_failed or '', self_link=link,
                   self_who=job._sa_self_who() if link else '', self_reached=bool(job.sa_arrived_customer_on),
                   self_phone=self.env['whatsapp.connect'].sudo()._pretty(job.sa_self_phone) if link and job.sa_self_phone else '')
        return out

    @api.model
    def _sa_done_today(self, shop_id=None):
        rows = super()._sa_done_today(shop_id)
        for row in rows:
            job = self.sudo().browse(row['id'])
            if job.sa_self_way == 'collect':
                row['rider'] = _("Picked up from store")
            elif job.sa_self_way == 'link':
                row['rider'] = _("Delivered by %s", job._sa_self_who())
        return rows

    @api.depends('sa_self_way', 'sa_self_accepted_on', 'sa_self_name', 'sa_arrived_customer_on')
    def _compute_sa_stage_text(self):
        super()._compute_sa_stage_text()
        for job in self:
            if job.sa_supply_waiting:
                continue
            state = job.sa_delivery_state
            if job.sa_self_way == 'link' and state in LINK_STATES:
                who = job._sa_self_who()
                if state == 'accepted':
                    job.sa_stage_text = _("%s accepted - next: takes the parcel", who) if job.sa_self_accepted_on \
                        else _("Link sent to %s, not accepted yet", who)
                elif state == 'picked':
                    job.sa_stage_text = _("%s has the parcel - next: starts", who)
                elif not job.sa_arrived_customer_on:
                    job.sa_stage_text = _("%s is on the way", who)
                else:
                    job.sa_stage_text = _("%s is with the customer - next: the customer's code", who)
            elif job.sa_self_way == 'collect' and state == 'out_for_delivery':
                job.sa_stage_text = _("Store pickup - next: type the customer's code")
            elif state == 'preparing':
                job.sa_stage_text = _("Next: pack it, then call a rider or hand it over")
