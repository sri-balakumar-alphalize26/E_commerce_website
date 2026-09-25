# 369 Mart Sign In (`mart369_auth`)

Customers create their own account on the storefront and sign in with their
**name or email** plus a password. Nothing to configure: installing the module
turns on free sign up.

Every account made this way is a **portal user**. It sees its own orders,
addresses and details and nothing else, and it cannot open the Odoo backend.
See who has signed up under **369 Mart → Customers**.

## The Customers screen

Styled like the storefront (navy / ocean blue / orange, rounded cards, pill buttons).

- **List** (default): a numbers strip on top — customers, new customers (with a
  14-day sign-up chart), ordered in 30 days, mobile on file, dormant. Click a tile
  to filter. One row per customer: avatar, name, email, mobile, city, signed up,
  last sign-in, orders, spent, status.
- **Board**: cards grouped New / Active / Dormant, with a follow-up hint on new
  customers without an order and on dormant ones.
- **Profile**: avatar, contact line and status; totals (orders, spent, average
  order, last order, last sign-in, customer for); tabs for Overview, Orders,
  Delivery addresses, Activity (sign-ins and orders) and Password & access
  (reset link, change password, archive).

![The Customers list](static/description/customers_list.png)
![The board](static/description/customers_board.png)
![A customer profile](static/description/customer_profile.png)
![Password & access](static/description/customer_password.png)

Status: *New* = signed up in the last 30 days, *Dormant* = no sign-in for 90 days,
*Archived* = sign-in blocked, everyone else *Active*. Both numbers are set in
**Settings → Customers**, and saving them recomputes every customer at once. A
New customer's badge says how long it has left: "New · 12 days left".

A New customer has a second badge: **Active · ordered 2 h ago** once they have
placed an order, **Not ordered yet** until then. Every Active and Dormant badge
says when the customer last ordered ("Active · ordered 3 d ago", "Dormant ·
no orders"), and so does the Last order column. *Placed* counts: a
cash-on-delivery order counts before anyone confirms it; an unpaid online
order or a cancelled one does not.

![The Customers desk: days left, and ordered or not](static/description/customers_new_days_left.png)
![The same in the web admin](static/description/web_admin_customers_days_left.png)

**Demo customers for Dormant.** `tools/seed_demo_customers.py` adds five
long-quiet customers - back-dated sign-up, last sign-in and (with the orders
module) orders placed months ago - so the Dormant tab has something to show:

    "C:\Program Files\Odoo 19.0.20260119\python\python.exe" odoo-bin shell ^
        -c odoo.conf -d <db> --no-http < tools/seed_demo_customers.py

Safe to run again: the same customers are moved back to the same dates and
their demo orders (`369M-DORM-…`) replaced. Run it from `cmd`, not by piping in
PowerShell - PowerShell adds a byte-order mark Python refuses.

![Dormant customers, with when they last ordered](static/description/customers_dormant.png)
![The same in the web admin](static/description/web_admin_customers_dormant.png)

**Settings → Customers** (Odoo's Settings screen and the web admin's) picks each
number from 15, 30, 45, 60, 90, 120 or 150 days, or **Custom…**, which asks for
any number in a small popup. A saved custom number shows as "21 days (custom)".

![Settings → Customers in Odoo, a custom 21 picked](static/description/settings_customers.png)
![The choices, in the web admin](static/description/settings_customers_dropdown.png)
![Custom… in Odoo](static/description/settings_customers_custom_odoo.png)
![Custom… in the web admin](static/description/settings_customers_custom_web_admin.png) Refreshed at every sign-in
and by the daily job "369 Mart: refresh customer status".

A mobile typed on the profile is checked for the customer's country and saved
as +919847021536; a landline or wrong length is refused.

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
