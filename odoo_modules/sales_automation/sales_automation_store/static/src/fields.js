/** @odoo-module **/

// Our own dropdown and calendar on the Store screens (24 Nov 2026), not the
// browser's. The list lies over everything, also over a popup.
import { _t } from "@web/core/l10n/translation";
import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";

function useFloating(self, width) {
    self.root = useRef("root");
    self.button = useRef("button");
    self.box = useRef("box");
    self.float = useState({ open: false, style: "" });
    const away = (ev) => {
        if (self.float.open && self.root.el && !self.root.el.contains(ev.target)) {
            self.close();
        }
    };
    const moved = (ev) => {
        if (self.float.open && !(self.box.el && ev.target instanceof Node && self.box.el.contains(ev.target))) {
            self.close();
        }
    };
    self.place = () => {
        const r = self.button.el.getBoundingClientRect();
        const w = Math.min(Math.max(r.width, width), window.innerWidth - 16);
        const left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8));
        const below = window.innerHeight - r.bottom - 12;
        const up = below < 300 && r.top > below;
        const room = Math.max(140, Math.min(370, (up ? r.top : below) - 8));
        self.float.style = `left:${left}px;width:${w}px;max-height:${room}px;` + (up ? `bottom:${window.innerHeight - r.top + 4}px` : `top:${r.bottom + 4}px`);
    };
    self.close = (focus = false) => {
        self.float.open = false;
        if (focus && self.button.el) {
            self.button.el.focus();
        }
    };
    onMounted(() => {
        document.addEventListener("pointerdown", away, true);
        window.addEventListener("resize", moved);
        document.addEventListener("scroll", moved, true);
    });
    onWillUnmount(() => {
        document.removeEventListener("pointerdown", away, true);
        window.removeEventListener("resize", moved);
        document.removeEventListener("scroll", moved, true);
    });
}

export class SaSelect extends Component {
    static template = "sales_automation_store.SaSelect";
    static props = {
        value: [String, Number, Boolean],
        options: Array,
        onChange: Function,
        label: String,
        placeholder: { type: String, optional: true },
        small: { type: Boolean, optional: true },
    };

    setup() {
        useFloating(this, 200);
        this.state = useState({ word: "", at: 0 });
        this.search = useRef("search");
        onPatched(() => {
            const on = this.box.el && this.box.el.querySelector(".at");
            if (on) {
                on.scrollIntoView({ block: "nearest" });
            }
        });
    }
    get current() {
        return this.props.options.find((o) => `${o.value}` === `${this.props.value}`);
    }
    get words() {
        return this.current ? this.current.label : this.props.placeholder || "";
    }
    get options() {
        const word = this.state.word.trim().toLowerCase();
        return word ? this.props.options.filter((o) => o.label.toLowerCase().includes(word)) : this.props.options;
    }
    get searches() {
        return this.props.options.length >= 8;
    }
    isOn(option) {
        return `${option.value}` === `${this.props.value}`;
    }
    toggle() {
        if (this.float.open) {
            this.close();
            return;
        }
        this.state.word = "";
        this.state.at = Math.max(0, this.props.options.findIndex((o) => this.isOn(o)));
        this.place();
        this.float.open = true;
        if (this.searches) {
            setTimeout(() => this.search.el && this.search.el.focus());
        }
    }
    pick(option) {
        if (option.disabled) {
            return;
        }
        this.close(true);
        if (!this.isOn(option)) {
            this.props.onChange(option.value);
        }
    }
    onWord(ev) {
        this.state.word = ev.target.value;
        this.state.at = 0;
    }
    onKey(ev) {
        if (!this.float.open) {
            if (["ArrowDown", "ArrowUp"].includes(ev.key)) {
                ev.preventDefault();
                this.toggle();
            }
            return;
        }
        const n = this.options.length;
        if (ev.key === "Escape") {
            ev.stopPropagation();
            this.close(true);
        } else if (ev.key === "Tab") {
            this.close();
        } else if (["ArrowDown", "ArrowUp"].includes(ev.key) && n) {
            ev.preventDefault();
            this.state.at = (this.state.at + (ev.key === "ArrowDown" ? 1 : n - 1)) % n;
        } else if (ev.key === "Enter" && n) {
            ev.preventDefault();
            ev.stopPropagation();
            this.pick(this.options[this.state.at] || this.options[0]);
        }
    }
}

