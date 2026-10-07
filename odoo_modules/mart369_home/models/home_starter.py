"""A home page arranged from the shop's own catalogue.

The module used to install a grocery page - "Fruits picked this morning",
"Atta & staples", tabs for Fashion and Books - as a starting point, and on a
shop that never replaced it (the Dubai computer-parts shop) that page was the
first thing every customer saw. This builds the starting point from what the
shop really sells instead: its biggest categories become the tabs, banners,
tiles and rows.

**Arranged once, then the admin owns it.** The result is an ordinary saved
page, every band of it editable, reorderable and removable in the page
editor. Nothing here runs on a timer; it runs on install, on the update that
replaces the untouched grocery page, and when somebody presses "Rebuild from
my catalogue" - and that always makes a *new* page, so an arranged one is
never overwritten.
"""

import re

from odoo import api, fields, models

from odoo.addons.mart369.models.serializers import slugify

TONES = ['navy', 'green', 'orange', 'indigo', 'teal', 'brown']

# Words a category name keeps in capitals ("CCTV CAMERA" -> "CCTV Camera").
KEEP_UPPER = {'LED', 'USB', 'HDMI', 'RAM', 'CPU', 'GPU', 'AIO', 'UPS', 'SSD',
              'HDD', 'LCD', 'TV', 'PC', 'IP', 'DC', 'AC', 'RE', 'DVD', 'CD'}

# What to draw for a category with no picture, and the pill's icon - matched
# on words in its name, first match wins. Drawings and icons are the app's
# own (ART_CHOICES / ICON_CHOICES), so there is nothing to upload.
LOOKS = [
    (r'keyboard', 'Keyboard', 'keyboard'),
    (r'mouse', 'Mouse', 'keyboard'),
    (r'laptop|notebook', 'Laptop', 'laptop'),
    (r'desktop|all in one|aio|computer|pc\b', 'Cabinet', 'laptop'),
    (r'monitor|screen|display|led|lcd|tv', 'Monitor', 'monitor'),
    (r'cctv|camera|webcam|dvr|nvr', 'Webcam', 'monitor'),
    (r'router|switch|wifi|network|access point|fiber|firewall', 'Router', 'wifi'),
    (r'cable|connector|jack|adapter|hdmi|usb', 'Cable', 'plug'),
    (r'charger|adaptor|power|battery|ups', 'Charger', 'plug'),
    (r'hard dis|ssd|hdd|storage|flash|memory', 'Ssd', 'cpu'),
    (r'ram\b', 'Ram', 'cpu'),
    (r'processor|cpu', 'Cpu', 'cpu'),
    (r'graphic|gpu', 'Gpu', 'cpu'),
    (r'fan|cooler', 'Cooler', 'cpu'),
    (r'speaker|audio|sound|microphone|amplifier', 'Speaker', 'plug'),
    (r'headphone|headset|earphone', 'Headphones', 'plug'),
    (r'toner|ink|cartridge|printer|paper', 'Box', 'pen'),
]


def _nice(name):
    """'LAPTOP KEYBOARD' -> 'Laptop Keyboard', keeping CCTV, LED, DC..."""
    name = ' '.join((name or '').split())
    if not name.isupper():
        return name
    words = []
    for word in name.split(' '):
        bare = re.sub(r'[^A-Z]', '', word)
        keep = bare in KEEP_UPPER or (bare and not re.search(r'[AEIOU]', bare))
        words.append(word if keep else word.capitalize())
    return ' '.join(words)


def _look(name):
    low = (name or '').lower()
    for pattern, art, icon in LOOKS:
        if re.search(pattern, low):
            return art, icon
    return 'Box', 'grid'


