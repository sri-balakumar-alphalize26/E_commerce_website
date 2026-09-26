"""Widen the backend board's action to both channels - and put it back.

The act_window's domain is a stored string on another module's record.
Written from a hook rather than a data record, because a data record's write
would survive uninstalling this module - and then the board would filter on
a field that no longer exists.
"""

WIDE = ("['|', ('mart369_ref', '!=', False), "
        "('mart369_channel', '=', 'whatsapp'), "
        "('mart369_state', 'not in', (False, 'draft'))]")
NARROW = ("[('mart369_ref', '!=', False), "
          "('mart369_state', 'not in', (False, 'draft'))]")


def post_init_hook(env):
    action = env.ref('mart369_order.action_mart369_orders',
                     raise_if_not_found=False)
    if action:
        action.domain = WIDE


def uninstall_hook(env):
    action = env.ref('mart369_order.action_mart369_orders',
                     raise_if_not_found=False)
    if action:
        action.domain = NARROW
