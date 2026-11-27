/** @odoo-module **/
// whatsapp_employee_tracker: its own copy of the WhatsApp Help pop-up (27 Nov 2026), so its Help
// works with any whatsapp_gateway version. Help pop-up: every WhatsApp guide opens over the current screen, in the
// same browser tab. A function client action (not a component action), so
// opening it from a form pop-up (Add email, Send...) keeps that form open.
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

const HELP_HOME = "/whatsapp_employee_tracker/static/help/help.html";
const PLAYER = "/whatsapp_employee_tracker/static/src/help/video.html";

/** A .webm opens in the small player page (title, controls, Back). */
export function helpSrc_wat(url) {
    url = url || HELP_HOME;
    return url.split(/[?#]/)[0].endsWith(".webm") ? `${PLAYER}?v=${encodeURIComponent(url)}` : url;
}

export class HelpDialog_wat extends Component {
    static template = "whatsapp_employee_tracker.HelpDialog";
    static components = { Dialog };
    static props = { url: { type: String, optional: true }, title: { type: String, optional: true }, close: Function };

    setup() {
        this.state = useState({ loaded: false });
        this.src = helpSrc_wat(this.props.url);
    }

    onLoad() {
        this.state.loaded = true;
    }
}

export function openHelp_wat(dialog, url, title) {
    dialog.add(HelpDialog_wat, { url: url || HELP_HOME, title: title || _t("Help") });
}

// return {'type': 'ir.actions.client', 'tag': 'whatsapp_employee_tracker.help', 'name': ..., 'params': {'url': ...}}
registry.category("actions").add("whatsapp_employee_tracker.help", (env, action) => {
    const params = action.params || {};
    openHelp_wat(env.services.dialog, params.url, action.name || params.title);
});

// <widget name="whatsapp_employee_tracker_help_link" url="/.../guide.html" string="How does it work?"/>
// a plain link in a form: nothing is saved, no required field is checked
export class HelpLink_wat extends Component {
    static template = "whatsapp_employee_tracker.HelpLink";
    static props = { ...standardWidgetProps, url: String, label: String };

    setup() {
        this.dialog = useService("dialog");
    }

    onClick() {
        openHelp_wat(this.dialog, this.props.url, this.props.label);
    }
}

registry.category("view_widgets").add("whatsapp_employee_tracker_help_link", {
    component: HelpLink_wat,
    extractProps: ({ attrs }) => ({ url: attrs.url || HELP_HOME, label: attrs.string || _t("Help") }),
});
