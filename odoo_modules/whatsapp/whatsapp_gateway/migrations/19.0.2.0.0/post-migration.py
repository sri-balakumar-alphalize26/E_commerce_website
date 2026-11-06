"""19.0.1.x -> 19.0.2.0.0: WhatsApp moves out of Odoo and onto a gateway.

Existing sessions are kept - other modules point Many2ones at them, and their
message history hangs off them - but everything that described an in-process
connection is now meaningless and is cleared out.

Nobody can send until an administrator opens each session and pastes the
gateway's API key. That is deliberate: silently inventing a key would leave a
session that looks configured and fails at the first send.
"""

import logging
import uuid

_logger = logging.getLogger(__name__)

# Columns that only made sense while the WhatsApp client lived inside Odoo.
DEAD_COLUMNS = (
    'owner_key',        # which worker held the client
    'owner_heartbeat',  # and when it last proved it was alive
    'db_path',          # the on-disk neonize session file
    'qr_image',         # a QR nobody scans here any more
    'qr_last_update',
    'auto_reconnect',   # there is no client in this process to reconnect
)


def migrate(cr, version):
    if not version:
        return

    # Old status values described a connection this process no longer has.
    # Anything left saying 'connected' would make get_connected_session() offer
    # a session that cannot send, which is the exact failure this rewrite is
    # meant to end. The cron re-reads the truth from the gateway within
    # five minutes.
    cr.execute("""
        UPDATE whatsapp_session
           SET status = 'disconnected',
               error_message = 'Set the gateway API key, then press Test Connection.'
    """)
    _logger.info("WhatsApp: reset %s session(s) to disconnected.", cr.rowcount)

    cr.execute("""
        UPDATE whatsapp_session
           SET gateway_url = COALESCE(NULLIF(gateway_url, ''), 'http://127.0.0.1:8085'),
               instance_name = COALESCE(NULLIF(instance_name, ''), 'nexgenn-main'),
               send_delay_ms = COALESCE(NULLIF(send_delay_ms, 0), 1200),
               dedupe_minutes = COALESCE(dedupe_minutes, 5),
               daily_cap = COALESCE(daily_cap, 0),
               allow_bulk = COALESCE(allow_bulk, FALSE)
    """)

    # One secret per session, so a leaked webhook URL cannot be replayed
    # against another.
    #
    # Checking only for NULL is not enough, and that is not a hypothetical:
    # Odoo evaluates a new column's default *once* and writes the same value to
    # every pre-existing row, so all sessions come out of the upgrade sharing a
    # single secret. Any row whose secret is not unique gets a fresh one.
    cr.execute("""
        SELECT id FROM whatsapp_session
         WHERE webhook_secret IS NULL
            OR webhook_secret = ''
            OR webhook_secret IN (SELECT webhook_secret
                                    FROM whatsapp_session
                                   WHERE webhook_secret IS NOT NULL
                                GROUP BY webhook_secret
                                  HAVING count(*) > 1)
    """)
    rows = cr.fetchall()
    for (session_id,) in rows:
        cr.execute("UPDATE whatsapp_session SET webhook_secret = %s WHERE id = %s",
                   (uuid.uuid4().hex, session_id))
    if rows:
        _logger.info("WhatsApp: issued %s unique webhook secret(s).", len(rows))

    # Messages stuck 'pending' were queued for a worker-owned client that will
    # never come back. Marking them failed is honest; leaving them pending
    # would have the new outbox cron send week-old messages the moment the
    # gateway connects.
    cr.execute("""
        UPDATE whatsapp_message
           SET status = 'failed'
         WHERE direction = 'outgoing' AND status = 'pending'
    """)
    if cr.rowcount:
        _logger.info("WhatsApp: marked %s stale queued message(s) as failed - "
                     "they predate the gateway and were never sent.", cr.rowcount)

    for column in DEAD_COLUMNS:
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'whatsapp_session' AND column_name = %s
        """, (column,))
        if cr.fetchone():
            cr.execute('ALTER TABLE whatsapp_session DROP COLUMN "%s"' % column)
            _logger.info("WhatsApp: dropped dead column whatsapp_session.%s", column)

    _logger.warning(
        "WhatsApp: sessions migrated to the gateway. Open each one, paste the "
        "gateway API key, then press Test Connection and Register Webhook. "
        "Nothing will send until you do.")
