"""The support bot knows who is delivering.

`mart369_support` cannot see the delivery stack, so "who is my rider?" either
fell through to the fallback or - because rule 40 matches "person" - "delivery
person" was handed to a human agent. Here, where the rider is known, the bot
gets one more kind of answer and the order answers mention the rider.

The name comes from `sale.order._mart369_rider_name()`, the same one the
order page and its map use. Like the rest of the bot, it never says the
delivery code, and it only ever reads the signed-in customer's own orders
(`_mart369_context`).
"""

from odoo import api, fields, models

from odoo.addons.mart369_support.models.bot import LIVE_STATES, STATUS_WORDS

RIDER_KIND = ('rider', 'Who is delivering their order')


class Mart369BotRule(models.Model):
    _inherit = 'mart369.bot.rule'

    kind = fields.Selection(
        selection_add=[RIDER_KIND],
        ondelete={'rider': 'set default'})

    # The console's editor checks kinds against mart369_support's own list,
    # which cannot know this one. Taught here rather than there.

    def _mart369_admin_row(self):
        row = super()._mart369_admin_row()
        if self.kind == RIDER_KIND[0]:
            row['kindLabel'] = RIDER_KIND[1]
        return row

    @api.model
    def mart369_admin_list(self, *args, **kwargs):
        payload = super().mart369_admin_list(*args, **kwargs)
        kinds = payload.get('kinds')
        if isinstance(kinds, list) and RIDER_KIND[0] not in [k.get('key') for k in kinds]:
            kinds.append({'key': RIDER_KIND[0], 'label': RIDER_KIND[1]})
        return payload

    @api.model
    def _mart369_admin_values(self, body):
        rider = isinstance(body, dict) and body.get('kind') == RIDER_KIND[0]
        if rider:
            body = dict(body, kind='static')
        values = super()._mart369_admin_values(body)
        if rider:
            values['kind'] = RIDER_KIND[0]
        return values


class Mart369Bot(models.AbstractModel):
    _inherit = 'mart369.bot'

    def _mart369_with_rider(self, text, order):
        name = order._mart369_rider_name() if order else ''
        if name and order.mart369_state in LIVE_STATES:
            text = '%s Your rider is %s.' % (text.rstrip(), name)
        return text

    def _mart369_answer_order(self, rule, ctx):
        reply = super()._mart369_answer_order(rule, ctx)
        if ctx['named'] and reply.get('text'):
            reply['text'] = self._mart369_with_rider(reply['text'], ctx['named'])
        return reply

    def _mart369_answer_track(self, rule, ctx):
        reply = super()._mart369_answer_track(rule, ctx)
        if ctx['live'] and reply.get('text'):
            reply['text'] = self._mart369_with_rider(reply['text'], ctx['live'][0])
        return reply

    def _mart369_answer_rider(self, rule, ctx):
        """Who is bringing it - for the order a rider is on, else the newest."""
        live = ctx['live']
        if not live:
            return {'text': rule.reply_alt or 'You have no orders on the way right now.',
                    'actions': [{'label': 'See all orders', 'go': ['account', 'orders']}]}
        named = {order: order._mart369_rider_name() for order in live}
        order = next((o for o in live if named[o]), live[0])
        name = named[order]
        words = STATUS_WORDS.get(order.mart369_state, '')
        if name:
            text = '%s is delivering order #%s. It is %s' % (name, order.mart369_ref or order.name, words)
            if order.mart369_eta:
                text += ', %s' % order.mart369_eta
            text += '. Open the order to follow them on the map or call them.'
            label = 'Track order'
        else:
            text = ("A rider hasn't been assigned to order #%s yet - it is %s. "
                    "Their name shows here as soon as one picks it up."
                    % (order.mart369_ref or order.name, words))
            label = 'Order details'
        return {'text': text, 'actions': [self._mart369_track(order, label)]}
