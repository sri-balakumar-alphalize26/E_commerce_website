# -*- coding: utf-8 -*-
"""One private link per enquiry and person, and the log of every click on it.

The link is the confirmation. Whoever it was sent to opens one page with the
picture and the details, and presses ACCEPT or REJECT once; the first press
is final and both buttons are disabled afterwards. A link is issued to one
number / one WeChat contact, so "who clicked" is that identity; the address
and browser of every hit are kept as evidence.
"""
import base64
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.tools import html2plaintext, html_sanitize
from odoo.addons.whatsapp_gateway.models import send_memo

_logger = logging.getLogger(__name__)

# The most the shop shows: the card picture and 12 more (mart369 MAX_EXTRA_IMAGES).
MAX_PICTURES = 13


class SaConfirmLink(models.Model):
    _name = 'sa.confirm.link'
    _description = 'Product confirmation link'
    _order = 'id desc'
    _rec_name = 'display_name'

    request_id = fields.Many2one('sa.group.request', 'Enquiry', required=True, ondelete='cascade', index=True)
    kind = fields.Selection([('customer', 'Customer'), ('vendor', 'Vendor')], required=True, index=True)
    channel = fields.Selection([('whatsapp', 'WhatsApp'), ('wechat', 'WeChat')], required=True, default='whatsapp')
    partner_id = fields.Many2one('res.partner', 'Contact', ondelete='set null')
    phone = fields.Char('Phone')
    lid = fields.Char('WhatsApp LID')
    wechat_name = fields.Char('WeChat remark')
    identity = fields.Char('Sent to', compute='_compute_identity', store=True,
                           help="The account this link was issued to - who a click is attributed to.")
    token = fields.Char('Token', required=True, index=True, copy=False, groups='base.group_user',
                        default=lambda self: secrets.token_urlsafe(24))

    @api.model
    def _sa_token_for(self, vals):
        """The same token for the same enquiry + kind + channel + person: a
        request that Odoo retries recreates the link with the token that is
        already in the customer's or vendor's chat."""
        import base64 as _b64
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret') or ''
        key = '%s|%s|%s|%s|%s' % (vals.get('request_id') or 0, vals.get('kind') or '', vals.get('channel') or '',
                                  vals.get('partner_id') or 0,
                                  vals.get('wechat_name') or vals.get('phone') or vals.get('lid') or '')
        digest = hmac.new(secret.encode('utf-8'), key.encode('utf-8'), 'sha256').digest()
        return _b64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')[:32]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('token') and vals.get('request_id'):
                memo = send_memo.current(self.env)
                kind = 'confirm|%s|%s|%s' % (vals.get('kind'), vals.get('channel'), vals.get('partner_id') or vals.get('phone'))
                vals['token'] = (memo.value(kind, lambda v=vals: self._sa_token_for(v)) if memo is not None
                                 else self._sa_token_for(vals))
        return super().create(vals_list)
    sent_on = fields.Datetime('Sent', readonly=True)
    reminded_on = fields.Datetime('Reminded', readonly=True)
    opened_on = fields.Datetime('First opened', readonly=True)
    open_count = fields.Integer('Opens', readonly=True, default=0)
    decided = fields.Selection([('accept', 'Accepted'), ('reject', 'Rejected')], 'Decision', readonly=True, index=True)
    decided_on = fields.Datetime('Decided', readonly=True)
    decided_ip = fields.Char('Decided from (IP)', readonly=True)
    decided_ua = fields.Char('Decided with (browser)', readonly=True)
    image_source = fields.Selection([('local', 'Product picture'), ('fetched', 'Fetched from the internet'),
                                     ('generated', 'AI reference picture'), ('none', 'No picture')],
                                    'Picture', readonly=True, default='none')
    product_id = fields.Many2one('product.template', related='request_id.product_id', store=False)
    ref_code = fields.Char(related='request_id.ref_code', store=False)
    click_ids = fields.One2many('sa.link.click', 'link_id', 'Clicks')
    picture_ids = fields.One2many('sa.confirm.picture', 'link_id', 'Other shots (no product record)')
    click_count = fields.Integer(compute='_compute_click_count')
    active = fields.Boolean(default=True)

    @api.depends('kind', 'partner_id', 'phone', 'lid', 'wechat_name', 'request_id.requester_name')
    def _compute_identity(self):
        for link in self:
            who = link.partner_id.name or (link.request_id.requester_name if link.kind == 'customer' else '') or ''
            acct = link.wechat_name and ('WeChat: %s' % link.wechat_name) or link.phone and ('WhatsApp: %s' % link.phone) \
                or link.lid and ('WhatsApp id: %s' % link.lid) or ''
            link.identity = ' - '.join(p for p in (who, acct) if p) or _('unknown')

    def _compute_click_count(self):
        for link in self:
            link.click_count = len(link.click_ids)

    @api.depends('kind', 'identity', 'request_id.ref_code')
    def _compute_display_name(self):
        for link in self:
            link.display_name = '#%s %s - %s' % (link.request_id.ref_code or '?', dict(
                self._fields['kind'].selection).get(link.kind, ''), link.identity or '')

    # ------------------------------------------------------------------
    # Lookup and URLs
    # ------------------------------------------------------------------
    @api.model
    def _by_token(self, token):
        """The link for this token, compared in constant time. Empty otherwise."""
        token = (token or '').strip()
        if not token or len(token) < 16 or len(token) > 64 or not all(c.isalnum() or c in '-_' for c in token):
            return self.browse()
        # One indexed candidate, then a constant-time compare on it.
        candidate = self.sudo().search([('token', '=', token)], limit=1)
        if candidate and hmac.compare_digest(str(candidate.token), token):
            return candidate
        return self.browse()

    @api.model
    def _public_base(self):
        params = self.env['ir.config_parameter'].sudo()
        return (params.get_param('sa_delivery.public_base_url') or params.get_param('web.base.url') or '').rstrip('/')

    def _url(self):
        """The link the person taps: through the database doorway, short."""
        self.ensure_one()
        return '%s/scoped_app/c?db=%s&t=%s' % (self._public_base(), quote(self.env.cr.dbname), self.sudo().token)

    def _image_url(self):
        """The picture alone (used by the WeChat bridge to send it as a file)."""
        self.ensure_one()
        return '%s/scoped_app/c?db=%s&t=%s&img=1' % (self._public_base(), quote(self.env.cr.dbname), self.sudo().token)

    # ------------------------------------------------------------------
    # The page's content
    # ------------------------------------------------------------------
    def _product(self):
        """The product this page is about. A word like "laptop" goes through
        the guided finder, which picks one of the shop's own products but only
        keeps it as the candidate until ACCEPT (`_finder_finish` sets
        `product_id`). The page shows that candidate from the first open - its
        photos, details and price - instead of "No photo yet" (22 Nov 2026)."""
        self.ensure_one()
        req = self.request_id
        if req.product_id:
            return req.product_id
        if getattr(req, 'finder_kind', '') == 'ours' and 'candidate_product_ids' in req._fields:
            return req.candidate_product_ids[:1]
        return req.product_id

    def _picture(self):
        """(bytes, mimetype) of the main picture shown on the page, or (b'', '')."""
        self.ensure_one()
        req = self.request_id
        raw, source = req._sa_confirm_picture(fetch=False)
        return raw, ('image/jpeg' if raw else '')

    def _picture_refs(self):
        """(record, field) of each picture the shop shows, in its order: the main
        one first, then the shop's own Extra Product Media. Without website_sale
        there is no such media, so the Confirmation pictures added by hand take
        its place. What a past internet search saved is never shown."""
        self.ensure_one()
        product = self._product()
        if not product:
            return []
        refs = [(product, 'image_1920')]
        variants = product.product_variant_ids
        if len(variants) == 1 and 'product_variant_image_ids' in variants._fields:
            refs += [(i, 'image_1920') for i in variants.product_variant_image_ids.sorted(lambda i: (i.sequence, i.id))]
        if 'product_template_image_ids' in product._fields:
            refs += [(i, 'image_1920') for i in product.product_template_image_ids.sorted(lambda i: (i.sequence, i.id))]
        else:
            refs += [(p, 'image') for p in product.sa_extra_picture_ids.filtered(lambda p: p.source != 'internet').sorted('sequence')]
        return refs

    def _picture_attachment(self, record, field):
        """The attachment holding `record.field`, or an empty recordset."""
        return self.env['ir.attachment'].sudo().search(
            [('res_model', '=', record._name), ('res_id', '=', record.id), ('res_field', '=', field)], limit=1)

    @api.model
    def _picture_remote_url(self, attachment):
        """The image server's public address of a picture stored there, or ''."""
        if attachment and 'imgsrv_url' in attachment._fields and attachment.imgsrv_url \
                and (attachment.store_fname or '').startswith('imgsrv:'):
            return attachment.imgsrv_url
        return ''

    def _picture_entries(self):
        """The page's pictures, no repeats, without reading a single one (17 Nov
        2026: the page and every picture request used to decode every full-size
        photo, which made the page slow on a phone). One dict per picture:
        {'record', 'field', 'version', 'url'} - `url` the image server's own
        address when it is stored there - or, for an enquiry with no picture of
        its own, {'raw', 'version'} with the reference picture's bytes."""
        self.ensure_one()
        entries, seen = [], set()
        for record, field in self._picture_refs():
            attachment = self._picture_attachment(record, field)
            if not attachment:
                continue
            if attachment.checksum:
                if attachment.checksum in seen:
                    continue
                seen.add(attachment.checksum)
            entries.append({'record': record, 'field': field, 'url': self._picture_remote_url(attachment),
                            'version': (attachment.checksum or str(attachment.id))[:12]})
        if not entries:
            main, _mt = self._picture()
            if main:
                entries.append({'raw': main, 'version': hashlib.sha1(main).hexdigest()[:12]})
        return entries[:MAX_PICTURES]

    def _picture_items(self):
        """The page's pictures, no repeats: the public address of one on the image
        server (the customer's browser loads it from there; the ERP downloads
        nothing), the bytes of any other. An enquiry with no picture of its own
        gets the reference picture."""
        self.ensure_one()
        items = []
        for entry in self._picture_entries():
            if 'raw' in entry:
                items.append(entry['raw'])
            elif entry['url']:
                items.append(entry['url'])
            elif entry['record'][entry['field']]:
                items.append(base64.b64decode(entry['record'][entry['field']]))
        return items

    def _attribute_rows(self):
        """(label, value) of the chosen variant's attributes, shown under the pictures."""
        return []

    def _shop_sections(self):
        """What the 369 Mart shop page prints under a product, read-only, for
        this link's product (owner, 8 Oct 2026: "show the details like the
        web"): {about_html, about, details, showcase, description}. Read
        through the shop's own payload model when it is installed
        (mart369_product, the junior's - never imported, only detected);
        {} without it. Empty parts are left out."""
        self.ensure_one()
        product = self._product()
        if not product:
            return {}
        out = {}
        page = self.env.get('mart369.product.page')
        if page is not None:
            page = page.sudo()
            parts = (('about_html', 'about_html'), ('about', 'about'),
                     ('details', 'product_details'), ('showcase', 'showcase'))
            for key, method in parts:
                try:
                    value = getattr(page, method)(product)
                except Exception as err:  # noqa: BLE001 - their change must never break the page
                    _logger.info("Sales Automation: shop part %s for %s skipped: %s", method, product.id, err)
                    value = None
                if value:
                    out[key] = value
            if out.get('about_html'):
                out.pop('about', None)
            # The badges under the price (7-day replacement, warranty, COD...),
            # worded per shop / category / product in their builder.
            try:
                shown = self.env['mart369.product.field'].sudo()._resolve_sections(product)
                values = {f.key: v for rows in shown.values() for f, v in rows}
                trust = page.trust(out.get('details') or [], values)
            except Exception as err:  # noqa: BLE001
                _logger.info("Sales Automation: shop badges for %s skipped: %s", product.id, err)
                trust = None
            if trust:
                out['trust'] = trust
        html = product.description_ecommerce if 'description_ecommerce' in product._fields else ''
        if html and html2plaintext(html).strip():
            cleaned = html_sanitize(html, strip_style=True, strip_classes=True)
            if cleaned and html2plaintext(cleaned).strip():
                out['description'] = str(cleaned)
        return out

    def _money(self, amount):
        """"AED 567.00" - with the decimals Odoo is set to for the currency
        (its rounding, Accounting > Currencies), like Odoo's own pages."""
        cur = self.request_id.currency_id
        digits = cur.decimal_places if cur else 2
        number = '{:,.{d}f}'.format(amount or 0.0, d=digits)
        symbol = (cur.symbol or cur.name or '') if cur else ''
        return ('%s %s' % (number, symbol) if cur and cur.position == 'after'
                else ('%s %s' % (symbol, number)).strip())

    def _page_extras(self):
        """What the page adds around the price for a customer (13 Nov 2026):
        {price, mrp, off, qty, total, stock: (tone, text), rating, rating_count,
        reviews: [{name, stars, when, text}]}. Each part only when it is known;
        a supplier's link gets none of the selling parts."""
        self.ensure_one()
        req, product = self.request_id, self._product()
        out = {}
        if self.kind != 'customer' or not product:
            return out
        qty = int(req.qty or 0)
        if qty:
            out['qty'] = qty
        price = req.agreed_price or req.quoted_price
        if price:
            out['price'] = self._money(price)
            # The website's rule: the "compare to" price, else the list price,
            # struck through when the customer pays less than it.
            mrp = getattr(product, 'compare_list_price', 0.0) or req._sa_priced(product).list_price or 0.0
            if mrp > price + 0.001:
                out['mrp'] = self._money(mrp)
                out['off'] = int(round((mrp - price) * 100 / mrp))
            if qty > 1:
                out['total'] = self._money(price * qty)
        # Stock: only for a product Inventory counts.
        if getattr(product, 'is_storable', False) or getattr(product, 'type', '') == 'product':
            free = sum(product.sudo().product_variant_ids.mapped('free_qty'))
            need = qty or 1
            if free >= need:
                out['stock'] = ('ok', _('In stock'))
            elif free > 0:
                out['stock'] = ('low', _('Only %s in stock') % int(free))
            else:
                out['stock'] = ('none', _('Not in stock right now - we will arrange it for you'))
        # Ratings and reviews, read the way the shop's product page reads them.
        page = self.env.get('mart369.product.page')
        if page is not None:
            try:
                data = page.sudo().reviews(product, {'rating', 'rating_count', 'reviews'}, {})
            except Exception as err:  # noqa: BLE001 - their change must never break the page
                _logger.info("Sales Automation: shop reviews for %s skipped: %s", product.id, err)
                data = {}
            if data.get('rating'):
                out['rating'] = data['rating']
                out['rating_count'] = data.get('ratingCount') or len(data.get('reviews') or [])
                out['reviews'] = [r for r in (data.get('reviews') or []) if r.get('text')][:3]
        promise = self._delivery_promise(qty or 1, out_of_stock=out.get('stock', ('',))[0] == 'none')
        if promise:
            out['delivery'] = promise
        return out

    def _chat_number(self):
        """Digits of the shop's own WhatsApp number - the session that runs
        this enquiry's group, where the 1:1 flow answers. Never the company
        phone or a hand-typed employee phone. '' when unknown."""
        self.ensure_one()
        session = self.request_id.sudo().group_id.session_id
        for raw in (getattr(session, 'phone_number', '') or '', getattr(session, 'authorized_number', '') or ''):
            digits = ''.join(c for c in raw.split('@')[0] if c.isdigit())
            if len(digits) >= 10:
                return digits
        return ''

    def _similar_after_reject(self, limit=4):
        """"Not this one?" (13 Nov 2026): up to `limit` products like the one
        the customer rejected, each a WhatsApp link saying "I want <name>" to
        the shop's number - the existing chat flow takes it from there, so
        nothing in the ordering changes. [] when there is no number, no
        storefront, or nothing similar."""
        self.ensure_one()
        req = self.request_id.sudo()
        number = self._chat_number()
        page = self.env.get('mart369.product.page')
        rejected = req.rejected_product_ids if 'rejected_product_ids' in req._fields else self.env['product.template']
        product = req.product_id or rejected[-1:]
        if not number or page is None or not product:
            return []
        try:
            page = page.sudo()
            items = page._similar(product, {'similar_items'}) or page._guess(product)
            items = (items - rejected - product)[:limit]
            out = []
            for tmpl in items:
                price = req._sa_priced(tmpl).list_price or 0.0
                out.append({
                    'name': tmpl.name or '',
                    # on the image server: its own address, no stop at Odoo
                    'image': (self.env['sa.picture'].url(
                        tmpl, 'image_256', '/web/image/product.template/%s/image_256' % tmpl.id)
                              if 'sa.picture' in self.env else
                              ('/web/image/product.template/%s/image_256' % tmpl.id
                               if tmpl.with_context(bin_size=True).image_128 else '')),
                    'price': self._money(price) if price else '',
                    'url': 'https://wa.me/%s?text=%s' % (number, quote(_('I want %s', tmpl.name or ''))),
                })
            return out
        except Exception as err:  # noqa: BLE001 - their change must never break the page
            _logger.info("Sales Automation: similar products for link %s skipped: %s", self.id, err)
            return []

    def _delivery_promise(self, qty, out_of_stock=False):
        """('quick'|'express', "25 mins") for this customer's address and
        product, decided by the shop's own rules (13 Nov 2026) - the same call
        the website makes, which already follows the hub rules and the
        WhatsApp Quick/Express shops (mart369_whatsapp_bridge). None when the
        storefront modules are not installed or anything goes wrong: the page
        must never break over a delivery line."""
        self.ensure_one()
        cart = self.env.get('mart369.cart')
        product = self._product()
        if cart is None or not product:
            return None
        try:
            req = self.request_id.sudo()
            order = req.order_id
            address = (order.partner_shipping_id or order.partner_id) if order else False
            if not address and hasattr(req, '_sa_address_book'):
                customer = self.partner_id or (req._sa_address_partner() if hasattr(req, '_sa_address_partner') else False)
                address = req._sa_address_book(customer)[:1] if customer else False
            cart = cart.sudo()
            tmpl = product.sudo()
            own = getattr(tmpl, 'mart_delivery_text', '') or getattr(tmpl, 'qe_delivery_text', '') or ''
            if out_of_stock and not own:
                return None          # the website's rule: nothing in stock is never Quick
            where = cart._mart369_where(address) if address else {}
            offer = cart._mart369_offer(tmpl, qty, where, variant=tmpl.product_variant_id)
            mode = 'quick' if offer.get('mode') == 'quick' and not out_of_stock else 'express'
            text = offer.get('when') or own
            if not text and 'mart369.delivery.rule' in self.env:
                rules = self.env['mart369.delivery.rule'].sudo()._mart369_rules()
                text = getattr(rules.get('quick' if mode == 'quick' else 'all'), 'eta', '') or ''
            return (mode, text)
        except Exception as err:  # noqa: BLE001
            _logger.info("Sales Automation: delivery line for link %s skipped: %s", self.id, err)
            return None

    def _details_rows(self):
        """Rows for the details table: (label EN, label ZH, value)."""
        self.ensure_one()
        req, product = self.request_id, self._product()
        rows = [(_('Product'), '产品', product.name or req._sa_confirm_name() or ''),
                (_('Reference'), '编号', '#%s' % (req.ref_code or ''))]
        qty = req.qty or 0
        rows.append((_('Quantity'), '数量', ('%d' % int(qty)) if qty else _('to confirm')))
        if product:
            if product.default_code:
                rows.append((_('Internal reference'), '内部编号', product.default_code))
            if product.barcode:
                rows.append((_('Barcode'), '条形码', product.barcode))
            if product.categ_id:
                rows.append((_('Category'), '类别', product.categ_id.complete_name or product.categ_id.name))
            brand = getattr(product, 'brand_id', False)
            if brand:
                rows.append((_('Brand'), '品牌', brand.display_name))
            if self.kind == 'customer':
                price = req.agreed_price or req.quoted_price
                if price:
                    rows.append((_('Price'), '价格', self._money(price)))
            for line in product.attribute_line_ids:
                values = ', '.join(line.value_ids.mapped('name'))
                if values:
                    rows.append((line.attribute_id.name, line.attribute_id.name, values))
            if product.weight:
                rows.append((_('Weight'), '重量', '%.3f %s' % (product.weight, getattr(product, 'weight_uom_name', '') or 'kg')))
            if product.volume:
                rows.append((_('Volume'), '体积', '%.3f %s' % (product.volume, getattr(product, 'volume_uom_name', '') or 'm³')))
            if product.uom_id:
                rows.append((_('Unit'), '单位', product.uom_id.name))
            desc = (product.description_sale or '').strip()
            if desc:
                rows.append((_('Description'), '描述', desc))
        else:
            rows.append((_('Asked for'), '需求', req.ai_search_term or req.raw_text or ''))
        return rows

    # ------------------------------------------------------------------
    # Clicks
    # ------------------------------------------------------------------
    def _record_click(self, action, ip='', user_agent='', token_ok=True):
        self.ensure_one()
        vals = {'link_id': self.id, 'request_id': self.request_id.id, 'kind': self.kind, 'channel': self.channel,
                'partner_id': self.partner_id.id, 'identity': self.identity, 'action': action,
                'ip': (ip or '')[:64], 'user_agent': (user_agent or '')[:300], 'token_ok': token_ok}
        self.env['sa.link.click'].sudo().create(vals)
        if action == 'open':
            self.sudo().write({'opened_on': self.opened_on or fields.Datetime.now(), 'open_count': self.open_count + 1})
        return True

    def _decide(self, action, ip='', user_agent='', later=False):
        """The first ACCEPT / REJECT is final. Returns the outcome key for the page.
        `later`: a customer's price and messages follow after the page moved on
        (the "accepted" task of sales_automation)."""
        self.ensure_one()
        if action not in ('accept', 'reject'):
            self._record_click('open', ip, user_agent)
            return 'open'
        # A double tap sends the same press several times at once. Lock the link
        # first: the second press waits for the first, and Odoo's own retry then
        # runs it again, where it finds the answer recorded (31 Oct 2026).
        self.env.cr.execute('SELECT id FROM %s WHERE id = %%s FOR UPDATE' % self._table, (self.id,))
        self.invalidate_recordset(['decided'])
        # a vendor asked on WhatsApp and on WeChat answers once
        if self.decided or (self.kind == 'vendor' and self._vendor_state() != 'ask'):
            self._record_click('again', ip, user_agent)
            return 'again'
        self.sudo().write({'decided': action, 'decided_on': fields.Datetime.now(),
                           'decided_ip': (ip or '')[:64], 'decided_ua': (user_agent or '')[:300]})
        self._record_click(action, ip, user_agent)
        if later and self.kind == 'customer':
            req = self.request_id.sudo()
            if action == 'accept':
                # the reminders see at once that this customer is active
                req.write({'sa_confirm_accepted_on': fields.Datetime.now()})
            self.env['sa.after.task'].sudo()._queue(req, False, 'accepted', mode=action, ref=self.id)
            return action
        try:
            # savepoint: a failed follow-up must not break the page that follows
            with self.env.cr.savepoint():
                self.request_id.sudo()._sa_confirm_link_decided(self, action)
        except Exception:  # noqa: BLE001 - the decision is recorded; the follow-up is logged
            _logger.exception("Sales Automation: follow-up after %s on link %s failed", action, self.id)
        return action

    # ------------------------------------------------------------------
    # Reminder
    # ------------------------------------------------------------------
    @api.model
    def _cron_confirm_remind(self):
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        minutes = max(1, settings.confirm_remind_minutes or 10)
        cutoff = fields.Datetime.now() - timedelta(minutes=minutes)
        links = self.sudo().search([('kind', '=', 'customer'), ('decided', '=', False), ('reminded_on', '=', False),
                                    ('sent_on', '!=', False), ('sent_on', '<=', cutoff),
                                    ('request_id.state', '=', 'awaiting_confirm')], limit=50)
        for link in links:
            try:
                link.request_id._say(_("Still waiting for you \U0001F642 Please open the link and press "
                                       "ACCEPT if this is the product you want:\n%(url)s\n\n_Ref %(ref)s_",
                                       url=link._url(), ref=link.request_id.ref_code or link.request_id.id))
            except Exception as err:  # noqa: BLE001
                _logger.warning("Sales Automation: confirm reminder for link %s failed: %s", link.id, err)
            link.write({'reminded_on': fields.Datetime.now()})
        return True


