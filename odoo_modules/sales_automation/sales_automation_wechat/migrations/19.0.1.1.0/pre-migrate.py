# -*- coding: utf-8 -*-
"""The single 'Price checks via' selection becomes two ticks. Existing rows
keep what they had; untouched vendors get the default: WeChat for a China
address, WhatsApp for everyone else. Runs before the fields are loaded, on
the old column, so nothing is lost to the recompute."""


def migrate(cr, version):
    cr.execute("ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS sa_via_whatsapp boolean")
    cr.execute("ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS sa_via_wechat boolean")
    cr.execute("""
        UPDATE res_partner
           SET sa_via_wechat = (sa_channel IN ('wechat', 'both')),
               sa_via_whatsapp = (sa_channel IN ('whatsapp', 'both'))
         WHERE sa_channel IS NOT NULL AND sa_via_whatsapp IS NULL AND sa_via_wechat IS NULL
    """)
    cr.execute("""
        UPDATE res_partner p
           SET sa_via_whatsapp = COALESCE(c.code, '') <> 'CN',
               sa_via_wechat = (COALESCE(c.code, '') = 'CN' AND COALESCE(p.sa_wechat_name, '') <> '')
          FROM (SELECT p2.id, c2.code FROM res_partner p2 LEFT JOIN res_country c2 ON c2.id = p2.country_id) c
         WHERE c.id = p.id AND p.sa_via_whatsapp IS NULL AND p.sa_via_wechat IS NULL
    """)
