/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);

        const model = this.props.resModel;
        this._isLoyaltyCard = model === "pos.loyalty.card";
        this._isCustomerDetails = false;

        // Detect Customer Details view: res.partner with customer_details_view context
        if (model === "res.partner") {
            try {
                const ctx = this.props.context || {};
                if (ctx.customer_details_view) {
                    this._isCustomerDetails = true;
                }
            } catch (e) {
                // fallback: skip
            }
        }

        if (this._isLoyaltyCard || this._isCustomerDetails) {
            this._actionService = useService("action");
            this._ormService = useService("orm");
            this._dialogService = useService("dialog");

            onMounted(() => {
                if (this._isLoyaltyCard) {
                    this._addDeletedCardsButton();
                }
                if (this._isCustomerDetails) {
                    this._addGenerateCardsButton();
                    this._addDeletedCustomersButton();
                }
            });
        }
    },

    _addGenerateCardsButton() {
        const cpButtons = document.querySelector(".o_control_panel_main_buttons .d-flex")
            || document.querySelector(".o_control_panel_main_buttons")
            || document.querySelector(".o_cp_buttons");

        if (!cpButtons) return;
        if (cpButtons.querySelector(".o_generate_cards_btn")) return;

        const btn = document.createElement("button");
        btn.className = "btn btn-primary o_generate_cards_btn ms-1";
        btn.innerHTML = "🎁 Generate Loyalty Cards";
        btn.addEventListener("click", () => {
            this._dialogService.add(ConfirmationDialog, {
                title: "Generate Loyalty Cards",
                body: "Generate loyalty cards for all customers who don't have one yet? "
                    + "Customers who already have a card are skipped.",
                confirmLabel: "Generate",
                confirm: async () => {
                    const action = await this._ormService.call(
                        "res.partner",
                        "action_generate_all_loyalty_cards",
                        [],
                    );
                    await this._actionService.doAction(action, {
                        onClose: async () => {
                            try {
                                if (this.model && this.model.root) {
                                    await this.model.root.load();
                                    this.render(true);
                                }
                            } catch {
                                window.location.reload();
                            }
                        },
                    });
                },
                cancel: () => {},
            });
        });
        cpButtons.appendChild(btn);
    },

    _addDeletedCardsButton() {
        const cpButtons = document.querySelector(".o_control_panel_main_buttons .d-flex")
            || document.querySelector(".o_control_panel_main_buttons")
            || document.querySelector(".o_cp_buttons");

        if (!cpButtons) return;
        if (cpButtons.querySelector(".o_deleted_loyalty_btn")) return;

        const btn = document.createElement("button");
        btn.className = "btn btn-secondary o_deleted_loyalty_btn ms-1";
        btn.innerHTML = "🗑️ Deleted Loyalty Cards";
        btn.addEventListener("click", async () => {
            const action = await this._ormService.call(
                "pos.loyalty.card",
                "action_view_deleted_cards",
                [],
            );
            await this._actionService.doAction(action, {
                onClose: async () => {
                    try {
                        if (this.model && this.model.root) {
                            await this.model.root.load();
                            this.render(true);
                        }
                    } catch {
                        window.location.reload();
                    }
                },
            });
        });
        cpButtons.appendChild(btn);
    },

    _addDeletedCustomersButton() {
        const cpButtons = document.querySelector(".o_control_panel_main_buttons .d-flex")
            || document.querySelector(".o_control_panel_main_buttons")
            || document.querySelector(".o_cp_buttons");

        if (!cpButtons) return;
        if (cpButtons.querySelector(".o_deleted_customers_btn")) return;

        const btn = document.createElement("button");
        btn.className = "btn btn-secondary o_deleted_customers_btn ms-1";
        btn.innerHTML = "🗑️ Deleted Customers";
        btn.addEventListener("click", async () => {
            const action = await this._ormService.call(
                "res.partner",
                "action_view_deleted_customers",
                [],
            );
            await this._actionService.doAction(action, {
                onClose: async () => {
                    try {
                        if (this.model && this.model.root) {
                            await this.model.root.load();
                            this.render(true);
                        }
                    } catch {
                        window.location.reload();
                    }
                },
            });
        });
        cpButtons.appendChild(btn);
    },
});
