/**
 * A box you type into like a Word page: bullets, numbers, headings, bold,
 * italic, links - with Odoo's own editor and its toolbar that pops up over the
 * words you select. Used for the HTML boxes of the 369 Mart editor (About this
 * item, Description), on the desk and inside Odoo's product form alike: every
 * change is handed up as HTML, and the host writes it where it belongs.
 *
 * Clean paste: plain text of two or more lines (copied from Amazon, a maker's
 * site, a PDF) arrives as a bulleted list, each line's lead before " - " in
 * bold. A paste that carries its own formatting (from Word) is Odoo's to handle.
 *
 * With `points` (About this item) it also counts the points as you type and
 * says which ones are too long for the page.
 */
import { Component, markup, useState } from "@odoo/owl";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { parseHTML } from "@html_editor/utils/html";

// What the product page shows before "Show more", and a point that no longer
// fits in about two lines there.
const SHOWN = 5;
const LONG = 250;

const BULLET = /^\s*(?:[•●⚫▪◦·*\-–—]|\d{1,2}[.)])\s*/;
const LEADS = [" — ", " – ", " - ", ": "];

function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** One pasted line as a list item: the bullet mark off, a short lead in bold. */
function pointHtml(line) {
    const text = line.replace(BULLET, "").trim();
    for (const mark of LEADS) {
        const at = text.indexOf(mark);
        if (at > 0 && at <= 60 && text.slice(at + mark.length).trim()) {
            const lead = text.slice(0, at).trim();
            const rest = text.slice(at + mark.length).trim();
            return `<li><b>${escapeHtml(lead)}</b> — ${escapeHtml(rest)}</li>`;
        }
    }
    return `<li>${escapeHtml(text)}</li>`;
}

export class RichBox extends Component {
    static template = "mart369_product.RichBox";
    static components = { Wysiwyg };
    static props = {
        value: { optional: true },
        onChange: Function,
        onFocus: { type: Function, optional: true },
        placeholder: { type: String, optional: true },
        // About this item: count the points, flag long ones.
        points: { type: Boolean, optional: true },
    };

    setup() {
        this.state = useState({ count: 0, long: [] });
        // Built once: the editor owns the text from here on, so a value coming
        // back down from the host must not reset the caret.
        this.config = {
            // Markup, not a string: Odoo's editor shows a plain string as
            // characters, which put the saved formatting on screen as code.
            content: markup(String(this.props.value || "")),
            Plugins: MAIN_PLUGINS,
            placeholder: this.props.placeholder || "",
            onChange: () => this.changed(),
            resources: {},
        };
        if (this.props.points) {
            this.count(String(this.props.value || ""));
        }
    }

    onLoad(editor) {
        this.editor = editor;
    }

    changed() {
        if (!this.editor) {
            return;
        }
        const html = this.editor.getContent();
        if (this.props.points) {
            this.count(html);
        }
        this.props.onChange(html);
    }

    /** Points are list items, else paragraphs with words in them. */
    count(html) {
        const box = document.createElement("div");
        box.innerHTML = html;
        let items = [...box.querySelectorAll("li")];
        if (!items.length) {
            items = [...box.querySelectorAll("p, div")].filter((el) => !el.querySelector("p, div"));
        }
        const texts = items.map((el) => el.textContent.trim()).filter(Boolean);
        this.state.count = texts.length;
        this.state.long = texts.map((t, i) => (t.length > LONG ? i + 1 : 0)).filter(Boolean);
    }

    get countText() {
        const n = this.state.count;
        if (!n) {
            return "";
        }
        if (n <= SHOWN) {
            return `${n} point${n === 1 ? "" : "s"} · shoppers see them all`;
        }
        return `${n} points · shoppers see the first ${SHOWN}, then Show more`;
    }

    get longText() {
        const long = this.state.long;
        if (!long.length) {
            return "";
        }
        const which = long.length === 1 ? `Point ${long[0]} is` : `Points ${long.join(", ")} are`;
        return `${which} long - keep each under about 2 lines on the page.`;
    }

    /** Lines of plain text become a bulleted list; anything else is Odoo's. */
    onPaste(ev) {
        const data = ev.clipboardData;
        if (!data || !this.editor) {
            return;
        }
        const html = data.getData("text/html");
        const text = data.getData("text/plain") || "";
        const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
        // A paste from Word or a web page keeps its own formatting; plain text
        // of one line is just typed in.
        if ((html && /<(ul|ol|li|table|h[1-6])\b/i.test(html)) || lines.length < 2) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const list = `<ul>${lines.map(pointHtml).join("")}</ul>`;
        this.editor.shared.dom.insert(parseHTML(document, list));
        this.editor.shared.history.addStep();
    }
}
