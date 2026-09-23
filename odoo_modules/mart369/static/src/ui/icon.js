/** Our icon set.
 *
 * The same strokes the app draws (components/home/shared.jsx) and the same set
 * the console draws (components/admin/AdminUI.jsx), so a screen means the same
 * thing by the same glyph wherever it is opened.
 *
 * It lives here, in the base module, because every screen needs it. It used to
 * live in mart369_home, which meant only the two builders could reach it and
 * the thirteen desks fell back to Font Awesome - Odoo's set, not ours.
 */
import { Component, onMounted, onPatched, useRef } from "@odoo/owl";

// Same strokes the app draws (components/home/shared.jsx).
const ICONS = {
    bag: '<path d="M5 8h14l-1 12H6z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
    basket: '<path d="M4 10h16l-1.6 9a2 2 0 0 1-2 1.6H7.6a2 2 0 0 1-2-1.6z"/><path d="m9 10 3-6 3 6"/>',
    leaf: '<path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15"/><path d="M5 19l8-8"/>',
    plug: '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0z"/><path d="M12 17v4"/>',
    pot: '<path d="M4 10h16v6a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"/><path d="M2 10h2M20 10h2M9 6c0-1 1-2 3-2s3 1 3 2"/>',
    pen: '<path d="m4 20 1-4L16 5l3 3L8 19z"/><path d="m14 7 3 3"/>',
    ticket: '<path d="M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-2a2 2 0 0 0 0-4z"/><path d="M10 6v12" stroke-dasharray="2 2"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    chev: '<path d="m6 9 6 6 6-6"/>',
    right: '<path d="m9 6 6 6-6 6"/>',
    cart: '<path d="M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 8H6"/><circle cx="10" cy="20" r="1.3"/><circle cx="17" cy="20" r="1.3"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    heart: '<path d="M12 20s-7.5-4.6-9.2-9.3C1.6 7.2 4 4 7.2 4c2 0 3.6 1.2 4.8 2.8C13.2 5.2 14.8 4 16.8 4 20 4 22.4 7.2 21.2 10.7 19.5 15.4 12 20 12 20z"/>',
    truck: '<path d="M3 6h11v10H3zM14 9h4l3 3.5V16h-7"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17.5" cy="17.5" r="1.8"/>',
    shirt: '<path d="m8 4-5 3 2 4 3-1v10h8V10l3 1 2-4-5-3a4 4 0 0 1-8 0z"/>',
    book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h7"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    scooter: '<path d="M4 16a3 3 0 1 0 6 0 3 3 0 0 0-6 0zM14 16a3 3 0 1 0 6 0 3 3 0 0 0-6 0z"/><path d="M7 16h7l3-8h3"/>',
    // Used by the editor's own chrome rather than by the shop.
    left: '<path d="m15 6-6 6 6 6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    trash: '<path d="M4 7h16M10 7V5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2"/><path d="M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    // The same eye with the lid drawn over it, so hidden reads as hidden.
    'eye-off': '<path d="M3 3l18 18"/><path d="M10.6 5.2A9.8 9.8 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3.3 4"/><path d="M6.2 6.4A17 17 0 0 0 2 12s4 7 10 7a9.6 9.6 0 0 0 4.3-1"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
    check: '<path d="m5 12 4.5 4.5L19 7"/>',
    info: '<circle cx="12" cy="12" r="8"/><path d="M12 11v5M12 8h.01"/>',
    // The console's own chrome (components/admin/AdminUI.jsx EXTRA), which the
    // shop itself never draws but every desk does.
    dash: '<rect x="3.5" y="3.5" width="7" height="9" rx="2"/><rect x="13.5" y="3.5" width="7" height="5" rx="2"/><rect x="3.5" y="15.5" width="7" height="5" rx="2"/><rect x="13.5" y="11.5" width="7" height="9" rx="2"/>',
    users: '<circle cx="9" cy="8" r="3.4"/><path d="M3 20a6 6 0 0 1 12 0"/><path d="M16 5.2a3.4 3.4 0 0 1 0 6.6M17 14.4A6 6 0 0 1 21 20"/>',
    gear: '<circle cx="12" cy="12" r="3.2"/><path d="M12 3.5v2.2M12 18.3v2.2M4.9 7.8l1.9 1.1M17.2 15.1l1.9 1.1M4.9 16.2l1.9-1.1M17.2 8.9l1.9-1.1"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    download: '<path d="M12 4v11M8 11.5l4 4 4-4"/><path d="M5 20h14"/>',
    dots: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
    up: '<path d="M12 19V6M6.5 11.5 12 6l5.5 5.5"/>',
    down: '<path d="M12 5v13M6.5 12.5 12 18l5.5-5.5"/>',
    store: '<path d="M4 9.5 5.6 5h12.8L20 9.5"/><path d="M4 9.5a2.4 2.4 0 0 0 4 1.6 2.4 2.4 0 0 0 4 0 2.4 2.4 0 0 0 4 0 2.4 2.4 0 0 0 4-1.6"/><path d="M5.5 11.6V20h13v-8.4"/><path d="M10 20v-5h4v5"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    live: '<circle cx="12" cy="12" r="3"/><path d="M7.5 7.5a6.4 6.4 0 0 0 0 9M16.5 16.5a6.4 6.4 0 0 0 0-9M4.5 4.5a10.6 10.6 0 0 0 0 15M19.5 19.5a10.6 10.6 0 0 0 0-15"/>',
    // The glyphs the desks' Font Awesome fallbacks used to carry.
    money: '<rect x="2.5" y="6.5" width="19" height="11" rx="2.5"/><circle cx="12" cy="12" r="2.6"/><path d="M6 10v4M18 10v4"/>',
    box: '<path d="m12 3 8.5 4.5v9L12 21l-8.5-4.5v-9z"/><path d="m3.5 7.5 8.5 4.5 8.5-4.5M12 12v9"/>',
    archive: '<rect x="3" y="4" width="18" height="4.5" rx="1.5"/><path d="M4.8 8.5V19a1.5 1.5 0 0 0 1.5 1.5h11.4a1.5 1.5 0 0 0 1.5-1.5V8.5"/><path d="M10 12.5h4"/>',
    star: '<path d="m12 3.5 2.7 5.6 6.1.8-4.5 4.3 1.1 6.1L12 17.4l-5.4 2.9 1.1-6.1-4.5-4.3 6.1-.8z"/>',
    wallet: '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18"/><circle cx="16.5" cy="14.5" r="1.4"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    // Drawn for the desks, which until now fell back to Font Awesome. Same
    // 24x24 box, same 1.8 stroke, so they sit beside the shop's own glyphs.
    warn: '<path d="M12 4.5 2.8 20h18.4z"/><path d="M12 10v4M12 17h.01"/>',
    ban: '<circle cx="12" cy="12" r="8.5"/><path d="m6 6 12 12"/>',
    pause: '<path d="M9.5 5v14M14.5 5v14"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.5-5.8"/><path d="M20 4v5h-5"/>',
    gift: '<rect x="3" y="9" width="18" height="11" rx="2"/><path d="M3 13h18M12 9v11"/><path d="M12 9S9.5 4 7.5 5.2 9 9 12 9zM12 9s2.5-5 4.5-3.8S15 9 12 9z"/>',
    camera: '<path d="M4 8h3l1.5-2h7L17 8h3a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 20 19H4a1.5 1.5 0 0 1-1.5-1.5v-8A1.5 1.5 0 0 1 4 8z"/><circle cx="12" cy="13" r="3.4"/>',
    pin: '<path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.6"/>',
    lock: '<rect x="4.5" y="10.5" width="15" height="9.5" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    chat: '<path d="M20.5 12.5c0 3.6-3.8 6.5-8.5 6.5a10 10 0 0 1-2.6-.33L4.5 20.5l1.2-3.3A6.6 6.6 0 0 1 3.5 12.5C3.5 8.9 7.3 6 12 6s8.5 2.9 8.5 6.5z"/>',
    send: '<path d="m21 3-9.5 9.5"/><path d="M21 3 14.5 21l-3-7.5-7.5-3z"/>',
    mail: '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="m3.5 7 8.5 6 8.5-6"/>',
    phone: '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
    chart: '<path d="M4 19h16"/><path d="m5 15 4.5-5 3.5 3L19 6"/>',
    megaphone: '<path d="M4 10v4a1.5 1.5 0 0 0 1.5 1.5H8l7 4V4.5l-7 4H5.5A1.5 1.5 0 0 0 4 10z"/><path d="M18 9.5a3.5 3.5 0 0 1 0 5"/>',
    moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z"/>',
    meh: '<circle cx="12" cy="12" r="8.5"/><path d="M9 15h6"/><path d="M9.5 9.5h.01M14.5 9.5h.01"/>',
    frown: '<circle cx="12" cy="12" r="8.5"/><path d="M9 15.5a4 4 0 0 1 6 0"/><path d="M9.5 9.5h.01M14.5 9.5h.01"/>',
    tap: '<path d="M9 11V6a1.8 1.8 0 0 1 3.6 0v5"/><path d="M12.6 11V9.2a1.7 1.7 0 0 1 3.4 0V11"/><path d="M16 11v-.5a1.7 1.7 0 0 1 3.4 0V15a6 6 0 0 1-6 6h-1.6a5 5 0 0 1-3.6-1.5L5 16"/>',
    target: '<circle cx="12" cy="12" r="7.5"/><circle cx="12" cy="12" r="2.6"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
};

export class Icon extends Component {
    static template = "mart369.Icon";
    static props = { n: String, size: { type: Number, optional: true }, class: { type: String, optional: true } };
    static defaultProps = { size: 20, class: "" };

    setup() {
        this.svg = useRef("svg");
        // The paths are drawn by hand rather than by `t-out`.
        //
        // `t-out` builds its markup as HTML, so every <path> came out in the
        // XHTML namespace - and an <svg> full of XHTML elements draws nothing
        // at all. The box was the right size, the stroke was the right colour,
        // and the icon was simply not there. Assigning innerHTML on the <svg>
        // node makes the browser parse the fragment in the SVG namespace,
        // which is the whole difference between an icon and an empty gap.
        const draw = () => {
            if (this.svg.el) {
                this.svg.el.innerHTML = ICONS[this.props.n] || ICONS.grid;
            }
        };
        onMounted(draw);
        onPatched(draw);
    }
}