class SaConfirmPicture(models.Model):
    """Extra pictures (other shots) for the page gallery: on the product when
    there is one, otherwise on the link."""
    _name = 'sa.confirm.picture'
    _description = 'Product confirmation extra picture'
    _order = 'sequence, id'

    product_tmpl_id = fields.Many2one('product.template', 'Product', ondelete='cascade', index=True)
    link_id = fields.Many2one('sa.confirm.link', 'Link', ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    image = fields.Binary('Picture', attachment=True)
    source = fields.Char('Source')


class SaLinkClick(models.Model):
    _name = 'sa.link.click'
    _description = 'Confirmation link click'
    _order = 'id desc'

    link_id = fields.Many2one('sa.confirm.link', 'Link', required=True, ondelete='cascade', index=True)
    request_id = fields.Many2one('sa.group.request', 'Enquiry', index=True, ondelete='cascade')
    ref_code = fields.Char(related='request_id.ref_code', store=False)
    kind = fields.Selection([('customer', 'Customer'), ('vendor', 'Vendor')], index=True)
    channel = fields.Selection([('whatsapp', 'WhatsApp'), ('wechat', 'WeChat')])
    partner_id = fields.Many2one('res.partner', 'Contact')
    identity = fields.Char('Account')
    action = fields.Selection([('open', 'Opened'), ('accept', 'Accepted'), ('reject', 'Rejected'),
                               ('again', 'Pressed again (ignored)')], required=True, index=True)
    at = fields.Datetime('When', default=fields.Datetime.now, required=True, index=True)
    ip = fields.Char('IP address')
    user_agent = fields.Char('Browser')
    token_ok = fields.Boolean('Valid link', default=True)
