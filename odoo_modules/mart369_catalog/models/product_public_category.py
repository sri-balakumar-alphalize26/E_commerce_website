"""A 369 Mart category.

No new model: the app's categories are Odoo's own ``product.public.category``,
which already has a parent, a sequence and a product list. What Odoo has no
opinion about is how the app *draws* a category - the pale background behind
the tiles, the ink colour of its heading, the one-line blurb under the title -
so those are added here.

The storefront addresses categories by slug ("fruits-vegetables"), not by id,
because the slug is in the URL the customer sees. Every category therefore gets
one, derived from its name unless an operator sets it, and it has to be unique.

A category with no children is still a category: the app shows "Launching soon"
for Fashion and Books, which have no products yet.
"""

import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.mart369.models.serializers import slugify

# Which of the app's two storefronts a category belongs to. Quick is the
# 10-minute grocery run; Express is everything that ships over days.
MODE_CHOICES = [
    ('quick', 'Quick'),
    ('all', 'Express'),
]


class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    mart_slug = fields.Char(
        string='App address', index=True, copy=False,
        help="How the app addresses this category in a URL, e.g. "
             "fruits-vegetables. Filled in from the name if left empty. "
             "Changing it breaks any link a customer has saved.")
    mart_in_app = fields.Boolean(
        string='Show in the app', default=True,
        help="Off: Odoo keeps the category, the 369 Mart app does not show it.")
    mart_mode = fields.Selection(
        MODE_CHOICES, string='Storefront', default='quick',
        help="Quick is the 10-minute grocery run, Express is everything that "
             "ships over days. Set on the top-level category; children follow it.")
    mart_tone = fields.Char(
        string='Background', default='#f4f6f8',
        help="The pale colour behind this category's page, e.g. #e8f5e9.")
    mart_accent = fields.Char(
        string='Heading colour', default='#0b4a6e',
        help="The ink colour for the category's title, e.g. #1f7a4c.")
    mart_blurb = fields.Char(
        string='One-line description',
        help="Sits under the title on the category page, e.g. "
             "Farm-fresh produce, picked daily.")

    mart_product_count = fields.Integer(
        string='Products in the app', compute='_compute_mart_product_count',
        help="Published products in this category and everything under it.")

    # Odoo 19 dropped _sql_constraints; a list here is ignored with only a
    # warning in the log, so the constraint would never reach Postgres.
    _mart_slug_uniq = models.Constraint(
        'unique (mart_slug)',
        'Two categories cannot share the same app address.',
    )

    # ------------------------------------------------------------- the slug

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('mart_slug') and vals.get('name'):
                vals['mart_slug'] = self._mart369_free_slug(vals['name'])
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        # Renaming a category that never had a slug gives it one; a category
        # that already has one keeps it, because customers may have the link.
        for category in self:
            if not category.mart_slug and category.name:
                category.mart_slug = category._mart369_free_slug(category.name)
        return res

    @api.model
    def _mart369_free_slug(self, name, ignore=None):
        """'Fresh Fruits' -> 'fresh-fruits', or 'fresh-fruits-2' if taken."""
        base = slugify(name) or 'category'
        candidate, n = base, 1
        while True:
            domain = [('mart_slug', '=', candidate)]
            if ignore:
                domain.append(('id', '!=', ignore))
            if not self.sudo().with_context(active_test=False).search_count(domain):
                return candidate
            n += 1
            candidate = '%s-%d' % (base, n)

    @api.constrains('mart_slug')
    def _check_mart_slug(self):
        for category in self:
            if category.mart_slug and slugify(category.mart_slug) != category.mart_slug:
                raise ValidationError(self.env._(
                    "An app address may only use lowercase letters, numbers and "
                    "hyphens. '%s' does not.", category.mart_slug))

    def _compute_mart_product_count(self):
        for category in self:
            category.mart_product_count = self.env['product.template'].sudo().search_count(
                category._mart369_product_domain())

    # -------------------------------------------------------------- reading

    def _mart369_mode(self):
        """A child inherits the storefront of its top-most parent."""
        self.ensure_one()
        top = self
        while top.parent_id:
            top = top.parent_id
        return top.mart_mode or 'quick'

    def _mart369_product_domain(self):
        """Published products in this category or any category beneath it."""
        self.ensure_one()
        return [
            ('is_published', '=', True),
            ('public_categ_ids', 'child_of', self.id),
        ]

    def _mart369_children(self):
        """The sub-categories the app should list, in the operator's order."""
        self.ensure_one()
        return self.child_id.filtered('mart_in_app').sorted(
            key=lambda c: (c.sequence, c.id))

    def _mart369_serialize(self, with_subs=True):
        """One node of the tree the app draws.

        Matches the shape of CATALOG in components/home/catalog.js, so the
        category pages need no change: slug, name, mode, tone, accent, blurb
        and an ordered list of subs.
        """
        self.ensure_one()
        node = {
            'slug': self.mart_slug or '',
            'name': self.name or '',
            'mode': self._mart369_mode(),
            'tone': self.mart_tone or '',
            'accent': self.mart_accent or '',
            'blurb': self.mart_blurb or '',
        }
        if with_subs:
            node['subs'] = [child._mart369_serialize(with_subs=False)
                            for child in self._mart369_children()]
        return node

    # ------------------------------------------------------- the staff screen

    ADMIN_TABS = ('all', 'live', 'hidden', 'empty')

    # What either screen may write, and nothing else. Name and `mart_slug` are
    # not here on purpose: the slug is a URL a customer may have saved, and the
    # name is Odoo's own field that the catalogue, the product pages and the
    # reports all lean on. Both belong in the Odoo form, which is still one
    # click away under "Catalog (all views)".
    ADMIN_FIELDS = ('mart_in_app', 'mart_mode', 'mart_blurb',
                    'mart_tone', 'mart_accent')

    @api.model
    def mart369_admin_list(self, tab='all', mode='', q='', limit=300):
        """The rows and the tiles in one call, filtered on the server.

        Read by both the app console (over /369mart/admin/categories) and the
        backend desk (over the ORM), so the two cannot drift.
        """
        domain = []
        if tab == 'live':
            domain = [('mart_in_app', '=', True)]
        elif tab == 'hidden':
            domain = [('mart_in_app', '=', False)]
        q = (q or '').strip()
        if q:
            domain = domain + ['|', ('name', 'ilike', q), ('mart_slug', 'ilike', q)]

        rows = self.search(domain, limit=limit)
        if mode in ('quick', 'all'):
            # Filtered here rather than in the domain because a child's
            # storefront is its top-level parent's, which no domain can see.
            rows = rows.filtered(lambda c: c._mart369_mode() == mode)
        if tab == 'empty':
            rows = rows.filtered(lambda c: not c.mart_product_count)

        everything = self.search([])
        live = everything.filtered('mart_in_app')
        empty = everything.filtered(lambda c: not c.mart_product_count)
        return {
            'rows': [row._mart369_admin_row() for row in rows],
            'counts': {
                'all': len(everything),
                'live': len(live),
                'hidden': len(everything) - len(live),
                'empty': len(empty),
            },
            'tiles': {
                'live': len(live),
                'hidden': len(everything) - len(live),
                'empty': len(empty),
                # Products a shopper can actually reach, counted once: summing
                # every category's own count would count a product in three
                # categories three times.
                'products': self.env['product.template'].sudo().search_count([
                    ('is_published', '=', True),
                    ('public_categ_ids', 'in', live.ids),
                ]) if live else 0,
            },
        }

    def _mart369_admin_row(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name or '',
            'slug': self.mart_slug or '',
            'parent': self.parent_id.name or '',
            # `mode` is what the app really uses - a child's is its top-level
            # parent's. `ownMode` is what this record holds, so the screen can
            # tell the two apart instead of showing a setting that does nothing.
            'mode': self._mart369_mode(),
            'ownMode': self.mart_mode or '',
            'topLevel': not self.parent_id,
            'tone': self.mart_tone or '',
            'accent': self.mart_accent or '',
            'blurb': self.mart_blurb or '',
            'products': self.mart_product_count,
            'children': len(self.child_id),
            'inApp': self.mart_in_app,
        }

    def mart369_admin_write(self, values):
        """Change how the app draws this category.

        Allow-listed to `ADMIN_FIELDS`. Not sudo'd: core grants the website
        designer write on `product.public.category`, so Odoo's own rules do
        the refusing.
        """
        self.ensure_one()
        clean = {k: v for k, v in (values or {}).items() if k in self.ADMIN_FIELDS}
        if not clean:
            raise UserError(self.env._("There is nothing here to change."))

        if 'mart_mode' in clean:
            if self.parent_id:
                # Writing it would store a value the app never reads, and the
                # screen would then show a storefront this category is not in.
                raise UserError(self.env._(
                    "\"%(name)s\" follows \"%(parent)s\". Change the storefront "
                    "on the top-level category instead.",
                    name=self.name, parent=self.parent_id.name))
            if clean['mart_mode'] not in dict(MODE_CHOICES):
                raise UserError(self.env._("That is not one of the storefronts."))

        for key in ('mart_tone', 'mart_accent'):
            if key in clean:
                clean[key] = self._mart369_check_colour(clean[key])

        if 'mart_in_app' in clean:
            clean['mart_in_app'] = bool(clean['mart_in_app'])

        self.write(clean)
        return self._mart369_admin_row()

    @api.model
    def _mart369_check_colour(self, value):
        """A colour the app can actually paint with.

        The storefront drops these straight into CSS, so anything that is not
        a hex colour is a silently broken category page rather than an error
        anybody sees.
        """
        value = (value or '').strip()
        if not value:
            return ''
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise UserError(self.env._(
                "A colour looks like #e8f5e9. '%s' does not.", value))
        return value.lower()
