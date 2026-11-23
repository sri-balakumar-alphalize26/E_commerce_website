# -*- coding: utf-8 -*-
"""The page of a link whose week is over (models/sa_link_expiry.py)."""
from odoo import _
from odoo.exceptions import AccessError
from odoo.http import request

_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>%(t)s</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f6f8fa;color:#13212b;font:16px/1.5 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{margin:16px;padding:32px 24px;max-width:420px;background:#fff;border:1px solid #e6ebef;border-radius:16px;text-align:center}
i{display:block;font-style:normal;font-size:40px}h1{font-size:20px;margin:10px 0 6px}p{margin:0;color:#52616d}</style></head>
<body><main><i aria-hidden="true">&#8987;</i><h1>%(t)s</h1><p>%(p)s</p></main></body></html>"""


def expired_page():
    return request.make_response(
        _HTML % {'t': _("This link has expired"), 'p': _("Please write to us in WhatsApp if you need anything.")},
        status=410, headers=[('Content-Type', 'text/html; charset=utf-8'), ('Cache-Control', 'no-store')])


def visit_expired(order):
    """Is this visit to `order` by a link whose week is over? Never for our own
    people, nor for a customer logged in who may see the order anyway."""
    user = request.env.user
    if user._is_internal():
        return False
    if not user._is_public():
        try:
            order.sudo(False).with_user(user).check_access('read')
            return False
        except AccessError:
            pass
    return order._sa_link_expired()