const pad = (n) => `${n}`.padStart(2, "0");
export function isoDay(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function fromIso(iso) {
    const [y, m, d] = (iso || "").split("-").map((x) => parseInt(x, 10));
    return y && m && d ? new Date(y, m - 1, d) : null;
}

export class SaDate extends Component {
    static template = "sales_automation_store.SaDate";
    static props = { value: String, onChange: Function, label: String, min: { type: String, optional: true } };

    setup() {
        useFloating(this, 290);
        this.state = useState({ year: 0, month: 0, at: "" });
        onPatched(() => {
            const on = this.box.el && this.box.el.querySelector(".at");
            if (on && this.box.el.contains(document.activeElement)) {
                on.focus();
            }
        });
    }
    get words() {
        const d = fromIso(this.props.value);
        if (!d) {
            return _t("Choose a day");
        }
        const text = d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" });
        return this.props.value === isoDay(new Date()) ? _t("Today") + ", " + text : text;
    }
    get title() {
        return new Date(this.state.year, this.state.month, 1).toLocaleDateString([], { month: "long", year: "numeric" });
    }
    get weekdays() {
        return [0, 1, 2, 3, 4, 5, 6].map((n) => new Date(2024, 0, 1 + n).toLocaleDateString([], { weekday: "short" }));
    }
    get days() {
        const lead = (new Date(this.state.year, this.state.month, 1).getDay() + 6) % 7;
        const count = new Date(this.state.year, this.state.month + 1, 0).getDate();
        const today = isoDay(new Date());
        const out = [];
        for (let i = 0; i < lead; i++) {
            out.push({ key: "e" + i, empty: true });
        }
        for (let n = 1; n <= count; n++) {
            const iso = `${this.state.year}-${pad(this.state.month + 1)}-${pad(n)}`;
            out.push({ key: iso, iso, n, past: !!this.props.min && iso < this.props.min, on: iso === this.props.value, today: iso === today, at: iso === this.state.at });
        }
        return out;
    }
    get canBack() {
        return !this.props.min || `${this.state.year}-${pad(this.state.month + 1)}` > this.props.min.slice(0, 7);
    }
    show(d) {
        this.state.year = d.getFullYear();
        this.state.month = d.getMonth();
        this.state.at = isoDay(d);
    }
    toggle() {
        if (this.float.open) {
            this.close();
            return;
        }
        this.show(fromIso(this.props.value) || new Date());
        this.place();
        this.float.open = true;
        setTimeout(() => {
            const on = this.box.el && this.box.el.querySelector(".at");
            if (on) {
                on.focus();
            }
        });
    }
    month(step) {
        if (step < 0 && !this.canBack) {
            return;
        }
        const d = new Date(this.state.year, this.state.month + step, 1);
        this.state.year = d.getFullYear();
        this.state.month = d.getMonth();
    }
    pick(day) {
        if (day.past) {
            return;
        }
        this.close(true);
        this.props.onChange(day.iso);
    }
    pickToday() {
        this.pick({ iso: isoDay(new Date()) });
    }
    onKey(ev) {
        if (!this.float.open) {
            return;
        }
        if (ev.key === "Escape") {
            ev.stopPropagation();
            this.close(true);
            return;
        }
        const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[ev.key];
        if (step && this.state.at) {
            ev.preventDefault();
            const d = fromIso(this.state.at);
            d.setDate(d.getDate() + step);
            if (!this.props.min || isoDay(d) >= this.props.min) {
                this.show(d);
            }
        }
    }
}
