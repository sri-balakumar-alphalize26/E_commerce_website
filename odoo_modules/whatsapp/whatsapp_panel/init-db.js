'use strict';

/**
 * Create the panel tables and the one admin login.
 *
 * Safe to run more than once: the schema uses IF NOT EXISTS and the admin is
 * only created when there is none. It never silently resets a password - use
 * `node init-db.js --reset-password` for that, deliberately.
 */

const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const crypto = require('crypto');
const bcrypt = require('bcryptjs');
const { pool, init } = require('./db');

function readablePassword() {
  // Avoids l/1/I and O/0 so it can be read off a screen and typed correctly.
  const alphabet = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  const bytes = crypto.randomBytes(18);
  return Array.from(bytes, b => alphabet[b % alphabet.length]).join('');
}

(async () => {
  await init();
  console.log('tables ready');

  const username = process.env.PANEL_ADMIN_USER || 'admin';
  const reset = process.argv.includes('--reset-password');
  const { rows } = await pool.query('SELECT id FROM wap_admin WHERE username = $1 AND company_id IS NULL AND database_id IS NULL', [username]);

  if (rows.length && !reset) {
    console.log(`admin '${username}' already exists - left alone`);
    console.log('(run with --reset-password to set a new one)');
  } else {
    const password = readablePassword();
    const hash = bcrypt.hashSync(password, 10);
    if (rows.length) {
      await pool.query('UPDATE wap_admin SET password_hash=$1 WHERE id=$2', [hash, rows[0].id]);
      console.log('password reset');
    } else {
      await pool.query('INSERT INTO wap_admin (username, password_hash) VALUES ($1,$2)', [username, hash]);
      console.log('admin created');
    }
    console.log('');
    console.log('    username: ' + username);
    console.log('    password: ' + password);
    console.log('');
    console.log('This is the only time it is shown. Change it after signing in.');
  }
  await pool.end();
})().catch(err => {
  console.error('failed:', err.message);
  process.exit(1);
});
