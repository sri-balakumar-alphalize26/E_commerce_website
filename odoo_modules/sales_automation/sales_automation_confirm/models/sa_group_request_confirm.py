# -*- coding: utf-8 -*-
"""The page is the confirmation.

Customer: once a product is matched, ONE chat message goes out - the picture
with a caption that carries the private link. Nothing is priced and no vendor
is asked until ACCEPT is pressed on the page. A YES typed in the chat only
earns a "please tap the link". REJECT walks the existing "that's not it" path.

Vendor (WhatsApp): the price check is the picture + link instead of the
YES / NO poll. ACCEPT on the page = "I have this exact product" and the price
is asked as before; REJECT = "don't have it".
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaGroupRequestConfirm(models.Model):
    _inherit = 'sa.group.request'

    sa_confirm_link_ids = fields.One2many('sa.confirm.link', 'request_id', 'Confirmation links')
    sa_confirm_link_id = fields.Many2one('sa.confirm.link', 'Customer link', copy=False, ondelete='set null')
    sa_confirm_accepted_on = fields.Datetime('Customer accepted the page', copy=False, readonly=True)
    sa_confirm_nudged_on = fields.Datetime('Told to tap the link', copy=False, readonly=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _sa_confirm_settings(self):
        return self.env['sa.ai.settings'].sudo().get_settings()

    def _sa_confirm_commit(self):
        """Kept for compatibility (tests mock it). Committing inside the
        webhook broke Odoo's own retry on a serialization failure, so the
        link is now saved on its own connection instead (see _sa_confirm_new_link)."""
        return True

    def _sa_confirm_new_link(self, vals, reuse_domain):
        """A link row for this enquiry + person, in THIS transaction.

        Written on another connection it was invisible to the request that
        made it (REPEATABLE READ: "Record does not exist" on the very next
        read, and the vendor sends failed). So it is an ordinary create. The
        token is derived from the enquiry, kind and person (see
        `sa.confirm.link._sa_token_for`), so when Odoo retries this request
        after a concurrent update the same token comes out again and the
        message that already went out stays valid; the page keeps retrying
        until the row is committed.
        """
        self.ensure_one()
        Link = self.env['sa.confirm.link'].sudo()
        found = Link.search(reuse_domain + [('request_id', '=', self.id), ('decided', '=', False)], order='id desc', limit=1)
        return found or Link.create(dict(vals, request_id=self.id))

    def _sa_confirm_customer_link(self):
        """The customer's link for this enquiry, made on first use."""
        self.ensure_one()
        if self.sa_confirm_link_id:
            return self.sa_confirm_link_id
        link = self._sa_confirm_new_link({
            'kind': 'customer', 'channel': 'whatsapp',
            'partner_id': self.requester_partner_id.id or False,
            'phone': self.requester_phone or '', 'lid': self.requester_lid or '',
        }, [('kind', '=', 'customer')])
        self.sudo().write({'sa_confirm_link_id': link.id})
        return link

    def _sa_confirm_send_picture(self, caption, destination=None, session=None):
        """Send the picture with the caption, or the caption alone when there
        is no picture. Returns the picture source."""
        self.ensure_one()
        raw, source = self._sa_confirm_picture(fetch=True)
        destination = destination or self._sa_reply_to()
        session = session or self.group_id.session_id
        guard = self.env['sa.outbox.guard'].sudo()
        if not guard.claim('confirm_pic|%s|%s|%s' % (self.id, destination, caption[:60]), 300):
            return source
        sent = False
        if raw:
            try:
                session.send_image(destination, raw, caption=caption)
                sent = True
            except Exception as err:  # noqa: BLE001 - fall back to text below
                _logger.warning("Sales Automation: confirm picture for %s to %s failed: %s", self.id, destination, err)
        if not sent:
            try:
                session.send_message(destination, caption)
            except Exception as err:  # noqa: BLE001
                _logger.warning("Sales Automation: confirm text for %s to %s failed: %s", self.id, destination, err)
        return source

    # ------------------------------------------------------------------
    # Customer
    # ------------------------------------------------------------------
    def _sa_confirm_customer_send(self, text_only=False):
        """The picture + link message to the customer (once)."""
        self.ensure_one()
        link = self._sa_confirm_customer_link()
        name = (self._sa_confirm_name() if getattr(self, 'sa_variant_id', False) else '') or self.product_id.name or self._sa_confirm_name() or _("this item")
        caption = _("\U0001F4E6 *%(product)s*\n"
                    "Please check the photo and details, then press ACCEPT:\n"
                    "%(url)s\n\n_Ref %(ref)s_",
                    product=name, url=link._url(), ref=self.ref_code or self.id)
        self._sa_stamp_asked()
        if text_only:
            self._say(caption)
            source = 'local' if self.product_id.image_1920 else 'none'
            source = self._sa_confirm_picture(fetch=True)[1] if source == 'none' else source
        else:
            source = self._sa_confirm_send_picture(self._sa_addressed(caption))
        link.sudo().write({'sent_on': link.sent_on or fields.Datetime.now(), 'image_source': source})
        return True

    def _ask_confirmation(self):
        """The picture + link instead of the YES / NO poll."""
        self.ensure_one()
        if not (self._sa_confirm_settings().confirm_enabled and self.product_id):
            return super()._ask_confirmation()
        self.state = 'awaiting_confirm'
        self._sa_confirm_customer_send()
        return True

    def _on_confirmed(self):
        """Gate: nothing is priced or sourced until the page's ACCEPT."""
        self.ensure_one()
        settings = self._sa_confirm_settings()
        if not settings.confirm_enabled or not (self.product_id or self._sa_confirm_name()) \
                or self.sa_confirm_accepted_on or self.env.context.get('sa_confirm_accepted'):
            return super()._on_confirmed()
        if self.state != 'awaiting_confirm':
            self.state = 'awaiting_confirm'
        link = self.sa_confirm_link_id
        if not link or not link.sent_on:
            # The finder already showed the picture; a text link is enough there.
            return self._sa_confirm_customer_send(text_only=bool(self.finder_locked))
        # A YES typed in the chat: point at the link, once.
        if not self.sa_confirm_nudged_on:
            self.sudo().write({'sa_confirm_nudged_on': fields.Datetime.now()})
            self._say(_("Please press ACCEPT on the page to confirm \U0001F447\n%(url)s\n\n_Ref %(ref)s_",
                        url=link._url(), ref=self.ref_code or self.id))
        return True

    def _sa_confirm_link_decided(self, link, action):
        """Called by the page after the first ACCEPT / REJECT was recorded."""
        self.ensure_one()
        if link.kind == 'customer':
            finder = self.state == 'finding' and self.finder_step == 'confirm'
            if action == 'accept':
                self.sudo().write({'sa_confirm_accepted_on': fields.Datetime.now()})
                self._say(_("✅ Confirmed - getting your price now.\n\n_Ref %(ref)s_",
                            ref=self.ref_code or self.id))
                if finder:
                    return self.with_context(sa_confirm_accepted=True)._finder_finish()
                if self.state == 'awaiting_confirm':
                    return self.with_context(sa_confirm_accepted=True)._on_confirmed()
                return True
            if finder:
                self._say(_("Noted - that is not it. Pick again below.\n\n_Ref %(ref)s_", ref=self.ref_code or self.id))
                return self._finder_back()
            self._say(_("Noted - that is not it. Checking what you asked for instead.\n\n_Ref %(ref)s_",
                        ref=self.ref_code or self.id))
            if self.state == 'awaiting_confirm':
                return self.with_context(sa_confirm_accepted=True)._reject_match()
            return True
        # vendor
        if link.channel == 'wechat':
            return self.env['sa.wechat.message'].sudo()._sa_page_confirm(link, action)
        session = self.group_id.employee_session_id.session_id or self.group_id.session_id
        phone = ''.join(ch for ch in (link.phone or link.partner_id.phone or '') if ch.isdigit())
        if action == 'accept':
            if link.partner_id and link.partner_id not in self.sa_vendor_yes_ids:
                self.sudo().write({'sa_vendor_yes_ids': [(4, link.partner_id.id)]})
            return self._sa_ask_vendor_price(session, phone)
        return self._sa_vendor_has_none(session, phone, link.partner_id)

    # ------------------------------------------------------------------
    # Vendor (WhatsApp)
    # ------------------------------------------------------------------
    def _sa_ask_vendor_confirm(self, session, vendor, name, qty, ask):
        """The picture + link price check. True = sent, the YES / NO poll is skipped."""
        self.ensure_one()
        if not self._sa_confirm_settings().confirm_vendor_enabled:
            return False
        phone = ''.join(ch for ch in (vendor.phone or '') if ch.isdigit())
        if not phone:
            return False
        Link = self.env['sa.confirm.link'].sudo()
        link = Link.search([('request_id', '=', self.id), ('kind', '=', 'vendor'),
                            ('partner_id', '=', vendor.id), ('channel', '=', 'whatsapp')], limit=1)
        if not link:
            link = self._sa_confirm_new_link({'kind': 'vendor', 'channel': 'whatsapp', 'partner_id': vendor.id, 'phone': phone},
                                             [('kind', '=', 'vendor'), ('partner_id', '=', vendor.id), ('channel', '=', 'whatsapp')])
        caption = _("\U0001F50E *Price check #%(ref)s*\n*%(product)s*%(qty)s\n"
                    "See the details and press ACCEPT if you have this exact product:\n%(url)s",
                    ref=self.ref_code, product=(self._sa_confirm_name() or name),
                    qty=(' x %d' % int(qty)) if qty else '', url=link._url())
        source = self._sa_confirm_send_picture(caption, destination=phone, session=session)
        link.write({'sent_on': link.sent_on or fields.Datetime.now(), 'image_source': source})
        return True

    def _sa_vendor_link_for(self, phone):
        """This vendor's WhatsApp link on this enquiry, if one was made."""
        self.ensure_one()
        vendor = self._sa_vendor_by_phone(phone)
        if not vendor:
            return self.env['sa.confirm.link']
        return self.env['sa.confirm.link'].sudo().search(
            [('request_id', '=', self.id), ('kind', '=', 'vendor'),
             ('channel', '=', 'whatsapp'), ('partner_id', '=', vendor.id)],
            order='id desc', limit=1)

    def _sa_vendor_confirmed(self, phone):
        """ACCEPT on the page counts as their YES."""
        self.ensure_one()
        if super()._sa_vendor_confirmed(phone):
            return True
        return self._sa_vendor_link_for(phone).decided == 'accept'

    def _sa_vendor_confirm_first_text(self, phone):
        """With the page on: send them back to it, link included. A link lost
        to a rolled-back request is made again; its token comes out the same,
        so the one already in their chat starts working too."""
        self.ensure_one()
        if not self._sa_confirm_settings().confirm_vendor_enabled:
            return super()._sa_vendor_confirm_first_text(phone)
        vendor = self._sa_vendor_by_phone(phone)
        link = self._sa_vendor_link_for(phone)
        if link.decided == 'reject':
            return _("You pressed REJECT for this product, so no price is needed. "
                     "Thank you \U0001F44D")
        if not link and vendor:
            digits = ''.join(ch for ch in (vendor.phone or phone or '') if ch.isdigit())
            link = self._sa_confirm_new_link(
                {'kind': 'vendor', 'channel': 'whatsapp', 'partner_id': vendor.id, 'phone': digits},
                [('kind', '=', 'vendor'), ('partner_id', '=', vendor.id), ('channel', '=', 'whatsapp')])
            link.write({'sent_on': link.sent_on or fields.Datetime.now()})
        if not link:
            return super()._sa_vendor_confirm_first_text(phone)
        return _("⚠️ Please check the product first and tap "
                 "*✔ ACCEPT* if you have this exact product:\n%(url)s\n\n"
                 "Then send your price, for example *#%(ref)s 450*.",
                 url=link._url(), ref=self.ref_code)
