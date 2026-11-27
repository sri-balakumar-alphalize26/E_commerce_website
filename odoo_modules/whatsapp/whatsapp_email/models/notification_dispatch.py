"""Generic Email + WhatsApp dispatch helpers used by sale.order, purchase.order,
account.move, and pos.order. Reads the active whatsapp.config record for
toggles, admin email, from email, and POS recipient lists."""

from odoo.modules.registry import Registry
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.whatsapp_gateway.models.whatsapp_session import WhatsAppQueued
import base64
import logging

_logger = logging.getLogger(__name__)


class WhatsAppEmailDispatch(models.AbstractModel):
    _name = 'whatsapp.email.dispatch'
    _description = 'Cross-channel (Email + WhatsApp) Notification Dispatcher'

    @api.model
    def run_after_commit(self, res_model, res_ids, method, priority=10):
        """Call record.<method>() once this transaction has committed.

        Sending inside the caller's transaction made a sale wait on WhatsApp: a
        deliberate 1200 ms pacing delay per message, and up to 30 s if the
        gateway does not answer. It also meant a gateway timeout could take the
        payment transaction with it.

        `priority` decides the order after the commit, lowest first, because
        registration order is not business order: Odoo posts the payment before
        Point of Sale creates the invoice, so the receipt would otherwise always
        reach the customer before the invoice it belongs to.

        Everything registered in one transaction shares a single post-commit
        callback so the order can be applied across all of it. Each entry still
        gets its own cursor, so one failure cannot take the others down, and
        failures are logged rather than raised - the sale is already committed
        and nothing here may undo it.
        """
        if not res_ids:
            return
        cr = self.env.cr
        queue = getattr(cr, '_wa_after_commit_queue', None)
        if queue is None:
            queue = []
            cr._wa_after_commit_queue = queue
            dbname = cr.dbname
            uid = self.env.uid

            def _drain():
                for _priority, model, ids, meth in sorted(queue,
                                                          key=lambda e: e[0]):
                    try:
                        with Registry(dbname).cursor() as new_cr:
                            env = api.Environment(new_cr, uid, {})
                            for record in env[model].browse(ids).exists():
                                try:
                                    getattr(record, meth)()
                                except Exception:  # noqa: BLE001
                                    _logger.exception(
                                        "after-commit %s.%s failed for id %s",
                                        model, meth, record.id)
                    except Exception:  # noqa: BLE001
                        # Nobody is watching a post-commit callback - the
                        # request that triggered it finished long ago - so say
                        # exactly what was lost.
                        _logger.exception(
                            "after-commit dispatch could not run for %s %s (%s)",
                            model, ids, meth)

            cr.postcommit.add(_drain)
        queue.append((priority, res_model, list(res_ids), method))


    # Every lookup below is for ONE company: the document's. Callers run in
    # `record.with_company(record.company_id)`, so self.env.company is it.
    # A company never borrows another company's settings, number or address:
    # that is chosen deliberately in its own WhatsApp and Email settings
    # (pick the same number for every company to share one).

    @api.model
    def _company(self, company=None):
        return company or self.env.company

    @api.model
    def get_config(self, company=None):
        return self.env['whatsapp.config'].sudo().search(
            [('company_id', '=', self._company(company).id)], limit=1)

    @api.model
    def get_default_email_session(self):
        config = self.get_config()
        if config and config.default_email_session_id:
            return config.default_email_session_id
        return self.env['email.session'].sudo().get_default_session()

    @api.model
    def get_default_whatsapp_session(self, company=None):
        """The number this company sends WhatsApp from, or an empty recordset.

        1. the number chosen in the company's settings ("Send WhatsApp from"),
        2. else a connected number of the company itself.
        """
        Session = self.env['whatsapp.session'].sudo()
        # An Odoo branch (child company) without its own Main uses its
        # parent's: branch -> parent -> grand-parent. Never a sister company.
        for each in self._company_chain(company):
            config = self.get_config(each)
            if config and config.default_whatsapp_session_id and config.default_whatsapp_session_id.active:
                return config.default_whatsapp_session_id
            # Ask the gateway rather than reading the status column, which goes
            # stale between cron runs and would hide a session that is connected.
            own = Session.get_connected_session(company_id=each.id)
            if own:
                return own
        return Session.browse()

    @api.model
    def _company_chain(self, company=None):
        chain, each = [], self._company(company)
        while each and each not in chain:
            chain.append(each)
            each = each.parent_id
        return chain

    @api.model
    def get_email_sender_session(self, company=None):
        """The gateway session that sends this company's e-mail, or an empty
        recordset.

        1. the address chosen in the company's settings ("Send email from"),
        2. else a number of the company that has its own e-mail account,
        3. else the company's WhatsApp number, when it has e-mail on.
        The panel holds each account's password; Odoo only picks the key.
        """
        company = self._company(company)
        Session = self.env['whatsapp.session'].sudo()
        for each in self._company_chain(company):        # branch, then its parent
            session = Session._mail_session_of_company(each.id)
            if session:
                return session
        session = self.get_default_whatsapp_session(company)
        if session and getattr(session, 'use_email', False) and session.authorized_email:
            return session
        return Session.browse()

    @api.model
    def _not_set_reason(self, channel, company=None):
        company = self._company(company)
        if channel == 'email':
            return _("%s has no e-mail address chosen. Open WhatsApp and Email > Settings (company %s) "
                     "and choose 'Send email from', or press Add email on a number.") % (company.name, company.name)
        return _("%s has no WhatsApp number chosen. Open WhatsApp and Email > Settings (company %s) "
                 "and choose 'Send WhatsApp from', or connect a number for it.") % (company.name, company.name)

    @api.model
    def send_result_notification(self, result, title=None):
        """Turn send_record()'s result into a notification that tells the truth.

        Every caller used to return a green "Send dispatched" whatever
        happened, so a send that failed on both channels looked exactly like
        one that worked - the errors were collected and then thrown away.
        """
        errors = (result or {}).get('errors') or []
        if errors:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': title or _('Send failed'),
                    'message': '\n'.join(errors),
                    'type': 'warning',
                    'sticky': True,
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title or _('Send Result'),
                'message': _('Sent. Check the chatter for per-channel status.'),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def send_record(self, record, partner, report_xmlid,
                    subject, body_html=None, wa_caption=None,
                    send_email=True, send_whatsapp=True,
                    email_session=None, whatsapp_session=None):
        """Send `record` PDF to `partner` via the requested channels.
        `email_session` and `whatsapp_session` may be passed explicitly to
        override the configured defaults. Failures log to the chatter and
        never block the originating action. Returns dict of channel -> bool."""
        result = {'email': False, 'whatsapp': False}
        # The document's company decides the number, the address and the name
        # in the message - not the company the user happens to be switched to.
        company = (getattr(record, 'company_id', False) if record else False) or self.env.company
        # one send = the PDF made once, for e-mail and WhatsApp (it took ~5 s each)
        self = self.with_company(company).with_context(wa_pdf_cache={})
        if record:
            record = record.with_company(company)
        if not partner:
            if record:
                record.message_post(body=_("Auto-send skipped: no partner on record."))
            return result

        errors = []
        if send_email:
            try:
                sess = email_session or self.get_email_sender_session()
                self._send_email(record, partner, report_xmlid, subject, body_html, sess)
                result['email'] = True
                if record:
                    record.message_post(body=_("📧 Email sent to %s") % partner.email)
            except Exception as e:
                _logger.exception("dispatch email failed: %s", e)
                if record:
                    record.message_post(body=_("📧 Email FAILED: %s") % str(e))
                errors.append(_("Email: %s") % str(e))

        if send_whatsapp:
            try:
                sess = whatsapp_session or self.get_default_whatsapp_session()
                # The company's choice (Settings: "Send the PDF on WhatsApp"),
                # or the tick in the Send form for this one send.
                want_pdf = self.env.context.get('wa_send_pdf')
                if want_pdf is None:
                    config = self.get_config(company)
                    want_pdf = config.wa_send_pdf if config else True
                details = self._wa_details(record, fallback=wa_caption or subject) if record else (wa_caption or subject)
                if want_pdf and report_xmlid:
                    # PDF with the details as its caption (WhatsApp keeps a caption short)
                    caption = details if len(details) <= 1000 else self._wa_details(record, lines=False)
                    self._send_whatsapp(record, partner, report_xmlid, caption, sess)
                else:
                    # no PDF: everything the PDF shows, as a message
                    self._send_whatsapp(record, partner, False, details, sess)
                result['whatsapp'] = True
                if record:
                    target = (getattr(partner, 'mobile', '') or '') or (partner.phone or '')
                    record.message_post(body=_("📱 WhatsApp sent to %s") % (target or partner.display_name))
            except Exception as e:
                _logger.exception("dispatch whatsapp failed: %s", e)
                if record:
                    record.message_post(body=_("📱 WhatsApp FAILED: %s") % str(e))
                errors.append(_("WhatsApp: %s") % str(e))

        result['errors'] = errors
        return result

    # ──────────────────────────────────────────────────────────────────────
    # The document as a WhatsApp message: what its PDF shows.
    # ──────────────────────────────────────────────────────────────────────

    _WA_LINES = ('order_line', 'invoice_line_ids', 'line_ids')        # first that exists
    _WA_QTY = ('product_uom_qty', 'product_qty', 'quantity', 'qty')
    _WA_SUB = ('price_subtotal', 'subtotal')

    @api.model
    def _wa_label(self, record):
        model = record._name
        if model == 'sale.order':
            return _('Quotation') if record.state in ('draft', 'sent') else _('Sale Order')
        if model == 'purchase.order':
            return _('Request for Quotation') if record.state in ('draft', 'sent') else _('Purchase Order')
        if model == 'account.move':
            return {'out_invoice': _('Invoice'), 'out_refund': _('Credit Note'), 'in_invoice': _('Vendor Bill'),
                    'in_refund': _('Vendor Refund')}.get(record.move_type, _('Journal Entry'))
        if model == 'account.payment':
            return _('Payment Receipt')
        return getattr(record, '_wa_doc_label', '') or record._description or _('Document')

    @api.model
    def _wa_money(self, amount, currency):
        try:
            from odoo.tools.misc import format_amount
            text = format_amount(self.env, amount or 0.0, currency) if currency else '%.2f' % (amount or 0.0)
        except Exception:  # noqa: BLE001
            text = '%s %.2f' % (currency.symbol if currency else '', amount or 0.0)
        # An Arabic symbol (ر.ع.) turns the whole line right-to-left on the phone:
        # "1 × 22.000 ر.ع. = 20.952 ر.ع." came out scrambled. Left-to-right marks
        # around each amount keep the line in reading order.
        return '‎%s‎' % text

    @api.model
    def _wa_num(self, value):
        value = value or 0.0
        return ('%d' % value) if float(value).is_integer() else ('%.3f' % value).rstrip('0').rstrip('.')

    @api.model
    def _sender_name(self, company=None):
        """The company's "Sender name" (WhatsApp and Email > Companies), else the database name."""
        config = self.get_config(company or self.env.company)
        return (config.sender_name or '').strip() if config and (config.sender_name or '').strip()             else self.env.cr.dbname

    @api.model
    def _pdf_once(self, report_xmlid, record):
        """The document's PDF, made once per send (send_record keeps a cache in
        the context) - e-mail and WhatsApp used to make it twice."""
        cache = self.env.context.get('wa_pdf_cache')
        key = (report_xmlid, record._name, record.id)
        if cache is not None and key in cache:
            return cache[key]
        pdf, _ext = self.env['ir.actions.report']._render_qweb_pdf(report_xmlid, res_ids=record.ids)
        if cache is not None:
            cache[key] = pdf
        return pdf

    @api.model
    def _doc_data(self, record):
        """What the document's PDF shows, read once for WhatsApp and e-mail:
        {label, name, date, partner, lines: [(what, qty, price, subtotal)],
         more, untaxed, tax, total, status, payment: [(label, text)], company}.
        Amounts are already formatted. Any document with lines works."""
        record = record.sudo()
        cur = getattr(record, 'currency_id', False)
        money = lambda value: self._wa_money(value, cur)  # noqa: E731
        day = (getattr(record, 'invoice_date', False) or getattr(record, 'date_order', False)
               or getattr(record, 'date', False))
        partner = getattr(record, 'partner_id', False)
        data = {
            'label': self._wa_label(record), 'name': getattr(record, 'name', '') or '',
            'date': (day.strftime('%d-%m-%Y') if hasattr(day, 'strftime') else str(day)) if day else '',
            'partner': partner.display_name if partner else '',
            'lines': [], 'more': 0, 'untaxed': '', 'tax': '', 'total': '', 'status': '', 'payment': [],
            'company': self._sender_name(record.company_id if 'company_id' in record._fields
                                         and record.company_id else self.env.company),
        }
        if record._name == 'account.payment':
            data['total'] = money(record.amount)
            memo = getattr(record, 'memo', False) or getattr(record, 'ref', False)
            if memo:
                data['payment'].append((_('Memo'), memo))
            invoices = getattr(record, 'reconciled_invoice_ids', False) or getattr(record, 'reconciled_bill_ids', False)
            if invoices:
                data['payment'].append((_('For'), ', '.join(invoices.mapped('name'))))
            return data
        field = next((f for f in self._WA_LINES if f in record._fields), None)
        rows = record[field] if field else []
        if field == 'line_ids' and record._name == 'account.move':
            rows = []                                        # journal items, not invoice lines
        rows = [l for l in rows if not getattr(l, 'display_type', False) or l.display_type in ('product', False)]
        for line in rows[:40]:
            what = (line.product_id.display_name if getattr(line, 'product_id', False) else '') \
                or getattr(line, 'description', '') or (line.name or '').split('\n')[0]
            qty = next((line[f] for f in self._WA_QTY if f in line._fields), 0)
            sub = next((line[f] for f in self._WA_SUB if f in line._fields), qty * (line.price_unit or 0))
            data['lines'].append((what, self._wa_num(qty), money(getattr(line, 'price_unit', 0)), money(sub)))
        data['more'] = max(0, len(rows) - 40)
        untaxed, tax = getattr(record, 'amount_untaxed', None), getattr(record, 'amount_tax', None)
        if untaxed is not None and tax:
            data['untaxed'], data['tax'] = money(untaxed), money(tax)
        data['total'] = money(getattr(record, 'amount_total', 0))
        due, paid = getattr(record, 'amount_residual', None), getattr(record, 'amount_paid', None)
        if record._name == 'account.move' and due is not None and record.state == 'posted':
            data['status'] = _('Paid ✓') if not due else '%s %s' % (_('Still due:'), money(due))
        elif paid:
            data['status'] = '%s %s' % (_('Paid:'), money(paid))
        return data

    @api.model
    def _wa_details(self, record, lines=True, fallback=''):
        """The document as WhatsApp text (*bold*): number, date, partner, every
        line (qty × price = subtotal), untaxed / tax / total, paid / due."""
        try:
            d = self._doc_data(record)
            out = ['*%s %s*' % (d['label'], d['name'])]
            if d['date']:
                out.append('📅 %s' % d['date'])
            if d['partner']:
                out.append('👤 %s' % d['partner'])
            if record._name == 'account.payment':
                out.append('💰 *%s %s*' % (_('Amount:'), d['total']))
                out += ['📝 %s: %s' % pair for pair in d['payment']]
            else:
                if lines and d['lines']:
                    out.append('──────────')
                    for i, (what, qty, price, sub) in enumerate(d['lines'], 1):
                        out.append('%d. %s' % (i, what))
                        out.append('    %s × %s = %s' % (qty, price, sub))
                    if d['more']:
                        out.append(_('… and %s more lines') % d['more'])
                    out.append('──────────')
                elif d['lines']:
                    out.append(_('%s lines') % (len(d['lines']) + d['more']))
                if d['untaxed']:
                    out.append('%s %s' % (_('Untaxed:'), d['untaxed']))
                    out.append('%s %s' % (_('Tax:'), d['tax']))
                out.append('💰 *%s %s*' % (_('Total:'), d['total']))
                if d['status']:
                    out.append(d['status'])
            out.append('— %s' % d['company'])
            return '\n'.join(out)
        except Exception as e:  # noqa: BLE001 - a message is better than none
            _logger.warning("WhatsApp details of %s could not be built: %s", record, e)
            return fallback or getattr(record, 'display_name', '')

    @api.model
    def _email_details_html(self, record, partner, with_pdf):
        """The same details as an e-mail body: greeting, a lines table,
        totals, regards. Says whether the PDF is attached."""
        from markupsafe import escape as e
        d = self._doc_data(record)
        cell = 'padding:6px 8px;border-bottom:1px solid #e3e6ea;'
        right = cell + 'text-align:right;'
        rows = ''.join(
            '<tr><td style="%s">%s</td><td style="%s">%s</td><td style="%s">%s</td><td style="%s">%s</td></tr>'
            % (cell, e(w), right, e(q), right, e(p), right, e(s)) for w, q, p, s in d['lines'])
        if d['more']:
            rows += '<tr><td colspan="4" style="%s">%s</td></tr>' % (cell, e(_('… and %s more lines') % d['more']))
        totals = ''
        if d['untaxed']:
            totals += '<tr><td style="%s">%s</td><td style="%s">%s</td></tr>' % (cell, e(_('Untaxed')), right, e(d['untaxed']))
            totals += '<tr><td style="%s">%s</td><td style="%s">%s</td></tr>' % (cell, e(_('Tax')), right, e(d['tax']))
        totals += ('<tr style="background:#017e84;color:#fff;font-weight:bold;"><td style="padding:6px 8px;">%s</td>'
                   '<td style="padding:6px 8px;text-align:right;">%s</td></tr>') % (
            e(_('Amount') if record._name == 'account.payment' else _('Total')), e(d['total']))
        if d['status']:
            totals += '<tr><td colspan="2" style="%s">%s</td></tr>' % (right, e(d['status']))
        extra = ''.join('<p style="margin:4px 0;"><b>%s:</b> %s</p>' % (e(k), e(v)) for k, v in d['payment'])
        table = ''
        if d['lines']:
            table = ('<table style="width:100%%;border-collapse:collapse;margin:12px 0;font-size:14px;">'
                     '<tr style="background:#f4f5f7;"><th style="%s text-align:left;">%s</th><th style="%s">%s</th>'
                     '<th style="%s">%s</th><th style="%s">%s</th></tr>%s</table>') % (
                cell, e(_('Product')), right, e(_('Qty')), right, e(_('Unit price')), right, e(_('Amount')), rows)
        return (
            '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:640px;">'
            '<p>%s %s,</p>'
            '<p>%s</p>'
            '<h3 style="margin:14px 0 2px;color:#017e84;">%s %s</h3>'
            '<p style="margin:0;color:#666;">%s</p>'
            '%s%s'
            '<table style="width:60%%;margin-left:40%%;border-collapse:collapse;font-size:14px;">%s</table>'
            '<p style="margin-top:16px;">%s<br/><b>%s</b></p></div>'
        ) % (
            e(_('Dear')), e(partner.name or ''),
            e(_('Please find the details of your document below - the PDF is attached.') if with_pdf
              else _('Please find the details of your document below.')),
            e(d['label']), e(d['name']), e(d['date']), extra, table, totals,
            e(_('Regards,')), e(d['company']))

    # ──────────────────────────────────────────────────────────────────────

    def _send_email(self, record, partner, report_xmlid, subject, body_html, email_session=None):
        """Send one document by email, on the gateway session.

        `email_session` is a whatsapp.session. It used to be an email.session
        wrapping an ir.mail_server, but that server stopped being reached the
        moment gateway routing went on - so the SMTP credentials behind it
        bought nothing, while still being required before anything could be
        sent. The gateway holds the vendor's mail account and decides the From.

        Sending here rather than through mail.mail also keeps email under the
        same unsubscribe list, blocked words and caps as WhatsApp. A customer
        who asked this vendor to stop should not have to ask twice.

        Raises on failure - send_record() catches it, posts the reason to the
        chatter and carries on with the other channel.
        """
        if not partner.email:
            raise UserError(_(
                "Partner '%s' has no email address - cannot send."
            ) % partner.display_name)

        session = email_session or self.get_email_sender_session()
        if not session:
            raise UserError(self._not_set_reason('email'))
        # send_email() belongs to whatsapp_gateway. Guard rather than assume:
        # a session record can come from another WhatsApp module that has no
        # email channel at all.
        if not hasattr(session, 'send_email'):
            raise UserError(_(
                "Session '%s' cannot send email - it has no gateway email "
                "channel.") % session.display_name)
        if not session.use_email:
            raise UserError(_(
                "Email is switched off for session '%s'. Tick Email on "
                "WhatsApp > Sessions, then try again.") % session.display_name)

        # The company's choice ("Attach the PDF to e-mails"), or the Send form's tick for this send.
        with_pdf = self.env.context.get('email_send_pdf')
        if with_pdf is None:
            config = self.get_config(record.company_id if record and 'company_id' in record._fields else None)
            with_pdf = config.email_send_pdf if config else True
        with_pdf = bool(with_pdf and report_xmlid and record)
        body = body_html
        if not body and record:
            try:
                body = self._email_details_html(record, partner, with_pdf)
            except Exception as err:  # noqa: BLE001 - the plain greeting still goes
                _logger.warning("E-mail details of %s could not be built: %s", record, err)
        body = body or (
            "<p>Dear %s,</p><p>Please find attached <strong>%s</strong>.</p>"
            "<p>Regards,<br/>%s</p>" % (
                partner.name,
                getattr(record, 'display_name', '') or getattr(record, 'name', ''),
                self.env.company.name,
            )
        )

        attachments = []
        if with_pdf:
            try:
                pdf_content = self._pdf_once(report_xmlid, record)
                fname = (getattr(record, 'name', None) or 'document').replace('/', '_')
                # send_email() base64-encodes bytes itself, so hand it the PDF
                # as it came out of the renderer.
                attachments.append({
                    'filename': '%s.pdf' % fname,
                    'content': pdf_content,
                    'mimetype': 'application/pdf',
                })
            except Exception as e:
                _logger.warning("Could not render report %s for %s: %s",
                                report_xmlid, record, e)

        # sudo() because _gateway_call reads gateway_api_key, which is
        # restricted to base.group_system. Without it the key reads as False
        # and the send fails with "no gateway URL or API key set".
        sender = self._sender_name(record.company_id if record and 'company_id' in record._fields
                                   and record.company_id else self.env.company)
        sent = session.sudo().with_context(wa_from_name=sender).send_email(
            partner.email,
            subject,
            body_html=body,
            attachments=attachments or None,
        )
        if not sent:
            # False is one of the gateway's own rules doing its job: an
            # unsubscribe, a blocked word, a cap. Raise, because returning
            # quietly would post "Email sent" for a message that never left.
            raise UserError(_(
                "The gateway did not send to %s. The address may have opted "
                "out, or a sending limit was reached.") % partner.email)

    def _send_whatsapp(self, record, partner, report_xmlid, caption, whatsapp_session=None):
        # Odoo 19 builds may not have res.partner.mobile — defensive lookup.
        mobile_raw = getattr(partner, 'mobile', '') or ''
        phone_raw = partner.phone or ''
        phone = mobile_raw or phone_raw
        if not phone:
            raise UserError(_(
                "Partner '%s' has no phone/mobile number — set one on the partner "
                "to enable WhatsApp auto-send."
            ) % partner.display_name)
        clean = self._clean_phone(phone)

        session = whatsapp_session
        if not session:
            raise UserError(self._not_set_reason('whatsapp'))
        if session.status != 'connected':
            raise UserError(_(
                "WhatsApp session '%s' is not connected (status: %s). "
                "Reconnect it before retrying."
            ) % (session.name, session.status))

        # Try the PDF; fall back to text only when the PDF can never arrive.
        if report_xmlid and record and hasattr(session, 'send_odoo_report'):
            try:
                # the PDF the e-mail of this send already made, if any
                pdf = self._pdf_once(report_xmlid, record)
                filename = "%s.pdf" % (record.display_name or 'document')
                result = session.send_document(clean, pdf, filename, caption, retry={
                    'retry_report_xmlid': report_xmlid, 'retry_res_model': record._name,
                    'retry_res_id': record.id, 'retry_filename': filename, 'retry_caption': caption or '',
                })
            except WhatsAppQueued:
                # Queued, and the retry now re-sends the real document. Sending
                # the caption as text here is what put every document on the
                # customer's phone twice - once as text, once as the PDF.
                _logger.info("dispatch: WhatsApp PDF queued for %s", clean)
                return
            except Exception as e:
                # A report that will not render, a bad xmlid: the PDF is never
                # coming, so the text is better than nothing. This is the case
                # the fallback was written for.
                _logger.warning(
                    "dispatch: send_odoo_report failed (%s) - falling back to text",
                    e,
                )
            else:
                if result is False:
                    # A policy rule refused it - opt-out, blocked word, daily
                    # cap, duplicate. Re-sending the same content as text would
                    # walk straight around the block.
                    _logger.info("dispatch: WhatsApp PDF refused by policy for %s",
                                 clean)
                else:
                    _logger.info("dispatch: WhatsApp PDF sent to %s", clean)
                return
        session.send_message(clean, caption)
        _logger.info("dispatch: WhatsApp text sent to %s", clean)

    @staticmethod
    def _clean_phone(phone):
        if not phone:
            return ''
        for ch in ('+', ' ', '-', '(', ')'):
            phone = phone.replace(ch, '')
        return phone
