# -*- coding: utf-8 -*-
"""What follows a signature or a payment, done after the customer's page has
moved on (owner, 23 Nov 2026: "the customer should not wait").

The signature request keeps the signature, confirms the order and decides
whether it can be paid; the payment request records the money. PDFs, WhatsApp
messages, the invoice and the email are a task here:

* started at once after the commit, in a thread; a cron picks up whatever that
  missed (scheduled jobs come round about once a minute);
* one task at a time per order, the signature's before the payment's;
* every finished part is remembered outside the task's own transaction, so a
  retry goes on from there: nothing is sent twice, no second invoice;
* WhatsApp not connected: it waits. Two of our own jobs at the same record (the
  customer pays while the order's PDF goes out): again at once, not counted as
  a failure. Anything else: again after 1, 2, 5, 10 and 30 minutes, then a
  to-do on the order for the staff.

The same for the ACCEPT page ("accepted", 23 Nov 2026): the answer is kept and
the page moves on; the price and the messages follow here.
"""
import logging
import threading
import time
from datetime import timedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.modules.registry import Registry
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import config

_logger = logging.getLogger(__name__)

RETRY_MINUTES = (1, 2, 5, 10, 30)
WAIT_MINUTES = 2            # WhatsApp not connected
GIVE_UP_HOURS = 24          # ... for this long
CLASH_SECONDS = (0.3, 0.7, 1.5, 3, 4)     # two jobs at the same record: again at once
LOCK_SPACE = 369021         # pg advisory lock: one runner per order


class SaNotConnected(Exception):
    """WhatsApp is not connected: wait, this is not a failed attempt."""


