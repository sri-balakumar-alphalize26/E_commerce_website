# -*- coding: utf-8 -*-
"""Live preview (24 Nov 2026): every settings page has two sides - the options,
and what happens with them now (static/src/preview). The views themselves stay
plain forms; the second side is added when the page is read."""
import json

from lxml import etree

from odoo import _, api, models

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


# the words a person reads, on the page and in its preview (24 Nov 2026)
WORDS = {
    'ai_enabled': "Should the AI read the messages?",
    'min_confidence': "How sure must the AI be? (0 to 1)",
    'max_products': "How many products to look at?",
    'require_confirmation': "Ask the customer to confirm the product?",
    'use_virtual_stock': "Count goods that are on the way?",
    'dm_use_buttons': "Use buttons in private chats?",
    'auto_confirm_order': "Go on to payment in the older private chat?",
    'active': "Use the AI?",
    'provider': "Which AI?",
    'model_name': "Which model?",
    'timeout_seconds': "How long may the AI take? (seconds)",
    'shop_picks_vendors': "Do you want to choose the vendors yourself?",
    'shop_pick_window_minutes': "How long do you get to choose? (minutes)",
    'shop_pick_customer_text': "What is the customer told meanwhile?",
    'sourcing_window_minutes': "How long do we wait for prices?",
    'vendor_choice_mode': "Who picks the winning price?",
    'vendor_money': "In which money do vendors answer?",
    'price_escalation_phone': "No vendor answers: who gets a WhatsApp?",
    'margin_percent': "How much do you add normally?",
    'supply_mode': "Who orders from the vendor?",
    'supply_auto_start': "When is it ordered?",
    'supply_auto_wait': "Wait for a cheaper late price?",
    'supply_auto_margin': "How much must be left to order by itself?",
    'supply_auto_limit': "Biggest order without asking you?",
    'supply_auto_days': "When are the goods here?",
    'customer_reply_minutes': "How long can the customer answer?",
    'pay_remind_minutes': "Not paid: remind after how long?",
    'pay_remind_max': "How many reminders?",
    'unlisted_vendor_ids': "Extra vendors",
    'margin_rules_enabled': "Different for some products or customers?",
    'margin_rules_by': "Different by what?",
    'bargain_enabled': "May the customer bargain?",
    'bargain_step_percent': "How much less each time?",
    'bargain_max_steps': "How many times?",
    'min_margin_percent': "How much must always be left?",
    'qty_bargain_all': "Quantity ranges for every product?",
    'price_approval_enabled': "Other price on the product page: ask you first?",
    'price_approval_tolerance_percent': "Which difference is too small to ask?",
    'price_auto_minutes': "How long before it goes by itself?",
    'price_auto_max_below': "How far below the page price is too low?",
    'pay_link_in_stock': "In stock: when is the payment link sent?",
    'pay_link_no_stock': "Not in stock: when is the payment link sent?",
    'pincode_country_id': "Which country for addresses?",
    'pincode_prefixes': "Where do you deliver? (postcodes)",
    'stale_after_minutes': "How long is a question open? (minutes)",
    'max_order_quantity': "Biggest quantity per order?",
    'address_link_enabled': "Send a form for the address?",
    'address_link_minutes': "How long does the form work? (minutes)",
    'link_group_note': "Tell the group about private messages?",
    'shop_contact_phone': "Which number for products you don't sell?",
    'chatter_action': "Answer small talk?",
    'chatter_reply_text': "With what?",
    'media_action': "What about photos and videos?",
    'media_reply_text': "With what?",
    'notice_on': "Show a panel with news?",
    'finder_enabled': "Offer choices for general words?",
    'finder_max_options': "How many choices?",
    'conduct_enabled': "Remove bad messages?",
    'conduct_links': "Remove adult links?",
    'conduct_warn': "Warn the person?",
    'conduct_warn_text': "With what text?",
    'takeover_enabled': "Stop the assistant when you write?",
    'takeover_minutes': "When does it answer again? (minutes)",
    'takeover_numbers': "Which other numbers are staff?",
    'wechat_enabled': "Ask vendors on WeChat?",
    'wechat_stale_minutes': "When is WeChat shown as down? (minutes)",
    'wechat_manual_when_down': "Send by hand when it is down?",
    'confirm_enabled': "Customer confirms on a page?",
    'confirm_vendor_enabled': "Vendor confirms on a page?",
    'confirm_remind_minutes': "Remind the customer after? (minutes)",
    'vendor_remind_minutes': "Remind the vendor after? (minutes)",
    'vendor_remind_max': "How many vendor reminders?",
}
REMIND = "When do we remind you to choose?"


def plain_words(arch):
    """Options named as short questions; tables inside the page stay as they are."""
    for node in arch.iter('field', 'label'):
        name = node.get('name') if node.tag == 'field' else node.get('for')
        if name not in WORDS or node.get('nolabel') or any(up.tag == 'list' for up in node.iterancestors()):
            continue
        node.set('string', REMIND if node.get('string') == 'Remind me after' else WORDS[name])


