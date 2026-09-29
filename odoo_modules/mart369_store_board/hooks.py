def uninstall_hook(env):
    """Put mart369_order's own Orders menu back (models/ir_ui_menu.py)."""
    env['ir.ui.menu']._mart369_board_give_back_orders_menu()
