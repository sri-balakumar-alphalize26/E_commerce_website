import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class Mart369HomeConfig(models.Model):
    """The one settings record. Global switches plus the two app modes."""

    _name = 'mart369.home.config'
    _description = '369 Mart Home Page Settings'

    name = fields.Char(default='Home Page Settings', readonly=True)

    mode_ids = fields.One2many(
        'mart369.home.mode', 'config_id', string='App Modes',
        help='The two tabs at the top of the app: Quick (delivery in minutes) '
             'and Express. Each one has its own banners, tiles and sections.')

    # ── How the app reaches the images ──
    image_base_url = fields.Char(
        string='Image address',
        help='Leave this empty in almost every case: the app then gets short '
             'addresses like /web/image/... and loads them through itself.\n'
             'Only fill it in (e.g. https://shop.example.com) when the app '
             'cannot pass image requests through to Odoo.')

    # ── Defaults and behaviour ──
    default_rail_limit = fields.Integer(
        string='Products per row', default=12,
        help='How many products a new row shows before the customer scrolls. '
             'Each row can override this.')
    cache_seconds = fields.Integer(
        string='Remember for (seconds)', default=60,
        help='How long the app may reuse the last home page it fetched before '
             'asking again. 60 is a good balance. Set 0 while you are making '
             'changes and want to see them instantly.')
    trash_days = fields.Integer(
        string='Keep removed items for (days)', default=30,
        help='Removing a banner, tile, tab or row puts it in the Trash '
             'instead of destroying it. This is how long it waits there '
             'before it is deleted for good. 0 means keep forever.')

    hide_out_of_stock = fields.Boolean(
        string='Hide sold-out products', default=False,
        help='On: a product with no stock left never appears in a row. '
             'Off: it still appears, marked as sold out.')

    api_url_preview = fields.Char(
        string='The app reads from', compute='_compute_api_url_preview',
        help='Give this address to whoever sets up the app.')

    @api.depends('image_base_url')
    def _compute_api_url_preview(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for rec in self:
            rec.api_url_preview = '%s/369mart/home' % base

    def _trash_days(self):
        """How long the Trash keeps things. Callable on an empty recordset."""
        config = self if len(self) == 1 else self._get()
        days = config.trash_days
        return days if days and days > 0 else 0

    @api.model
    def _cron_purge_trash(self):
        """Empty the Trash of anything past its retention. Runs nightly.

        0 days means the operator asked to keep removed items indefinitely,
        so nothing is deleted.
        """
        keep = self._get()._trash_days()
        if not keep:
            return 0
        cutoff = fields.Datetime.now() - timedelta(days=keep)
        gone = 0
        for model in ('mart369.home.section', 'mart369.home.banner',
                      'mart369.home.tile', 'mart369.home.tab'):
            records = self.env[model].with_context(active_test=False).search(
                [('deleted_at', '!=', False), ('deleted_at', '<', cutoff)])
            gone += len(records)
            records.unlink()
        if gone:
            _logger.info('369 Mart: emptied %s item(s) from the Trash', gone)
        return gone

    @api.model
    def _get(self):
        """The settings record, created on first use."""
        rec = self.search([], limit=1)
        if not rec:
            rec = self.create({})
        return rec

    # ------------------------------------------------------------- serialise

    def _serialize_modes(self):
        """The whole payload: {'quick': {...}, 'all': {...}}."""
        self.ensure_one()
        modes = self.mode_ids.filtered('active').sorted('sequence')
        return {m.key: m._serialize() for m in modes}

    # --------------------------------------------------------------- buttons

    def action_open_api(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/369mart/home', 'target': 'new'}
