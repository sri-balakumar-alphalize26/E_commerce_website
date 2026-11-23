# WhatsApp control panel

Sits between every Odoo and the Evolution API gateway. A request is accepted only
when its key, its `X-Odoo-Url` and its `X-Odoo-Db` all match one registered
database, and it goes out only on the number the administrator assigned to that
database.

```
Odoo (many servers, many databases)
     |  its own key + the address and database it is
     v
panel :8086  -- role checks, number assignment, spam rules, quotas --
     |  adds the master key, which no tenant ever sees
     v
Evolution :8085  ->  one instance per NUMBER; a number serves one or many databases
```

## Logins (since 26 Sep 2026)

One sign-in form for everybody: vendor name + username + password.

| Role | Vendor field | Sees | Can do |
|---|---|---|---|
| Platform administrator | empty | everything | vendors and their logins, servers, databases, numbers, client logins, blocked words, every opt-out |
| Vendor | its name | its databases and numbers | each database's e-mail account and caps, the client password, its opt-outs, the QR pages of its numbers |
| Client (one per database) | the vendor's name | its one database | scan / reconnect the QR of its number, read the authorized number and sender address, its activity and opt-outs |

Reset or create a login from the command line:

    node reset_login.js --admin "password"
    node reset_login.js --vendor 369ai [--user admin] "password"
    node reset_login.js --db res-test1 [--user spa] "password"     (creates the client login when none exists)

## Numbers

A **number** = one Evolution instance + the ONE phone allowed to scan it
(`wap_number.authorized_number`). The administrator registers it on the *Add database* form (one
form: database, its user, its number, its mail), on the database page, or under *Numbers*, and may tick several
databases for one number. Every 30 s (and on every QR
page and `/v1/config` call) the panel compares the paired phone with the
authorized one; a different phone is logged out at once, the attempt is logged
on every database of the number, and sends are refused with
`scanned with A; only B is allowed` until the right phone scans. The same phone
number can never be attached to two number records.

The instance's webhook always points at this panel (`/hook/<instance>`); the
panel forwards every incoming message to each database on that number, with an
`X-Odoo-Database` header. Odoo tells the panel its own webhook address on
`/v1/config` (`X-Odoo-Webhook`), which Odoo sends on *Load Settings* and from
its cron, so nothing is typed by hand.

## Databases

`wap_database`: server + name + token (the setup key wraps the token and this
panel's address), vendor, assigned number, caps, `contact_number` for the
signature, `odoo_webhook_url`. Its e-mail account is its own row in `wap_email`
(`database_id`); `/email/send` always uses that account and drops any `from`
the caller sends.

## Endpoints Odoo calls

* `GET /v1/config` - what this database should use (number, authorized phone,
  pairing state, sender e-mail, limits). Both `X-Odoo-Db` and `X-Odoo-Url`
  headers are required.
* `/message/*`, `/chat/*`, `/group/*`, `/instance/connectionState`,
  `/instance/fetchInstances` - proxied to the gateway on the database's own
  instance, after opt-out, blocked-word and cap checks. `connectionState`
  answers `wrong_number` / `close` locally while the number cannot be used.
* `POST /email/send` - through the database's own SMTP account.

## Files

`server.js` (routes), `db.js` (schema + migrations, run at every start),
`views.js` (layout), `ui.js` (the look and the animations of every page), `mail.js` (SMTP), `reset_login.js`, `init-db.js`. Logs in
`logs\panel.log`. Runs as the Windows service `whatsapp-panel` (nssm). The
files from before the role rewrite are kept beside the new ones as `*.bak-roles`.
