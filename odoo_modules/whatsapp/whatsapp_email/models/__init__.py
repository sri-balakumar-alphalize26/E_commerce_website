# NOTE: whatsapp.session / whatsapp.message connection layer, whatsapp.mixin,
# whatsapp.group, res.partner WA fields and the base whatsapp.config / POS
# WhatsApp notify all live in `whatsapp_gateway` and are reused as-is.
# This module only adds Email + cross-channel auto-send on top of them.
from . import whatsapp_config        # _inherit: adds email/auto-send fields
from . import whatsapp_session_main  # _inherit: Main number / Main e-mail per company
from . import whatsapp_message       # _inherit: incoming credit-approval hook
from . import email_session
from . import notification_dispatch
from . import sale_order
from . import purchase_order
from . import account_move
from . import account_payment
from . import easy_orders_send
from . import pos_order
from . import help_document
