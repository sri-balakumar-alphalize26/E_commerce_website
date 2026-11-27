"""Each company now sends from its own chosen WhatsApp number and e-mail.

Before 19.0.5.0.0 every document went out on the first connected number of the
database, and a company without settings borrowed the first company's. So that
nothing stops sending on upgrade, this fills in exactly what used to happen:

* a company without settings gets a copy of the first settings record
  (its auto-send switches),
* an empty "Send WhatsApp from" becomes the company's own number, else the
  number that used to send for everybody,
* an empty "Send email from" becomes the company's own number with an e-mail,
  else the address that used to mail for everybody.

Afterwards the admin changes them per company (WhatsApp and Email >
Configuration > Sending per company).
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Config = env['whatsapp.config'].sudo()
    Session = env['whatsapp.session'].sudo()
    first = Config.search([], order='id', limit=1)
    toggles = [name for name in Config._fields if name.startswith('auto_send_')
               or name.startswith('pos_email_notify') or name == 'pos_owner_emails']
    sessions = Session.search([('active', '=', True), ('gateway_api_key', '!=', False)], order='id')
    mailers = sessions.filtered(lambda s: s.use_email and s.authorized_email)

    for company in env['res.company'].sudo().search([]):
        config = Config.search([('company_id', '=', company.id)], limit=1)
        if not config:
            vals = {'company_id': company.id}
            if first:
                vals.update({name: first[name] for name in toggles})
            config = Config.create(vals)
            _logger.info("whatsapp_email: settings for %s copied from %s", company.name,
                         first.company_id.name if first else '-')
        vals = {}
        if not config.default_whatsapp_session_id:
            own = sessions.filtered(lambda s: s.company_id == company)[:1]
            chosen = own or (first.default_whatsapp_session_id if first else Session) or sessions[:1]
            if chosen:
                vals['default_whatsapp_session_id'] = chosen.id
        if not config.email_session_id:
            own = mailers.filtered(lambda s: s.company_id == company)[:1]
            chosen = own or mailers[:1]
            if chosen:
                vals['email_session_id'] = chosen.id
        if vals:
            config.write(vals)
            _logger.info("whatsapp_email: %s sends from %s", company.name, vals)
