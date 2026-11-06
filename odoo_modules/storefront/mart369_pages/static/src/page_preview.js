/**
 * The info page as shoppers see it, beside its form: the real shop page
 * (ShopFrame, from the 369 Mart product editor). It shows what is saved, so
 * it reloads after Save - the record's write date is its key.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { ShopFrame } from "@mart369_product/products/shop_frame";

export class PagePreview extends Component {
    static template = "mart369_pages.PagePreview";
    static components = { ShopFrame };
    static props = { ...standardWidgetProps };

    get url() {
        const record = this.props.record;
        return record.resId ? record.data.preview_url || "" : "";
    }

    get key() {
        const record = this.props.record;
        return `${record.resId}-${record.data.write_date || ""}`;
    }
}

registry.category("view_widgets").add("mart369_page_preview", { component: PagePreview });
