import base64
import logging
import traceback
import pytz

from io import BytesIO
from odoo import models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')

# === Pillow for card image generation ===
try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
    _logger.info('LOYALTY WA: Pillow is available for card image generation')
except ImportError:
    PILLOW_AVAILABLE = False
    _logger.warning('LOYALTY WA: Pillow NOT installed! Run: pip install Pillow')

# === python-barcode for barcode generation ===
try:
    from barcode import Code128
    from barcode.writer import ImageWriter
    BARCODE_LIB_AVAILABLE = True
except ImportError:
    BARCODE_LIB_AVAILABLE = False
    _logger.warning('LOYALTY WA: python-barcode NOT installed! Run: pip install python-barcode')


class LoyaltyWhatsAppService(models.AbstractModel):
    _name = 'pos.loyalty.whatsapp.service'
    _description = 'Loyalty WhatsApp Service (Neonize)'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _to_ist(self, dt):
        """Convert a UTC datetime to Indian Standard Time string."""
        if not dt:
            return ''
        utc_dt = dt.replace(tzinfo=pytz.UTC)
        ist_dt = utc_dt.astimezone(IST)
        return ist_dt.strftime('%d-%m-%Y %I:%M %p')

    @api.model
    def _shop_name(self):
        """Business name for customer messages (Loyalty Settings, fallback company)."""
        try:
            cfg = self.env['pos.loyalty.card.settings'].get_settings()
            name = (cfg.card_company_name or '').strip()
        except Exception:
            name = ''
        return name or (self.env.company.name or '')

    @api.model
    def _shop_header(self):
        """Header: shop name (centered) + divider + one blank line."""
        name = self._shop_name()
        if not name:
            return ''
        pad = max(0, (24 - len(name)) // 2)
        return "%s*%s*\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n" % (
            ' ' * pad, name)

    @api.model
    def _get_whatsapp_session(self):
        """Get the first connected WhatsApp neonize session.

        Checks both the whatsapp.config POS session setting and falls back
        to any connected session for the current company.
        The neonize session's send_message/send_image/send_document methods
        already verify the in-memory client, so we only check DB status here.
        Returns: whatsapp.session record or False
        """
        if 'whatsapp.session' not in self.env:
            return False
        # Try POS-specific session from whatsapp.config
        try:
            config = self.env['whatsapp.config'].sudo().get_config()
            if config.pos_session_id:
                _logger.info('LOYALTY WA: Using POS config session: %s (status=%s)',
                             config.pos_session_id.name, config.pos_session_id.status)
                return config.pos_session_id
        except Exception as e:
            _logger.info('LOYALTY WA: No POS config session: %s', e)

        # Fallback: find any connected session for this company
        session = self.env['whatsapp.session'].sudo().search([
            ('status', '=', 'connected'),
            '|',
            ('company_id', '=', self.env.company.id),
            ('company_id', '=', False),
        ], limit=1)

        if not session:
            # Try any connected session at all
            session = self.env['whatsapp.session'].sudo().search([
                ('status', '=', 'connected'),
            ], limit=1)

        if not session:
            _logger.warning('LOYALTY WA: No connected WhatsApp neonize session found')
            return False

        _logger.info('LOYALTY WA: Found session: %s (ID=%s, status=%s)',
                     session.name, session.id, session.status)
        return session

    @api.model
    def _clean_phone(self, phone):
        """Clean phone number for neonize: digits only, with country code.

        Neonize/WhatsApp expects <dial><local> (no + sign, no spaces). The dial
        code and local length come from the global Loyalty Settings, so this
        follows the configured country.
        """
        if not phone:
            return ''
        cfg = self.env['pos.loyalty.card.settings'].get_settings()
        dial = ''.join(filter(str.isdigit, cfg.country_dial_code or '')) or '91'
        n = cfg.mobile_number_length or 10
        # Remove all non-digit characters
        clean = ''.join(filter(str.isdigit, str(phone)))
        if not clean:
            return ''
        # Normalize to <dial><local> format
        if len(clean) == n:
            clean = dial + clean
        elif len(clean) == n + 1 and clean.startswith('0'):
            clean = dial + clean[1:]
        elif clean.startswith(dial) and len(clean) == len(dial) + n:
            pass  # Already correct
        elif not clean.startswith(dial):
            clean = dial + clean
        return clean

    # ------------------------------------------------------------------
    # Low-level send methods using Neonize whatsapp.session
    # ------------------------------------------------------------------

    @api.model
    def _send_text(self, phone, message):
        """Send a plain text WhatsApp message via neonize session."""
        session = self._get_whatsapp_session()
        if not session:
            _logger.warning('LOYALTY WA: No active neonize session, cannot send text')
            return False

        clean_phone = self._clean_phone(phone)
        if not clean_phone:
            _logger.warning('LOYALTY WA: Invalid phone: %s', phone)
            return False

        try:
            _logger.info('LOYALTY WA: Sending text to %s via neonize session %s',
                         clean_phone, session.name)
            session.send_message(clean_phone, message)
            _logger.info('LOYALTY WA: Text sent OK to %s', clean_phone)
            return True
        except UserError as e:
            _logger.error('LOYALTY WA: Text send FAILED to %s: %s', clean_phone, e)
            return False
        except Exception as e:
            _logger.error('LOYALTY WA: Text send FAILED to %s: %s', clean_phone, e)
            return False

    @api.model
    def _send_image(self, phone, image_base64, caption=''):
        """Send an image via WhatsApp using neonize session.send_image().

        Args:
            phone: Phone number (any format, will be cleaned)
            image_base64: Base64 encoded image string
            caption: Optional caption text
        Returns: True on success, False on failure
        """
        session = self._get_whatsapp_session()
        if not session:
            _logger.warning('LOYALTY WA: No active neonize session, cannot send image')
            return False

        clean_phone = self._clean_phone(phone)
        if not clean_phone:
            _logger.warning('LOYALTY WA: Invalid phone: %s', phone)
            return False

        try:
            # Clean base64 string (accept bytes; remove data URI prefix if present)
            raw_b64 = image_base64
            if isinstance(raw_b64, bytes):
                raw_b64 = raw_b64.decode()
            if raw_b64.startswith('data:'):
                raw_b64 = raw_b64.split(',', 1)[1] if ',' in raw_b64 else raw_b64

            _logger.info('LOYALTY WA: Sending image to %s via neonize (%d chars b64)',
                         clean_phone, len(raw_b64))
            # session.send_image expects base64 string or bytes
            session.send_image(clean_phone, raw_b64, caption=caption)
            _logger.info('LOYALTY WA: Image sent OK to %s', clean_phone)
            return True
        except UserError as e:
            _logger.error('LOYALTY WA: Image send FAILED to %s: %s', clean_phone, e)
            return False
        except Exception as e:
            _logger.error('LOYALTY WA: Image send FAILED to %s: %s', clean_phone, e)
            return False

    @api.model
    def _send_document(self, phone, file_base64, filename, caption='', mimetype='application/pdf'):
        """Send a document (PDF, etc.) via WhatsApp using neonize session.send_document().

        Args:
            phone: Phone number (any format, will be cleaned)
            file_base64: Base64 encoded file string
            filename: Filename for the document
            caption: Optional caption text
            mimetype: MIME type of the document
        Returns: True on success, False on failure
        """
        session = self._get_whatsapp_session()
        if not session:
            _logger.warning('LOYALTY WA: No active neonize session, cannot send document')
            return False

        clean_phone = self._clean_phone(phone)
        if not clean_phone:
            _logger.warning('LOYALTY WA: Invalid phone: %s', phone)
            return False

        try:
            # Clean base64 string (accept bytes; remove data URI prefix if present)
            raw_b64 = file_base64
            if isinstance(raw_b64, bytes):
                raw_b64 = raw_b64.decode()
            if raw_b64.startswith('data:'):
                raw_b64 = raw_b64.split(',', 1)[1] if ',' in raw_b64 else raw_b64

            _logger.info('LOYALTY WA: Sending document "%s" to %s via neonize',
                         filename, clean_phone)
            # session.send_document expects base64 string or bytes
            session.send_document(clean_phone, raw_b64, filename, caption, mimetype)
            _logger.info('LOYALTY WA: Document sent OK to %s', clean_phone)
            return True
        except UserError as e:
            _logger.error('LOYALTY WA: Document send FAILED to %s: %s', clean_phone, e)
            return False
        except Exception as e:
            _logger.error('LOYALTY WA: Document send FAILED to %s: %s', clean_phone, e)
            return False

    # ------------------------------------------------------------------
    # Card Image Generation using Pillow
    # ------------------------------------------------------------------

    @api.model
    def _get_font(self, size, bold=False):
        """Get a TTF font. Tries Windows then Linux paths."""
        if bold:
            paths = [
                'C:/Windows/Fonts/arialbd.ttf',
                'C:/Windows/Fonts/calibrib.ttf',
                'C:/Windows/Fonts/segoeui.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
                '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
            ]
        else:
            paths = [
                'C:/Windows/Fonts/arial.ttf',
                'C:/Windows/Fonts/calibri.ttf',
                'C:/Windows/Fonts/segoeui.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
            ]
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except (IOError, OSError):
                continue
        # Last fallback
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    @api.model
    def _get_mono_font(self, size):
        """Get a monospace font for barcode text."""
        paths = [
            'C:/Windows/Fonts/consola.ttf',
            'C:/Windows/Fonts/cour.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
        ]
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except (IOError, OSError):
                continue
        return self._get_font(size, bold=False)

    @api.model
    def _generate_loyalty_card_image(self, card, full=False):
        """
        Generate loyalty card as PNG image using Pillow.
        Returns base64 encoded PNG string or False.

        Design matches the QWeb report:
        - Dark blue (#1a237e) background with rounded corners
        - Gold "LOYALTY CARD" title
        - Card number, status, customer name
        - SINCE date
        - Barcode in white box
        - Company name top-right
        """
        if not PILLOW_AVAILABLE:
            _logger.error('LOYALTY WA IMAGE: Pillow NOT available!')
            _logger.error('LOYALTY WA IMAGE: Please run: pip install Pillow')
            return False

        if not card.exists():
            _logger.error('LOYALTY WA IMAGE: Card does not exist')
            return False

        _logger.info('LOYALTY WA IMAGE: === GENERATING for %s (ID=%s) ===',
                     card.card_number, card.id)

        try:
            # ---- Settings: colours + sizes (mm); image scales with the card ----
            cfg = self.env['pos.loyalty.card.settings'].get_settings()

            def _hex(h, dflt):
                try:
                    h = (h or '').lstrip('#')
                    if len(h) == 3:
                        h = ''.join(c * 2 for c in h)
                    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
                except Exception:
                    return dflt

            cw = cfg.card_width or 86.0
            ch = cfg.card_height or 54.0
            PPMM = 10.0
            W = int(round(cw * PPMM))
            H = int(round(ch * PPMM))
            R = max(6, int(round(min(W, H) * 0.05)))

            def _f(mm, fb, bold=False):
                return self._get_font(max(8, int(round((mm or fb) * PPMM))), bold=bold)

            WHITE = (255, 255, 255)
            DARK = (51, 51, 51)
            BG = _hex(cfg.background_color, (26, 35, 126))
            c_company = _hex(cfg.company_color, (255, 215, 0))
            c_title = _hex(cfg.title_color, (255, 215, 0))
            c_number = _hex(cfg.text_color, (255, 255, 255))
            c_active = _hex(cfg.status_color, (76, 175, 80))
            c_susp = (244, 67, 54)
            c_name = _hex(cfg.name_color, (224, 224, 224))
            c_since = _hex(cfg.since_color, (170, 170, 170))
            c_points = _hex(cfg.points_color, (255, 215, 0))

            f_company = _f(cfg.company_font_size, 5.0, bold=True)
            f_title = _f(cfg.title_font_size, 4.0, bold=True)
            f_number = _f(cfg.number_font_size, 6.0, bold=True)
            f_status = _f(cfg.status_font_size, 3.5, bold=True)
            f_name = _f(cfg.name_font_size, 4.0)
            f_since = _f(cfg.since_font_size, 2.5)
            f_points = _f(cfg.points_font_size, 3.5, bold=True)
            f_mono = self._get_mono_font(max(10, int(H * 0.032)))

            img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            bg = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            if full:
                ImageDraw.Draw(bg).rectangle([(0, 0), (W - 1, H - 1)], fill=BG)
            else:
                ImageDraw.Draw(bg).rounded_rectangle([(0, 0), (W - 1, H - 1)], radius=R, fill=BG)
            img = Image.alpha_composite(img, bg)
            d = ImageDraw.Draw(img)

            PAD = int(W * 0.045)
            y = int(H * 0.05)

            # ---- Company name: big, centered, top ----
            co = (cfg.card_company_name or '').strip() or (card.company_id.name if card.company_id else '')
            if co:
                bb = d.textbbox((0, 0), co, font=f_company)
                d.text(((W - (bb[2] - bb[0])) // 2, y), co, fill=c_company, font=f_company)
                y += (bb[3] - bb[1]) + int(H * 0.035)

            # ---- LOYALTY CARD (below, left) ----
            d.text((PAD, y), 'LOYALTY CARD', fill=c_title, font=f_title)
            tb = d.textbbox((0, 0), 'LOYALTY CARD', font=f_title)
            y += (tb[3] - tb[1]) + int(H * 0.02)

            # ---- Card number ----
            d.text((PAD, y), card.card_number or '', fill=c_number, font=f_number)
            nb = d.textbbox((0, 0), card.card_number or 'X', font=f_number)
            y += (nb[3] - nb[1]) + int(H * 0.02)

            # ---- Status ----
            state_map = dict(card._fields['state'].selection)
            slabel = state_map.get(card.state, 'NEW').upper()
            d.text((PAD, y), slabel, fill=(c_susp if card.state == 'suspended' else c_active), font=f_status)
            sb = d.textbbox((0, 0), slabel, font=f_status)
            y += (sb[3] - sb[1]) + int(H * 0.015)

            # ---- Customer name ----
            cname = (card.name or '').upper()
            if len(cname) > 22:
                cname = cname[:22] + '...'
            d.text((PAD, y), cname, fill=c_name, font=f_name)

            # ---- Barcode: fixed bottom-right, high-res / scannable ----
            bc_done = False
            box_w = int(W * 0.36)
            box_h = int(H * 0.30)
            bx = W - PAD - box_w
            by = H - int(H * 0.06) - box_h
            if card.card_number and card.card_number != 'New' and BARCODE_LIB_AVAILABLE:
                try:
                    bio = BytesIO()
                    Code128(card.card_number, writer=ImageWriter()).write(bio, {
                        'module_width': 0.5,
                        'module_height': 15.0,
                        'quiet_zone': 6.0,
                        'font_size': 0,
                        'write_text': False,
                    })
                    bio.seek(0)
                    bc_img = Image.open(bio).convert('RGBA')
                    inner_w = box_w - int(box_w * 0.12)
                    asp = bc_img.height / bc_img.width
                    inner_h = int(inner_w * asp)
                    max_h = box_h - int(box_h * 0.34)
                    if inner_h > max_h:
                        inner_h = max_h
                        inner_w = int(inner_h / asp)
                    bc_img = bc_img.resize((inner_w, inner_h), Image.LANCZOS)
                    d.rounded_rectangle([(bx, by), (bx + box_w, by + box_h)],
                                        radius=int(box_h * 0.12), fill=WHITE)
                    img.paste(bc_img, (bx + (box_w - inner_w) // 2, by + int(box_h * 0.12)), bc_img)
                    nbb = d.textbbox((0, 0), card.card_number, font=f_mono)
                    d.text((bx + (box_w - (nbb[2] - nbb[0])) // 2, by + int(box_h * 0.12) + inner_h + 2),
                           card.card_number, fill=DARK, font=f_mono)
                    bc_done = True
                except Exception as e:
                    _logger.warning('LOYALTY WA IMAGE: Barcode error: %s', e)
            if not bc_done and card.card_number:
                d.rounded_rectangle([(bx, by), (bx + box_w, by + box_h)], radius=12, fill=WHITE)
                nbb = d.textbbox((0, 0), card.card_number, font=f_number)
                d.text((bx + (box_w - (nbb[2] - nbb[0])) // 2, by + box_h // 3),
                       card.card_number, fill=DARK, font=f_number)

            # ---- SINCE + POINTS: bottom-left (won't move the barcode) ----
            yb = H - int(H * 0.06)
            pts_txt = 'POINTS: %d' % int(round(card.total_points or 0))
            pb = d.textbbox((0, 0), pts_txt, font=f_points)
            yb -= (pb[3] - pb[1])
            d.text((PAD, yb), pts_txt, fill=c_points, font=f_points)
            since = card.registration_date.strftime('%b %Y') if card.registration_date else ''
            since_txt = 'SINCE: %s' % since
            zb = d.textbbox((0, 0), since_txt, font=f_since)
            yb -= (zb[3] - zb[1]) + int(H * 0.01)
            d.text((PAD, yb), since_txt, fill=c_since, font=f_since)

            # Convert RGBA → RGB (smaller file, WhatsApp compatible)
            rgb = Image.new('RGB', img.size, WHITE)
            rgb.paste(img, mask=img.split()[3])

            out = BytesIO()
            rgb.save(out, format='PNG', optimize=True)
            png_b64 = base64.b64encode(out.getvalue()).decode('utf-8')

            _logger.info('LOYALTY WA IMAGE: SUCCESS - %d bytes for card %s',
                         len(out.getvalue()), card.card_number)
            return png_b64

        except Exception as e:
            _logger.error('LOYALTY WA IMAGE: FAILED: %s', e)
            _logger.error(traceback.format_exc())
            return False

    # ------------------------------------------------------------------
    # High-level: Send card image
    # ------------------------------------------------------------------

    @api.model
    def send_loyalty_card_image(self, card_id):
        """Generate and send loyalty card as PNG image via WhatsApp (neonize)."""
        card = self.env['pos.loyalty.card'].browse(card_id)
        if not card.exists() or not card.phone:
            _logger.warning('LOYALTY WA: No card or phone for ID %s', card_id)
            return False

        _logger.info('LOYALTY WA: === SEND CARD IMAGE for %s to %s ===',
                     card.card_number, card.phone)

        img_b64 = self._generate_loyalty_card_image(card)
        if not img_b64:
            _logger.error('LOYALTY WA: Image generation FAILED for %s', card.card_number)
            return False

        caption = "🪪 Your Loyalty Card – %s" % card.card_number

        # Send using neonize session.send_image()
        result = self._send_image(card.phone, img_b64, caption)

        if result:
            _logger.info('LOYALTY WA: Card image SENT to %s', card.phone)
        else:
            _logger.error('LOYALTY WA: Card image FAILED to send to %s', card.phone)

        return result

    # ------------------------------------------------------------------
    # High-level: Send PDF (legacy, kept as fallback)
    # ------------------------------------------------------------------

    @api.model
    def send_loyalty_card_pdf(self, card_id):
        """Generate and send loyalty card PDF via neonize."""
        card = self.env['pos.loyalty.card'].browse(card_id)
        if not card.exists() or not card.phone:
            return False

        try:
            report_result = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                'pos_loyalty_card.action_report_loyalty_card',
                [card.id],
            )
            pdf_content = report_result[0]
            if pdf_content and len(pdf_content) > 100:
                pdf_b64 = base64.b64encode(pdf_content).decode('utf-8')
                caption = "🪪 Your Loyalty Card – %s" % card.card_number
                filename = "Loyalty_Card_%s.pdf" % card.card_number
                return self._send_document(card.phone, pdf_b64, filename, caption,
                                           mimetype='application/pdf')
        except Exception as e:
            _logger.error('LOYALTY WA PDF: Failed: %s', e)

        return False

    # ------------------------------------------------------------------
    # High-level: Welcome flow (called on card activation)
    # ------------------------------------------------------------------

    @api.model
    def _store_card_image(self, card, img_b64, event_type):
        """Save a card image snapshot for history / gallery / download."""
        if not img_b64:
            return False
        try:
            return self.env['pos.loyalty.card.image'].sudo().create({
                'card_id': card.id,
                'image': img_b64,
                'points': card.total_points or 0.0,
                'event_type': event_type,
            })
        except Exception as e:
            _logger.error('LOYALTY WA: store card image failed for %s: %s', card.card_number, e)
            return False

    @api.model
    def send_new_card_welcome(self, card_id):
        """
        Send welcome text + loyalty card IMAGE to new customer via neonize.
        Called from action_activate() and create().
        """
        card = self.env['pos.loyalty.card'].browse(card_id)
        if not card.exists() or not card.phone:
            _logger.warning('LOYALTY WA: Cannot send welcome - no card/phone for ID %s', card_id)
            return False

        _logger.info('LOYALTY WA: ====== WELCOME FLOW START: %s (%s) ======',
                     card.card_number, card.phone)

        # ---- Step 1: Welcome text message (configurable template) ----
        cfg = self.env['pos.loyalty.card.settings'].get_settings()
        welcome_msg = cfg.render_welcome(
            card.name, card.card_number, card.phone, int(round(card.total_points or 0)))
        welcome_msg = "%s%s" % (self._shop_header(), welcome_msg)
        text_ok = self._send_text(card.phone, welcome_msg)
        _logger.info('LOYALTY WA: Welcome text: %s', 'OK' if text_ok else 'FAILED')

        # ---- Step 2: Generate + SAVE + SEND the card image (rounded, visiting-card look) ----
        _logger.info('LOYALTY WA: Generating card image for %s...', card.card_number)
        img_b64 = self._generate_loyalty_card_image(card)
        if img_b64:
            self._store_card_image(card, img_b64, 'creation')
            try:
                self._send_image(card.phone, img_b64,
                                 caption='\U0001FAAA Your Loyalty Card - %s' % card.card_number)
            except Exception as e:
                _logger.error('LOYALTY WA: welcome image send failed: %s', e)
            _logger.info('LOYALTY WA: Card image sent for %s', card.card_number)
        else:
            _logger.error('LOYALTY WA: Image generation FAILED for %s', card.card_number)

        # ---- Step 3: Send the loyalty card as a PDF (same as email/print) ----
        if cfg.whatsapp_send_card_pdf:
            try:
                pdf, _ct = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                    'pos_loyalty_card.action_report_loyalty_card', [card.id])
                if pdf:
                    self._send_document(
                        card.phone, base64.b64encode(pdf).decode(),
                        'LoyaltyCard_%s.pdf' % (card.card_number or card.id),
                        caption='', mimetype='application/pdf')
                    _logger.info('LOYALTY WA: Card PDF sent for %s', card.card_number)
            except Exception as e:
                _logger.error('LOYALTY WA: welcome PDF send failed: %s', e)
        else:
            _logger.info('LOYALTY WA: Card PDF send disabled in settings, skipping')

        _logger.info('LOYALTY WA: ====== WELCOME FLOW END: %s ======', card.card_number)
        return True

    @api.model
    def _send_card_text_fallback(self, card):
        """Send card details as text when image/PDF fails."""
        msg = (
            "🪪 *Your Loyalty Card Details*\n\n"
            "Card Number: *%s*\n"
            "Name: %s\n"
            "Phone: %s\n\n"
            "Please save this card number for future reference."
        ) % (card.card_number, card.name, card.phone)
        self._send_text(card.phone, msg)

    # ------------------------------------------------------------------
    # Order Receipt
    # ------------------------------------------------------------------

    @api.model
    def send_order_receipt(self, order_id):
        """Send order receipt summary via WhatsApp (neonize)."""
        order = self.env['pos.order'].browse(order_id)
        if not order.exists() or not order.loyalty_card_id:
            return False

        card = order.loyalty_card_id
        if not card.phone:
            _logger.warning('LOYALTY WA: No phone on card %s for order %s',
                            card.card_number, order.name)
            return False

        _logger.info('LOYALTY WA: Sending receipt for %s to card %s',
                     order.name, card.card_number)

        # Build order lines
        lines_text = ""
        for line in order.lines:
            if line.customer_note == 'LOYALTY_DISCOUNT':
                continue
            product_name = line.full_product_name or line.product_id.display_name or ''
            lines_text += "  • %s × %g = ₹%.2f\n" % (product_name, line.qty, line.price_subtotal_incl)

        points_earned = order.loyalty_points_earned or 0
        points_redeemed = order.loyalty_points_redeemed or 0
        discount_amount = order.loyalty_discount_amount or 0

        card.invalidate_recordset(['total_points'])
        current_balance = card.total_points

        # Payments
        payment_text = ""
        for payment in order.payment_ids:
            if not payment.is_change:
                payment_text += "  💳 %s: ₹%.2f\n" % (
                    payment.payment_method_id.name, payment.amount)

        change_text = ""
        if order.amount_return > 0:
            change_text = "  🔄 Change: ₹%.2f\n" % order.amount_return

        msg = (
            "🧾 *Purchase Receipt*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📋 *Order:* %(order_name)s\n"
            "📅 *Date:* %(date)s\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "*Items:*\n%(lines)s\n"
        ) % {
            'order_name': order.name or order.pos_reference or '',
            'date': self._to_ist(order.date_order),
            'lines': lines_text,
        }

        if points_redeemed > 0 and discount_amount > 0:
            msg += "🎁 *Loyalty Discount:* -₹%.2f (%d pts)\n\n" % (discount_amount, points_redeemed)

        msg += (
            "*Total: ₹%(total).2f*\n\n"
            "%(payments)s"
            "%(change)s"
            "━━━━━━━━━━━━━━━━━━\n"
            "⭐ *LOYALTY CARD*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🪪 Card: %(card_number)s\n"
            "👤 Member: %(member)s\n"
        ) % {
            'total': order.amount_total,
            'payments': payment_text,
            'change': change_text,
            'card_number': card.card_number,
            'member': card.name,
        }

        if points_earned > 0:
            msg += "✅ Points Earned: +%d\n" % round(points_earned)
        if points_redeemed > 0:
            msg += "🔻 Points Redeemed: -%d\n" % round(points_redeemed)

        msg += (
            "💰 *Point Balance: %(balance)d pts*\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Thank you for shopping with us! 🙏"
        ) % {
            'balance': round(current_balance),
        }

        msg = "%s%s" % (self._shop_header(), msg)
        sent = self._send_text(card.phone, msg)
        # Generate the FULL card image (updated points, no white corners) + send it in-chat.
        try:
            img_b64 = self._generate_loyalty_card_image(card, full=True)
            if img_b64:
                self._store_card_image(card, img_b64, 'order')
                cap = '\U0001FAAA %s   ⭐ Points: %d' % (
                    card.card_number, int(round(card.total_points or 0)))
                if points_earned > 0:
                    cap += '  (+%d)' % round(points_earned)
                self._send_image(card.phone, img_b64, cap)
        except Exception as e:
            _logger.error('LOYALTY WA: order card image send failed: %s', e)
        return sent

    # ------------------------------------------------------------------
    # Send simple receipt (when loyalty is OFF - no points info)
    # ------------------------------------------------------------------

    @api.model
    def send_order_receipt_simple(self, order_id):
        """Send order receipt via WhatsApp WITHOUT loyalty points info.
        Used when loyalty is disabled but customer is linked."""
        order = self.env['pos.order'].browse(order_id)
        if not order.exists():
            return False

        # Get phone from loyalty card or partner (customer-only mode)
        phone = None
        if order.loyalty_card_id and order.loyalty_card_id.phone:
            phone = order.loyalty_card_id.phone
        elif order.partner_id and order.partner_id.phone:
            phone = order.partner_id.phone
        elif order.partner_id and hasattr(order.partner_id, 'mobile') and order.partner_id.mobile:
            phone = order.partner_id.mobile

        if not phone:
            _logger.warning('LOYALTY WA: No phone for simple receipt on order %s', order.name)
            return False

        _logger.info('LOYALTY WA: Sending simple receipt for %s to %s', order.name, phone)

        # Build order lines
        lines_text = ""
        for line in order.lines:
            if line.customer_note == 'LOYALTY_DISCOUNT':
                continue
            product_name = line.full_product_name or line.product_id.display_name or ''
            lines_text += "  • %s × %g = ₹%.2f\n" % (product_name, line.qty, line.price_subtotal_incl)

        # Payments
        payment_text = ""
        for payment in order.payment_ids:
            if not payment.is_change:
                payment_text += "  💳 %s: ₹%.2f\n" % (
                    payment.payment_method_id.name, payment.amount)

        change_text = ""
        if order.amount_return > 0:
            change_text = "  🔄 Change: ₹%.2f\n" % order.amount_return

        customer_name = ''
        if order.loyalty_card_id:
            customer_name = order.loyalty_card_id.name
        elif order.partner_id:
            customer_name = order.partner_id.name

        msg = (
            "🧾 *Purchase Receipt*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📋 *Order:* %(order_name)s\n"
            "📅 *Date:* %(date)s\n"
        ) % {
            'order_name': order.name or order.pos_reference or '',
            'date': self._to_ist(order.date_order),
        }

        if customer_name:
            msg += "👤 *Customer:* %s\n" % customer_name

        msg += (
            "━━━━━━━━━━━━━━━━━━\n\n"
            "*Items:*\n%(lines)s\n"
            "*Total: ₹%(total).2f*\n\n"
            "%(payments)s"
            "%(change)s"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Thank you for shopping with us! 🙏"
        ) % {
            'lines': lines_text,
            'total': order.amount_total,
            'payments': payment_text,
            'change': change_text,
        }

        msg = "%s%s" % (self._shop_header(), msg)
        return self._send_text(phone, msg)
