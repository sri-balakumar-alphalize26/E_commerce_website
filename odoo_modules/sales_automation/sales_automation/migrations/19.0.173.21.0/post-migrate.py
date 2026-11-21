"""Customer Links (21 Nov 2026): one choice per link replaces the single
"Send Links & PDFs Privately" switch. A database that had switched it off
keeps sending links in the group: every personal link becomes Group."""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'sa_ai_settings' AND column_name = 'private_links'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE sa_ai_settings
           SET link_confirm = 'group', link_address = 'group', link_sign = 'group',
               link_pay = 'group', link_track = 'group', link_map = 'group',
               link_review = 'group', link_web = 'group', link_docs = 'group'
         WHERE private_links IS FALSE
    """)
