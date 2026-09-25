"""The console's customer profile page: GET /369mart/admin/customers/<id>/profile.

The model does the work (models/customer_profile.py). Same rule as every admin
route: the group is checked first, and a shopper is refused, not filtered.
"""

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

EDITOR_GROUP = 'website.group_website_designer'


class Mart369CustomerProfileApi(http.Controller):

    @http.route('/369mart/admin/customers/<int:user_id>/profile', type='http', auth='user',
                methods=['GET'], csrf=False, sitemap=False)
    def profile(self, user_id, **kwargs):
        if not request.env.user.has_group(EDITOR_GROUP):
            return request.make_json_response(
                {'ok': False, 'error': 'You do not have access to this.'}, status=403)
        try:
            customer = request.env['res.users'].mart369_admin_profile(user_id)
        except AccessError as exc:
            return request.make_json_response({'ok': False, 'error': str(exc)}, status=403)
        except UserError as exc:
            return request.make_json_response({'ok': False, 'error': str(exc)}, status=404)
        return request.make_json_response({'ok': True, 'customer': customer})
