"""Our modules upgrade themselves when their code is newer than the database.

Copying a new version of a module onto a server and restarting Odoo loads the
new code against the old tables: a field added since has no column yet, and
every page that reads it ends in "500 Internal Server Error". Odoo creates
columns only when a module is upgraded (Apps > Upgrade, or `odoo -u`), never on
a restart.

So when Odoo loads a database, this compares each of our installed modules'
version on disk (its __manifest__.py) with the version the database recorded
at its last install or upgrade, and upgrades the ones that are newer - the
same steps as Apps > Upgrade:

* wait until no scheduled job is running on that database, then mark the
  modules "to upgrade" (the scheduler skips a database while modules are
  marked, so no job starts during the upgrade);
* reload the registry with the upgrade - the nested reload Odoo does itself
  after uninstalling modules (odoo/modules/loading.py, "Reloading registry
  once more").

Copy, restart, and each database brings itself up to date the first time it
is opened, by a visitor or by the scheduler.

The scheduler often opens a database first, from inside a job it has locked.
An upgrade from there would have to rewrite that locked job (our data files
declare scheduled jobs) and fails, so from a job this only starts a short
background thread that does the upgrade a few seconds later, outside the job.

What triggers it is the manifest `version`: raise it whenever a change adds or
changes fields, models or data files. A change that keeps the version is not
upgraded.

The same file is in mart369, sales_automation, whatsapp_gateway and
pos_loyalty_card. Every module of ours is one of those or depends on one, so
whichever is installed covers the rest; the first copy to run does the work
and the others find nothing left to do. ai369_image_server is a separate
product: it has no copy and is never upgraded from here.

If an upgrade fails, the error and its traceback go to the log, the site keeps
serving with the code it loaded, and the same versions are not tried again for
ten minutes, so workers do not loop on it.
"""
import logging
import os
import sys
import threading
import time

import psycopg2

from odoo import SUPERUSER_ID, api, models
from odoo.modules import Manifest
from odoo.modules import module as odoo_module
from odoo.modules.registry import Registry
from odoo.tools import config, parse_version

_logger = logging.getLogger(__name__)

# Every module of ours is one of these or depends on one of them
# (ai369_image_server is a separate product and is left alone).
_ROOTS = ('mart369', 'sales_automation', 'whatsapp_gateway', 'pos_loyalty_card')
# Postgres advisory lock: one upgrader per database at a time, across workers.
_LOCK_KEY = 369036917
_FAILED_PARAM = 'auto_upgrade.failed'
_RETRY_AFTER = 600          # seconds before the same failed versions are tried again
_JOB_WAIT = '20s'           # how long to wait for a running scheduled job
_LATER = 5                  # seconds before the background upgrade starts
_BUSY_LATER = 60            # ... and when a scheduled job was still running

# Shared by the copies of this file in the other modules (each is its own
# Python module), so they are kept on a module every copy imports.
_SHARED = vars(odoo_module)
# Databases being upgraded by this process right now: the reload runs this
# hook again, and it must not wait on the lock its own caller holds.
_RUNNING = _SHARED.setdefault('_our_auto_upgrade_running', set())
# Databases with a background upgrade already waiting to start.
_WAITING = _SHARED.setdefault('_our_auto_upgrade_waiting', set())


class _SchedulerBusy(Exception):
    pass


def _pending(cr):
    """Our installed modules whose code on disk is newer than the database,
    as {name: (version in database, version on disk)}."""
    cr.execute("""
        WITH RECURSIVE ours(name) AS (
            SELECT name FROM ir_module_module
             WHERE name IN %(roots)s AND state IN %(states)s
            UNION
            SELECT m.name
              FROM ir_module_module m
              JOIN ir_module_module_dependency d ON d.module_id = m.id
              JOIN ours o ON o.name = d.name
             WHERE m.state IN %(states)s
        )
        SELECT m.name, m.latest_version
          FROM ir_module_module m JOIN ours o ON o.name = m.name
    """, {'roots': _ROOTS, 'states': ('installed', 'to upgrade')})
    pending = {}
    for name, db_version in cr.fetchall():
        manifest = Manifest.for_addon(name, display_warning=False)
        if not manifest or not db_version or not manifest.get('installable', True):
            continue
        if parse_version(manifest.version) > parse_version(db_version):
            pending[name] = (db_version, manifest.version)
    return pending


def _describe(pending):
    return ', '.join('%s %s -> %s' % (n, pending[n][0], pending[n][1]) for n in sorted(pending))


def _signature(pending):
    return ','.join('%s=%s' % (name, pending[name][1]) for name in sorted(pending))


def _failed_recently(cr, signature):
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [_FAILED_PARAM])
    row = cr.fetchone()
    if not row or not row[0]:
        return False
    tried, _sep, at = row[0].rpartition('|')
    try:
        return tried == signature and time.time() - float(at) < _RETRY_AFTER
    except ValueError:
        return False


def _set_failed(cr, value):
    if value:
        cr.execute("""
            INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, 1, now() AT TIME ZONE 'UTC', 1, now() AT TIME ZONE 'UTC')
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = EXCLUDED.write_date
        """, [_FAILED_PARAM, value])
    else:
        cr.execute("DELETE FROM ir_config_parameter WHERE key = %s", [_FAILED_PARAM])
    cr.commit()


