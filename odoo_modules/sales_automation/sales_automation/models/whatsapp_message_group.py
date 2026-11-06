"""Group traffic on whatsapp.message.

The gateway records one row per message with `phone` holding the other party.
For a group that other party is the group itself, and the human who typed is
lost. These three fields keep both: `group_jid` says which group, and
`participant_phone` says who inside it - the number the sales flow later
messages privately.

`participant_is_lid` is not a detail. WhatsApp hides some members behind an
@lid address that carries no real number, and there is no way to open a direct
chat with one. The flow has to know that before it promises the customer a DM.
"""

from odoo import api, fields, models


class WhatsAppMessage(models.Model):
    _inherit = 'whatsapp.message'

    sa_request_id = fields.Many2one(
        'sa.group.request', string='Enquiry', index=True, ondelete='set null',
        help="Which enquiry this message belongs to. Recorded when the "
             "message is handled: the same customer can have two enquiries "
             "open minutes apart, and a timestamp cannot tell them apart.")
    group_jid = fields.Char(
        'Group JID', index=True,
        help="The @g.us address of the group this message belongs to. "
             "Empty for ordinary one-to-one messages.",
    )
    participant_phone = fields.Char(
        'Sender in Group', index=True,
        help="Digits of the group member who sent this message. Empty when "
             "WhatsApp hid the sender behind an @lid address.",
    )
    participant_is_lid = fields.Boolean(
        'Sender Hidden (LID)',
        help="WhatsApp addressed the sender by @lid, so their real number is "
             "not available and they cannot be messaged directly.",
    )
    participant_lid = fields.Char(
        'Sender LID', index=True,
        help="WhatsApp's alias for the sender inside this group. Stable per "
             "person, so it identifies them even where no number is exposed.",
    )
    quoted_wa_message_id = fields.Char(
        'Replying To', index=True,
        help="The WhatsApp id of the message this one replied to. It is how a "
             "vendor's price is tied to the exact request it answers, rather "
             "than to whichever request happened to be open.",
    )

    def _sa_is_group(self):
        """True for a message that belongs to a group, incoming or outgoing.

        Outgoing group messages are written by the gateway's own `_log`, which
        knows nothing about `group_jid` - hence the second test on the address
        itself rather than trusting the field alone.
        """
        self.ensure_one()
        return bool(self.group_jid) or '@g.us' in (self.phone or '')

    @api.model_create_multi
    def create(self, vals_list):
        """Backfill `group_jid` on outgoing group messages.

        Everything downstream filters on `group_jid`. Without this, a reply the
        module posts into a group would look like an ordinary message to a
        number that happens to be 18 digits long.
        """
        for vals in vals_list:
            phone = vals.get('phone') or ''
            if '@g.us' in phone and not vals.get('group_jid'):
                vals['group_jid'] = phone
        return super().create(vals_list)
