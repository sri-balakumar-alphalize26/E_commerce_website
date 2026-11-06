"""Put a message on the wire once, even when Odoo replays the request.

Odoo retries a whole HTTP request up to five times when Postgres reports
SERIALIZATION_FAILURE. The database work of the failed attempts is rolled back,
but anything the attempt already sent over the network is not - so on 31 Aug a
single "None of these" produced four identical "Let me check that for you"
messages in the group while `whatsapp.message` recorded one:

    05:18:22 sourcing 'Dell Inspiron Laptop Battery'   <- sent
    05:18:26 SERIALIZATION_FAILURE, 4 tries left
    05:18:28 sourcing 'Dell Inspiron Laptop Battery'   <- sent again
    ...

An ordinary table cannot help, because the retry rolls it back along with
everything else. This one is written on its own connection and committed
immediately, so it survives the rollback and the replay can see it.
"""

import hashlib
import logging

from odoo import api, fields, models
from odoo.sql_db import db_connect

_logger = logging.getLogger(__name__)


class SaOutboxGuard(models.Model):
    _name = 'sa.outbox.guard'
    _description = 'Recently Sent WhatsApp Messages'
    _order = 'id desc'

    digest = fields.Char('Message Digest', required=True, index=True)
    sent_at = fields.Datetime('Sent At', required=True,
                              default=fields.Datetime.now)

    @api.model
    def release(self, key):
        """Give a claim back, so the work it guarded can be attempted again.

        `claim` commits on its own connection precisely so a concurrent
        duplicate cannot slip past while the first attempt is still running.
        The cost is that a claim also survives the ROLLBACK of the attempt
        that took it - and then the retry is suppressed and the work is lost.
        That is not theoretical: on 8 Sep a webhook took 42 seconds, its
        transaction rolled back, the retry was waved through as a duplicate,
        and an enquiry the customer had already been sent a poll for never
        existed. Their tap then had nothing to belong to.

        Never raises: a guard that cannot be released must not take the
        request down with it.
        """
        if not key:
            return True
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
        try:
            cr = db_connect(self.env.cr.dbname).cursor()
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: outbox guard unavailable "
                            "for release (%s)", err)
            return False
        try:
            cr.execute("DELETE FROM sa_outbox_guard WHERE digest = %s",
                       (digest,))
            cr.commit()
            return True
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: could not release the guard "
                            "on %s (%s)", key, err)
            try:
                cr.rollback()
            except Exception:  # noqa: BLE001
                pass
            return False
        finally:
            try:
                cr.close()
            except Exception:  # noqa: BLE001
                pass

    @api.model
    def claim(self, key, seconds=60):
        """True when this exact message may be sent, False when it just was.

        `seconds` covers the retry window rather than the conversation: the
        replays finish inside half a minute, and a customer who genuinely asks
        the same thing again a minute later should still get an answer.

        Never blocks a send because the guard itself failed - a missing message
        is worse than a repeated one.
        """
        if not key:
            return True
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
        try:
            cr = db_connect(self.env.cr.dbname).cursor()
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: outbox guard unavailable (%s)", err)
            return True
        try:
            cr.execute("""
                SELECT 1 FROM sa_outbox_guard
                 WHERE digest = %s
                   AND sent_at > (now() at time zone 'UTC') - make_interval(secs => %s)
                 LIMIT 1
            """, (digest, seconds))
            if cr.fetchone():
                return False
            cr.execute("""
                INSERT INTO sa_outbox_guard (digest, sent_at, create_date, write_date)
                VALUES (%s, (now() at time zone 'UTC'), (now() at time zone 'UTC'),
                        (now() at time zone 'UTC'))
            """, (digest,))
            cr.execute("""
                DELETE FROM sa_outbox_guard
                 WHERE sent_at < (now() at time zone 'UTC') - make_interval(hours => 6)
            """)
            cr.commit()
            return True
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: outbox guard failed (%s)", err)
            try:
                cr.rollback()
            except Exception:  # noqa: BLE001
                pass
            return True
        finally:
            try:
                cr.close()
            except Exception:  # noqa: BLE001
                pass