class SaAfterTask(models.Model):
    _name = 'sa.after.task'
    _description = 'After a signature or payment'
    _order = 'id'

    request_id = fields.Many2one('sa.group.request', required=True, ondelete='cascade', index=True)
    order_id = fields.Many2one('sale.order', ondelete='cascade')
    step = fields.Selection([('signed', 'Signed'), ('paid', 'Paid'), ('accepted', 'Product page answered')],
                            required=True)
    mode = fields.Char(help="Signed: pay, wait or stop. Product page: accept or reject.")
    ref = fields.Integer(default=0, help="Product page: its link. An enquiry can have several.")
    state = fields.Selection([('todo', 'To do'), ('done', 'Done'), ('failed', 'Needs a person')],
                             default='todo', required=True, index=True)
    done = fields.Char(default='', help="Finished parts.")
    tries = fields.Integer(default=0)
    next_on = fields.Datetime(index=True)
    error = fields.Char()
    tz = fields.Char()
    lang = fields.Char()

    _request_step_uniq = models.Constraint('unique(request_id, step, ref)', 'One task per step.')

    # ---------------------------------------------------------- starting
    @api.model
    def _queue(self, request, order, step, mode='', ref=0):
        """The task for this step (the one there already, else a new one)."""
        task = self.sudo().search([('request_id', '=', request.id), ('step', '=', step), ('ref', '=', ref)], limit=1)
        if not task:
            task = self.sudo().create({'request_id': request.id, 'order_id': order.id if order else False,
                                       'step': step, 'mode': mode, 'ref': ref,
                                       'tz': self.env.context.get('tz') or self.env.user.tz or False,
                                       'lang': self.env.context.get('lang') or False})
        task._start_soon()
        return task

    def _start_soon(self):
        cron = self.env.ref('sales_automation.cron_sa_after_order', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        if config['test_enable'] or self.env.context.get('sa_after_no_thread'):
            return
        dbname, ids = self.env.cr.dbname, self.ids

        def start():
            threading.Thread(target=_run_in_thread, args=(dbname, ids), daemon=True,
                             name='sa.after.%s' % ids).start()
        self.env.cr.postcommit.add(start)

    # ---------------------------------------------------------- running
    @api.model
    def _cron_run(self):
        now = fields.Datetime.now()
        for task in self.sudo().search([('state', '=', 'todo'), '|', ('next_on', '=', False),
                                        ('next_on', '<=', now)], limit=40):
            task._run_locked()
        # a payment whose paid task never came (nothing asked for it): its email
        late = self.env['sa.group.request'].sudo().search(
            [('sa_pay_mail_on', '!=', False), ('sa_pay_mail_on', '<=', now - timedelta(minutes=30)),
             ('order_id', '!=', False)], limit=20)
        for req in late:
            if not self.sudo().search_count([('request_id', '=', req.id), ('step', '=', 'paid'),
                                             ('state', '=', 'todo')]):
                try:
                    with self.env.cr.savepoint():
                        req._sa_pay_mail(req.order_id)
                except Exception as err:  # noqa: BLE001 - not tried for ever
                    _logger.warning("Payment email of %s not sent: %s", req.order_id.name, err)
                    req.sa_pay_mail_on = False
        return True

    def _run_locked(self):
        """Run this order's tasks unless another runner has them."""
        self.ensure_one()
        cr, key = self.env.cr, self.request_id.id
        cr.execute('SELECT pg_try_advisory_lock(%s, %s)', (LOCK_SPACE, key))
        if not cr.fetchone()[0]:
            return False
        try:
            # a fresh snapshot: the runner before us may have finished it
            cr.commit()
            self.env.invalidate_all()
            return self._run(commit=True)
        except Exception:
            cr.rollback()           # the unlock below needs a clean transaction
            raise
        finally:
            cr.execute('SELECT pg_advisory_unlock(%s, %s)', (LOCK_SPACE, key))
            cr.commit()

    def _run(self, commit=False):
        """One attempt. True when the task is finished."""
        self.ensure_one()
        task = self.sudo()
        if not task.exists() or task.state != 'todo':
            return False
        if task.next_on and task.next_on > fields.Datetime.now():
            return False
        if task.step == 'paid' and self.sudo().search_count(
                [('request_id', '=', task.request_id.id), ('step', '=', 'signed'), ('state', '=', 'todo')]):
            first = self.sudo().search([('request_id', '=', task.request_id.id), ('step', '=', 'signed'),
                                        ('state', '=', 'todo')], limit=1)
            if not first._run(commit=commit) and first.state == 'todo':
                return False                # the sales order first, then the invoice
        cr = self.env.cr
        clashes = 0
        while True:
            work = task.with_context(sa_after_task=task.id, sa_after_commit=commit,
                                     sa_after_last=task.tries >= len(RETRY_MINUTES))
            try:
                work._work()            # every part has its own savepoint
                self.env.flush_all()
                break
            except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY as err:
                if not commit or clashes >= len(CLASH_SECONDS):
                    return task._failed(err, commit)
                # finished parts are remembered: only the clashing one is done again
                cr.rollback()
                self.env.invalidate_all()
                _logger.info("After %s of enquiry %s: another job has the same record, again (%s)",
                             task.step, task.request_id.id, clashes + 1)
                time.sleep(CLASH_SECONDS[clashes])
                cr.commit()             # a fresh snapshot
                self.env.invalidate_all()
                clashes += 1
            except SaNotConnected:
                return task._wait_connected(commit)
            except Exception as err:  # noqa: BLE001 - tried again later
                return task._failed(err, commit)
        task._put({'state': 'done', 'error': False, 'next_on': False}, commit)
        return True

    def _wait_connected(self, commit):
        if commit:
            self.env.cr.rollback()
            self.env.invalidate_all()
        if self.create_date and self.create_date < fields.Datetime.now() - timedelta(hours=GIVE_UP_HOURS):
            return self._give_up(_("WhatsApp was not connected for a day."), commit)
        self._put({'next_on': fields.Datetime.now() + timedelta(minutes=WAIT_MINUTES),
                   'error': 'WhatsApp is not connected'}, commit)
        return False

    def _failed(self, err, commit):
        task = self
        if commit:
            self.env.cr.rollback()
            self.env.invalidate_all()
        _logger.warning("After %s of %s: %s", task.step, task.order_id.name or task.request_id.ref_code,
                        err, exc_info=True)
        if task.tries >= len(RETRY_MINUTES):
            return task._give_up(str(err)[:250], commit)
        task._put({'tries': task.tries + 1, 'error': str(err)[:250],
                   'next_on': fields.Datetime.now() + timedelta(minutes=RETRY_MINUTES[task.tries])}, commit)
        return False

    def _put(self, vals, commit):
        self.sudo().write(vals)
        self.env.flush_all()
        if commit:
            self.env.cr.commit()

    def _give_up(self, why, commit):
        """A person has to look: a to-do on the order."""
        self._put({'state': 'failed', 'error': why}, commit)
        order = self.order_id.sudo()
        if not order:
            _logger.error("After %s of enquiry %s given up: %s", self.step, self.request_id.ref_code, why)
            try:
                self.request_id.sudo()._sa_enquiry_notify()
            except Exception as err:  # noqa: BLE001
                _logger.warning("The counter was not told about enquiry %s: %s", self.request_id.id, err)
            return False
        try:
            order.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_("WhatsApp: order PDF / invoice / message not finished"),
                note=_("After %(step)s of %(order)s: %(why)s", step=self.step, order=order.name, why=why),
                user_id=order.user_id.id or SUPERUSER_ID)
            if commit:
                self.env.cr.commit()
        except Exception as err:  # noqa: BLE001
            _logger.error("After %s of %s failed (%s), and no to-do could be made: %s",
                          self.step, order.name, why, err)
        return False

    def _work(self):
        self.ensure_one()
        # as the customer's request had it: the order's company, their language
        # and time zone
        ctx = dict(self.env.context)
        if self.tz:
            ctx['tz'] = self.tz
        if self.lang:
            ctx['lang'] = self.lang
        group = self.request_id.group_id
        company = self.order_id.company_id or (group and self.request_id._company_for(group)) or self.env.company
        req = self.request_id.with_context(ctx).with_company(company)
        if self.step == 'accepted':
            return req._sa_after_accepted_work(self.ref, self.mode)
        order = self.order_id.with_context(ctx).with_company(company)
        if self.step == 'signed':
            return req._sa_after_signed_work(order, self.mode)
        return req._sa_group_confirmed(order)

    # ---------------------------------------------------------- parts
    def _has(self, name):
        return name in (self.done or '').split(',')

    def _remember(self, name):
        """Kept even when the task's own transaction is undone later: what went
        out on WhatsApp went out."""
        self.ensure_one()
        if not self.env.context.get('sa_after_commit'):
            self.sudo().done = ','.join(x for x in ((self.done or '').split(',') + [name]) if x)
            return
        with self.env.registry.cursor() as cr:
            cr.execute("UPDATE sa_after_task SET done = COALESCE(NULLIF(done, '') || ',', '') || %s WHERE id = %s",
                       (name, self.id))


