'use strict';

/**
 * Reset (or create) one panel login from the command line.
 *
 *   node reset_login.js --admin                       "new password"
 *   node reset_login.js --vendor 369ai [--user admin] "new password"
 *   node reset_login.js --db res-test1 [--user spa]   "new password"
 *
 * --db matches wap_database.db_name; with --user it creates the client login
 * when none exists yet. Exactly one row must match, otherwise nothing is done.
 */

const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const bcrypt = require('bcryptjs');
const { pool } = require('./db');

const args = process.argv.slice(2);
function opt(name) { const i = args.indexOf(name); return i === -1 ? null : args[i + 1]; }
const password = args[args.length - 1];
const isAdmin = args.includes('--admin');
const vendor = opt('--vendor');
const db = opt('--db');
const user = opt('--user');

if (!password || password.length < 6 || password.startsWith('--')) {
  console.error('Give a password of at least 6 characters as the last argument.');
  process.exit(2);
}

(async () => {
  let rows;
  if (isAdmin) {
    ({ rows } = await pool.query(
      'SELECT id, username FROM wap_admin WHERE company_id IS NULL AND database_id IS NULL' + (user ? ' AND username = $1' : ''),
      user ? [user] : []));
  } else if (vendor) {
    ({ rows } = await pool.query(
      `SELECT a.id, a.username FROM wap_admin a JOIN wap_company c ON c.id = a.company_id
        WHERE a.database_id IS NULL AND lower(c.name) = lower($1)` + (user ? ' AND a.username = $2' : ''),
      user ? [vendor, user] : [vendor]));
  } else if (db) {
    const dbs = await pool.query('SELECT id, company_id, db_name FROM wap_database WHERE db_name = $1', [db]);
    if (dbs.rows.length !== 1) { console.error(`${dbs.rows.length} databases called ${db}; expected exactly one.`); process.exit(3); }
    ({ rows } = await pool.query('SELECT id, username FROM wap_admin WHERE database_id = $1', [dbs.rows[0].id]));
    if (!rows.length && user) {
      const made = await pool.query(
        'INSERT INTO wap_admin (username, password_hash, company_id, database_id) VALUES ($1,$2,$3,$4) RETURNING id',
        [user, bcrypt.hashSync(password, 10), dbs.rows[0].company_id, dbs.rows[0].id]);
      console.log(`Created client login ${user} for ${db} (id=${made.rows[0].id}).`);
      process.exit(0);
    }
  } else {
    console.error('Say which login: --admin, --vendor <name> or --db <db_name>.');
    process.exit(2);
  }
  if (rows.length !== 1) {
    console.error(`${rows.length} logins match; add --user <username> to pick one.`);
    process.exit(3);
  }
  await pool.query('UPDATE wap_admin SET password_hash = $1 WHERE id = $2', [bcrypt.hashSync(password, 10), rows[0].id]);
  console.log(`Reset done for id=${rows[0].id}, username=${rows[0].username}`);
  process.exit(0);
})().catch(err => { console.error(err.message); process.exit(1); });
