# -*- coding: utf-8 -*-
"""Home delivery: the page of the one person who has the link. Looking never
changes anything (WhatsApp opens links to preview them); every step is a POST."""
import logging
from urllib.parse import quote_plus

import psycopg2

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class SaStaffDelivery(http.Controller):

    def _job(self, picking_id, token):
        job = request.env['stock.picking'].sudo().browse(int(picking_id)).exists()
        return job if job and job._sa_self_token_ok(token) else None

    def _page(self, job, token='', error='', told=''):
        values = {'job': job, 'token': token, 'error': error, 'told': told}
        if job:
            partner = job.partner_id
            locked = not job.sa_customer_revealed()
            where = job.sa_customer_area() if locked else ', '.join(filter(None, [
                partner.street, partner.street2, partner.city, partner.zip, partner.country_id.name]))
            values.update(
                partner=partner, locked=locked, where=where, due=job._sa_self_due(), state=job.sa_delivery_state,
                currency=(job.sa_currency_id or job.company_id.currency_id).name or '',
                map_url='https://www.google.com/maps/search/?api=1&query=%s' % quote_plus(where) if where and not locked else '')
        response = request.render('sales_automation_store.staff_delivery_page', values)
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    @http.route('/wa/staff/<int:picking_id>', type='http', auth='public', methods=['GET'], website=False, csrf=False)
    def page(self, picking_id, token=None, **kw):
        # a wrong link, an old one and a finished one look the same
        return self._page(self._job(picking_id, token), token)

    @http.route('/wa/staff/<int:picking_id>/<string:step>', type='http', auth='public', methods=['POST'], website=False, csrf=False)
    def step(self, picking_id, step, token=None, **kw):
        job = self._job(picking_id, token)
        if not job:
            return self._page(None)
        error = told = ''
        try:
            if step == 'done':
                error = job.with_context(sa_by_link=True)._sa_self_finish(kw.get('code'), kw.get('cash') == '1')
            elif step == 'again':
                told = job.sa_resend_customer_code()['message']
            elif step == 'fail':
                why = (kw.get('why') or '').strip()[:120]
                if why:
                    job._sa_self_back(why)
                else:
                    error = _("Say why it could not be delivered.")
            else:
                with request.env.cr.savepoint():
                    job._sa_self_step(step)
        except psycopg2.OperationalError:
            raise
        except UserError as err:
            error = str(err.args[0] if err.args else err)
        except Exception:  # noqa: BLE001 - a person at a door gets words
            _logger.exception("Store: step %s of job %s failed", step, picking_id)
            request.env.cr.rollback()
            error = _("It did not work. Try again, or call the shop.")
        if error or told:
            return self._page(self._job(picking_id, token), token, error, told)
        return request.redirect('/wa/staff/%s?token=%s' % (picking_id, quote_plus(token)), code=303)
