"""Drawing the loyalty card: the picture that is printed, stored in Card Images
and attached to the card email.

It used to live in the WhatsApp service, which sent it. WhatsApp went out of
this module in 19.0.2.0.0 (the shop has its own WhatsApp connector); the drawing
stayed, because printing and emailing a card still need it.
"""

import base64
import logging
import traceback

from io import BytesIO
from odoo import models, api

_logger = logging.getLogger(__name__)

# === Pillow for card image generation ===
try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
    _logger.info('LOYALTY CARD: Pillow is available for card image generation')
except ImportError:
    PILLOW_AVAILABLE = False
    _logger.warning('LOYALTY CARD: Pillow NOT installed! Run: pip install Pillow')

# === python-barcode for barcode generation ===
try:
    from barcode import Code128
    from barcode.writer import ImageWriter
    BARCODE_LIB_AVAILABLE = True
except ImportError:
    BARCODE_LIB_AVAILABLE = False
    _logger.warning('LOYALTY CARD: python-barcode NOT installed! Run: pip install python-barcode')



class LoyaltyCardRender(models.AbstractModel):
    _name = 'pos.loyalty.card.render'
    _description = 'Loyalty Card Picture'


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
            _logger.error('LOYALTY CARD: store card image failed for %s: %s', card.card_number, e)
            return False