class Mart369HomeVersion(models.Model):
    _inherit = 'mart369.home.version'

    # ------------------------------------------------------------ the inputs

    @api.model
    def _mart369_top_categories(self, limit=10):
        """[(category, listed product count)], biggest first.

        Only categories the app shows (`mart_in_app`, when the catalogue is
        installed) and only listed products - published, not a service - so a
        category of repair charges never becomes a tab.
        """
        Template = self.env['product.template'].sudo()
        Category = self.env['product.public.category'].sudo()
        groups = Template._read_group(
            Template._mart369_listed_domain() + [('public_categ_ids', '!=', False)],
            ['public_categ_ids'], ['__count'])
        shown = 'mart_in_app' in Category._fields
        ranked = sorted(
            ((categ, count) for categ, count in groups
             if categ and (not shown or categ.mart_in_app)),
            key=lambda pair: (-pair[1], pair[0].name or ''))
        return ranked[:limit]

    @api.model
    def _mart369_category_path(self, categ):
        """The address the storefront opens a category by: its slug, under
        its parents' ("laptops/laptop-keyboard")."""
        ids = [int(i) for i in (categ.parent_path or '%d/' % categ.id).split('/') if i]
        slugs = []
        for c in categ.browse(ids):
            # mart_slug is the catalogue module's; without it, the same rule.
            slugs.append((c.mart_slug if 'mart_slug' in c._fields else '') or slugify(c.name or ''))
        return '/'.join(s for s in slugs if s)

    # ------------------------------------------------------------ the build

    @api.model
    def _mart369_build_starter(self, name=None, make_current=True):
        """A new saved page arranged from the catalogue. Returns it.

        An empty catalogue still gets a page - My Home, a New-this-week row
        that fills itself as products are added, and Offers - rather than a
        grocery page standing in for one.
        """
        config = self.env['mart369.config'].sudo()._get()
        top = self._mart369_top_categories(limit=10)
        today = fields.Date.context_today(self)
        # The delivery thresholds belong to the shop, not to a page: carried
        # over from the page that was live, so rebuilding moves nothing else.
        old = {m.key: m for m in self.sudo()._mart369_live().mode_ids}
        page = self.sudo().create({
            'name': name or self.env._('From your catalogue'),
            'note': self.env._(
                'Arranged automatically from your biggest categories on %s. '
                'Rearrange it freely - nothing changes it on its own.', today),
            'config_id': config.id,
        })
        for seq, (key, label, free_at) in enumerate(
                [('quick', 'Quick', 499), ('all', 'Express', 999)], start=1):
            was = old.get(key)
            mode = self.env['mart369.home.mode'].sudo().create({
                'config_id': config.id,
                'version_id': page.id,
                'key': key,
                'name': was.name if was else label,
                'sequence': seq * 10,
                'free_delivery_at': was.free_delivery_at if was else free_at,
            })
            self._mart369_fill_mode(mode, top)
        if make_current:
            # Switched on by writing, not by creating it switched on: create()
            # settles "exactly one everyday page" by keeping the first one it
            # finds, which would be the old page; write() turns the others off.
            page.write({'is_current': True})
        return page

    @api.model
    def _mart369_fill_mode(self, mode, top):
        Tab = self.env['mart369.home.tab'].sudo()
        Banner = self.env['mart369.home.banner'].sudo()
        Tile = self.env['mart369.home.tile'].sudo()
        Section = self.env['mart369.home.section'].sudo()
        express = mode.key == 'all'
        path = {categ.id: self._mart369_category_path(categ) for categ, __ in top}

        # Tabs: home, the five biggest categories, offers.
        Tab.create({'mode_id': mode.id, 'key': 'home', 'name': self.env._('My Home'),
                    'icon': 'bag' if not express else 'grid', 'route_view': 'home',
                    'sequence': 10})
        for i, (categ, __) in enumerate(top[:5], start=2):
            Tab.create({
                'mode_id': mode.id, 'key': (slugify(categ.name) or 'c%d' % categ.id)[:40],
                'name': _nice(categ.name), 'icon': _look(categ.name)[1],
                'route_view': 'category', 'route_param': path[categ.id],
                'sequence': i * 10,
            })
        Tab.create({'mode_id': mode.id, 'key': 'offers', 'name': self.env._('Offers'),
                    'icon': 'ticket', 'route_view': 'offers', 'sequence': 90})

        # Banners: one per big category, in turn through the shop's colours.
        for i, (categ, count) in enumerate(top[:4]):
            Banner.create({
                'mode_id': mode.id, 'key': 'b%d' % (i + 1),
                'kicker': [self.env._('Biggest range'), self.env._('Popular'),
                           self.env._('Top category'), self.env._('Shop by category')][i],
                'name': _nice(categ.name),
                'note': self.env._('%s to choose from', count),
                'tone': TONES[i % len(TONES)],
                'art_lines': _look(categ.name)[0],
                'href': '/category/%s' % path[categ.id],
                'sequence': (i + 1) * 10,
            })

        # Tiles: the eight biggest, wearing the category's own logo if it has
        # one and the app's drawing if not.
        for i, (categ, __) in enumerate(top[:8]):
            has_logo = 'image_128' in categ._fields and bool(categ.image_128)
            Tile.create({
                'mode_id': mode.id, 'key': (slugify(categ.name) or 'c%d' % categ.id)[:40],
                'name': _nice(categ.name), 'public_categ_id': categ.id,
                'route': path[categ.id],
                'image_source': 'category' if has_logo else 'art',
                'art': _look(categ.name)[0],
                'sequence': (i + 1) * 10,
            })

        # Rows: what is new, then a row for each of the biggest categories.
        # Express leads with best sellers, which only means something once a
        # shop has sold; its category rows start further down the list so the
        # two modes don't read as one page twice.
        Section.create({
            'mode_id': mode.id, 'kind': 'rail', 'key': 'new',
            'name': self.env._('New this week'), 'subtitle': self.env._('Just landed in store'),
            'source': 'rule', 'rule': 'new', 'limit': 12, 'sequence': 10,
        })
        if express:
            Section.create({
                'mode_id': mode.id, 'kind': 'rail', 'key': 'best',
                'name': self.env._('Most loved'), 'subtitle': self.env._('What customers buy most'),
                'source': 'rule', 'rule': 'best', 'limit': 12, 'sequence': 20,
            })
        rows = top[2:6] if express and len(top) > 5 else top[:4]
        for i, (categ, __) in enumerate(rows, start=3):
            Section.create({
                'mode_id': mode.id, 'kind': 'rail',
                'key': (slugify(categ.name) or 'c%d' % categ.id)[:40],
                'name': _nice(categ.name),
                'view_all_route': path[categ.id],
                'source': 'category', 'public_categ_id': categ.id,
                'limit': 12, 'sequence': i * 10,
            })

    # ------------------------------------------------------------ the button

    def action_mart369_build_starter(self):
        """"Rebuild from my catalogue": a new page, switched on. The one that
        was live stays saved, so switching back is one click."""
        page = self._mart369_build_starter()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mart369.home.version',
            'res_id': page.id,
            'view_mode': 'form',
            'target': 'current',
        }
