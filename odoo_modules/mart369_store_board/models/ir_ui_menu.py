"""One Orders entry under 369 Mart › Sales.

The Counter's menu takes the desk's place; the desk's own menu is switched
off, not deleted or repointed, so it comes back untouched when this module is
uninstalled (hooks.py). The desk itself stays one click away, through the
toggle at the top of the Counter.
"""

from odoo import api, models

DESK_MENU = 'mart369_order.menu_mart369_orders'


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _mart369_board_take_orders_menu(self):
        menu = self.env.ref(DESK_MENU, raise_if_not_found=False)
        if menu and menu.active:
            menu.sudo().active = False

    @api.model
    def _mart369_board_give_back_orders_menu(self):
        menu = self.env.ref(DESK_MENU, raise_if_not_found=False)
        if menu and not menu.active:
            menu.sudo().active = True
