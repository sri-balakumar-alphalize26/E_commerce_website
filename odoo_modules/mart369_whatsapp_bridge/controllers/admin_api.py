"""The console's orders list learns one word: which door.

`GET /369mart/admin/orders?channel=whatsapp|website` filters the same list
the console already reads. Everything else - the group check, the shapes,
the errors - is the parent's, untouched.
"""

from odoo import http

from odoo.addons.mart369_order.controllers.admin_api import (
    _GET, Mart369OrderAdminApi)


class Mart369BridgeAdminApi(Mart369OrderAdminApi):

    @http.route('/369mart/admin/orders', **_GET)
    def orders(self, tab=None, mode=None, when=None, q=None, sort=None,
               limit=None, offset=None, pay=None, channel=None, **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            page = self._orders().mart369_admin_list(
                tab=tab, mode=mode, when=when, q=q, sort=sort, pay=pay,
                limit=limit or 30, offset=offset or 0,
                channel=channel if channel in ('website', 'whatsapp') else None)
        except Exception as exc:  # noqa: BLE001 - same shape as the parent
            return self._fail(str(exc))
        page['ok'] = True
        return self._json(page)
