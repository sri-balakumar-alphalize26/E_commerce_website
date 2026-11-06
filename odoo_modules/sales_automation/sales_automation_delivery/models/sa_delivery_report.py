# -*- coding: utf-8 -*-
"""Delivery analysis - one read-only row per job."""

from odoo import fields, models, tools


class SaDeliveryReport(models.Model):
    _name = 'sa.delivery.report'
    _description = 'Delivery Analysis'
    _auto = False
    _rec_name = 'ref_code'
    _order = 'offered_on desc, id desc'

    ref_code = fields.Char('Job Code', readonly=True)
    picking_id = fields.Many2one('stock.picking', 'Delivery', readonly=True)
    order_id = fields.Many2one('sale.order', 'Order', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Customer', readonly=True)
    city = fields.Char('City', readonly=True)
    country_id = fields.Many2one('res.country', 'Country', readonly=True)

    shop_id = fields.Many2one('sa.delivery.shop', 'Shop', readonly=True)
    rider_id = fields.Many2one(
        'sa.delivery.partner', 'Rider / Courier', readonly=True)
    kind = fields.Selection([
        ('own', 'Own Rider'),
        ('third_party', 'Delivery Partner'),
    ], string='Carrier Kind', readonly=True)

    delivery_state = fields.Selection([
        ('none', 'Not a Delivery Job'),
        ('to_assign', 'To Dispatch'),
        ('offered', 'Offered'),
        ('accepted', 'Accepted'),
        ('picked', 'Picked Up'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ], string='Delivery Status', readonly=True)

    offered_on = fields.Datetime('Offered', readonly=True)
    accepted_on = fields.Datetime('Accepted', readonly=True)
    picked_on = fields.Datetime('Picked Up', readonly=True)
    delivered_on = fields.Datetime('Delivered', readonly=True)

    # Minutes, because a delivery that takes days is the exception and an
    # hours column would read 0 for most of them.
    minutes_to_accept = fields.Float('Mins to Accept', readonly=True,
                                     aggregator='avg')
    minutes_to_deliver = fields.Float('Mins to Deliver', readonly=True,
                                      aggregator='avg')

    amount_total = fields.Float('Order Total', readonly=True)
    cod_amount = fields.Float('Collected on Delivery', readonly=True)
    job_count = fields.Integer('Jobs', readonly=True, aggregator='sum')
    company_id = fields.Many2one('res.company', 'Company', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    p.id                        AS id,
                    p.id                        AS picking_id,
                    p.sa_ref_code               AS ref_code,
                    p.sale_id                   AS order_id,
                    p.partner_id                AS partner_id,
                    rp.city                     AS city,
                    rp.country_id               AS country_id,
                    p.sa_shop_id                AS shop_id,
                    p.sa_delivery_partner_id    AS rider_id,
                    dp.kind                     AS kind,
                    p.sa_delivery_state         AS delivery_state,
                    p.sa_offered_on             AS offered_on,
                    p.sa_accepted_on            AS accepted_on,
                    p.sa_picked_on              AS picked_on,
                    p.sa_delivered_on           AS delivered_on,
                    EXTRACT(EPOCH FROM (p.sa_accepted_on - p.sa_offered_on))
                        / 60.0                  AS minutes_to_accept,
                    EXTRACT(EPOCH FROM (p.sa_delivered_on - p.sa_offered_on))
                        / 60.0                  AS minutes_to_deliver,
                    COALESCE(so.amount_total, 0) AS amount_total,
                    CASE WHEN p.sa_delivery_state = 'delivered'
                         THEN COALESCE(p.sa_cod_amount, 0) ELSE 0 END
                                                AS cod_amount,
                    1                           AS job_count,
                    p.company_id                AS company_id
                FROM stock_picking p
                LEFT JOIN res_partner rp        ON rp.id = p.partner_id
                LEFT JOIN sa_delivery_partner dp ON dp.id = p.sa_delivery_partner_id
                LEFT JOIN sale_order so         ON so.id = p.sale_id
                WHERE p.sa_delivery_state IS NOT NULL
                  AND p.sa_delivery_state <> 'none'
            )
        """ % self._table)