def fold_advanced(arch):
    """What is rarely needed is folded: a group called Advanced, or the tabs
    under a heading called Advanced."""
    for node in list(arch.iter('group', 'separator')):
        if node.get('string') != 'Advanced':
            continue
        inside = node if node.tag == 'group' else node.getnext()
        if inside is None or not isinstance(inside.tag, str):
            continue
        fold = etree.Element('details', {'class': 'sa_fold'})
        etree.SubElement(fold, 'summary').text = 'Advanced'
        if node.get('invisible'):
            fold.set('invisible', node.get('invisible'))
        parent = inside.getparent()
        fold.tail, inside.tail = inside.tail, None
        parent.replace(inside, fold)
        fold.append(inside)
        inside.attrib.pop('invisible', None)
        if node.tag == 'group':
            inside.attrib.pop('string')
        else:
            node.getparent().remove(node)


def add_preview(model, arch, view):
    page = PAGES.get(view.name) if view else None
    sheet = arch.find('.//sheet') if page else None
    if sheet is None:
        return arch
    plain_words(arch)
    fold_advanced(arch)
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
    etree.SubElement(right, 'widget', {'name': 'sa_live_preview', 'page': page[0], 'words': json.dumps(WORDS)})
    return arch


class SaAiSettingsPreview(models.Model):
    _inherit = 'sa.ai.settings'

    @api.model
    def sa_flow_steps(self):
        """How an enquiry goes with the saved settings, step by step. `you`: a
        person is needed. Each step names the pages it is set on."""
        if not self.env.user.has_group('sales_automation.group_sa_user'):
            return []
        s = self.sudo().get_settings()
        money = self.env.company.currency_id.name or ''

        def has(name, value=True):
            return name in s._fields and (bool(s[name]) if value is True else s[name] == value)

        manual = has('vendor_choice_mode', 'manual')
        auto = has('supply_mode', 'auto')
        margin = '%g' % (s.margin_percent or 0.0)
        sell = s._sa_sell(100.0, s.margin_percent)
        own = ''
        if s.margin_rules_enabled:
            own = ' ' + (_("A group with an own margin gets its own.") if s.margin_rules_by == 'group'
                         else _("A category with an own margin gets its own."))
        base = 'sales_automation.action_sa_settings_'
        vendor, price = (_("Vendors & Customer Replies"), base + 'vendor'), (_("Price & Margin"), base + 'margin')
        steps = [
            (False, _("A customer asks in the group"), _("We don't have it in stock, so we ask vendors."),
             [(_("WhatsApp Groups"), 'sales_automation.action_sa_sales_group')]),
            (False, _("The customer confirms the product"),
             _("On a page with the picture: ACCEPT or REJECT.") if has('confirm_enabled') else _("In the chat: YES or NO."),
             [(_("Product Confirmation"), 'sales_automation_confirm.action_sa_settings_confirm')]),
            (s.shop_picks_vendors, _("Who is asked?"),
             _("YOU choose the vendors. Not chosen in %s minutes: all are asked.", s.shop_pick_window_minutes) if s.shop_picks_vendors
             else _("All vendors of the category."), [(_("The Shop Counter"), base + 'counter')]),
            (False, _("Vendors send their prices"),
             _("Vendor A: 110, vendor B: 100. After %s minutes we remind you to choose.", s.sourcing_window_minutes) if manual
             else _("Vendor A: 110, vendor B: 100. We wait up to %s minutes.", s.sourcing_window_minutes), [vendor]),
            (manual, _("One price wins"), _("YOU choose on Store > Enquiries.") if manual else _("The lowest: vendor B, 100."), [vendor]),
            (False, _("We add your margin"), _("%(p)s%%: 100 becomes %(s).2f %(m)s.", p=margin, s=sell, m=money) + own, [price]),
            (s.price_approval_enabled, _("Is the product page price different?"),
             _("YOU choose first. After %s minute(s) our price goes by itself.", s.price_auto_minutes)
             if s.price_approval_enabled and not manual and s.price_auto_minutes
             else _("YOU choose first. The customer waits.") if s.price_approval_enabled else _("The customer is told at once."), [price]),
            (False, _("The customer gets the price"),
             _("Answer within %s minutes.", s.customer_reply_minutes) if s.customer_reply_minutes else _("Answer within 24 hours."), [vendor]),
            (False, _("The customer asks for a better price"),
             _("The price can come down, never below the lowest margin.") if s.bargain_enabled else _("The first price is the last price."), [price]),
            (False, _("Address, order and payment"),
             _("Address form, then the payment link.") if s.address_link_enabled else _("Address in the chat, then the payment link."),
             [(_("Delivery Address"), base + 'address'), (_("Payments"), base + 'payments'), (_("Customer Links"), base + 'links')]),
        ]
        if 'supply_mode' in s._fields:
            steps.append((not auto, _("We order from the vendor"),
                          _("By itself, when at least %s%% is left. Less: you are asked.", '%g' % (s.supply_auto_margin or 0.0)) if auto
                          else _("YOU order on Store > Orders."), [vendor]))
        manager = self.env.user.has_group('sales_automation.group_sa_manager')
        return [{'you': bool(you), 'title': title, 'text': text,
                 'links': [{'name': name, 'action': xmlid} for name, xmlid in links
                           if manager and self.env.ref(xmlid, raise_if_not_found=False)]}
                for you, title, text, links in steps]

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
