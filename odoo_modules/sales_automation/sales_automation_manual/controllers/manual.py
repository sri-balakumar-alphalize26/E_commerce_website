# -*- coding: utf-8 -*-
"""The user manual, served to logged-in users from the module's static folder."""
import os

from odoo import http
from odoo.http import request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_DIR = os.path.join(HERE, 'static', 'manual')


class SaManual(http.Controller):

    @http.route('/sa/manual', type='http', auth='user', website=False)
    def manual_page(self, **kw):
        path = os.path.join(MANUAL_DIR, 'User_Manual.html')
        with open(path, 'rb') as f:
            body = f.read()
        return request.make_response(body, headers=[('Content-Type', 'text/html; charset=utf-8'),
                                                    ('Cache-Control', 'no-cache')])

    @http.route('/sa/manual/flow', type='http', auth='user', website=False)
    def manual_flow(self, **kw):
        """FULL_FLOW.md as plain text (Markdown), for copying into a wiki or reading raw."""
        path = os.path.join(MANUAL_DIR, 'FULL_FLOW.md')
        if not os.path.exists(path):
            return request.not_found()
        with open(path, 'rb') as f:
            body = f.read()
        return request.make_response(body, headers=[('Content-Type', 'text/markdown; charset=utf-8'),
                                                    ('Content-Disposition', 'inline; filename="FULL_FLOW.md"')])

    @http.route('/sa/manual/pdf', type='http', auth='user', website=False)
    def manual_pdf(self, **kw):
        path = os.path.join(MANUAL_DIR, 'User_Manual.pdf')
        if not os.path.exists(path):
            return request.not_found()
        with open(path, 'rb') as f:
            body = f.read()
        return request.make_response(body, headers=[('Content-Type', 'application/pdf'),
                                                    ('Content-Disposition', 'attachment; filename="User_Manual.pdf"')])
