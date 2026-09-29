/** A category's logo: the built-in picker, the upload, and the cropper.
 *
 * The twin of the console's LogoField (components/admin/LogoField.jsx) - same
 * two panes, same sizes, same three values written: mart_icon, mart_art and
 * mart_logo.
 *
 * Two sizes, because the app draws the two levels differently: a main
 * category's logo is the 18px mark on its pill in the top bar, a
 * sub-category's fills its whole tile (104px on the home page, 88 on the
 * category page). An upload always goes through the cropper, which shows it
 * at those sizes and saves a square of a fixed size - 128 or 512 px - so what
 * is picked here is what the app shows.
 *
 * No crop library: the whole job is one drawImage onto a canvas.
 *
 * Here in the base module rather than in the catalogue, like the rest of the
 * kit, because the drawings it offers (static/img/art) live here too.
 */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { _t } from "@web/core/l10n/translation";
import { Icon } from "./icon";

/* Kept in step with ICON_CHOICES and ART_CHOICES in models/serializers.py -
   the server refuses anything else - and with LOGO_ICONS / LOGO_ART in the
   console's LogoField.jsx. */
export const LOGO_ICONS = [
    ["keyboard", _t("Keyboard")], ["plug", _t("Plug")], ["wifi", _t("Wi-Fi")], ["cpu", _t("Chip")],
    ["laptop", _t("Laptop")], ["monitor", _t("Monitor")], ["ticket", _t("Ticket")], ["grid", _t("Grid")],
    ["bolt", _t("Lightning")], ["bag", _t("Bag")], ["basket", _t("Basket")], ["leaf", _t("Leaf")],
    ["pot", _t("Pot")], ["pen", _t("Pen")], ["shirt", _t("Shirt")], ["book", _t("Book")],
];
export const LOGO_ART = [
    ["Keyboard", _t("Keyboard")], ["Mouse", _t("Mouse")], ["Headphones", _t("Headphones")], ["Webcam", _t("Webcam")],
    ["Monitor", _t("Monitor")], ["Laptop", _t("Laptop")], ["Cabinet", _t("PC case")], ["Cpu", _t("Processor")],
    ["Gpu", _t("Graphics card")], ["Motherboard", _t("Motherboard")], ["Ram", _t("Memory")], ["Ssd", _t("Storage")],
    ["Psu", _t("Power supply")], ["Cooler", _t("Cooler")], ["Router", _t("Router")], ["Adapter", _t("Adapter")],
    ["Cable", _t("Cable")], ["Charger", _t("Charger")], ["Speaker", _t("Speaker")], ["Lamp", _t("Lamp")],
    ["Box", _t("Box")], ["Pack", _t("Pack")], ["Bottle", _t("Bottle")], ["Jar", _t("Jar")],
    ["Bar", _t("Chocolate")], ["Basket", _t("Basket")], ["Apple", _t("Apple")], ["Banana", _t("Banana")],
    ["Orange", _t("Orange")], ["Grapes", _t("Grapes")], ["Pomegranate", _t("Pomegranate")], ["Tomato", _t("Tomato")],
    ["Onion", _t("Onion")], ["Leafy", _t("Leafy greens")], ["Soap", _t("Soap bottle")], ["SoapBar", _t("Soap bar")],
    ["Towels", _t("Towels")], ["Plates", _t("Plates")], ["Flask", _t("Flask")], ["Board", _t("Chopping board")],
];

export const LOGO_SIZES = {
    main: {
        out: 128, min: 128,
        title: _t("Small: 18 × 18 px"),
        hint: _t("Shown at 18 × 18 px beside the name on the top bar. Use a simple, bold mark - a PNG with a transparent background reads best. Saved as 128 × 128."),
    },
    sub: {
        out: 512, min: 512,
        title: _t("Full tile: 104 × 104 px"),
        hint: _t("Fills the whole tile - 104 × 104 px on the home page, 88 × 88 on the category page. Use a picture at least 512 × 512. Saved as 512 × 512."),
    },
};

/** Where a built-in drawing is, as a file (made by scripts/export-art.mjs). */
export function artUrl(name) {
    return `/mart369/static/img/art/${name || "Box"}.svg`;
}

