/*
 * Reset the WhatsApp Panel's platform-administrator password.
 *
 * The shipped `init-db.js --reset-password` cannot be used safely here. It
 * finds the row with `WHERE username = $1` and then updates `rows[0].id` -
 * but this install has two accounts both called `admin`:
 *
 *     id=1  admin  company_id NULL   <- the platform administrator
 *     id=2  admin  company_id 2      <- a vendor's own login
 *
 * With no ORDER BY, which row comes back first is unspecified, so running it
 * can reset the vendor's password instead and lock them out while reporting
 * success.
 *
 * This targets `id = 1 AND company_id IS NULL`, so it can only ever touch the
 * platform administrator. The vendor login is left exactly as it is.
 *
 * Usage:  node reset_panel_admin.js "the-new-password"
 */
require('dotenv').config({ quiet: true });

const { Pool } = require('pg');
const bcrypt = require('bcryptjs');

const password = process.argv[2];
if (!password || password.length < 6) {
  console.error('Give a password of at least 6 characters as the argument.');
  process.exit(1);
}

const pool = new Pool({ connectionString: process.env.PANEL_DATABASE_URL });

pool.query(
  'UPDATE wap_admin SET password_hash = $1 ' +
  'WHERE id = 1 AND company_id IS NULL RETURNING id, username',
  [bcrypt.hashSync(password, 10)]
).then((res) => {
  if (!res.rows.length) {
    console.log('No platform-administrator row matched. Nothing changed.');
  } else {
    console.log('Reset done for id=' + res.rows[0].id +
                ', username=' + res.rows[0].username);
    console.log('The vendor login (id=2) was not touched.');
  }
  return pool.end();
}).catch((err) => {
  console.error('Failed: ' + err.message);
  return pool.end().then(() => process.exit(1));
});
