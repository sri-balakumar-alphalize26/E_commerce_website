"""Put some orders and returns in the shop, so the screens have something to show.

    "C:\\Program Files\\Odoo 19.0\\python\\python.exe" odoo-bin shell \\
        -c odoo.conf -d <db> --no-http < tools/seed_demo_orders.py

`mart369_parts_demo` does this for the catalogue - "so every screen has
something to show" - but orders are not catalogue and have no business
appearing in every install, so this is a tool rather than module data. Odoo's
own `demo:` key would not help either: demo data is switched off on the
databases this runs against, so it would never load.

It places orders the way the module does, through
`sale.order._mart369_place`, and moves them with `mart369_action_advance()`.
The one thing it skips is the gateway: rather than stand up a test provider on
a live database, it does what `payment_transaction.py:110-123` does for cash on
delivery - write the paid fields and set the state - so an order that gets here
is indistinguishable from one somebody placed.

Re-running is safe: every record it makes is prefixed `369M-DEMO`, and it
removes the previous batch before making a new one.
"""

from odoo import fields

PREFIX = '369M-DEMO'
CUSTOMERS = [
    ('Meera Sundaram', 'meera.demo@369mart.test', '+91 98450 11223'),
    ('Anjali Raghavan', 'anjali.demo@369mart.test', '+91 98450 44556'),
    ('Vikram Iyer', 'vikram.demo@369mart.test', '+91 98450 77889'),
]

# What each demo order should end up as. `steps` is how many times to press
# the board's own next-step button after placing.
ORDERS = [
    {'who': 0, 'mode': 'quick', 'steps': 0, 'method': 'upi',  'late': False},
    {'who': 1, 'mode': 'quick', 'steps': 0, 'method': 'cod',  'late': True},
    {'who': 2, 'mode': 'quick', 'steps': 1, 'method': 'card', 'late': False},
    {'who': 0, 'mode': 'all',   'steps': 1, 'method': 'upi',  'late': False},
    {'who': 1, 'mode': 'quick', 'steps': 2, 'method': 'cod',  'late': False},
    {'who': 2, 'mode': 'all',   'steps': 3, 'method': 'upi',  'late': False},
    {'who': 0, 'mode': 'quick', 'steps': 3, 'method': 'card', 'late': False},
]

# Returns, hung off the delivered orders above. One of each state the queue
# sorts by, so every tile has something behind it.
RETURNS = [
    {'order': 5, 'kind': 'refund',  'state': 'requested',
     'reason': 'Damaged or leaking',
     'detail': 'Sending back: 1 x the item - Pickup: today',
     'photos': 2},
    {'order': 6, 'kind': 'replace', 'state': 'pickup',
     'reason': 'Wrong item delivered',
     'detail': 'Sending back: 1 x the item - Pickup: tomorrow morning',
     'photos': 1},
    {'order': 5, 'kind': 'refund',  'state': 'picked',
     'reason': 'Quality not as expected',
     'detail': 'Sending back: 1 x the item - Pickup: today',
     'photos': 0},
]


def log(message):
    print('[seed] %s' % message)


def wipe(env):
    """Take the last batch out before making another."""
    orders = env['sale.order'].sudo().search([('mart369_ref', 'like', PREFIX + '%')])
    if not orders:
        return
    returns = env['mart369.order.return'].sudo().search(
        [('order_id', 'in', orders.ids)])
    photos = returns.mapped('photo_ids')
    log('removing %d order(s), %d return(s), %d photo(s) from the last run'
        % (len(orders), len(returns), len(photos)))
    returns.unlink()
    # Odoo deletes a record's own attachments with it, and now that `res_id`
    # is set these really are the return's own - so by here most of them are
    # already gone. `exists()` rather than assuming either way.
    photos.exists().unlink()
    # An order that has been confirmed cannot simply be deleted; put it back to
    # a draft first, which is what Odoo asks of anyone deleting a sale order.
    orders.sudo().filtered(lambda o: o.state != 'draft').action_cancel()
    orders.sudo().write({'mart369_state': 'draft'})
    orders.sudo().unlink()


def customer(env, name, login, phone):
    """A shopper with somewhere to deliver to."""
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if not user:
        user = env['res.users'].sudo().create({
            'name': name, 'login': login, 'email': login,
        })
    partner = user.partner_id
    partner.sudo().write({'phone': phone})
    address = env['res.partner'].sudo().search(
        [('parent_id', '=', partner.id), ('type', '=', 'delivery')], limit=1)
    if not address:
        address = env['res.partner'].sudo().create({
            'name': name,
            'parent_id': partner.id,
            # One delivery address per partner: a second `type=delivery` child
            # silently demotes the first to `other`.
            'type': 'delivery',
            'street': '12 Residency Road',
            'city': 'Kochi',
            'zip': '682016',
            'phone': phone,
        })
    return partner, address