const VIEW = 280; // the crop square, in CSS px - the maths is in these
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/**
 * The cropper, as a dialog. `onDone` gets a data: URL of the square PNG.
 */
export class LogoCropDialog extends Component {
    static template = "mart369.LogoCropDialog";
    static components = { Dialog, Icon };
    static props = {
        close: { type: Function },
        src: { type: String },
        level: { type: String },
        name: { type: String, optional: true },
        tone: { type: String, optional: true },
        accent: { type: String, optional: true },
        onDone: { type: Function },
    };

    setup() {
        this.size = LOGO_SIZES[this.props.level];
        this.stage = useRef("stage");
        this.state = useState({ ready: false, scale: 1, x: 0, y: 0, error: "" });
        this.img = null;
        this.drag = null;
        onWillStart(() => this.load());
    }

    load() {
        return new Promise((resolve) => {
            const i = new Image();
            i.onload = () => {
                const w = i.naturalWidth || 512;
                const h = i.naturalHeight || 512;
                this.img = { el: i, w, h, fit: Math.min(VIEW / w, VIEW / h), fill: Math.max(VIEW / w, VIEW / h) };
                // A small mark starts whole; a tile starts filled, edge to edge.
                this.frame(this.props.level === "main" ? "fit" : "fill");
                this.state.ready = true;
                resolve();
            };
            i.onerror = () => {
                this.state.error = _t("That picture could not be opened.");
                resolve();
            };
            i.src = this.props.src;
        });
    }

    /** Put the picture at `scale`, top-left at (x, y). A picture bigger than
     *  the square cannot leave a gap; a smaller one stays inside it. */
    place(scale, x, y) {
        const w = this.img.w * scale;
        const h = this.img.h * scale;
        this.state.scale = scale;
        this.state.x = clamp(x, Math.min(0, VIEW - w), Math.max(0, VIEW - w));
        this.state.y = clamp(y, Math.min(0, VIEW - h), Math.max(0, VIEW - h));
    }

    /** "fit": the whole picture shows. "fill": it covers the square. */
    frame(how) {
        if (!this.img) {
            return;
        }
        const s = this.img[how];
        this.place(s, (VIEW - this.img.w * s) / 2, (VIEW - this.img.h * s) / 2);
    }

    get minScale() {
        return this.img ? this.img.fit : 1;
    }

    get maxScale() {
        return this.img ? this.img.fill * 4 : 1;
    }

    /** Zoom about the middle of the square, so what is being looked at stays put. */
    zoomTo(s) {
        if (!this.img) {
            return;
        }
        const next = clamp(s, this.minScale, this.maxScale);
        const { scale, x, y } = this.state;
        const cx = (VIEW / 2 - x) / scale;
        const cy = (VIEW / 2 - y) / scale;
        this.place(next, VIEW / 2 - cx * next, VIEW / 2 - cy * next);
    }

    get zoomPct() {
        const span = this.maxScale - this.minScale || 1;
        return Math.round(((this.state.scale - this.minScale) / span) * 100);
    }

    onZoom(ev) {
        const span = this.maxScale - this.minScale;
        this.zoomTo(this.minScale + (Number(ev.target.value) / 100) * span);
    }

    onPointerDown(ev) {
        if (!this.img) {
            return;
        }
        ev.currentTarget.setPointerCapture(ev.pointerId);
        const r = this.stage.el.getBoundingClientRect();
        this.drag = { px: ev.clientX, py: ev.clientY, x: this.state.x, y: this.state.y, k: VIEW / r.width };
    }

    onPointerMove(ev) {
        const d = this.drag;
        if (d) {
            this.place(this.state.scale, d.x + (ev.clientX - d.px) * d.k, d.y + (ev.clientY - d.py) * d.k);
        }
    }

    onPointerUp() {
        this.drag = null;
    }

    onWheel(ev) {
        ev.preventDefault();
        this.zoomTo(this.state.scale * (ev.deltaY < 0 ? 1.08 : 1 / 1.08));
    }

