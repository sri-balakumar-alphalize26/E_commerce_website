/** 28 Nov 2026: on a product, the top button says "In store" / "Hidden"
 *  instead of Published / Unpublished. Website pages, blogs and the rest keep
 *  their own words. */
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

const PRODUCT_MODELS = ["product.template", "product.product"];
const field = registry.category("fields").get("website_redirect_button", null);

if (field) {
    patch(field.component.prototype, {
        get info() {
            if (PRODUCT_MODELS.includes(this.props.record.resModel)) {
                return this.props.record.data[this.props.name] ? _t("In store") : _t("Hidden");
            }
            return super.info;
        },
    });
}
