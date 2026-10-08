/**
 * A box you type into like a Word page: bullets, numbers, headings, bold,
 * italic, links - with Odoo's own editor and its toolbar that pops up over the
 * words you select. Used for the HTML boxes of the 369 Mart editor (About this
 * item, Description), on the desk and inside Odoo's product form alike: every
 * change is handed up as HTML, and the host writes it where it belongs.
 */
import { Component } from "@odoo/owl";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";

export class RichBox extends Component {
    static template = "mart369_product.RichBox";
    static components = { Wysiwyg };
    static props = {
        value: { optional: true },
        onChange: Function,
        onFocus: { type: Function, optional: true },
        placeholder: { type: String, optional: true },
    };

    setup() {
        // Built once: the editor owns the text from here on, so a value coming
        // back down from the host must not reset the caret.
        this.config = {
            content: String(this.props.value || ""),
            Plugins: MAIN_PLUGINS,
            placeholder: this.props.placeholder || "",
            onChange: () => this.changed(),
            resources: {},
        };
    }

    onLoad(editor) {
        this.editor = editor;
    }

    changed() {
        if (!this.editor) {
            return;
        }
        this.props.onChange(this.editor.getContent());
    }
}
