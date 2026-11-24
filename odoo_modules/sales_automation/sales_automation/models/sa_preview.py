# -*- coding: utf-8 -*-
"""Live preview (24 Nov 2026): every settings page has two sides - the options,
and what happens with them now (static/src/preview). The views themselves stay
plain forms; the second side is added when the page is read."""
from lxml import etree

from odoo import api, models

# the page's view -> (its preview, fields the preview needs that are not on the page)
PAGES = {
    'sa.ai.settings.form': ('ai', []),
    'sa.settings.counter.form': ('counter', []),
    'sa.settings.vendor.form': ('vendor', ['sa_money', 'margin_percent', 'margin_rules_enabled', 'margin_rules_by']),
    'sa.settings.margin.form': ('margin', ['sa_money', 'supply_mode', 'supply_auto_margin']),
    'sa.settings.payments.form': ('payments', []),
    'sa.settings.address.form': ('address', []),
    'sa.settings.links.form': ('links', []),
    'sa.settings.chatter.form': ('chatter', []),
    'sa.settings.notify.form': ('notify', []),
    'sa.settings.finder.form': ('finder', []),
    'sa.settings.conduct.form': ('conduct', []),
    'sa.settings.takeover.form': ('takeover', []),
    'sa.settings.wechat.form': ('wechat', []),
    'sa.settings.confirm.form': ('confirm', []),
    'sa.sales.group.form': ('group', []),
}


def add_preview(model, arch, view):
    page = PAGES.get(view.name) if view else None
    sheet = arch.find('.//sheet') if page else None
    if sheet is None:
        return arch
    left = etree.Element('div', {'class': 'sa_side_left'})
    for node in list(sheet):
        # what Odoo wants at the top of the sheet stays there
        if not isinstance(node.tag, str) or node.get('name') == 'button_box' or node.tag == 'widget' \
                or 'oe_title' in (node.get('class') or ''):
            continue
        left.append(node)
    there = {node.get('name') for node in arch.iter('field')}
    for name in page[1]:
        if name in model._fields and name not in there:
            etree.SubElement(left, 'field', {'name': name, 'invisible': '1'})
    two = etree.SubElement(sheet, 'div', {'class': 'sa_two_sides'})
    two.append(left)
    right = etree.SubElement(two, 'div', {'class': 'sa_side_right'})
    etree.SubElement(right, 'widget', {'name': 'sa_live_preview', 'page': page[0]})
    return arch


class SaAiSettingsPreview(models.Model):
    _inherit = 'sa.ai.settings'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        return (add_preview(self, arch, view) if view_type == 'form' else arch), view


class SaSalesGroupPreview(models.Model):
    _inherit = 'sa.sales.group'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        return (add_preview(self, arch, view) if view_type == 'form' else arch), view
