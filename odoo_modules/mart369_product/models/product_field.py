import operator as _op

from odoo import _, api, fields, models
from odoo.exceptions import UserError

OPERATORS = {
    '=': _op.eq, '!=': _op.ne, '>': _op.gt, '>=': _op.ge,
    '<': _op.lt, '<=': _op.le,
}

# How a field's value is obtained.
SOURCE = [
    ('odoo', 'A field on the product'),
    ('text', 'Text typed here'),
    ('computed', 'Worked out by the app'),
]

# What kind of value it is, so the right editor is offered.
VALUE_KIND = [
    ('text', 'One line'),
    ('lines', 'A list, one per line'),
    ('html', 'Rich text'),
    ('bool', 'Yes / no'),
]


class Mart369ProductField(models.Model):
    """One thing the product page can show, and whether it shows.

    `show` here is the **global** switch: the default for every product. A
    product deviates only where someone deliberately set it to Always show or
    Always hide - see mart369.product.override.
    """

    _name = 'mart369.product.field'
    _description = '369 Mart Product Page Field'
    _order = 'section_id, sequence, id'

    key = fields.Char(
        string='Key', required=True,
        help='The internal name, e.g. manufacturer_address. The app and the '
             'API use this. Leave it alone once the app is live.')
    name = fields.Char(
        string='Field', required=True, translate=True,
        help='The label the customer sees, e.g. Manufacturer address.')
    section_id = fields.Many2one(
        'mart369.product.section', string='Section',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(
        default=10,
        help='The order it appears in within its section.')

    show = fields.Boolean(
        string='Show by default', default=True,
        help='The setting for every product. A product can still be set to '
             'always show or always hide this, one by one.')

    source = fields.Selection(
        SOURCE, string='Value comes from', required=True, default='text',
        help='Where the value is read from when the field is shown.')
    odoo_field = fields.Char(
        string='Product field',
        help='Only for "a field on the product": the technical name, '
             'e.g. weight or default_code.')
    default_value = fields.Text(
        string='Default text', translate=True,
        help='Used for every product unless its category or the product '
             'itself says otherwise.')
    value_kind = fields.Selection(
        VALUE_KIND, string='Kind of value', required=True, default='text')

    per_product = fields.Boolean(
        string='Can differ per product', default=True,
        help='On: an employee can type a different value on one product. '
             'Off: only the default (or the category default) is ever used, '
             'though the field can still be hidden on a product.')

    note = fields.Char(
        string='What it is', translate=True,
        help='A short reminder for whoever is editing.')
    active = fields.Boolean(default=True)

    category_value_ids = fields.One2many(
        'mart369.product.category.value', 'field_id', string='By category')
    override_count = fields.Integer(
        string='Products differing', compute='_compute_override_count',
        search='_search_override_count',
        help='How many products were deliberately set to something other '
             'than the default for this field.')

    _key_uniq = models.Constraint('unique (key)', 'Two fields cannot share a key.')

    def _compute_override_count(self):
        Override = self.env['mart369.product.override']
        counts = dict(Override._read_group(
            [('field_id', 'in', self.ids), ('state', '!=', 'follow')],
            groupby=['field_id'], aggregates=['__count']))
        for rec in self:
            rec.override_count = counts.get(rec, 0)

    def _search_override_count(self, operator, value):
        """Let "some products differ" be a real filter.

        The count is worked out on the fly, so Odoo cannot search it without
        this: gather the fields that have any deviating product and answer in
        terms of ids.
        """
        rows = self.env['mart369.product.override']._read_group(
            [('state', '!=', 'follow')], groupby=['field_id'], aggregates=['__count'])
        counts = {field.id: count for field, count in rows}
        matched = [fid for fid, count in counts.items()
                   if OPERATORS[operator](count, value)]
        if operator in ('=', '>', '>=') and not (operator == '=' and not value):
            return [('id', 'in', matched)]
        # "no products differ" also means every field with no rows at all.
        return [('id', 'in', matched)] if matched else [('id', 'not in', list(counts))]

    def action_toggle_show(self):
        for rec in self:
            rec.show = not rec.show
        return True

    # ------------------------------------------------------------ resolving

    def _state_for(self, product, overrides=None):
        """'follow' / 'show' / 'hide' for this product."""
        self.ensure_one()
        row = (overrides or {}).get((product.id, self.id))
        if row is None:
            row = self.env['mart369.product.override'].search([
                ('product_tmpl_id', '=', product.id), ('field_id', '=', self.id),
            ], limit=1)
        return row.state if row else 'follow'

    def _visible_for(self, product, overrides=None):
        """Does the app show this field on this product?

        The section switch is a master: off means off, whatever anything else
        says. Otherwise the product's own choice wins, and "follow" falls back
        to the global default.
        """
        self.ensure_one()
        if not self.section_id.show:
            return False
        state = self._state_for(product, overrides)
        if state == 'show':
            return True
        if state == 'hide':
            return False
        return self.show

    def _value_for(self, product, overrides=None, category_values=None):
        """The value to show: the product's own, else its category's, else
        the global default (or the Odoo field it points at)."""
        self.ensure_one()

        row = (overrides or {}).get((product.id, self.id))
        if row is None:
            row = self.env['mart369.product.override'].search([
                ('product_tmpl_id', '=', product.id), ('field_id', '=', self.id),
            ], limit=1)
        if row and row.value:
            return row.value

        if self.source == 'odoo' and self.odoo_field:
            if self.odoo_field not in product._fields:
                return ''
            value = product[self.odoo_field]
            return value if value not in (None, False) else ''

        # A category the product belongs to may override the global default.
        cat_values = category_values
        if cat_values is None:
            cat_values = self._category_values(product)
        if self.id in cat_values:
            return cat_values[self.id]

        return self.default_value or ''

    def _category_values(self, product):
        """{field_id: value} from this product's categories.

        A product can sit in several categories; the deepest one wins, so a
        sub-category can refine what its parent set.
        """
        categories = product.public_categ_ids
        if not categories:
            return {}
        rows = self.env['mart369.product.category.value'].search([
            ('public_categ_id', 'in', categories.ids),
        ])
        depth = {c.id: len((c.parent_path or '').strip('/').split('/'))
                 for c in categories}
        best = {}
        for row in rows:
            d = depth.get(row.public_categ_id.id, 0)
            current = best.get(row.field_id.id)
            if current is None or d >= current[0]:
                best[row.field_id.id] = (d, row.value)
        return {fid: value for fid, (d, value) in best.items()}

    # --------------------------------------------------------------- the API

    @api.model
    def _resolve(self, product):
        """{field key: value} for exactly the fields this product shows.

        The one method both the API and the builder preview use, so what an
        employee sees on the mock is what a customer gets.
        """
        fields_all = self.search([])
        overrides = {
            (o.product_tmpl_id.id, o.field_id.id): o
            for o in self.env['mart369.product.override'].search(
                [('product_tmpl_id', '=', product.id)])
        }
        cat_values = fields_all[:1]._category_values(product) if fields_all else {}

        out = {}
        for field in fields_all:
            if not field._visible_for(product, overrides):
                continue
            out[field.key] = field._value_for(product, overrides, cat_values)
        return out

    # ------------------------------------------------------- the builder

    def _builder_row(self, product=None, overrides=None, cat_values=None,
                     cat_rows=None):
        """One field, as every screen that edits it sees it.

        Extracted so `builder_load` and the routes that write a single row
        answer with the same shape by construction. Two dicts that drift is
        how a panel starts showing one thing and saving another.
        """
        self.ensure_one()
        Page = self.env['mart369.product.page']
        row = {
            'id': self.id, 'key': self.key, 'name': self.name,
            'section_id': self.section_id.id,
            'sequence': self.sequence, 'show': self.show,
            'source': self.source, 'odoo_field': self.odoo_field or '',
            'default_value': self.default_value or '',
            'value_kind': self.value_kind, 'per_product': self.per_product,
            'note': self.note or '', 'override_count': self.override_count,
            'state': 'follow', 'visible': self.show, 'value': '',
            # The raw per-product wording. `value` above is run through
            # _as_text for display, so it is not what an editor may write
            # back - a bool would return as "Yes", html would be flattened.
            'product_value': '', 'has_override': False,
            'value_source': 'default',
            'category_values': list((cat_rows or {}).get(self.id, [])),
        }
        if not product:
            return row

        override = (overrides or {}).get((product.id, self.id))
        row['state'] = self._state_for(product, overrides)
        row['visible'] = self._visible_for(product, overrides)
        row['value'] = Page._as_text(
            self, self._value_for(product, overrides, cat_values), product)
        row['product_value'] = (override.value or '') if override else ''
        row['has_override'] = bool(override)
        row['value_source'] = self._value_source_for(
            product, overrides, cat_values)
        return row

    def _value_source_for(self, product, overrides=None, category_values=None):
        """Which of the four layers the value actually came from.

        The console offers three editors for the same field - shop, category
        and product - and without this they are indistinguishable: you cannot
        tell whether the words on screen are the ones you are about to edit
        or ones inherited from elsewhere. Same ladder as `_value_for`.
        """
        self.ensure_one()
        override = (overrides or {}).get((product.id, self.id))
        if override and override.value:
            return 'product'
        if self.source == 'odoo' and self.odoo_field:
            return 'odoo'
        cat_values = category_values
        if cat_values is None:
            cat_values = self._category_values(product)
        if self.id in cat_values:
            return 'category'
        return 'default'

    @api.model
    def builder_load(self, product_id=None):
        """Everything the Product Page screen draws from, in one call.

        Rows are grouped by section and carry both the value and whether the
        app would show it, so the mock can draw the real page and grey out
        what is switched off rather than silently omitting it.
        """
        Product = self.env['product.template']
        product = Product.browse(product_id).exists() if product_id else Product
        if not product:
            product = Product.search([('is_published', '=', True)], limit=1)

        sections = self.env['mart369.product.section'].search([])
        fields_all = self.search([])
        Page = self.env['mart369.product.page']

        # One read for the whole recordset. Touched per field inside the loop
        # this is one _read_group each, and there are about fifty.
        fields_all.mapped('override_count')

        # Every category value, grouped by field, in one search rather than
        # one search per field.
        cat_rows = {}
        for row in self.env['mart369.product.category.value'].search([]):
            cat_rows.setdefault(row.field_id.id, []).append({
                'id': row.id,
                'categ_id': row.public_categ_id.id,
                'categ_name': row.public_categ_id.display_name,
                'value': row.value or '',
            })

        overrides, cat_values, card, page = {}, {}, None, {}
        if product:
            overrides = {
                (product.id, o.field_id.id): o
                for o in self.env['mart369.product.override'].search(
                    [('product_tmpl_id', '=', product.id)])
            }
            cat_values = fields_all[:1]._category_values(product) if fields_all else {}
            # The shopper's own payload. The sudo() is the model's, for a
            # preview read; the admin routes on top of this add none.
            page = Page.sudo().payload(product)
            card = page['p']

        by_section = {}
        for field in fields_all:
            by_section.setdefault(field.section_id.id, []).append(
                field._builder_row(product, overrides, cat_values, cat_rows))

        return {
            'sections': [{
                'id': s.id, 'key': s.key, 'name': s.name,
                'sequence': s.sequence, 'show': s.show, 'note': s.note or '',
                'rows': by_section.get(s.id, []),
            } for s in sections],
            'product': {
                'id': product.id, 'name': product.display_name,
                'is_published': product.is_published,
                'categories': [{'id': c.id, 'name': c.display_name}
                               for c in product.public_categ_ids],
            } if product else None,
            'card': card,
            # The rails the page ends with. Without them the editor has no
            # "frequently bought together" to put a handle on, and inventing
            # products on an admin screen is not an option.
            'preview': {
                'variants': page.get('variants', []),
                'bundle': page.get('bundle', []),
                'similar': page.get('similar', []),
                'related': page.get('related', []),
            },
        }

    @api.model
    def set_product_state(self, field_id, product_id, state):
        """Follow the default, always show, or always hide - for one product.

        'follow' deletes the row rather than storing it: a product that
        follows everywhere should have nothing of its own, so that changing a
        shop-wide default still reaches it.
        """
        if state not in ('follow', 'show', 'hide'):
            # Raised, not written: otherwise a bad state reaches the selection
            # constraint and surfaces as a 500 rather than "that is not one of
            # the three choices".
            raise ValueError(_("'%s' is not follow, show or hide.", state))
        Override = self.env['mart369.product.override']
        row = Override.search([
            ('product_tmpl_id', '=', product_id), ('field_id', '=', field_id),
        ], limit=1)
        if state == 'follow':
            if row and not row.value:
                row.unlink()
            elif row:
                row.state = 'follow'
            return True
        if row:
            row.state = state
        else:
            Override.create({
                'product_tmpl_id': product_id,
                'field_id': field_id,
                'state': state,
            })
        return True

    @api.model
    def set_product_value(self, field_id, product_id, value):
        """Wording for one product only.

        Two rules hold this together, and both mirror `set_product_state`:

        * Typing wording never forces the field visible. A new row is created
          as 'follow', so the shop-wide switch still decides who sees it.
        * Clearing the wording of a field that is following removes the row.
          A 'follow' row with nothing in it is a tombstone: it makes
          `override_count` and the "differs from the default" filter both
          claim this product is special when it is not. An explicit show or
          hide is a separate decision and survives the words being cleared.
        """
        field = self.browse(field_id).exists()
        if not field:
            raise ValueError(_('No such field.'))
        if not field.per_product:
            raise UserError(_('This field is the same for every product.'))

        Override = self.env['mart369.product.override']
        row = Override.search([
            ('product_tmpl_id', '=', product_id), ('field_id', '=', field_id),
        ], limit=1)
        value = (value or '').strip()

        if not value:
            if row and row.state == 'follow':
                row.unlink()
            elif row:
                row.value = False
            return True

        if row:
            row.value = value
        else:
            Override.create({
                'product_tmpl_id': product_id,
                'field_id': field_id,
                'value': value,
                'state': 'follow',
            })
        return True

    @api.model
    def reset_product_state(self, field_ids, product_id):
        """Put these fields back to following the shop default."""
        self.env['mart369.product.override'].search([
            ('product_tmpl_id', '=', product_id),
            ('field_id', 'in', field_ids),
        ]).unlink()
        return True

    @api.model
    def _resolve_sections(self, product):
        """{section key: [(field, value), ...]} in page order, visible only.

        The product-information table and the specifications grid are ordered
        lists of labelled values, so the API needs the label and the order,
        not just the value.
        """
        fields_all = self.search([])
        overrides = {
            (o.product_tmpl_id.id, o.field_id.id): o
            for o in self.env['mart369.product.override'].search(
                [('product_tmpl_id', '=', product.id)])
        }
        cat_values = fields_all[:1]._category_values(product) if fields_all else {}

        out = {}
        for field in fields_all:
            if not field._visible_for(product, overrides):
                continue
            value = field._value_for(product, overrides, cat_values)
            out.setdefault(field.section_id.key, []).append((field, value))
        return out

    @api.model
    def _section_shown(self, section_key):
        """Is this whole band switched on?"""
        section = self.env['mart369.product.section'].search(
            [('key', '=', section_key)], limit=1)
        return bool(section) and section.show

    @api.model
    def _visible_keys(self, product):
        """Just the keys, for callers that only need to know what shows."""
        overrides = {
            (o.product_tmpl_id.id, o.field_id.id): o
            for o in self.env['mart369.product.override'].search(
                [('product_tmpl_id', '=', product.id)])
        }
        return {f.key for f in self.search([])
                if f._visible_for(product, overrides)}
