# -*- coding: utf-8 -*-
"""A doorway that binds a database before opening a customer's link.

A customer taps a link in WhatsApp with no Odoo session at all. This server
hosts two dozen databases with no `dbfilter`, so Odoo cannot tell which one the
request belongs to - and `/wa/pay`, `/wa/track` and `/wa/delivery` are
`auth='public'`, which means they are not in the no-database routing map
either. Werkzeug answers 404 before any of our code runs, and there is nowhere
on those URLs to put a `?db=` that would be read.

`dbfilter` is not the answer: twenty-three other databases share this server
and filtering to one would break every other tenant.

So the link points here instead:

    <base>/scoped_app/wa-link?db=res-test1&to=/wa/pay/402?method=upi&token=...

Round one: this module is not in `server_wide_modules`, so the request is
served by core's own `Home.web_client`, whose first act is `ensure_db()`. That
validates `?db=` against `db_filter` - so a database cannot be forged - stores
it on the session, and aborts with a 302 to the same URL.

Round two: the session now names a database, the request routes through that
database's registry where this override exists, and it 303s to the real target.

Two invisible redirects, no login screen, nothing in odoo.conf, and no other
database on the server is touched.

`/scoped_app/` rather than `/odoo/` because this is a link a customer reads on
their phone and the install is white-labelled: the vendor's name has no
business in it. Both paths reach the same handler.
"""

import re
from urllib.parse import parse_qsl, urlsplit

from werkzeug.urls import url_encode

from odoo import http
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import ensure_db
from odoo.http import request

ENTRY_SUBPATH = 'wa-link'
TARGET_PARAM = 'to'

# Consumed by us or by the route we are borrowing, so never copied onto the
# target's own query string.
RESERVED_PARAMS = ('db', TARGET_PARAM, 'subpath', 's_action')

# Where the doorway is willing to send a visitor. A redirect target taken from
# a URL is an open redirect unless it is checked, and an open redirect on our
# own domain is a phishing primitive - so this is a whitelist, matched against
# the PATH only. Anything else, including a protocol-relative "//evil.example"
# that urlsplit reads as a host rather than a path, fails to match and gets a
# 404.
ALLOWED_TARGETS = (
    re.compile(r'^/wa/pay/\d{1,12}$'),
    re.compile(r'^/wa/track/\d{1,12}$'),
    re.compile(r'^/wa/track/\d{1,12}/pos$'),
    re.compile(r'^/wa/delivery/\d{1,12}$'),
    re.compile(r'^/wa/delivery/\d{1,12}/[a-z_]{1,32}$'),
    # The shop typing a price in when no vendor answered.
    re.compile(r'^/wa/quote/\d{1,12}$'),
    re.compile(r'^/wa/quote/\d{1,12}/[a-z]{1,10}$'),
    # The customer signing the order on its portal page (`_sa_portal_link`),
    # and paying a confirmed order through Odoo's payment link
    # (`_sa_pay_link_any_state`). Both were sent through this doorway and
    # answered "Not Found" until they were listed here.
    re.compile(r'^/my/orders/\d{1,12}$'),
    re.compile(r'^/my/orders/\d{1,12}/[a-z_]{1,32}$'),
    re.compile(r'^/payment/pay$'),
    re.compile(r'^/payment/pay/[a-z_]{1,32}$'),
)


class WhatsAppLinkEntry(Home):
    """Bind the database, then hand the customer to the link they tapped."""

    @http.route()
    def web_client(self, s_action=None, **kw):
        if kw.get('subpath') != ENTRY_SUBPATH:
            return super().web_client(s_action=s_action, **kw)

        # Aborts with a 302 to this same URL the first time round; that is how
        # the session ends up carrying the database.
        ensure_db()
        if not request.db:
            # Unknown or filtered-out database. Say nothing about which.
            return request.not_found()

        # `to` arrives as a path with its own query string attached. Split it
        # and whitelist the path alone: urlsplit puts "//evil.example/x" in
        # .netloc, leaving .path as the innocent-looking "/x".
        target = urlsplit(kw.get(TARGET_PARAM) or '')
        if not any(rx.match(target.path) for rx in ALLOWED_TARGETS):
            return request.not_found()

        # The target's own parameters, plus any that ended up at the top level:
        # only the first survives inside `to`, because the "&" that separates
        # the second makes it a parameter of this URL instead.
        params = dict(parse_qsl(target.query))
        params.update({
            key: value
            for key, value in request.httprequest.args.items()
            if key not in RESERVED_PARAMS
        })

        # Rebuilt from the matched path, never echoed, so the redirect cannot
        # be steered off this host.
        url = target.path
        if params:
            url = '%s?%s' % (url, url_encode(params))
        return request.redirect(url, code=303)
