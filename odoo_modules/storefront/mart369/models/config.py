"""The settings every 369 Mart module shares.

One record, created on first use. It lived in `mart369_home` as
`mart369.home.config` while the home page was the foundation - but the cart,
the catalogue and the product page all read `cache_seconds` from it for their
Cache-Control headers, which meant three modules depended on the home page for
a number that has nothing to do with home pages.

Only the genuinely shared settings are here. `mart369_home` inherits this model
and adds its own - the app modes, the row length, the trash window - so the
settings screen simply shows more fields when the home page is installed.
"""

from odoo import api, fields, models, tools


class Mart369Config(models.Model):
    _name = 'mart369.config'
    _description = '369 Mart Settings'

    name = fields.Char(default='369 Mart Settings', readonly=True)

    image_base_url = fields.Char(
        string='Image address',
        help='Leave this empty in almost every case: the app then gets short '
             'addresses like /web/image/... and loads them through itself.\n'
             'Only fill it in (e.g. https://shop.example.com) when the app '
             'cannot pass image requests through to 369ai.')

    cache_seconds = fields.Integer(
        string='Remember for (seconds)', default=60,
        help='How long the app may reuse the last answer it fetched before '
             'asking again. 60 is a good balance. Set 0 while you are making '
             'changes and want to see them instantly.')

    @api.model
    def _get(self):
        """The settings record, created on first use."""
        rec = self.search([], limit=1)
        if not rec:
            rec = self.create({})
        return rec

    @api.model
    @tools.ormcache()
    def _image_base(self):
        """The Image address setting. Every picture address on every card asks
        for it, so it is read once rather than once per picture."""
        return self._get().image_base_url or ''

    def write(self, vals):
        result = super().write(vals)
        if 'image_base_url' in vals:
            self.env.registry.clear_cache()
        return result
