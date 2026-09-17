/**
 * 369 Mart customers and addresses.
 *
 * One screen for whoever runs the shop: every customer who signed up in the
 * app, with their delivery addresses folded underneath. What an employee needs
 * to see first is what is *missing* - no mobile, no pincode, no map location -
 * so those are red dots on the row rather than something you find by opening
 * each record.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const FILTERS = [
    { key: "all", label: _t("All") },
    { key: "no_mobile", label: _t("Missing mobile") },
    { key: "no_pin", label: _t("Missing pincode") },
    { key: "no_address", label: _t("No address") },
];

/** "3 days ago" - close enough for a staff screen, and no library needed. */
function ago(value) {
    if (!value) {
        return "";
    }
    const then = new Date(value.replace(" ", "T") + "Z");
    const days = Math.floor((Date.now() - then.getTime()) / 86400000);
    if (Number.isNaN(days)) {
        return "";
    }
    if (days <= 0) {
        return _t("today");
    }
    if (days === 1) {
        return _t("yesterday");
    }
    if (days < 30) {
        return _t("%s days ago", days);
    }
    const months = Math.floor(days / 30);
    return months === 1 ? _t("a month ago") : _t("%s months ago", months);
}

function initials(name) {
    return (name || "?")
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((w) => w[0].toUpperCase())
        .join("");
}

export class Mart369Console extends Component {
    static template = "mart369_address.Console";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            customers: [],
            open: {},          // customer id -> addresses shown
            search: "",
            filter: "all",
            loading: true,
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        const users = await this.orm.searchRead(
            "res.users",
            [["share", "=", true]],
            ["name", "login", "email", "phone", "partner_id", "active", "create_date", "login_date"],
            { order: "create_date desc", limit: 500 }
        );
        const partnerIds = users.map((u) => u.partner_id && u.partner_id[0]).filter(Boolean);
        const addresses = partnerIds.length
            ? await this.orm.searchRead(
                  "res.partner",
                  [["parent_id", "in", partnerIds], ["type", "=", "delivery"]],
                  [
                      "parent_id", "name", "phone", "mart369_alt_phone", "mart369_label",
                      "mart369_default", "street", "street2", "city", "zip", "state_id",
                      "partner_latitude", "partner_longitude",
                  ],
                  { order: "mart369_default desc, id asc" }
              )
            : [];

        const byParent = {};
        for (const a of addresses) {
            const pid = a.parent_id[0];
            (byParent[pid] = byParent[pid] || []).push({
                ...a,
                gaps: this.gapsFor(a),
                cityLine: [a.city, a.zip].filter(Boolean).join(" "),
            });
        }

        this.state.customers = users.map((u) => {
            const list = byParent[u.partner_id && u.partner_id[0]] || [];
            return {
                ...u,
                initials: initials(u.name),
                joined: ago(u.create_date),
                seen: u.login_date ? ago(u.login_date) : _t("never"),
                addresses: list,
                count: list.length,
                default: list.find((a) => a.mart369_default) || null,
            };
        });
        this.state.loading = false;
    }

    gapsFor(address) {
        const gaps = [];
        if (!address.phone) {
            gaps.push(_t("no mobile"));
        }
        if (!address.zip) {
            gaps.push(_t("no pincode"));
        }
        if (!address.street) {
            gaps.push(_t("no street"));
        }
        if (!address.partner_latitude && !address.partner_longitude) {
            gaps.push(_t("no map location"));
        }
        return gaps;
    }

    get rows() {
        const term = this.state.search.trim().toLowerCase();
        return this.state.customers.filter((c) => {
            if (term) {
                const hay = [c.name, c.login, c.phone, ...c.addresses.map((a) => a.city)]
                    .filter(Boolean)
                    .join(" ")
                    .toLowerCase();
                if (!hay.includes(term)) {
                    return false;
                }
            }
            switch (this.state.filter) {
                case "no_mobile":
                    return !c.phone || c.addresses.some((a) => !a.phone);
                case "no_pin":
                    return c.addresses.some((a) => !a.zip);
                case "no_address":
                    return c.count === 0;
                default:
                    return true;
            }
        });
    }

    toggle(id) {
        this.state.open[id] = !this.state.open[id];
    }

    setFilter(key) {
        this.state.filter = key;
    }

    get filters() {
        return FILTERS;
    }

    labelClass(address) {
        const label = (address.mart369_label || "").toLowerCase();
        return label === "home" ? "o_mart_home" : label === "work" ? "o_mart_work" : "o_mart_other";
    }

    /** Open the real Odoo record, for anything this screen does not do. */
    openCustomer(customer) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.users",
            res_id: customer.id,
            views: [[false, "form"]],
        });
    }

    openAddress(address) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: address.id,
            views: [[false, "form"]],
        });
    }

    async makeDefault(address) {
        await this.orm.call("res.partner", "action_mart369_make_default", [[address.id]]);
        await this.load();
    }

    /** Whatever is on screen now, as a spreadsheet. */
    exportCsv() {
        const head = ["Customer", "Email", "Mobile", "Type", "Delivered to", "Address mobile",
                      "Flat", "Area", "City", "Pincode", "Default", "Missing"];
        const lines = [head];
        for (const c of this.rows) {
            if (!c.addresses.length) {
                lines.push([c.name, c.login, c.phone || "", "", "", "", "", "", "", "", "", "no address"]);
            }
            for (const a of c.addresses) {
                lines.push([
                    c.name, c.login, c.phone || "", a.mart369_label || "", a.name || "",
                    a.phone || "", a.street || "", a.street2 || "", a.city || "", a.zip || "",
                    a.mart369_default ? "yes" : "", a.gaps.join("; "),
                ]);
            }
        }
        const csv = lines
            .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
            .join("\n");
        const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = "369mart-customers.csv";
        link.click();
        URL.revokeObjectURL(url);
    }
}

registry.category("actions").add("mart369_address.console", Mart369Console);