def rules(env):
    """The two delivery rules, without which a basket has no postage."""
    Rule = env['mart369.delivery.rule'].sudo()
    for mode, values in (
        ('quick', {'label': 'Quick', 'eta': 'Delivery in 13 mins',
                   'min_order': 99.0, 'free_above': 499.0, 'fee': 30.0}),
        ('all', {'label': 'Express', 'eta': 'Delivery in 2-3 days',
                 'min_order': 0.0, 'free_above': 999.0, 'fee': 49.0}),
    ):
        rule = Rule.search([('mode', '=', mode)], limit=1)
        if rule:
            rule.write(values)
        else:
            Rule.create(dict(values, mode=mode))


def basket(env, mode):
    """Something really on sale, dear enough to clear the Quick minimum."""
    products = env['product.template'].sudo().search(
        [('is_published', '=', True), ('list_price', '>', 150)], limit=40)
    if not products:
        raise SystemExit('[seed] no published products with a price - '
                         'install mart369_parts_demo first')
    picked = products[:2] if len(products) > 1 else products
    return {str(p.id): 1 for p in picked}, picked


def place(env, partner, address, spec, index):
    """One order, placed and moved to where it should sit."""
    items, picked = basket(env, spec['mode'])
    order = env['sale.order'].sudo()._mart369_place(partner, {
        'ref': '%s-%d' % (PREFIX, index + 1),
        'items': items,
        'address_id': address.id,
        'mode': spec['mode'],
        'slot': 'Today, 6 - 8 PM' if spec['mode'] == 'quick' else 'Tomorrow',
    })

    # What the cash-on-delivery path writes before it sets the state. No
    # gateway is stood up: this is a demo shop, not a demo payment.
    order.write({
        'mart369_txn': '%s-TXN-%d' % (PREFIX, index + 1),
        'mart369_method': spec['method'],
        'mart369_placed_at': fields.Datetime.now(),
    })
    order._mart369_set_state('placed')
    order._mart369_confirm()
    order._mart369_issue_otp()

    for _step in range(spec['steps']):
        order.mart369_action_advance()

    if spec['late']:
        # Due an hour ago, so the queue has something to shout about.
        order.write({'mart369_due_at': fields.Datetime.subtract(
            fields.Datetime.now(), hours=1)})
    return order, picked


def photos(env, order, picked, count):
    """The customer's photos of what arrived.

    The product's own picture stands in for one, which is honest enough for a
    demo and beats a grey square. `res_id` is set, which the real route does
    not do - see the note in controllers/order_api.py.
    """
    made = env['ir.attachment'].sudo()
    for n in range(count):
        source = picked[n % len(picked)]
        if not source.image_1920:
            continue
        made |= env['ir.attachment'].sudo().create({
            'name': '%s-return-%d.jpg' % (order.mart369_ref, n + 1),
            'datas': source.image_1920,
            'res_model': 'mart369.order.return',
            'type': 'binary',
        })
    return made


def main(env):
    log('starting')
    wipe(env)
    rules(env)

    people = [customer(env, *who) for who in CUSTOMERS]
    orders = []
    for index, spec in enumerate(ORDERS):
        partner, address = people[spec['who']]
        order, picked = place(env, partner, address, spec, index)
        orders.append((order, picked))
        log('order %s  %-9s %-5s %s'
            % (order.mart369_ref, order.mart369_state, spec['method'],
               'LATE' if spec['late'] else ''))

    Return = env['mart369.order.return'].sudo()
    for spec in RETURNS:
        order, picked = orders[spec['order']]
        record = Return.create({
            'order_id': order.id,
            'kind': spec['kind'],
            'reason': spec['reason'],
            'detail': spec['detail'],
            'amount': order.amount_total,
            'state': 'requested',
        })
        shots = photos(env, order, picked, spec['photos'])
        if shots:
            record.write({'photo_ids': [(6, 0, shots.ids)]})
            # What the real route forgets, and why the photos cannot be served.
            shots.write({'res_id': record.id})
        # Walk it up with the model's own button rather than writing the state,
        # so anything that hangs off a transition really happens.
        while record.state != spec['state']:
            record.mart369_action_advance()
        log('return on %s  %-9s %-7s %d photo(s)'
            % (order.mart369_ref, record.state, record.kind, len(shots)))

    env.cr.commit()
    log('done - %d orders, %d returns' % (len(ORDERS), len(RETURNS)))


main(env)  # noqa: F821  (`env` is provided by `odoo-bin shell`)
