"""Put some long-quiet customers in the shop, so Dormant has something to show.

    "C:\\Program Files\\Odoo 19.0\\python\\python.exe" odoo-bin shell \\
        -c odoo.conf -d <db> --no-http < tools/seed_demo_customers.py

A tool, not module data, for the reason `mart369_order/tools/seed_demo_orders.py`
gives: customers have no business appearing in every install, and demo data is
switched off on the databases this runs against.

Dormant means no sign-in for the days set in Settings > Customers (90 by
default), so each customer is back-dated: when they signed up, when they last
signed in (a `res.users.log` row - Odoo's `login_date` reads the newest one),
and, when the orders module is installed, orders placed that long ago - so the
badge can say "Dormant · ordered 160 d ago", or "Dormant · no orders".

Re-running is safe: the customers are found by login and moved back to the
same dates, and their demo orders (refs `369M-DORM-`) are replaced.
"""

from datetime import timedelta

from odoo import fields

PREFIX = '369M-DORM'
# name, login, mobile, signed up (days ago), last sign-in (days ago, None:
# never came back), orders placed (days ago each)
CUSTOMERS = [
    ('Suresh Babu', 'suresh.dormant@369mart.test', '+91 94430 21876', 200, 150, [160]),
    ('Lakshmi Narayanan', 'lakshmi.dormant@369mart.test', '+91 98840 55310', 120, None, []),
    ('Farhan Ali', 'farhan.dormant@369mart.test', '+91 99620 18745', 300, 95, [100, 210]),
    ('Priya Menon', 'priya.dormant@369mart.test', '+91 97460 33092', 400, 180, [190, 250, 330]),
    ('Karthik Raja', 'karthik.dormant@369mart.test', '+91 90030 64128', 150, 130, []),
]


def log(message):
    print('[seed] %s' % message)


def ago(days):
    return fields.Datetime.now() - timedelta(days=days)


def customer(env, name, login, phone):
    """A storefront account: a portal user with an Indian mobile."""
    Users = env['res.users'].sudo().with_context(active_test=False)
    user = Users.search([('login', '=', login)], limit=1)
    india = env.ref('base.in')
    if not user:
        user = Users.create({
            'name': name, 'login': login, 'email': login,
            'group_ids': [(6, 0, [env.ref('base.group_portal').id])],
        })
    user.write({'active': True})
    # The country first: the mobile is checked against it, and the company
    # this runs in is in Oman.
    user.partner_id.write({'country_id': india.id, 'city': 'Chennai'})
    user.write({'phone': phone})
    return user


def backdate(env, user, joined, seen):
    """Signed up `joined` days ago; last signed in `seen` days ago (None: only
    the sign-up visit, so Dormant counts from the sign-up)."""
    cr = env.cr
    cr.execute('UPDATE res_users SET create_date = %s WHERE id = %s', (ago(joined), user.id))
    cr.execute('UPDATE res_partner SET create_date = %s WHERE id = %s',
               (ago(joined), user.partner_id.id))
    cr.execute('DELETE FROM res_users_log WHERE create_uid = %s', (user.id,))
    if seen is not None:
        cr.execute('INSERT INTO res_users_log (create_uid, create_date, write_uid, write_date) '
                   'VALUES (%s, %s, %s, %s)', (user.id, ago(seen), user.id, ago(seen)))
    user.invalidate_recordset()


def wipe_orders(env):
    if 'sale.order' not in env:
        return
    orders = env['sale.order'].sudo().search([('mart369_ref', 'like', PREFIX + '%')])
    if orders:
        log('removing %d demo order(s) from the last run' % len(orders))
        env.cr.execute("UPDATE sale_order SET state = 'cancel' WHERE id IN %s", (tuple(orders.ids),))
        orders.invalidate_recordset()
        orders.unlink()


def old_order(env, user, days, index):
    """A delivered order placed `days` ago. Written straight to its final state
    - it is history, and walking a months-old order through packing and
    delivery today would stamp today's dates on every step."""
    Order = env['sale.order'].sudo()
    product = env['product.product'].sudo().search(
        [('sale_ok', '=', True), ('is_published', '=', True), ('list_price', '>', 0)], limit=1)
    order = Order.create({
        'partner_id': user.partner_id.id,
        'mart369_ref': '%s-%d' % (PREFIX, index),
        'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1})],
    })
    when = ago(days)
    env.cr.execute(
        "UPDATE sale_order SET state = 'sale', mart369_state = 'delivered', "
        "mart369_placed_at = %s, date_order = %s, create_date = %s WHERE id = %s",
        (when, when, when, order.id))
    order.invalidate_recordset()
    return order


def main(env):
    log('starting')
    wipe_orders(env)
    has_orders = 'sale.order' in env and 'mart369_placed_at' in env['sale.order']._fields
    users = env['res.users']
    index = 1
    for name, login, phone, joined, seen, placed in CUSTOMERS:
        user = customer(env, name, login, phone)
        backdate(env, user, joined, seen)
        refs = []
        if has_orders:
            for days in placed:
                refs.append(old_order(env, user, days, index).mart369_ref)
                index += 1
        users |= user
        log('%-18s joined %3dd ago, last seen %s, orders %s'
            % (name, joined, '%dd ago' % seen if seen is not None else 'never',
               ', '.join(refs) or 'none'))

    users._mart369_refresh_status()
    for user in users:
        log('%-18s -> %s' % (user.name, user.mart369_status))
    env.cr.commit()
    log('done - %d customers' % len(users))


main(env)  # noqa: F821  (`env` is provided by `odoo-bin shell`)
