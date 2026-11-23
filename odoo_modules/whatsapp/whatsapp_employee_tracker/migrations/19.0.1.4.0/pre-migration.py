def migrate(cr, version):
    """One employee session per employee became: one at a time."""
    for name in ('wa_employee_session_employee_unique', 'wa_employee_session_session_unique'):
        cr.execute('ALTER TABLE wa_employee_session DROP CONSTRAINT IF EXISTS %s' % name)
