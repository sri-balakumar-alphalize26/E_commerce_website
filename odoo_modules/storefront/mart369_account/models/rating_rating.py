"""Reviews, and the two rating systems joined up.

`mart369_product` already reads reviews off `rating.rating` and honestly returns
`[]` when a product has none (product_page.py:144-188). What never existed was a
way to write one: the app kept reviews in `369mart.reviews`, a localStorage map
identical for nobody but the browser holding it, while the product page showed
three hardcoded reviewers on all 108 products.

Two systems become one here. In the app a product review and an order/rider
rating were unrelated blobs in different keys; in Odoo both are `rating.rating`,
on different `res_model`s, which is why they can finally be counted together.

The one thing worth getting right: **a review that misses `REVIEW_DOMAIN`
(product_page.py:12-16) saves and is never seen again.** `consumed` must be set,
`rating` must be at least 1, and `is_internal` must be false - and `is_internal`
is a *stored related* field on `message_id.is_internal`, so with no message
behind the rating it has to be written explicitly rather than left to default.
"""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import review_filter
from .review_media import REPORT_REASONS, REPORTS_TO_HOLD

HIDE_REASONS = ['Abusive', 'Not about the product', 'Personal details', 'Spam', 'Other']

# What the app's review form collects, beyond a score and a comment.
TAGS_UP = ['Fresh', 'Well packed', 'Good value', 'As described', 'Fast delivery']
TAGS_DOWN = ['Not fresh', 'Damaged', 'Wrong item', 'Poor quality', 'Late delivery']


