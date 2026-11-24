"""The details page of a number: is everything on it the same number?
(24 Nov 2026). It only warns; nothing is refused."""
import re

from odoo import _, api, fields, models


def _digits(text):
    return ''.join(c for c in (text or '') if c.isdigit())


def _same(one, two):
    return one == two or (min(len(one), len(two)) >= 9 and one[-9:] == two[-9:])


class WhatsAppSessionPage(models.Model):
    _inherit = 'whatsapp.session'

    number_mismatch = fields.Text(compute='_compute_number_mismatch', compute_sudo=True, groups='base.group_system')

    def _other_numbers(self):
        """[(what it is, number)] that should be this session's number. Hook."""
        self.ensure_one()
        named = re.search(r'(?<!\d)\d{10,15}$', self.instance_name or '')
        return [(_("Instance"), named.group() if named else ''), (_("Connected Phone"), _digits(self.phone_number))]

    @api.depends('instance_name', 'phone_number', 'authorized_number')
    def _compute_number_mismatch(self):
        pretty = self.env['whatsapp.connect']._pretty
        for rec in self:
            own = _digits(rec.authorized_number)
            other = [(what, number) for what, number in rec._other_numbers() if number and not _same(number, own)] if own else []
            rec.number_mismatch = _(
                "This number is %(own)s, but %(other)s. Check which one is meant before scanning.",
                own=pretty(own), other=', '.join('%s: %s' % (what, pretty(number)) for what, number in other)) if other else False
