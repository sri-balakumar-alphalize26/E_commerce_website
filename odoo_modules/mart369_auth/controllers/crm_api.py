"""Tags and staff notes, for the app's own admin console.

The model does the work (models/customer_crm.py), so the Odoo desk - which
calls the same methods through the ORM - refuses the same things in the same
words. Same rule as every admin route: the group is checked first, and a
shopper is refused, not filtered.
"""

import json

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from .admin_api import Mart369CustomerAdminApi

_BASE = {'type': 'http', 'auth': 'user', 'csrf': False, 'sitemap': False}


class Mart369CustomerCrmApi(Mart369CustomerAdminApi):

    def _body(self):
        try:
            data = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    def _run(self, fn):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            with request.env.cr.savepoint():
                return self._json(dict({'ok': True}, **fn()))
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except UserError as exc:
            return self._fail(str(exc))

    # The list, with the Tag filter. The parent route has no `tag` argument,
    # so it travels on the context to the model's domain.
    @http.route()
    def customers(self, tag=None, **kwargs):
        if tag:
            request.update_context(mart369_tag=tag)
        return super().customers(**kwargs)

    @http.route('/369mart/admin/customer-tags', methods=['GET'], **_BASE)
    def tags(self, **kwargs):
        return self._run(lambda: {'tags': request.env['res.users'].mart369_admin_tags()})

    @http.route('/369mart/admin/customers/<int:user_id>/tags', methods=['PATCH'], **_BASE)
    def set_tags(self, user_id, **kwargs):
        names = self._body().get('tags') or []
        if not isinstance(names, list):
            return self._fail('Send the tags as a list of names.')
        return self._run(lambda: {
            'tags': request.env['res.users'].mart369_admin_set_tags(user_id, names)})

    @http.route('/369mart/admin/customers/<int:user_id>/notes', methods=['POST'], **_BASE)
    def add_note(self, user_id, **kwargs):
        text = self._body().get('text') or ''
        return self._run(lambda: {
            'notes': request.env['res.users'].mart369_admin_add_note(user_id, text)})

    @http.route('/369mart/admin/customers/<int:user_id>/notes/<int:note_id>',
                methods=['PATCH'], **_BASE)
    def edit_note(self, user_id, note_id, **kwargs):
        text = self._body().get('text') or ''
        return self._run(lambda: {
            'notes': request.env['res.users'].mart369_admin_edit_note(user_id, note_id, text)})

    @http.route('/369mart/admin/customers/<int:user_id>/notes/<int:note_id>',
                methods=['DELETE'], **_BASE)
    def delete_note(self, user_id, note_id, **kwargs):
        return self._run(lambda: {
            'notes': request.env['res.users'].mart369_admin_delete_note(user_id, note_id)})
