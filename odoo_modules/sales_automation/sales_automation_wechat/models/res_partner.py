# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartnerWeChat(models.Model):
    _inherit = 'res.partner'

    sa_via_whatsapp = fields.Boolean(
        'Ask on WhatsApp', default=False,
        help="Price checks go to this vendor's phone on WhatsApp.")
    sa_via_wechat = fields.Boolean(
        'Ask on WeChat', default=False,
        help="Price checks go to this vendor's WeChat contact through the bridge PC.")
    sa_wechat_name = fields.Char(
        'WeChat contact remark', index=True,
        help="Exactly the remark (备注) this vendor has in the shop's WeChat contact "
             "list. The bridge sends to that name, so it must match to the letter.")
    sa_channel = fields.Selection([
        ('none', 'Not asked'), ('whatsapp', 'WhatsApp'), ('wechat', 'WeChat'), ('both', 'WhatsApp and WeChat'),
    ], 'Price checks via', compute='_compute_sa_channel', store=True)

    @api.depends('sa_via_whatsapp', 'sa_via_wechat')
    def _compute_sa_channel(self):
        for p in self:
            p.sa_channel = ('both' if (p.sa_via_whatsapp and p.sa_via_wechat)
                            else 'wechat' if p.sa_via_wechat
                            else 'whatsapp' if p.sa_via_whatsapp else 'none')

    @api.model
    def _sa_default_ticks(self, country):
        """China → WeChat, anywhere else → WhatsApp."""
        if country and (country.code or '').upper() == 'CN':
            return {'sa_via_whatsapp': False, 'sa_via_wechat': True}
        return {'sa_via_whatsapp': True, 'sa_via_wechat': False}

    @api.onchange('country_id')
    def _onchange_country_sa_ticks(self):
        for p in self:
            if not p.sa_via_whatsapp and not p.sa_via_wechat:
                p.update(self._sa_default_ticks(p.country_id))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'sa_via_whatsapp' not in vals and 'sa_via_wechat' not in vals:
                country = self.env['res.country'].browse(vals.get('country_id') or 0) if vals.get('country_id') else None
                vals.update(self._sa_default_ticks(country))
        return super().create(vals_list)

    @api.constrains('sa_wechat_name')
    def _check_wechat_name_unique(self):
        for p in self.filtered('sa_wechat_name'):
            name = p.sa_wechat_name.strip()
            other = self.search([('id', '!=', p.id), ('sa_wechat_name', '=ilike', name)], limit=1)
            if other:
                raise ValidationError(_("The WeChat remark %(name)s is already used by %(who)s.",
                                        name=name, who=other.display_name))

    def _sa_wechat_reachable(self):
        self.ensure_one()
        return bool(self.sa_via_wechat and (self.sa_wechat_name or '').strip())

    def _sa_whatsapp_reachable(self):
        self.ensure_one()
        return bool(self.sa_via_whatsapp and (self.phone or '').strip())

    def _sa_sourcing_reachable(self):
        """Used by sales_automation's `_sourcing_vendors`: any ticked channel
        that can actually be used."""
        self.ensure_one()
        return self._sa_whatsapp_reachable() or self._sa_wechat_reachable()