class RatingRating(models.Model):
    _inherit = 'rating.rating'

    mart369_title = fields.Char(
        string='Headline', help="The short line above the review, up to 60 characters.")
    mart369_tags = fields.Char(
        string='Tags', help="What the customer ticked, comma separated. The app "
                            "offers a different set above and below three stars.")
    mart369_photos = fields.Integer(
        string='Photos', default=0,
        help="How many photos the customer attached. A count rather than the "
             "images: the app has only ever collected a number.")
    mart369_helpful = fields.Integer(string='Found helpful', default=0)
    mart369_verified = fields.Boolean(
        string='Verified purchase', default=False, readonly=True,
        help="Set when the customer really bought this, checked against their "
             "own order lines.")
    # Moderation (review_filter.py): why a review waits, and why staff hid one.
    mart369_held_reason = fields.Char(string='Held because', readonly=True)
    mart369_hidden_reason = fields.Char(string='Hidden because')
    mart369_reports = fields.Integer(string='Reported by shoppers', default=0, readonly=True)
    mart369_media_ids = fields.One2many('mart369.review.media', 'rating_id', string='Photos and video')

    # ------------------------------------------------------------- writing

    @api.model
    def _mart369_review_for(self, partner, product):
        """This customer's review of this product, if there is one.

        One review per product per customer is a hard assumption in the app -
        it reads `myReviews[p.id]` - so writing is an upsert, never a create.
        """
        if not partner or not product:
            return self.browse()
        return self.sudo().search([
            ('res_model', '=', 'product.template'),
            ('res_id', '=', product.id),
            ('partner_id', '=', partner.id),
        ], limit=1)

    @api.model
    def _mart369_write_review(self, partner, product, values):
        """Create or update a review. Returns the rating record."""
        stars = int(values.get('stars') or 0)
        stars = max(1, min(5, stars))
        tags = self._mart369_clean_tags(values.get('tags'), stars)

        write = {
            'rating': stars,
            'feedback': (values.get('text') or '').strip()[:500],
            'mart369_title': (values.get('title') or '').strip()[:60] or False,
            'mart369_tags': ','.join(tags) or False,
            'mart369_photos': max(0, min(3, int(values.get('photos') or 0))),
            # Without these three the review is invisible to the product page.
            'consumed': True,
            'is_internal': False,
        }

        # Clean goes live at once; anything the filter holds waits for staff.
        extra = self.env['mart369.config'].sudo()._get().review_blocked_words
        reasons = review_filter.check(write['mart369_title'] or '', write['feedback'], extra)
        write['mart369_held_reason'] = ', '.join(reasons) or False

        existing = self._mart369_review_for(partner, product)
        if existing:
            # A review staff hid stays hidden however its author retypes it -
            # moderation is the store's. One the filter held is looked at
            # again: fixed, it goes live; newly flagged, it waits.
            if existing.mart369_state != 'hidden':
                if reasons:
                    write['mart369_state'] = 'pending'
                elif existing.mart369_held_reason and existing.mart369_state == 'pending':
                    write['mart369_state'] = 'published'
            write.pop('mart369_photos', None)
            existing.sudo().write(write)
            return existing

        write.update({
            'res_model_id': self.env['ir.model']._get_id('product.template'),
            'res_id': product.id,
            'partner_id': partner.id,
            'mart369_verified': self._mart369_has_bought(partner, product),
            'mart369_state': 'pending' if reasons else 'published',
            'mart369_photos': 0,
        })
        return self.sudo().create(write)

    # ------------------------------------------------ what shoppers can do

    def _mart369_vote(self, partner, kind, reason=None):
        """Helpful or Report, once each per customer. Three reports send a
        live review back to Waiting."""
        self.ensure_one()
        if kind not in ('helpful', 'report'):
            raise UserError(_('Unknown vote.'))
        if partner == self.partner_id:
            raise UserError(_('That is your own review.'))
        Vote = self.env['mart369.review.vote'].sudo()
        if Vote.search_count([('rating_id', '=', self.id), ('partner_id', '=', partner.id),
                              ('kind', '=', kind)]):
            return False
        Vote.create({'rating_id': self.id, 'partner_id': partner.id, 'kind': kind,
                     'reason': reason if reason in REPORT_REASONS else (reason and 'Other')})
        me = self.sudo()
        if kind == 'helpful':
            me.mart369_helpful = (me.mart369_helpful or 0) + 1
        else:
            me.mart369_reports = (me.mart369_reports or 0) + 1
            if me.mart369_reports >= REPORTS_TO_HOLD and me.mart369_state == 'published':
                me.write({'mart369_state': 'pending', 'mart369_held_reason': 'reported by shoppers'})
        return True

    def _mart369_add_media(self, name, mime, data):
        self.ensure_one()
        media = self.env['mart369.review.media']._mart369_add(self, name, mime, data)
        self.sudo().mart369_photos = len(self.sudo().mart369_media_ids.filtered(lambda m: m.kind == 'photo'))
        return media

    @api.model
    def _mart369_clean_tags(self, tags, stars):
        """Only tags from the pool the app would have offered for that score."""
        pool = TAGS_UP if stars > 3 else TAGS_DOWN
        if isinstance(tags, str):
            tags = [part.strip() for part in tags.split(',')]
        return [tag for tag in (tags or []) if tag in pool]

    @api.model
    def _mart369_has_bought(self, partner, product):
        """Did this customer actually buy it?

        Impossible to answer before mart369_order: there were no order lines to
        check against. The product page prints "Verified purchase" under every
        review regardless, so this is the field that makes that true.
        """
        return bool(self.env['sale.order.line'].sudo().search_count([
            ('order_id.partner_id', '=', partner.id),
            ('order_id.mart369_state', 'in', ('placed', 'packed', 'shipped', 'out', 'delivered')),
            ('product_id.product_tmpl_id', '=', product.id),
        ]))

    # ------------------------------------------------------------ the order

    @api.model
    def _mart369_rate_order(self, partner, order, values):
        """The order and rider rating, which the app kept in orderPatches.

        Same model as a product review, a different `res_model`. The rider is
        the rated party rather than the subject, which is what `rated_partner_id`
        is for.

        Not moderated, on purpose. The row carries a `mart369_state` because the
        field has a default and every row on the table gets one, but nothing
        reads it here and the staff screens filter these out by `res_model`.
        They never reach a product page - they are the customer telling the
        store how a delivery went - so there is nothing to publish or hide.
        """
        stars = max(1, min(5, int(values.get('stars') or 0)))
        existing = self.sudo().search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', order.id),
            ('partner_id', '=', partner.id),
        ], limit=1)
        write = {
            'rating': stars,
            'feedback': (values.get('comment') or '').strip()[:300],
            'mart369_tags': ','.join(
                [t for t in (values.get('tags') or []) if isinstance(t, str)][:6]) or False,
            'consumed': True,
            'is_internal': False,
        }
        if existing:
            existing.sudo().write(write)
            return existing
        write.update({
            'res_model_id': self.env['ir.model']._get_id('sale.order'),
            'res_id': order.id,
            'partner_id': partner.id,
        })
        return self.sudo().create(write)

    # --------------------------------------------------------- serializing

    def _mart369_serialize(self):
        """One entry of the app's `369mart.reviews` map."""
        self.ensure_one()
        return {
            'stars': int(round(self.rating)),
            'title': self.mart369_title or '',
            'text': self.feedback or '',
            'tags': [t for t in (self.mart369_tags or '').split(',') if t],
            'photos': self.mart369_photos or 0,
            'at': int(self.create_date.timestamp() * 1000) if self.create_date else None,
            'edited': bool(self.write_date and self.create_date
                           and (self.write_date - self.create_date).total_seconds() > 1),
            'helpful': self.mart369_helpful or 0,
            'verified': bool(self.mart369_verified),
            # Their own review, so they are told why nobody else can see it.
            'state': self.mart369_state or 'published',
            'heldReason': self.mart369_held_reason or '',
            'media': [m._mart369_serialize() for m in self.sudo().mart369_media_ids],
            'reply': self.publisher_comment or '',
        }

    # ---------------------------------------------------------- the console

    # Product reviews, whatever their moderation state. The state is the one
    # thing the screen exists to change, so it must not also be the thing that
    # hides rows from it - `REVIEW_DOMAIN` is for the shop, not for staff.
    ADMIN_DOMAIN = [
        ('res_model', '=', 'product.template'),
        ('consumed', '=', True),
        ('is_internal', '=', False),
        ('rating', '>=', 1),
    ]

    def _mart369_admin_serialize(self, names=None):
        """One review as the staff screens draw it.

        Its own shape rather than a wider `_mart369_serialize`: that one is a
        customer reading their own reviews back. Who wrote a review, and what
        staff have done with it, are not part of that.

        `names` is an optional {product id: name} so a list of reviews does not
        read one product at a time.
        """
        self.ensure_one()
        if names is None:
            names = {}
        return {
            'id': self.id,
            'productId': self.res_id,
            'product': names.get(self.res_id) or self.res_name or '',
            'by': self.partner_id.name or 'Someone',
            'stars': int(round(self.rating)),
            'title': self.mart369_title or '',
            'text': self.feedback or '',
            'tags': [t for t in (self.mart369_tags or '').split(',') if t],
            'photos': self.mart369_photos or 0,
            'verified': bool(self.mart369_verified),
            'helpful': self.mart369_helpful or 0,
            'at': int(self.create_date.timestamp() * 1000) if self.create_date else None,
            'state': self.mart369_state or 'published',
            'heldReason': self.mart369_held_reason or '',
            'hiddenReason': self.mart369_hidden_reason or '',
            'reports': self.mart369_reports or 0,
            'media': [m._mart369_serialize(staff=True) for m in self.sudo().mart369_media_ids],
            'mediaWaiting': len(self.sudo().mart369_media_ids.filtered(lambda m: m.state == 'pending')),
            'reply': self.publisher_comment or '',
            'replyBy': self.publisher_id.name or '',
        }

    @api.model
    def mart369_admin_counts(self):
        """Just the tallies, for the badge in the console's sidebar.

        `search_count` rather than `mart369_admin_list`: the badge asks every
        minute and wants one number, and building every review's payload to
        throw all of it away is the kind of cost nobody notices until the shop
        has a few thousand reviews.
        """
        return {
            'pending': self.search_count(
                self.ADMIN_DOMAIN + [('mart369_state', '=', 'pending')]),
            'published': self.search_count(
                self.ADMIN_DOMAIN + [('mart369_state', '=', 'published')]),
            'hidden': self.search_count(
                self.ADMIN_DOMAIN + [('mart369_state', '=', 'hidden')]),
        }

    @api.model
    def mart369_admin_list(self, state=None, q=None, verified=None, photos=None):
        """The reviews the staff screens list, and the tiles above them.

        The tiles count every product review, not the filtered ones - a tab
        that said "Waiting 3" only while you were looking at Waiting would be
        useless for deciding whether to look. That holds for `verified` and
        `photos` too: narrowing the list must not change how much is waiting.

        `verified` and `photos` are the two filters the Odoo search view has
        always offered (views/review_views.xml) and the console never did.
        Both are tri-state - None means "do not care", so a screen that never
        sends them behaves exactly as before.
        """
        every = self.search(self.ADMIN_DOMAIN, order='create_date desc')

        rows_for_counts = every
        matched = every
        if state in ('pending', 'published', 'hidden'):
            matched = matched.filtered(lambda r: (r.mart369_state or 'published') == state)

        term = (q or '').strip()
        if term:
            # Product name is a search of its own: `res_id` is a bare integer,
            # not a relation, so it cannot be walked in a domain.
            hits = self.env['product.template'].sudo().search(
                [('name', 'ilike', term)]).ids
            low = term.lower()
            matched = matched.filtered(
                lambda r: r.res_id in hits
                or low in (r.partner_id.name or '').lower()
                or low in (r.mart369_title or '').lower()
                or low in (r.feedback or '').lower())

        # Tri-state, and read as a flag rather than a truthiness test: `False`
        # has to be able to mean "only the unverified ones".
        if verified is not None:
            want = bool(verified)
            matched = matched.filtered(lambda r: bool(r.mart369_verified) == want)
        if photos is not None:
            want = bool(photos)
            matched = matched.filtered(lambda r: bool(r.mart369_photos) == want)

        names = {}
        if matched:
            products = self.env['product.template'].sudo().browse(
                [r.res_id for r in matched]).exists()
            names = {p.id: p.display_name for p in products}

        scored = [r.rating for r in rows_for_counts if r.rating]
        return {
            'reviews': [r._mart369_admin_serialize(names) for r in matched],
            'counts': {
                'all': len(rows_for_counts),
                'pending': sum(1 for r in rows_for_counts
                               if (r.mart369_state or 'published') == 'pending'),
                'published': sum(1 for r in rows_for_counts
                                 if (r.mart369_state or 'published') == 'published'),
                'hidden': sum(1 for r in rows_for_counts
                              if (r.mart369_state or 'published') == 'hidden'),
            },
            # Rounded here so the console never has to decide what to do with
            # a rating out of an empty list.
            'average': round(sum(scored) / len(scored), 1) if scored else 0.0,
            'report': self._mart369_admin_report(every),
            'hideReasons': HIDE_REASONS,
        }

    @api.model
    def _mart369_admin_report(self, every):
        """Worst-rated products (three reviews or more) and the complaints
        ticked most in the last 30 days."""
        per = {}
        for r in every:
            if (r.mart369_state or 'published') != 'hidden':
                per.setdefault(r.res_id, []).append(r.rating)
        worst = sorted((sum(v) / len(v), len(v), pid) for pid, v in per.items() if len(v) >= 3)[:5]
        names = {p.id: p.display_name for p in self.env['product.template'].sudo().browse(
            [pid for __, __, pid in worst]).exists()}
        since = fields.Datetime.now() - timedelta(days=30)
        tally = {}
        for r in every.filtered(lambda x: x.create_date and x.create_date >= since):
            for tag in (r.mart369_tags or '').split(','):
                if tag in TAGS_DOWN:
                    tally[tag] = tally.get(tag, 0) + 1
        return {
            'worst': [{'productId': pid, 'product': names.get(pid, ''), 'average': round(avg, 1),
                       'count': n} for avg, n, pid in worst],
            'complaints': [{'tag': t, 'count': n}
                           for t, n in sorted(tally.items(), key=lambda kv: -kv[1])],
        }

    # ------------------------------------------------------ staff actions

    def _mart369_staff_one(self, rating_id):
        row = self.search(self.ADMIN_DOMAIN + [('id', '=', int(rating_id or 0))], limit=1)
        if not row:
            raise UserError(_('There is no such review.'))
        return row

    @api.model
    def mart369_admin_moderate(self, rating_id, state, reason=None):
        """Publish, or hide with a reason."""
        row = self._mart369_staff_one(rating_id)
        if state == 'hidden':
            if reason not in HIDE_REASONS:
                raise UserError(_('Pick why it is hidden.'))
            row.write({'mart369_state': 'hidden', 'mart369_hidden_reason': reason})
        elif state == 'published':
            row.write({'mart369_state': 'published', 'mart369_hidden_reason': False,
                       'mart369_held_reason': False})
        else:
            raise UserError(_('Publish or hide.'))
        return row._mart369_admin_serialize()

    @api.model
    def mart369_admin_reply(self, rating_id, text):
        """The shop's public reply, shown under the review."""
        row = self._mart369_staff_one(rating_id)
        text = (text or '').strip()[:1000]
        row.sudo().write({'publisher_comment': text or False,
                          'publisher_id': self.env.user.partner_id.id if text else False,
                          'publisher_datetime': fields.Datetime.now() if text else False})
        return row._mart369_admin_serialize()

    @api.model
    def mart369_admin_media(self, media_id, action):
        """Show a photo or video, or remove it (and its file)."""
        media = self.env['mart369.review.media'].sudo().browse(int(media_id or 0)).exists()
        if not media:
            raise UserError(_('That photo or video is gone.'))
        row = self._mart369_staff_one(media.rating_id.id)
        if action == 'approve':
            media.state = 'approved'
        elif action == 'remove':
            media.unlink()
            row.sudo().mart369_photos = len(
                row.sudo().mart369_media_ids.filtered(lambda m: m.kind == 'photo'))
        else:
            raise UserError(_('Approve or remove.'))
        return row._mart369_admin_serialize()
