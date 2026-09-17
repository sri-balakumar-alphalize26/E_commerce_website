"""Payments, saved methods and the 369 Wallet, for the signed-in customer.

Same shape as mart369_address's routes: type='http' answering bare JSON, called by
the storefront's own server rather than straight from a browser.

The rule that matters here is the same one: a customer may only ever touch their
own saved method, their own wallet and their own payment. Every route goes through
_own_token() or _own_tx(), and both come back empty for anyone else's id - so
guessing an id gets a 404, not somebody else's card.

Nothing in here accepts a card number. Saving a card opens a validation transaction
and the provider's own form does the tokenising; a body carrying a number or a CVV
is refused outright.
"""

import logging

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'], 'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'], 'csrf': False, 'sitemap': False}
_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['PATCH'], 'csrf': False, 'sitemap': False}
_DELETE = {'type': 'http', 'auth': 'user', 'methods': ['DELETE'], 'csrf': False, 'sitemap': False}

# Keys that would mean the browser is trying to hand us a card. Refused loudly,
# so a well-meaning change to the app cannot quietly start posting one.
_FORBIDDEN = ('num', 'number', 'card', 'cardnum', 'card_number', 'pan', 'cvv', 'cvc')


class Mart369PaymentApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:
            data = None
        return data if isinstance(data, dict) else {}

    def _fail(self, error, field=None, status=400):
        payload = {'ok': False, 'error': error}
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _me(self):
        return request.env.user.partner_id

    def _own_token(self, tid):
        """One saved method, but only if it is this customer's.

        Anything else - another customer's card, an archived one, a made-up id,
        something that is not a number at all - comes back empty and the caller
        answers 404. sudo() on the browse is deliberate: a record rule raising
        AccessError would surface as a 403 and confirm the id exists.
        """
        empty = request.env['payment.token'].browse()
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            return empty
        token = request.env['payment.token'].sudo().with_context(
            active_test=False).browse(tid).exists()
        if not token or token.partner_id != self._me():
            return empty
        return token

    def _wallet(self):
        return request.env['loyalty.card']._mart369_wallet(self._me())

    def _own_tx(self, reference):
        """One payment, but only if it is this customer's.

        Keyed by reference rather than id: that is what the app holds, and it is
        unguessable in a way a sequential id is not. Same rule as everywhere else -
        empty recordset out, 404 from the caller.
        """
        empty = request.env['payment.transaction'].browse()
        if not reference or not isinstance(reference, str):
            return empty
        tx = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
        ], limit=1)
        if not tx or tx.partner_id != self._me():
            return empty
        return tx

    def _methods(self):
        """Both lists, in the shape `369mart.payments` already holds."""
        tokens = request.env['payment.token'].sudo().search([
            ('partner_id', '=', self._me().id),
            ('active', '=', True),
        ], order='mart369_default desc, id asc')
        cards = tokens.filtered(lambda t: t.mart369_kind == 'card')
        upis = tokens.filtered(lambda t: t.mart369_kind == 'upi')
        return {
            'ok': True,
            'cards': [t._mart369_serialize() for t in cards],
            'upis': [t._mart369_serialize() for t in upis],
        }

    # -------------------------------------------------------- saved methods

    @http.route('/369mart/payment/methods', **_GET)
    def methods(self, **kwargs):
        return self._json(self._methods())

    @http.route('/369mart/payment/methods/upi', **_POST)
    def add_upi(self, **kwargs):
        body = self._body()
        Token = request.env['payment.token']
        ok, vpa = Token._mart369_check_vpa(body.get('vpa'))
        if not ok:
            return self._fail(vpa, 'vpa')

        existing = Token.sudo().search([
            ('partner_id', '=', self._me().id),
            ('mart369_vpa', '=', vpa),
            ('active', '=', True),
        ], limit=1)
        if existing:
            return self._fail(_("This UPI ID is already saved."), 'vpa')

        method = request.env.ref('payment.payment_method_upi', raise_if_not_found=False)
        provider = request.env['payment.provider'].sudo().search([
            ('state', '!=', 'disabled'),
        ], order='sequence asc', limit=1)
        if not provider or not method:
            return self._fail(_("No payment provider is set up yet."), status=400)

        token = Token.sudo().create({
            'provider_id': provider.id,
            'payment_method_id': method.id,
            'partner_id': self._me().id,
            'payment_details': vpa,
            'provider_ref': vpa,
            'mart369_vpa': vpa,
            'mart369_upi_app': Token._mart369_upi_app_from_vpa(vpa),
            'mart369_holder': self._me().name or '',
        })
        if not Token.sudo().search_count([
            ('partner_id', '=', self._me().id),
            ('mart369_kind', '=', 'upi'),
            ('mart369_default', '=', True),
        ]):
            token._mart369_set_default()

        payload = {'ok': True, 'upi': token._mart369_serialize()}
        payload.update({k: v for k, v in self._methods().items() if k != 'ok'})
        return self._json(payload, status=201)

    @http.route('/369mart/payment/methods/card', **_POST)
    def add_card(self, **kwargs):
        """Start saving a card. The number never comes here.

        The app's own form keeps its markup; it just stops being where the card
        is typed. The provider renders its field, tokenises, and we keep the
        brand and last four it hands back.
        """
        body = self._body()
        if any(key in body for key in _FORBIDDEN):
            _logger.warning('mart369: a card number was posted to the API and refused')
            return self._fail(
                _("Card details must be entered on the payment form, not sent to us."),
                status=400)
        return self._fail(
            _("Saving a card needs a card provider. None is set up yet."), status=400)

    @http.route('/369mart/payment/methods/<int:tid>', **_PATCH)
    def update_method(self, tid, **kwargs):
        token = self._own_token(tid)
        if not token:
            return self._fail(_("No such payment method."), status=404)
        body = self._body()
        if not body.get('default'):
            return self._fail(_("Only the chosen payment method can be changed here."))
        token._mart369_set_default()
        return self._json(self._methods())

    @http.route('/369mart/payment/methods/<int:tid>', **_DELETE)
    def remove_method(self, tid, **kwargs):
        token = self._own_token(tid)
        if not token:
            return self._fail(_("No such payment method."), status=404)
        was_default, kind = token.mart369_default, token.mart369_kind
        # Archive rather than delete: past payments still point here.
        token.sudo().write({'active': False, 'mart369_default': False})
        if was_default:
            remaining = request.env['payment.token'].sudo().search([
                ('partner_id', '=', self._me().id),
                ('mart369_kind', '=', kind),
                ('active', '=', True),
            ], limit=1)
            if remaining:
                remaining._mart369_set_default()
        return self._json(self._methods())

    # --------------------------------------------------------------- wallet

    @http.route('/369mart/wallet', **_GET)
    def wallet(self, **kwargs):
        card = self._wallet()
        try:
            limit = int(kwargs.get('limit') or 200)
        except (TypeError, ValueError):
            limit = 200
        rows = card._mart369_ledger(limit=min(max(limit, 1), 200), before=kwargs.get('before'))
        return self._json({
            'ok': True,
            'balance': card._mart369_balance(),
            'limit': request.env['loyalty.card']._mart369_limit(),
            'min_topup': request.env['loyalty.card']._mart369_topup_min(),
            'ledger': [r._mart369_serialize() for r in rows],
        })

    @http.route('/369mart/wallet/topup', **_POST)
    def topup(self, **kwargs):
        """Start adding money. Nothing is credited here.

        The app's own top-up is a setTimeout that succeeds unconditionally
        (AccountExtras.jsx:144) - the money appears without anyone being charged.
        Here the balance does not move until the provider confirms, in
        _mart369_credit_wallet.
        """
        body = self._body()
        Card = request.env['loyalty.card']
        card = self._wallet()
        currency = card.currency_id or request.env.company.currency_id

        try:
            amount = currency.round(float(body.get('amount')))
        except (TypeError, ValueError):
            return self._fail(_("Enter an amount."), 'amount')

        minimum = Card._mart369_topup_min()
        if currency.compare_amounts(amount, minimum) < 0:
            return self._fail(_("Add at least %s.", currency.format(minimum)), 'amount')

        limit = Card._mart369_limit()
        room = limit - card.points
        if currency.compare_amounts(amount, room) > 0:
            return self._fail(_(
                "You can add up to %(room)s (wallet limit %(limit)s).",
                room=currency.format(max(0.0, room)), limit=currency.format(limit)), 'amount')

        provider = request.env['payment.provider']._mart369_provider_for(
            body.get('method') or 'upi', self._me(), amount, currency)
        if not provider:
            return self._fail(_("No payment provider is set up yet."))

        tx = self._create_tx(provider, amount, currency, kind='topup', card=card)
        return self._json({
            'ok': True,
            'reference': tx.reference,
            'txn': tx.mart369_txn,
            'state': tx.state,
            'balance': card._mart369_balance(),
        }, status=201)

    @http.route('/369mart/wallet/topup/<string:reference>', **_GET)
    def topup_status(self, reference, **kwargs):
        tx = self._own_tx(reference)
        if not tx or tx.mart369_kind != 'topup':
            return self._fail(_("No such top-up."), status=404)
        card = tx.mart369_wallet_card_id or self._wallet()
        entry = tx.mart369_history_id
        return self._json({
            'ok': True,
            'state': tx.state,
            'balance': card._mart369_balance(),
            'entry': entry._mart369_serialize() if entry else None,
        })

    # -------------------------------------------------------------- payment

    def _create_tx(self, provider, amount, currency, kind='order',
                   card=None, token=None, order_ref=None, wallet_used=0.0,
                   client_priced=False):
        """One place where a transaction is made, so the fields cannot drift."""
        method = provider.payment_method_ids[:1]
        values = {
            'provider_id': provider.id,
            'payment_method_id': method.id,
            'partner_id': self._me().id,
            'amount': amount,
            'currency_id': currency.id,
            'operation': 'online_token' if token else 'online_direct',
            'mart369_kind': kind,
            'mart369_order_ref': order_ref or False,
            'mart369_wallet_card_id': card.id if card else False,
            'mart369_wallet_used': wallet_used,
            'mart369_amount_client': client_priced,
        }
        if token:
            values['token_id'] = token.id
        return request.env['payment.transaction'].sudo().create(values)

    @http.route('/369mart/payment/pay', **_POST)
    def pay(self, **kwargs):
        """Take a payment for a basket.

        The order of operations is the point. The app writes the order and *then*
        debits the wallet (Home.jsx:441 and :443), so a crash between the two lines
        is a free order - and because the browser decides how much wallet it used,
        it can also claim a balance it does not have to drag the remainder under the
        cash-on-delivery limit.

        Here the wallet is debited first, inside one transaction, and it raises
        rather than clamping. Whatever is left is what the gateway is asked for, and
        what a cash payment is measured against.
        """
        body = self._body()
        if any(key in body for key in _FORBIDDEN):
            _logger.warning('mart369: a card number was posted to /pay and refused')
            return self._fail(
                _("Card details must be entered on the payment form, not sent to us."))

        method = body.get('method')
        if method not in ('upi', 'card', 'netbanking', 'cod', 'wallet'):
            return self._fail(_("Choose how you want to pay."), 'method')

        card = self._wallet()
        currency = card.currency_id or request.env.company.currency_id
        Tx = request.env['payment.transaction']
        try:
            gross, client_priced = Tx._mart369_amount_for(
                body.get('order_ref'), body.get('amount'), currency)
        except UserError as exc:
            return self._fail(str(exc), 'amount')

        # 1. The wallet leg, first and for real.
        wallet_used = 0.0
        if body.get('wallet_use') or method == 'wallet':
            wallet_used = min(card._mart369_balance(), gross)
            wallet_used = currency.round(wallet_used)

        payable = currency.round(gross - wallet_used)

        token = None
        if body.get('token_id'):
            token = self._own_token(body.get('token_id'))
            if not token:
                return self._fail(_("No such payment method."), status=404)

        # 2. Who takes the rest. Asked before any money moves, so a basket that
        #    cannot be paid for does not leave the wallet short.
        provider = request.env['payment.provider']
        if currency.is_zero(payable):
            settle_provider = request.env.ref(
                'mart369_payment.payment_provider_wallet', raise_if_not_found=False)
            if not settle_provider or settle_provider.state == 'disabled':
                return self._fail(_("The 369 Wallet is not switched on yet."))
            provider = settle_provider
        else:
            provider = provider._mart369_provider_for(method, self._me(), payable, currency)
            if not provider:
                if method == 'cod':
                    return self._fail(_(
                        "Cash on delivery is available on orders up to %s.",
                        currency.format(
                            request.env.ref('delivery.payment_provider_cod').maximum_amount)))
                return self._fail(_("That way of paying is not available right now."), 'method')

        # 3. Move the wallet money, then record the payment. Same request, so a
        #    failure anywhere rolls both back.
        try:
            if wallet_used:
                card._mart369_move(
                    wallet_used, 'spend', _("Order"),
                    sub=_("Order #%s", body.get('order_ref') or ''))
        except UserError as exc:
            return self._fail(str(exc), 'wallet')

        tx = self._create_tx(
            provider, payable or wallet_used, currency,
            kind='order', card=card, token=token,
            order_ref=body.get('order_ref'), wallet_used=wallet_used,
            client_priced=client_priced)

        if currency.is_zero(payable):
            # Nothing external to confirm: the ledger row is the settlement.
            tx._set_done(state_message=_("Paid from the 369 Wallet."))
            tx._post_process()
        else:
            tx._set_pending()

        payload = {
            'ok': True,
            'reference': tx.reference,
            'txn': tx.mart369_txn,
            'state': tx.state,
            'wallet_used': wallet_used,
            'payable': payable,
        }
        return self._json(payload, status=201)

    @http.route('/369mart/payment/status/<string:reference>', **_GET)
    def status(self, reference, **kwargs):
        tx = self._own_tx(reference)
        if not tx:
            return self._fail(_("No such payment."), status=404)
        payload = tx._mart369_serialize()
        return self._json(payload, status=200 if payload.get('ok') else 200)

    @http.route('/369mart/payment/<string:reference>/cancel', **_POST)
    def cancel(self, reference, **kwargs):
        tx = self._own_tx(reference)
        if not tx:
            return self._fail(_("No such payment."), status=404)
        if tx.state == 'done':
            return self._fail(_("This payment has already gone through."), status=409)
        tx._set_canceled(state_message=_("Cancelled by the customer."))
        tx._post_process()
        return self._json({'ok': True})
