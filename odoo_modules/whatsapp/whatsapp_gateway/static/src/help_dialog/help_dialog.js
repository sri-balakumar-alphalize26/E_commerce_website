/** @odoo-module **/
// Help pop-up: every WhatsApp guide opens over the current screen, in the
// same browser tab. A function client action (not a component action), so
// opening it from a form pop-up (Add email, Send...) keeps that form open.
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

const HELP_HOME = "/whatsapp_gateway/static/src/help/help.html";
const PLAYER = "/whatsapp_gateway/static/src/help/video.html";

/** A .webm opens in the small player page (title, controls, Back). */
export function waHelpSrc(url) {
    url = url || HELP_HOME;
    return url.split(/[?#]/)[0].endsWith(".webm") ? `${PLAYER}?v=${encodeURIComponent(url)}` : url;
}

export class WaHelpDialog extends Component {
    static template = "whatsapp_gateway.HelpDialog";
    static components = { Dialog };
    static props = { url: { type: String, optional: true }, title: { type: String, optional: true }, close: Function };

    setup() {
        this.state = useState({ loaded: false });
        this.src = waHelpSrc(this.props.url);
    }

    onLoad() {
        this.state.loaded = true;
    }
}

export function openWaHelp(dialog, url, title) {
    dialog.add(WaHelpDialog, { url: url || HELP_HOME, title: title || _t("Help") });
}

// return {'type': 'ir.actions.client', 'tag': 'whatsapp_gateway.help', 'name': ..., 'params': {'url': ...}}
registry.category("actions").add("whatsapp_gateway.help", (env, action) => {
    const params = action.params || {};
    openWaHelp(env.services.dialog, params.url, action.name || params.title);
});

// <widget name="wa_help_link" url="/.../guide.html" string="How does it work?"/>
// a plain link in a form: nothing is saved, no required field is checked
export class WaHelpLink extends Component {
    static template = "whatsapp_gateway.HelpLink";
    static props = { ...standardWidgetProps, url: String, label: String };

    setup() {
        this.dialog = useService("dialog");
    }

    onClick() {
        openWaHelp(this.dialog, this.props.url, this.props.label);
    }
}

registry.category("view_widgets").add("wa_help_link", {
    component: WaHelpLink,
    extractProps: ({ attrs }) => ({ url: attrs.url || HELP_HOME, label: attrs.string || _t("Help") }),
});
