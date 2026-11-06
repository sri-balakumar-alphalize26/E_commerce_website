# -*- coding: utf-8 -*-
"""Which pincodes get Quick, which get Express."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaQeServiceArea(models.Model):
    _name = 'sa.qe.service.area'
    _description = 'Quick / Express Service Area'
    _order = 'pincode'
    _rec_name = 'pincode'

    pincode = fields.Char(
        'Pincode or its start', required=True,
        help="A whole pincode, or the first digits of one. The longest match "
             "wins, so 6820 beats 68.")
    name = fields.Char('Area')
    quick = fields.Boolean('Quick', default=True)
    express = fields.Boolean('Express', default=True)
    eta = fields.Char('Promise', default='13 mins',
                      help="What the customer in this area is told.")
    active = fields.Boolean(default=True)

    _pincode_uniq = models.Constraint(
        'unique(pincode)', 'That pincode already has an area.')

    @api.model
    def _qe_clean(self, pin):
        return ''.join((pin or '').split()).upper()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'pincode' in vals:
                vals['pincode'] = self._qe_clean(vals['pincode'])
        return super().create(vals_list)

    def write(self, vals):
        if 'pincode' in vals:
            vals['pincode'] = self._qe_clean(vals['pincode'])
        return super().write(vals)

    @api.constrains('pincode')
    def _check_pincode(self):
        for area in self:
            if not (area.pincode or '').isalnum():
                raise ValidationError(_("A pincode is letters and digits only."))

    @api.model
    def _qe_match(self, pin):
        """The area for `pin`: the longest stored prefix of it, or nothing."""
        pin = self._qe_clean(pin)
        if not pin:
            return self.browse()
        prefixes = [pin[:n] for n in range(len(pin), 0, -1)]
        areas = self.sudo().search([('pincode', 'in', prefixes)])
        if not areas:
            return self.browse()
        return max(areas, key=lambda a: len(a.pincode or ''))
