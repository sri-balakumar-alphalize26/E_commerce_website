/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { CheckBox } from "@web/core/checkbox/checkbox";
import { BooleanField } from "@web/views/fields/boolean/boolean_field";
import { booleanToggleField } from "@web/views/fields/boolean_toggle/boolean_toggle_field";

/**
 * Single-active toggle for the Loyalty Settings / Points Rules lists.
 * On click it calls the server `action_activate` method directly (which turns
 * the others off), then reloads the list — so it works straight from a
 * NON-editable list without entering row-edit mode. Turning a record OFF from
 * the list is not allowed (you switch by turning another ON).
 */
export class LoyaltyActiveToggleField extends BooleanField {
    static template = "pos_loyalty_card.LoyaltyActiveToggle";
    static components = { CheckBox };
    static props = {
        ...BooleanField.props,
        autosave: { type: Boolean, optional: true },
    };

    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.orm = useService("orm");
    }

    stopClick() {
        // wrapper handler; the .stop modifier prevents the row from opening.
    }

    async onChange(newValue) {
        const record = this.props.record;
        // Only activation is allowed from the list.
        if (!newValue || record.data[this.props.name]) {
            this.state.value = record.data[this.props.name];
            return;
        }
        const ok = await new Promise((resolve) => {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Switch active"),
                body: _t(
                    "Switch the active record to this one? The currently active one will be turned off."
                ),
                confirmLabel: _t("Switch"),
                confirm: () => resolve(true),
                cancelLabel: _t("Cancel"),
                cancel: () => resolve(false),
            });
        });
        if (!ok) {
            this.state.value = false;
            return;
        }
        try {
            await this.orm.call(record.resModel, "action_activate", [[record.resId]]);
            await record.model.load();
        } catch (e) {
            this.state.value = false;
            throw e;
        }
    }
}

export const loyaltyActiveToggleField = {
    ...booleanToggleField,
    component: LoyaltyActiveToggleField,
    displayName: _t("Single-active Toggle"),
};

registry.category("fields").add("loyalty_active_toggle", loyaltyActiveToggleField);
