import base64
import io
import zipfile
from odoo import models, fields, _
from odoo.exceptions import UserError


class LoyaltyCardImageDownloadWizard(models.TransientModel):
    _name = 'pos.loyalty.card.image.download.wizard'
    _description = 'Download Loyalty Card Images as ZIP'

    mode = fields.Selection([
        ('all', 'All images'),
        ('card', 'By card number'),
        ('date', 'By date range'),
    ], string='Download', default='all', required=True)
    card_id = fields.Many2one('pos.loyalty.card', string='Loyalty Card')
    date_from = fields.Date(string='From')
    date_to = fields.Date(string='To')

    def action_download(self):
        self.ensure_one()
        Image = self.env['pos.loyalty.card.image']
        domain = []
        fname_part = 'all'
        if self.mode == 'card':
            if not self.card_id:
                raise UserError(_('Please choose a loyalty card.'))
            domain = [('card_id', '=', self.card_id.id)]
            fname_part = (self.card_id.card_number or 'card').replace('/', '-')
        elif self.mode == 'date':
            if not self.date_from or not self.date_to:
                raise UserError(_('Please choose both From and To dates.'))
            domain = [('snapshot_day', '>=', self.date_from), ('snapshot_day', '<=', self.date_to)]
            fname_part = '%s_to_%s' % (self.date_from, self.date_to)

        records = Image.search(domain, order='card_number, create_date')
        if not records:
            raise UserError(_('No card images found for this selection.'))

        buf = io.BytesIO()
        seen = {}
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rec in records:
                if not rec.image:
                    continue
                day = rec.create_date.strftime('%Y-%m-%d') if rec.create_date else 'nodate'
                name = '%s_%s' % (rec.card_number or 'card', day)
                seen[name] = seen.get(name, 0) + 1
                if seen[name] > 1:
                    name = '%s_%d' % (name, seen[name])
                zf.writestr(name + '.png', base64.b64decode(rec.image))

        attachment = self.env['ir.attachment'].create({
            'name': 'loyalty_cards_%s.zip' % fname_part,
            'datas': base64.b64encode(buf.getvalue()),
            'mimetype': 'application/zip',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
