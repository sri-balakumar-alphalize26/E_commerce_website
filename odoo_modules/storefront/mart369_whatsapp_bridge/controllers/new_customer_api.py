"""➕ New customer from the app's admin console.

POST /369mart/admin/customers with {name, mobile, country, email?,
address?} - the same rule as the backend wizard
(wizard/new_customer.py `_mart369_create_customer`). Staff only: the group
is checked first and anyone else is refused, as on every admin route.
"""
from odoo import http
from odoo.http import request

EDITOR_GROUP = 'website.group_website_designer'


class Mart369NewCustomerApi(http.Controller):

    @http.route('/369mart/admin/customers', type='http', auth='user', methods=['POST'],
                csrf=False, sitemap=False)
    def new_customer(self, **kwargs):
        if not request.env.user.has_group(EDITOR_GROUP):
            return request.make_json_response(
                {'ok': False, 'error': 'You do not have access to this.'}, status=403)
        try:
            body = request.get_json_data()
        except Exception:  # noqa: BLE001 - an empty or broken body is just empty
            body = None
        result = request.env['mart369.new.customer']._mart369_create_customer(
            body if isinstance(body, dict) else {})
        if result.get('ok'):
            return request.make_json_response(result, status=201)
        status = 409 if 'already' in (result.get('error') or '') else 400
        return request.make_json_response(result, status=status)
