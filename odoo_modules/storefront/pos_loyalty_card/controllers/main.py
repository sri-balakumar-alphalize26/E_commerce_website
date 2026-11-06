from odoo import http
from odoo.http import request


class LoyaltyCardController(http.Controller):

    @http.route('/loyalty_card/view/<int:card_id>', type='http', auth='user')
    def loyalty_card_view(self, card_id, **kw):
        """Render a centered, on-screen view of a loyalty card with a Print button."""
        card = request.env['pos.loyalty.card'].browse(card_id).exists()
        if not card:
            return request.not_found()
        cfg = request.env['pos.loyalty.card.settings'].get_settings()
        html = request.env['ir.qweb']._render('pos_loyalty_card.card_view_page', {
            'o': card,
            'docs': card,
            'cfg': cfg,
        })
        return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')])