def _run_in_thread(dbname, ids):
    threading.current_thread().dbname = dbname
    try:
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            for task in env['sa.after.task'].browse(ids).exists():
                task._run_locked()
    except Exception as err:  # noqa: BLE001 - the cron takes it
        _logger.warning("After-order task %s not started at once (%s) - the scheduled job takes it", ids, err)


class SaGroupRequestAfter(models.Model):
    _inherit = 'sa.group.request'

    def _sa_after_part(self, name, do, sends=False):
        """Do one part once. Outside a task it is simply done."""
        self.ensure_one()
        task = self.env['sa.after.task'].sudo().browse(self.env.context.get('sa_after_task') or 0).exists()
        if not task:
            return do()
        if task._has(name):
            return None
        commit = self.env.context.get('sa_after_commit')
        if sends:
            session = self.group_id.session_id
            session._refresh_state()
            if session.status != 'connected':
                raise SaNotConnected()
        sent = False
        try:
            with self.env.cr.savepoint():
                res = do()
                if sends:
                    # at once: what went out must not go out again because
                    # something of ours could not be saved afterwards
                    task._remember(name)
                    sent = True
        except Exception as err:  # noqa: BLE001
            if sent or isinstance(err, PG_CONCURRENCY_EXCEPTIONS_TO_RETRY) \
                    or not (sends and self.env.context.get('sa_after_last')):
                raise
            _logger.warning("After-order part %s of enquiry %s given up: %s", name, self.id, err)
            res = None
        self.env.flush_all()
        if commit:
            self.env.cr.commit()            # the invoice stands before it is ticked off
        if not sent:
            task._remember(name)
        if commit:
            self.env.cr.commit()            # a new snapshot: the tick is seen
        task.invalidate_recordset(['done'])
        return res

    def _sa_after_again(self, text):
        """The duplicate filters (one minute, five in a private chat) took a
        failed try for a sent message: a retry is worded invisibly different."""
        task = self.env['sa.after.task'].sudo().browse(self.env.context.get('sa_after_task') or 0).exists()
        return text + '\u200b' * (task.tries if task else 0)

    def _sa_must_send(self, send):
        """Send, or raise: a message WhatsApp did not take must not wait in the
        outbox next to this task's own retry."""
        self.ensure_one()
        Message = self.env['whatsapp.message'].sudo()
        last = Message.search([], order='id desc', limit=1).id or 0
        if send() is False:
            raise RuntimeError("WhatsApp did not take the message")
        Message.search([('id', '>', last), ('direction', '=', 'outgoing'), ('status', '=', 'pending'),
                        ('session_id', '=', self.group_id.session_id.id)]).write({'status': 'failed'})
        return True

    # ---------------------------------------------------------- signed
    def _sa_after_signed_work(self, order, mode):
        """The signed order's PDF (made once: on the order and on WhatsApp),
        the words, Odoo's email."""
        self.ensure_one()
        order = order.sudo()
        pdf = []

        def render():
            if not pdf:
                data, _kind = self.env['ir.actions.report'].sudo().with_context(
                    sale_include_signature=True)._render_qweb_pdf('sale.action_report_saleorder', order.ids)
                pdf.append(data)
            return pdf[0]

        if order.signature:
            self._sa_after_part('attach', lambda: order.message_post(
                attachments=[('%s.pdf' % order.name, render())], author_id=order.partner_id.id,
                body=_("Order signed by %s", order.signed_by or order.partner_id.name or ''),
                message_type='comment', subtype_xmlid='mail.mt_comment'))
        session = self.group_id.session_id
        fname = ((order.name or 'Order').replace('/', '_')) + '.pdf'
        self._sa_after_part('pdf', lambda: self._sa_must_send(lambda: self._sa_send_doc(
            lambda to: session.send_document(
                to, render(), fname, caption=_("\U0001F4C4 Order %(name)s - confirmed. Thank you!", name=order.name or '')),
            note=_("\U0001F4C4 Your order %s (PDF) is in your *private chat* \U0001F512") % (order.name or ''))), sends=True)
        if mode == 'stop':
            self._sa_after_part('words', lambda: self._sa_signed_stop(order, self._sa_flow_end()), sends=True)
        elif not (mode == 'pay' and (self.sa_paid_on or self._sa_order_is_paid(order))):
            # paid meanwhile: "pay here" would be wrong, the invoice follows
            self._sa_after_part('words', lambda: self._sa_must_send(
                lambda: self._say(self._sa_after_again(self._sa_signed_words(order, mode)))), sends=True)
        self._sa_after_part('mail', lambda: order.with_context(sa_after_mail=True)._send_order_confirmation_mail()
                            if order.state == 'sale' else None)
        return True

    # ---------------------------------------------------------- product page
    def _sa_after_accepted_work(self, ref, action):
        """Filled in by the confirmation page module."""
        return True

    # ---------------------------------------------------------- paid
    sa_pay_mail_on = fields.Datetime('Payment email to send since', copy=False, readonly=True)

    def _sa_pay_mail(self, order):
        """Odoo's payment email (with the order's PDF), once."""
        self.ensure_one()
        if not self.sa_pay_mail_on:
            return True
        order.sudo().with_context(sa_after_mail=True)._send_payment_succeeded_for_order_mail()
        self.sudo().write({'sa_pay_mail_on': False})
        return True

    def _sa_group_confirmed(self, order):
        """Paid: queued while the customer waits; done by the task."""
        self.ensure_one()
        if self.env.context.get('sa_after_task') or self.env.context.get('sa_after_now'):
            res = super()._sa_group_confirmed(order)
            if self.env.context.get('sa_after_task'):
                self._sa_after_part('pay_mail', lambda: self._sa_pay_mail(order))
            else:
                self._sa_pay_mail(order)
            return res
        if self.sa_paid_told_on:
            return False
        if not self.sa_paid_on:
            self.write({'sa_paid_on': fields.Datetime.now()})
        self.env['sa.after.task']._queue(self, order, 'paid')
        return True


