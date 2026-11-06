/** @odoo-module **/

/**
 * The two Chart.js pieces. Chart.js is lazy-loaded from the `web.chartjs_lib`
 * bundle the way the gauge field does it, and every chart is destroyed when
 * its component leaves, or the canvas leaks a listener per visit.
 */

import { loadBundle } from "@web/core/assets";
import { Component, onWillStart, onWillUnmount, useEffect, useRef } from "@odoo/owl";
import { cssVar } from "./util";

class ChartBase extends Component {
    setup() {
        this.canvas = useRef("canvas");
        this.chart = null;
        onWillStart(() => loadBundle("web.chartjs_lib"));
        // Redrawn on a theme switch as well as on new data: the colours are
        // read from the --sai-* properties at draw time, so a chart drawn
        // at night would keep its night colours on a day page.
        useEffect(
            () => {
                this.draw();
                return () => this.destroy();
            },
            () => [this.props.data, this.props.theme],
        );
        onWillUnmount(() => this.destroy());
    }

    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    draw() {}
}

/** A ring around the star number. */
export class ScoreRing extends ChartBase {
    static template = "sales_automation_insights.ScoreRing";
    static props = { stars: Number, enough: Boolean, data: { optional: true },
                     theme: { type: String, optional: true } };

    draw() {
        const el = this.canvas.el;
        if (!el || !window.Chart) {
            return;
        }
        const accent = cssVar(el, "--sai-accent", "#ff7a1a");
        const line = cssVar(el, "--sai-line", "#262626");
        const pct = this.props.enough ? Math.max(0, Math.min(1, (this.props.stars - 1) / 4)) : 0;
        this.chart = new window.Chart(el, {
            type: "doughnut",
            data: { datasets: [{ data: [pct, 1 - pct],
                                 backgroundColor: [accent, line], borderWidth: 0 }] },
            options: { cutout: "76%", plugins: { legend: { display: false }, tooltip: { enabled: false } },
                       animation: { duration: 400 } },
        });
    }
}

/** The compare view's radar: one polygon per compared row. */
export class Radar extends ChartBase {
    static template = "sales_automation_insights.Radar";
    static props = { data: Object, theme: { type: String, optional: true } };

    draw() {
        const el = this.canvas.el;
        if (!el || !window.Chart) {
            return;
        }
        const palette = [cssVar(el, "--sai-accent", "#ff7a1a"), "#60a5fa", "#22c55e", "#a78bfa"];
        const grid = cssVar(el, "--sai-line", "#262626");
        const text = cssVar(el, "--sai-muted", "#8a8a8a");
        this.chart = new window.Chart(el, {
            type: "radar",
            data: {
                labels: this.props.data.labels,
                datasets: this.props.data.datasets.map((d, i) => ({
                    label: d.name, data: d.data,
                    borderColor: palette[i % palette.length],
                    backgroundColor: palette[i % palette.length] + "33",
                    pointBackgroundColor: palette[i % palette.length],
                })),
            },
            options: {
                scales: { r: { min: 0, max: 1, ticks: { display: false },
                               grid: { color: grid }, angleLines: { color: grid },
                               pointLabels: { color: text, font: { size: 11 } } } },
                plugins: { legend: { labels: { color: text } } },
            },
        });
    }
}
