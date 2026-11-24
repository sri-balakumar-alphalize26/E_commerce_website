/** @odoo-module **/

// A message's text in pieces, as WhatsApp shows it: *bold*, _italic_, ~struck~,
// ```code``` and links. Pieces, never HTML: what a customer wrote stays text.
const LINK = /https?:\/\/[^\s<>"]+/;
const MARKS = { "*": "bold", "_": "italic", "~": "strike" };
const MARK = /(^|[\s.,!?:;()\[\]{}"'*_~-])([*_~])(?=\S)([^\n]*?\S)\2(?=$|[\s.,!?:;()\[\]{}"'*_~-])/;

function plain(text, style, out) {
    if (text) {
        out.push({ text, ...style });
    }
}
function marks(text, style, out) {
    const m = MARK.exec(text);
    if (!m || style[MARKS[m[2]]]) {
        return plain(text, style, out);
    }
    plain(text.slice(0, m.index) + m[1], style, out);
    marks(m[3], { ...style, [MARKS[m[2]]]: true }, out);
    marks(text.slice(m.index + m[0].length), style, out);
}
function links(text, out) {
    const m = LINK.exec(text);
    if (!m) {
        return marks(text, {}, out);
    }
    const href = m[0].replace(/[.,!?:;)\]*~]+$/, "");
    marks(text.slice(0, m.index), {}, out);
    out.push({ text: href, href });
    links(text.slice(m.index + href.length), out);
}
export function waText(text) {
    const out = [];
    for (const [i, part] of String(text || "").split("```").entries()) {
        if (i % 2) {
            plain(part, { code: true }, out);
        } else {
            links(part, out);
        }
    }
    return out;
}