class SaleOrderAfter(models.Model):
    _inherit = 'sale.order'

    def _sa_after_signed_here(self):
        """A WhatsApp group order being signed: its email goes with the task."""
        self.ensure_one()
        req = self.sudo()._sa_group_enquiry()
        return bool(req and req.group_id and req.sa_sign_link_sent_on and not req.sa_pay_link_sent_on)

    def _send_order_confirmation_mail(self):
        if self.env.context.get('sa_after_mail'):
            return super()._send_order_confirmation_mail()
        later = self.filtered(lambda o: o.signed_on and o._sa_after_signed_here())
        rest = self - later
        return super(SaleOrderAfter, rest)._send_order_confirmation_mail() if rest else None

    def _send_payment_succeeded_for_order_mail(self):
        """A signed WhatsApp group order: its payment email (and its PDF) goes
        with the paid task; the customer's page does not wait for it."""
        if self.env.context.get('sa_after_mail'):
            return super()._send_payment_succeeded_for_order_mail()
        later = self.browse()
        for order in self:
            req = order.sudo()._sa_group_enquiry()
            if order.state == 'sale' and req and req.group_id and req.sa_sign_link_sent_on and req.order_id == order:
                if not req.sa_pay_mail_on:
                    req.sudo().write({'sa_pay_mail_on': fields.Datetime.now()})
                later |= order
        rest = self - later
        return super(SaleOrderAfter, rest)._send_payment_succeeded_for_order_mail() if rest else None
