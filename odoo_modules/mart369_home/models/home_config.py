import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class Mart369HomeConfig(models.Model):
    """The home page's own settings, added to the shared ones.

    `image_base_url`, `cache_seconds` and `_get()` live on `mart369.config` in
    the base module, because the cart, the catalogue and the product page read
    them too. What is left here is genuinely about home pages.
    """

    _inherit = 'mart369.config'

    mode_ids = fields.One2many(
        'mart369.home.mode', 'config_id', string='App Modes',
        help='The two tabs at the top of the app: Quick (delivery in minutes) '
             'and Express. Each one has its own banners, tiles and sections.')

    # ── How the app reaches the images ──
    # ── Defaults and behaviour ──
    default_rail_limit = fields.Integer(
        string='Products per row', default=12,
        help='How many products a new row shows before the customer scrolls. '
             'Each row can override this.')
    trash_days = fields.Integer(
        string='Keep removed items for (days)', default=30,
        help='Removing a banner, tile, tab, row or a whole saved page puts '
             'it in the Trash instead of destroying it. This is how long it '
             'waits there before it is deleted for good. 0 means keep '
             'forever.')

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
                      'mart369.home.tile', 'mart369.home.tab',
                      'mart369.home.version'):
            records = self.env[model].with_context(active_test=False).search(
                [('deleted_at', '!=', False), ('deleted_at', '<', cutoff)])
            gone += len(records)
            records.unlink()
        if gone:
            _logger.info('369 Mart: emptied %s item(s) from the Trash', gone)
        return gone

    # ------------------------------------------------------------- serialise

    def _serialize_modes(self):
        """The whole payload: {'quick': {...}, 'all': {...}}.

        Served from whichever saved page is live: one that is inside its
        scheduled window, or the everyday one. Which is how a festival page
        takes over on time and hands back afterwards without anybody being
        awake for either.
        """
        self.ensure_one()
        version = self.env['mart369.home.version']._mart369_live()
        # A saved page with no modes would serve an empty home page. That can
        # only happen mid-upgrade, and a blank shop is never the right answer
        # to it - fall back to whatever the settings still hold.
        modes = version.mode_ids if version.mode_ids else self.mode_ids
        modes = modes.filtered('active').sorted('sequence')
        return {m.key: m._serialize() for m in modes}

    # --------------------------------------------------------------- buttons

    def action_open_api(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/369mart/home', 'target': 'new'}
