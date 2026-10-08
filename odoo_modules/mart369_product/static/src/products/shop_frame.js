/**
 * The real shop page, on the right of the 369 Mart editor: exactly what a
 * shopper sees at <shop>/product/<id>. Drawn at a desktop's 1280 px and
 * scaled down to fit the column, or at a phone's 400 px. It shows the saved
 * product, so it reloads after Save (the editor is rebuilt then) or on Refresh.
 */
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

const WIDTH = { desktop: 1280, phone: 400 };

export class ShopFrame extends Component {
    static template = "mart369_product.ShopFrame";
    static props = { url: String };

    setup() {
        this.box = useRef("box");
        this.state = useState({ mode: "desktop", scale: 1, height: 600, n: 0 });
        onMounted(() => {
            this.observer = new ResizeObserver(() => this.measure());
            this.observer.observe(this.box.el);
            this.measure();
        });
        onWillUnmount(() => this.observer?.disconnect());
    }

    get width() {
        return WIDTH[this.state.mode];
    }

    get src() {
        // A fresh address on Refresh, so no cached page is shown.
        const join = this.props.url.includes("?") ? "&" : "?";
        return `${this.props.url}${join}preview=${this.state.n}`;
    }

    measure() {
        const el = this.box.el;
        if (!el) {
            return;
        }
        this.state.scale = Math.min(1, el.clientWidth / this.width);
        this.state.height = el.clientHeight / this.state.scale;
    }

    setMode(mode) {
        this.state.mode = mode;
        this.measure();
    }

    refresh() {
        this.state.n++;
    }
}