def _inside_scheduled_job():
    """True when the scheduler is loading the database from inside a job it
    has locked (threaded and multi-worker servers alike)."""
    frame = sys._getframe(1)
    while frame is not None:
        code = frame.f_code
        if (code.co_name in ('_process_jobs', '_process_jobs_loop', '_process_job')
                and os.path.basename(code.co_filename) == 'ir_cron.py'):
            return True
        frame = frame.f_back
    return False


def _hold_scheduler(cr, pending):
    """Wait for a running scheduled job to finish, then mark the modules to
    upgrade so the scheduler skips this database until the upgrade is done
    (the same check Apps > Upgrade makes). Raises _SchedulerBusy when a job
    is still running after _JOB_WAIT."""
    try:
        cr.execute("SET LOCAL lock_timeout = %s", [_JOB_WAIT])
        cr.execute("SELECT id FROM ir_cron FOR UPDATE")
    except psycopg2.errors.LockNotAvailable as e:
        cr.rollback()
        raise _SchedulerBusy() from e
    cr.execute("UPDATE ir_module_module SET state = 'to upgrade' "
               "WHERE name IN %s AND state = 'installed'", [tuple(pending)])
    cr.commit()


def _upgrade_later(db_name, delay, why):
    """Start the upgrade from a background thread, outside any scheduled job."""
    if db_name in _WAITING:
        return
    _WAITING.add(db_name)
    _logger.warning("Database %s has modules to upgrade; %s", db_name, why)

    def run():
        time.sleep(delay)
        _WAITING.discard(db_name)
        try:
            registry = Registry(db_name)   # a first load runs the hook here
            with registry.cursor() as cr:
                upgrade_if_code_is_newer(api.Environment(cr, SUPERUSER_ID, {}))
        except Exception:  # noqa: BLE001
            _logger.exception("Background module upgrade on %s stopped", db_name)

    threading.Thread(target=run, name='auto-upgrade-%s' % db_name, daemon=True).start()


def upgrade_if_code_is_newer(env):
    if config['test_enable'] or odoo_module.current_test:
        return
    cr = env.cr
    db_name = cr.dbname
    if db_name in _RUNNING:
        return
    try:
        if not _pending(cr):
            return
    except Exception:  # noqa: BLE001 - never stop a database from loading
        _logger.exception("Could not compare module versions on %s", db_name)
        return

    if _inside_scheduled_job():
        _upgrade_later(db_name, _LATER, "upgrading them in the background, outside "
                                        "the scheduled job that opened it")
        return

    current = env.registry
    # Let go of what this transaction holds, so the upgrade's ALTER TABLEs do
    # not wait on it (Odoo commits here too before reloading).
    cr.commit()
    _RUNNING.add(db_name)
    lock_cr = current.cursor()
    try:
        lock_cr.execute("SELECT pg_advisory_lock(%s)", [_LOCK_KEY])
        # A fresh transaction, so the check sees what another worker that
        # held the lock may have upgraded meanwhile.
        lock_cr.commit()
        pending = _pending(lock_cr)
        if not pending:
            return
        signature = _signature(pending)
        if _failed_recently(lock_cr, signature):
            _logger.info("Not upgrading %s on %s: the same upgrade failed less than %s "
                         "minutes ago (see the error above)", ', '.join(sorted(pending)),
                         db_name, _RETRY_AFTER // 60)
            return
        try:
            _hold_scheduler(lock_cr, pending)
        except _SchedulerBusy:
            _upgrade_later(db_name, _BUSY_LATER, "a scheduled job is still running, "
                                                 "trying again in %s seconds" % _BUSY_LATER)
            return
        _logger.warning("Code on disk is newer than database %s, upgrading: %s",
                        db_name, _describe(pending))
        try:
            Registry.new(db_name, upgrade_modules=sorted(pending))
        except Exception:  # noqa: BLE001
            _logger.exception(
                "Upgrading %s on %s failed. The site keeps the code it loaded; "
                "fix the error, then restart Odoo or upgrade the module in Apps.",
                ', '.join(sorted(pending)), db_name)
            # Registry.new removes the registry it fails on (and resets the
            # module states); put back the one we had, or loading fails too.
            Registry.registries[db_name] = current
            lock_cr.rollback()
            _set_failed(lock_cr, '%s|%s' % (signature, time.time()))
            return
        lock_cr.commit()
        left = _pending(lock_cr)
        if left:
            _logger.error("After upgrading, %s on %s still record an older version",
                          ', '.join(sorted(left)), db_name)
            _set_failed(lock_cr, '%s|%s' % (_signature(left), time.time()))
        else:
            _logger.warning("Upgraded %s on %s", ', '.join(sorted(pending)), db_name)
            _set_failed(lock_cr, None)
    except Exception:  # noqa: BLE001
        _logger.exception("Automatic module upgrade on %s stopped", db_name)
    finally:
        _RUNNING.discard(db_name)
        try:
            lock_cr.rollback()
            lock_cr.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])
            lock_cr.commit()
        except Exception:  # noqa: BLE001
            _logger.exception("Could not release the module upgrade lock on %s", db_name)
        finally:
            lock_cr.close()


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _register_hook(self):
        super()._register_hook()
        upgrade_if_code_is_newer(self.env)