    onKeyDown(ev) {
        if (!this.img) {
            return;
        }
        const step = ev.shiftKey ? 20 : 4;
        const by = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[ev.key];
        if (by) {
            ev.preventDefault();
            this.place(this.state.scale, this.state.x + by[0], this.state.y + by[1]);
        } else if (ev.key === "+" || ev.key === "=") {
            this.zoomTo(this.state.scale * 1.1);
        } else if (ev.key === "-") {
            this.zoomTo(this.state.scale / 1.1);
        }
    }

    /** The same framing, drawn `px` wide - for the stage and the previews. */
    shot(px) {
        const k = px / VIEW;
        const { scale, x, y } = this.state;
        return `left:${x * k}px;top:${y * k}px;width:${this.img.w * scale * k}px;height:${this.img.h * scale * k}px;`;
    }

    get small() {
        return this.img && Math.min(this.img.w, this.img.h) < this.size.min;
    }

    get sourceLine() {
        if (!this.img) {
            return "";
        }
        const { w, h } = this.img;
        const min = this.size.min;
        return this.small
            ? _t("This picture is %(w)s × %(h)s. It will look soft - %(min)s × %(min)s or bigger is best.", { w, h, min })
            : _t("This picture is %(w)s × %(h)s - big enough.", { w, h });
    }

    save() {
        const n = this.size.out;
        const k = n / VIEW;
        const canvas = document.createElement("canvas");
        canvas.width = n;
        canvas.height = n;
        const ctx = canvas.getContext("2d");
        ctx.imageSmoothingQuality = "high";
        const { scale, x, y } = this.state;
        ctx.drawImage(this.img.el, x * k, y * k, this.img.w * scale * k, this.img.h * scale * k);
        let url;
        try {
            url = canvas.toDataURL("image/png");
        } catch {
            this.state.error = _t("That picture could not be cropped here. Save it as a PNG or JPEG and try again.");
            return;
        }
        this.props.onDone(url);
        this.props.close();
    }
}

/**
 * The field: Built-in | Upload your own.
 *
 * `value` is { icon, art, image } - image the picture's address, a fresh
 * data: URL from the cropper, or "" for none. `onChange` gets the fields to
 * send: { mart_icon } / { mart_art } / { mart_logo: dataUrl | false }.
 */
export class LogoField extends Component {
    static template = "mart369.LogoField";
    static components = { Icon };
    static props = {
        level: { type: String },
        value: { type: Object },
        name: { type: String, optional: true },
        tone: { type: String, optional: true },
        accent: { type: String, optional: true },
        onChange: { type: Function },
    };

    setup() {
        this.dialog = useService("dialog");
        this.input = useRef("file");
        this.state = useState({ pane: this.props.value.image ? "upload" : "builtin", error: "" });
        this.artUrl = artUrl;
    }

    get size() {
        return LOGO_SIZES[this.props.level];
    }

    get choices() {
        return this.props.level === "main" ? LOGO_ICONS : LOGO_ART;
    }

    get current() {
        return this.props.level === "main" ? this.props.value.icon : this.props.value.art;
    }

    isOn(key) {
        return !this.props.value.image && this.current === key;
    }

    pick(key) {
        const field = this.props.level === "main" ? "mart_icon" : "mart_art";
        // Picking a built-in one is picking what shows, so an upload goes.
        this.props.onChange(this.props.value.image ? { [field]: key, mart_logo: false } : { [field]: key });
    }

    choose() {
        this.input.el?.click();
    }

    remove() {
        this.props.onChange({ mart_logo: false });
    }

    async onFile(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        this.state.error = "";
        if (!file) {
            return;
        }
        if (!/^image\/(png|jpe?g|webp|gif|svg\+xml)$/.test(file.type)) {
            this.state.error = _t("Choose a PNG, JPEG, WebP, GIF or SVG picture.");
            return;
        }
        if (file.size > 15 * 1024 * 1024) {
            this.state.error = _t("That file is over 15 MB. Choose a smaller one.");
            return;
        }
        const src = await getDataURLFromFile(file);
        this.dialog.add(LogoCropDialog, {
            src,
            level: this.props.level,
            name: this.props.name || "",
            tone: this.props.tone || "",
            accent: this.props.accent || "",
            onDone: (url) => {
                this.state.pane = "upload";
                this.props.onChange({ mart_logo: url });
            },
        });
    }
}
