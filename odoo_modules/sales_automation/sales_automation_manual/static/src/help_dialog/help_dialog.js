/** @odoo-module **/
// sales_automation_manual: its own copy of the WhatsApp Help pop-up (27 Nov 2026), so its Help
// works with any whatsapp_gateway version. Help pop-up: every WhatsApp guide opens over the current screen, in the
// same browser tab. A function client action (not a component action), so
// opening it from a form pop-up (Add email, Send...) keeps that form open.
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

const HELP_HOME = "/sales_automation_manual/static/help/help.html";
const PLAYER = "/sales_automation_manual/static/src/help/video.html";

/** A .webm opens in the small player page (title, controls, Back). */
export function helpSrc_sam(url) {
    url = url || HELP_HOME;
    return url.split(/[?#]/)[0].endsWith(".webm") ? `${PLAYER}?v=${encodeURIComponent(url)}` : url;
}

export class HelpDialog_sam extends Component {
    static template = "sales_automation_manual.HelpDialog";
    static components = { Dialog };
    static props = { url: { type: String, optional: true }, title: { type: String, optional: true }, close: Function };

    setup() {
        this.state = useState({ loaded: false });
        this.src = helpSrc_sam(this.props.url);
    }

    onLoad() {
        this.state.loaded = true;
    }
}

export function openHelp_sam(dialog, url, title) {
    dialog.add(HelpDialog_sam, { url: url || HELP_HOME, title: title || _t("Help") });
}

// return {'type': 'ir.actions.client', 'tag': 'sales_automation_manual.help', 'name': ..., 'params': {'url': ...}}
registry.category("actions").add("sales_automation_manual.help", (env, action) => {
    const params = action.params || {};
    openHelp_sam(env.services.dialog, params.url, action.name || params.title);
});

// <widget name="sales_automation_manual_help_link" url="/.../guide.html" string="How does it work?"/>
// a plain link in a form: nothing is saved, no required field is checked
export class HelpLink_sam extends Component {
    static template = "sales_automation_manual.HelpLink";
    static props = { ...standardWidgetProps, url: String, label: String };

    setup() {
        this.dialog = useService("dialog");
    }

    onClick() {
        openHelp_sam(this.dialog, this.props.url, this.props.label);
    }
}

registry.category("view_widgets").add("sales_automation_manual_help_link", {
    component: HelpLink_sam,
    extractProps: ({ attrs }) => ({ url: attrs.url || HELP_HOME, label: attrs.string || _t("Help") }),
});
