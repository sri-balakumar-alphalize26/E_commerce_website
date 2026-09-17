# 369 Mart Sign In (`mart369_auth`)

Customers create their own account on the storefront and sign in with their
**name or email** plus a password. Nothing to configure: installing the module
turns on free sign up.

Every account made this way is a **portal user**. It sees its own orders,
addresses and details and nothing else, and it cannot open the Odoo backend.
See who has signed up under **369 Mart → Customers**.

## The routes

All under `/369mart/auth/`, JSON in and out, called by the storefront's own
server (`app/api/auth/*`), never straight from a browser.

| Route | Body | Answer |
|---|---|---|
| `POST signup` | `{name, email, password}` | `201 {ok, name, email}` and the session cookie, or `{ok:false, error, field}` |
| `POST login` | `{login, password}` — email or full name | `200 {ok, name, email}` and the session cookie, or `401` |
| `POST logout` | — | `{ok:true}` |
| `GET  me` | — | `{ok, name, email, phone, partner_id}` or `401` |
| `POST forgot` | `{email}` | always `{ok:true}` |

## Why the login is the email

`res.users.login` must be unique and full names are not — two Arun Kumars
would block the second sign up. So the email is the login and the name is the
name. Signing in by name works whenever the name is unique; if two accounts
share it the answer asks for the email instead.

## Needs

- An **outgoing mail server** in Odoo, or "Forgot password" answers ok but
  sends nothing.
- The server must know its database (`-d` or `dbfilter`), as for `mart369_home`.

## Tests

`odoo-bin -d <db> --test-enable --test-tags mart369_auth --stop-after-init`
