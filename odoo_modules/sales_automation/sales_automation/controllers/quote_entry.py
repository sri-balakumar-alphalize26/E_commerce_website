# -*- coding: utf-8 -*-
"""Type a price in, from a link, with no Odoo account.

The counter screen is `auth='user'`. A shopkeeper who is not an Odoo user
cannot open it - the same objection that produced the rider's job link. So
this is a public page whose only credential is the token in the URL, compared
in constant time and never printed back.

A typed price is a *write* from a public route, which is the shape of both
security incidents this codebase has recorded (the untokened `/wa/rider/<id>`
and the GET-able `/wa/pay/<id>/confirm`). Three things keep it honest:

  * the price is APPENDED as a vendor quote, never written over the enquiry,
    so it is auditable and another price can be picked instead;
  * applying it needs a POST, and a separate confirm step before that, so no
    link-preview crawler can price anything;
  * a wrong token is a 404 that says nothing about why.
"""
import hmac
import logging

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class SaQuoteEntry(http.Controller):

    def _enquiry(self, request_id, token):
        """The enquiry this token opens, or None."""
        enquiry = request.env['sa.group.request'].sudo().browse(
            int(request_id))
        if not enquiry.exists() or not token:
            return None
        secret = enquiry.sudo().sa_price_token or ''
        if not secret or not hmac.compare_digest(str(secret), str(token)):
            return None
        return enquiry

    def _values(self, enquiry, token, **extra):
        product = enquiry.product_id
        vendors = enquiry.sourcing_vendor_ids or enquiry.shop_pick_vendor_ids
        values = {
            'enquiry': enquiry,
            'token': token,
            'name': (product.name or enquiry.ai_search_term
                     or enquiry.raw_text or ''),
            'vendors': vendors,
            'margin': request.env['sa.ai.settings'].sudo(
                ).get_settings().margin_percent or 0.0,
            'currency': enquiry.currency_id.name or '',
            'error': '',
        }
        yes, no, silent = enquiry._sa_vendor_lists()
        seller, hint = enquiry._sa_price_hint()
        values.update({
            'said_yes': yes, 'said_no': no, 'silent': silent,
            'hint_price': hint,
            'hint_vendor': seller.partner_id.name if seller else '',
        })
        values.update(extra)
        return values

    def _spent(self, enquiry, token):
        """Already priced - show the receipt, not the form again.

        Nothing stopped whoever holds the link opening it a second time and
        quoting the customer twice. `sa_price_stalled` is the exact condition
        the link exists for, so once it is False the link is spent. The token
        is deliberately left valid: a 404 would be indistinguishable from a
        wrong token, and the honest answer to "I tapped my link again" is the
        receipt.
        """
        _logger.info("Sales Automation: price link for enquiry %s reopened "
                     "after it was already priced", enquiry.id)
        return request.render('sales_automation.sa_quote_done_page',
                              self._values(enquiry, token))

    @http.route('/wa/quote/<int:request_id>', type='http', auth='public',
                website=False, csrf=False)
    def form(self, request_id, token=None, **kw):
        enquiry = self._enquiry(request_id, token)
        if not enquiry:
            return request.not_found()
        if not enquiry.sa_price_stalled:
            return self._spent(enquiry, token)
        return request.render('sales_automation.sa_quote_entry_page',
                              self._values(enquiry, token))

    @http.route('/wa/quote/<int:request_id>/confirm', type='http',
                auth='public', methods=['POST'], csrf=False)
    def confirm(self, request_id, token=None, **kw):
        """Show back what will be quoted, before anything is written."""
        enquiry = self._enquiry(request_id, token)
        if not enquiry:
            return request.not_found()
        if not enquiry.sa_price_stalled:
            return self._spent(enquiry, token)
        raw = (kw.get('cost') or '').strip()
        try:
            cost = float(raw.replace(',', ''))
            if cost <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return request.render(
                'sales_automation.sa_quote_entry_page',
                self._values(enquiry, token,
                             error=_("Type the price as a number, like 500.")))
        margin = request.env['sa.ai.settings'].sudo(
            ).get_settings().margin_percent or 0.0
        vendor = request.env['res.partner'].sudo().browse(
            int(kw['vendor_id'])) if (kw.get('vendor_id') or '').isdigit() \
            else request.env['res.partner']
        return request.render(
            'sales_automation.sa_quote_confirm_page',
            self._values(enquiry, token, cost=cost,
                         days=(kw.get('days') or '').strip(),
                         vendor=vendor,
                         sell=cost * (1.0 + margin / 100.0)))

    @http.route('/wa/quote/<int:request_id>/apply', type='http',
                auth='public', methods=['POST'], csrf=False)
    def apply(self, request_id, token=None, **kw):
        enquiry = self._enquiry(request_id, token)
        if not enquiry:
            return request.not_found()
        if not enquiry.sa_price_stalled:
            return self._spent(enquiry, token)
        try:
            enquiry._sa_apply_manual_price(
                kw.get('cost'), vendor_id=(kw.get('vendor_id') or None),
                days=(kw.get('days') or 0), source=_("price link"))
        except UserError as err:
            return request.render(
                'sales_automation.sa_quote_entry_page',
                self._values(enquiry, token, error=str(err)))
        except Exception as err:  # noqa: BLE001
            _logger.exception("Sales Automation: manual price for enquiry %s "
                              "failed: %s", enquiry.id, err)
            return request.render(
                'sales_automation.sa_quote_entry_page',
                self._values(enquiry, token, error=_(
                    "Something went wrong saving that. Try again.")))
        enquiry.invalidate_recordset()
        return request.render('sales_automation.sa_quote_done_page',
                              self._values(enquiry, token))
