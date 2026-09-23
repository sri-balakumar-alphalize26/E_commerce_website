/** Our "are you sure?", which is Odoo's with our face on it.
 *
 * It extends `ConfirmationDialog` and overrides nothing but the template, so
 * every line of behaviour is still Odoo's: `_confirm`, `_cancel`, `_dismiss`,
 * the `isProcess` latch that stops a double press, the Escape handling and the
 * focus trap. Only the markup is ours.
 *
 * Extending rather than restyling, because there is nowhere to hang a class.
 * `web.ConfirmationDialog` passes no `contentClass` to its Dialog, so a rule
 * written against it would have to target every `.modal-content` in the
 * backend - including Odoo's own dialogs in form views, which are not ours to
 * repaint. A subclass gets us a class of our own and touches nothing else.
 *
 * Props are `ConfirmationDialog`'s, unchanged, so a call site swaps the
 * component name and nothing else.
 */
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { Icon } from "./icon";

export class Confirm extends ConfirmationDialog {
    static template = "mart369.Confirm";
    static components = { Dialog, Icon };

    /** Odoo says which button is dangerous through `confirmClass`, which is a
     *  bootstrap name. Read it rather than adding a prop of our own, so a call
     *  site that already says `btn-danger` keeps working and gets the red
     *  treatment - the icon included. */
    get danger() {
        return (this.props.confirmClass || "").includes("danger");
    }

    get icon() {
        return this.danger ? "trash" : "check";
    }
}
