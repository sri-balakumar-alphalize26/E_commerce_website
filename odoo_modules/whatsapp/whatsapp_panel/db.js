'use strict';

/**
 * Postgres access + schema for the WhatsApp control panel.
 *
 * Tables live in the same `evolution` database but under a wap_ prefix, so they
 * cannot collide with anything Prisma owns. Prisma only ever migrates its own
 * tables, and it is never pointed at these.
 *
 * Who owns what (since 26 Sep 2026):
 *
 *   platform admin  -> vendors, servers, databases, NUMBERS, every login
 *   vendor          -> sees its databases and numbers; sets each database's
 *                      mail account and its client password
 *   client          -> one login per database; sees that database only
 *   number          -> one Evolution instance + the ONE phone that may scan it;
 *                      assigned to one or many databases by the admin
 */

const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.PANEL_DATABASE_URL,
  max: 8,
  idleTimeoutMillis: 30000,
});

/** Normalise a server address down to scheme://host[:port], lowercased.
 *
 * Odoo reports its own address from web.base.url, which may carry a path, a
 * trailing slash or odd casing. Comparing raw strings would reject a server
 * that is registered perfectly well, so both sides are reduced to an origin
 * before they are ever compared.
 */
function origin(raw) {
  if (!raw) return '';
  let value = String(raw).trim();
  if (!/^https?:\/\//i.test(value)) value = 'https://' + value;
  try {
    const url = new URL(value);
    return (url.protocol + '//' + url.host).toLowerCase();
  } catch (err) {
    return '';
  }
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS wap_admin (
  id            SERIAL PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A software company - one of the vendors on this platform. Its numbers live
-- in wap_number now; instance_name here is only the pre-2026-09 shared one,
-- kept NULL once it has been turned into a number record.
CREATE TABLE IF NOT EXISTS wap_company (
  id            SERIAL PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  instance_name TEXT UNIQUE,
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wap_server (
  id         SERIAL PRIMARY KEY,
  name       TEXT NOT NULL,
  base_url   TEXT NOT NULL UNIQUE,
  active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A WhatsApp number: one Evolution instance and the ONE phone number that is
-- allowed to scan it. The admin creates it and assigns it to one or several
-- databases. A scan by any other phone is logged out again by the panel.
CREATE TABLE IF NOT EXISTS wap_number (
  id                 SERIAL PRIMARY KEY,
  company_id         INTEGER NOT NULL REFERENCES wap_company(id) ON DELETE RESTRICT,
  label              TEXT NOT NULL DEFAULT '',
  authorized_number  TEXT NOT NULL DEFAULT '',
  instance_name      TEXT NOT NULL UNIQUE,
  pair_state         TEXT NOT NULL DEFAULT 'close',
  paired_number      TEXT NOT NULL DEFAULT '',
  profile_name       TEXT NOT NULL DEFAULT '',
  pair_checked_at    TIMESTAMPTZ,
  last_wrong_number  TEXT NOT NULL DEFAULT '',
  wrong_number_at    TIMESTAMPTZ,
  wrong_number_count INTEGER NOT NULL DEFAULT 0,
  hook_secret        TEXT NOT NULL DEFAULT '',
  webhook_applied    BOOLEAN NOT NULL DEFAULT FALSE,
  active             BOOLEAN NOT NULL DEFAULT TRUE,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS wap_number_authorized_idx
  ON wap_number (authorized_number) WHERE authorized_number <> '';

CREATE TABLE IF NOT EXISTS wap_database (
  id           SERIAL PRIMARY KEY,
  server_id    INTEGER NOT NULL REFERENCES wap_server(id) ON DELETE CASCADE,
  company_id   INTEGER REFERENCES wap_company(id) ON DELETE RESTRICT,
  db_name      TEXT NOT NULL,
  tenant_label TEXT NOT NULL DEFAULT '',
  token        TEXT NOT NULL UNIQUE,
  active       BOOLEAN NOT NULL DEFAULT TRUE,
  daily_cap    INTEGER NOT NULL DEFAULT 500,
  per_minute   INTEGER NOT NULL DEFAULT 20,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (server_id, db_name)
);

-- Opt-outs follow the number a person blocked. A row with a database_id is
-- for that database; a row with only company_id is vendor-wide.
CREATE TABLE IF NOT EXISTS wap_optout (
  id         SERIAL PRIMARY KEY,
  phone      TEXT NOT NULL UNIQUE,
  reason     TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Words that must never leave any number. Enforced here rather than in Odoo
-- so a misconfigured or compromised tenant cannot bypass it.
CREATE TABLE IF NOT EXISTS wap_block (
  id         SERIAL PRIMARY KEY,
  pattern    TEXT NOT NULL UNIQUE,
  reason     TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One outgoing mail account per DATABASE (database_id set). Rows with only a
-- company_id are the pre-2026-09 vendor accounts, kept as a template and
-- never used to send.
CREATE TABLE IF NOT EXISTS wap_email (
  id          SERIAL PRIMARY KEY,
  company_id  INTEGER REFERENCES wap_company(id) ON DELETE CASCADE,
  host        TEXT NOT NULL,
  port        INTEGER NOT NULL DEFAULT 587,
  secure      BOOLEAN NOT NULL DEFAULT FALSE,   -- true = SMTPS on connect (465)
  username    TEXT NOT NULL DEFAULT '',
  password    TEXT NOT NULL DEFAULT '',
  from_name   TEXT NOT NULL DEFAULT '',
  from_email  TEXT NOT NULL,
  active      BOOLEAN NOT NULL DEFAULT TRUE,
  daily_cap   INTEGER NOT NULL DEFAULT 1000,
  per_minute  INTEGER NOT NULL DEFAULT 30,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wap_email_optout (
  id         SERIAL PRIMARY KEY,
  company_id INTEGER REFERENCES wap_company(id) ON DELETE CASCADE,
  email      TEXT NOT NULL,
  reason     TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wap_log (
  id          SERIAL PRIMARY KEY,
  database_id INTEGER REFERENCES wap_database(id) ON DELETE SET NULL,
  claimed_url TEXT NOT NULL DEFAULT '',
  claimed_db  TEXT NOT NULL DEFAULT '',
  remote_ip   TEXT NOT NULL DEFAULT '',
  phone       TEXT NOT NULL DEFAULT '',
  channel     TEXT NOT NULL DEFAULT 'whatsapp',
  endpoint    TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL,
  detail      TEXT NOT NULL DEFAULT '',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS wap_log_created_idx ON wap_log (created_at DESC);
CREATE INDEX IF NOT EXISTS wap_log_db_idx ON wap_log (database_id, created_at DESC);
`;

/** Bring an older installation up to date. Every statement is idempotent. */
const MIGRATE = `
-- ---- 2026-08: software companies
ALTER TABLE wap_log      ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'whatsapp';
ALTER TABLE wap_admin    ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES wap_company(id) ON DELETE CASCADE;
ALTER TABLE wap_database ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES wap_company(id) ON DELETE RESTRICT;
ALTER TABLE wap_database ADD COLUMN IF NOT EXISTS contact_number TEXT NOT NULL DEFAULT '';
ALTER TABLE wap_admin DROP CONSTRAINT IF EXISTS wap_admin_username_key;
DROP INDEX IF EXISTS wap_admin_username_key;
ALTER TABLE wap_optout   ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES wap_company(id) ON DELETE CASCADE;
-- The constraint has to go before the index: the unique index is owned by the
-- constraint, so dropping the index first fails with "cannot drop index ...
-- because constraint ... requires it".
ALTER TABLE wap_optout DROP CONSTRAINT IF EXISTS wap_optout_phone_key;
DROP INDEX IF EXISTS wap_optout_phone_key;

-- ---- 2026-09-26: admin -> vendor -> client -> database -> number / email
-- A client login is a wap_admin row bound to one database. Usernames are
-- unique within their scope: platform, one vendor, or one database.
ALTER TABLE wap_admin ADD COLUMN IF NOT EXISTS database_id INTEGER REFERENCES wap_database(id) ON DELETE CASCADE;
DROP INDEX IF EXISTS wap_admin_company_username_idx;
CREATE UNIQUE INDEX IF NOT EXISTS wap_admin_scope_username_idx
  ON wap_admin (COALESCE(company_id, 0), COALESCE(database_id, 0), username);

-- The number is its own record now; the vendor no longer owns one.
ALTER TABLE wap_company ALTER COLUMN instance_name DROP NOT NULL;
ALTER TABLE wap_database ADD COLUMN IF NOT EXISTS number_id INTEGER REFERENCES wap_number(id) ON DELETE SET NULL;
ALTER TABLE wap_database ADD COLUMN IF NOT EXISTS odoo_webhook_url TEXT NOT NULL DEFAULT '';
-- Optional footer: the no-reply notice plus the support number, on WhatsApp and e-mail.
ALTER TABLE wap_database ADD COLUMN IF NOT EXISTS sign_messages BOOLEAN NOT NULL DEFAULT TRUE;

-- Mail account per database.
ALTER TABLE wap_email ADD COLUMN IF NOT EXISTS database_id INTEGER REFERENCES wap_database(id) ON DELETE CASCADE;
ALTER TABLE wap_email ALTER COLUMN company_id DROP NOT NULL;
ALTER TABLE wap_email DROP CONSTRAINT IF EXISTS wap_email_company_id_key;
DROP INDEX IF EXISTS wap_email_company_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS wap_email_database_idx ON wap_email (database_id) WHERE database_id IS NOT NULL;

-- Opt-outs per database, vendor-wide rows still allowed (database_id NULL).
ALTER TABLE wap_optout       ADD COLUMN IF NOT EXISTS database_id INTEGER REFERENCES wap_database(id) ON DELETE CASCADE;
ALTER TABLE wap_email_optout ADD COLUMN IF NOT EXISTS database_id INTEGER REFERENCES wap_database(id) ON DELETE CASCADE;
ALTER TABLE wap_email_optout ALTER COLUMN company_id DROP NOT NULL;
DROP INDEX IF EXISTS wap_optout_company_phone_idx;
CREATE UNIQUE INDEX IF NOT EXISTS wap_optout_scope_phone_idx
  ON wap_optout (COALESCE(company_id, 0), COALESCE(database_id, 0), phone);
ALTER TABLE wap_email_optout DROP CONSTRAINT IF EXISTS wap_email_optout_company_id_email_key;
DROP INDEX IF EXISTS wap_email_optout_company_id_email_key;
CREATE UNIQUE INDEX IF NOT EXISTS wap_email_optout_scope_idx
  ON wap_email_optout (COALESCE(company_id, 0), COALESCE(database_id, 0), lower(email));

-- ---- 2026-11-23: several numbers in one database. Each number of a database
-- is its own row: own key, own webhook, own caps. The same number only once.
ALTER TABLE wap_database DROP CONSTRAINT IF EXISTS wap_database_server_id_db_name_key;
CREATE UNIQUE INDEX IF NOT EXISTS wap_database_number_once_idx
  ON wap_database (server_id, db_name, number_id) WHERE number_id IS NOT NULL;

-- How many numbers this database's own Odoo may have by adding them itself.
-- 0 = only the administrator adds numbers here. A database added from now on
-- starts with 10; those that are there keep what they have.
ALTER TABLE wap_database ADD COLUMN IF NOT EXISTS own_numbers_max INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wap_database ALTER COLUMN own_numbers_max SET DEFAULT 10;

-- One number turned off: '' = on, 'admin' (here) or 'odoo' (there).
ALTER TABLE wap_database ADD COLUMN IF NOT EXISTS off_by TEXT NOT NULL DEFAULT '';

-- Incoming messages Odoo could not take (restart, upgrade): sent again for a
-- few minutes. Emptied as they are delivered or given up.
CREATE TABLE IF NOT EXISTS wap_retry (
  id          SERIAL PRIMARY KEY,
  database_id INTEGER NOT NULL REFERENCES wap_database(id) ON DELETE CASCADE,
  number_id   INTEGER,
  payload     TEXT NOT NULL,
  tries       INTEGER NOT NULL DEFAULT 0,
  first_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  next_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS wap_retry_db_idx ON wap_retry (database_id, id);
ALTER TABLE wap_retry ADD COLUMN IF NOT EXISTS arrived BIGINT NOT NULL DEFAULT 0;

-- 2026-11-26: a new Odoo database links itself (POST /v1/link) with its
-- vendor's link token (one per vendor, the same for every database). Per
-- vendor; the administrator can switch it off or make a new token.
ALTER TABLE wap_company ADD COLUMN IF NOT EXISTS odoo_link BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE wap_company ADD COLUMN IF NOT EXISTS link_token TEXT;
ALTER TABLE wap_company ALTER COLUMN link_token SET DEFAULT md5(random()::text || clock_timestamp()::text);
UPDATE wap_company SET link_token = md5(random()::text || clock_timestamp()::text || id::text)
 WHERE link_token IS NULL OR link_token = '';
CREATE UNIQUE INDEX IF NOT EXISTS wap_company_link_token_idx ON wap_company (link_token);

-- 2026-11-26: a free number is offered in Odoo only where allowed - each Odoo
-- database is a separate client. '' = nobody (the administrator assigns it),
-- '*' = every database of the vendor, '<server id>:<db name>' = that database.
ALTER TABLE wap_number ADD COLUMN IF NOT EXISTS offer_to TEXT NOT NULL DEFAULT '';
`;

/**
 * Data brought forward from the vendor-owns-the-number layout. SQL only, so a
 * gateway that is down at start-up cannot stop the panel from coming up.
 */
const CARRY_FORWARD = `
-- Each vendor's shared instance becomes a number record ...
INSERT INTO wap_number (company_id, label, instance_name, hook_secret)
SELECT c.id, c.name || ' number', c.instance_name, md5(random()::text || clock_timestamp()::text)
  FROM wap_company c
 WHERE c.instance_name IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM wap_number n WHERE n.instance_name = c.instance_name);
-- ... assigned to every database of that vendor that has no number yet ...
UPDATE wap_database d SET number_id = n.id
  FROM wap_company c JOIN wap_number n ON n.instance_name = c.instance_name
 WHERE c.id = d.company_id AND d.number_id IS NULL;
-- ... and the vendor row lets go of it.
UPDATE wap_company SET instance_name = NULL WHERE instance_name IS NOT NULL;
-- The vendor's mail account is copied onto each of its databases.
INSERT INTO wap_email (database_id, company_id, host, port, secure, username, password,
                       from_name, from_email, active, daily_cap, per_minute)
SELECT d.id, e.company_id, e.host, e.port, e.secure, e.username, e.password,
       e.from_name, e.from_email, e.active, e.daily_cap, e.per_minute
  FROM wap_email e
  JOIN wap_database d ON d.company_id = e.company_id
 WHERE e.database_id IS NULL
   AND NOT EXISTS (SELECT 1 FROM wap_email x WHERE x.database_id = d.id);
-- Client rows created before company_id was denormalised onto them.
UPDATE wap_admin a SET company_id = d.company_id
  FROM wap_database d
 WHERE d.id = a.database_id AND a.company_id IS DISTINCT FROM d.company_id;
`;

async function init(defaults = {}) {
  await pool.query(SCHEMA);
  await pool.query(MIGRATE);

  // Databases registered before software companies existed have no company and
  // would silently stop sending, so one is created to adopt them.
  //
  // Gated on there being orphans to adopt. Without that gate an empty panel -
  // one deliberately cleared to be set up from scratch - would grow a company
  // back on every restart, pointing at an instance that may no longer exist.
  const orphans = await pool.query(
    'SELECT count(*)::int AS n FROM wap_database WHERE company_id IS NULL');
  const companies = await pool.query('SELECT count(*)::int AS n FROM wap_company');
  if (orphans.rows[0].n && !companies.rows[0].n && defaults.companyName && defaults.instance) {
    await pool.query('INSERT INTO wap_company (name, instance_name) VALUES ($1,$2)',
      [defaults.companyName, defaults.instance]);
  }
  await pool.query(`
    UPDATE wap_database SET company_id = (SELECT id FROM wap_company ORDER BY id LIMIT 1)
     WHERE company_id IS NULL`);
  await pool.query(`
    UPDATE wap_optout SET company_id = (SELECT id FROM wap_company ORDER BY id LIMIT 1)
     WHERE company_id IS NULL AND database_id IS NULL`);

  await pool.query(CARRY_FORWARD);
}

module.exports = { pool, init, origin };
