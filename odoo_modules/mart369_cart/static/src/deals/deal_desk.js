/**
 * The deals desk - 369 Mart > Deals.
 *
 * The twin of the app's console screen, and deliberately the same one: staff
 * who work in Odoo should not get a different answer to "what is on offer"
 * than staff who work in the console. Both read `mart369_admin_list` on the
 * model, so the tiles and the cards cannot drift apart.
 *
 * What the list and form next door cannot say, and this does:
 *
 *  - **on now** is not the same as **switched on**. A deal can be on and
 *    waiting for Friday, or on and finished. Three different situations that
 *    a single checkbox renders identically, and each means something else to
 *    somebody asking why a price has not moved.
 *  - what a shopper will actually pay. The card shows the old price struck
 *    through and the new one beside it, worked out from the same numbers the
 *    storefront prices with - so nobody has to do the arithmetic to check.
 *
 * Editing happens in a dialog rather than a side panel. A deal is a short
 * form that is opened, changed and closed, not something you sit beside the
 * list and tinker with; and a dialog leaves the cards their full width, which
 * is what they need to show three prices without truncating product names.
 *
 * Nothing is written to the products. The lower price is computed whenever a
 * card, a basket or an order is priced, which is why switching a deal off
 * puts every price back with no cleanup.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const M = { deal: "mart369.deal", product: "product.template" };

/* Tile -> which deals it shows. `all` is the default, because a deal that is
   not running yet is exactly what somebody comes here to check on. */
export const TILES = [
    { key: "all", label: _t("All deals"), icon: "fa-tags" },
    { key: "live", label: _t("On right now"), icon: "fa-bolt" },
    { key: "scheduled", label: _t("Starting later"), icon: "fa-clock-o" },
    { key: "off", label: _t("Switched off"), icon: "fa-pause" },
];

/** Money, in whatever the shop quotes in. Shared by both components. */
function format(amount, currency) {
    const n = Number(amount) || 0;
    const shown = n.toLocaleString(currency?.locale || undefined, {
        minimumFractionDigits: currency ? currency.decimals : 2,
        maximumFractionDigits: currency ? currency.decimals : 2,
    });
    if (!currency?.symbol) {
        return shown;
    }
    return currency.position === "after"
        ? `${shown} ${currency.symbol}`
        : `${currency.symbol}${shown}`;
}

/**
 * The editor, in a dialog.
 *
 * Holds its own draft so that typing never rewrites the card behind it, and
 * nothing reaches the shop until Save. Closing throws the draft away, which
 * is what somebody pressing Cancel means.
 */
export class DealDialog extends Component {
    static template = "mart369_cart.DealDialog";
    static components = { Dialog };
    static props = {
        deal: { type: [Object, { value: null }], optional: true },
        currency: { type: [Object, { value: null }], optional: true },
        onSaved: Function,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        const deal = this.props.deal;
        this.state = useState({
            draft: deal
                ? {
                    id: deal.id, name: deal.name, note: deal.note, kind: deal.kind,
                    value: deal.value, floor: deal.floor,
                    startsOn: deal.startsOn || "", endsOn: deal.endsOn || "",
                    products: [...deal.products],
                }
                : {
                    id: null, name: "", note: "", kind: "percent", value: 10,
                    floor: 0, startsOn: "", endsOn: "", products: [],
                },
            q: "",
            results: [],
            busy: false,
            error: "",
        });

        this.search = useDebounced(this._search, 300);
    }

    edit(field, ev) {
        const value = ev.target.value;
        this.state.draft[field] =
            field === "value" || field === "floor" ? parseFloat(value || 0) : value;
    }

    async _search() {
        const q = (this.state.q || "").trim();
        if (!q) {
            this.state.results = [];
            return;
        }
        try {
            this.state.results = await this.orm.searchRead(
                M.product,
                [["is_published", "=", true], ["name", "ilike", q]],
                ["id", "name", "list_price"],
                { limit: 12 }
            );
        } catch {
            this.state.results = [];
        }
    }

    onSearch(ev) {
        this.state.q = ev.target.value;
        this.search();
    }

    add(product) {
        const draft = this.state.draft;
        if (draft.products.some((p) => p.id === product.id)) {
            return;
        }
        draft.products.push({
            id: product.id, name: product.name, price: product.list_price,
        });
        this.state.q = "";
        this.state.results = [];
    }

    drop(id) {
        this.state.draft.products = this.state.draft.products.filter((p) => p.id !== id);
    }

    /* What this draft would charge for something at `price`. Mirrors
       `_mart369_apply` on the model so the dialog can show the new price
       while it is being typed - the server still decides on save. */
    preview(price) {
        const d = this.state.draft;
        if (!d || !price) {
            return price;
        }
        const cut = d.kind === "percent" ? (price * (d.value || 0)) / 100 : d.value || 0;
        let out = price - cut;
        if (d.floor) {
            out = Math.max(out, d.floor);
        }
        return Math.max(out, 0.01);
    }

    money(amount) {
        return format(amount, this.props.currency);
    }

    forInput(value) {
        return value ? value.slice(0, 16).replace(" ", "T") : "";
    }

    get canSave() {
        const d = this.state.draft;
        return d.name.trim().length > 1 && d.products.length > 0 && d.value > 0;
    }

    async save() {
        if (!this.canSave || this.state.busy) {
            return;
        }
        const d = this.state.draft;
        const values = {
            name: d.name.trim(),
            note: d.note || false,
            kind: d.kind,
            value: d.value || 0,
            floor: d.floor || 0,
            starts_on: d.startsOn ? d.startsOn.replace("T", " ").slice(0, 19) : false,
            ends_on: d.endsOn ? d.endsOn.replace("T", " ").slice(0, 19) : false,
            product_ids: [[6, 0, d.products.map((p) => p.id)]],
        };
        this.state.busy = true;
        try {
            if (d.id) {
                await this.orm.write(M.deal, [d.id], values);
            } else {
                await this.orm.create(M.deal, [values]);
            }
            this.props.close();
            await this.props.onSaved(
                d.id ? _t('"%s" saved.', values.name) : _t('"%s" created.', values.name)
            );
        } catch (err) {
            /* The dialog stays open with the message in it. The model refuses
               a percentage over 90 in its own words, and closing would throw
               away everything just typed. */
            this.state.error =
                err?.data?.message || err?.message?.data?.message || err?.message ||
                _t("That could not be saved.");
        } finally {
            this.state.busy = false;
        }
    }
}

export class DealDesk extends Component {
    static template = "mart369_cart.DealDesk";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.TILES = TILES;

        this.state = useState({
            deals: [],
            trash: [],
            trashDays: 30,
            trashOpen: false,
            counts: {},
            onOffer: 0,
            currency: null,
            tab: "all",
            loading: true,
            busy: false,
            error: "",
        });

        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------- reading

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(M.deal, "mart369_admin_list", []);
            this.state.deals = data.deals;
            this.state.trash = data.trash || [];
            this.state.trashDays = data.trashDays;
            this.state.counts = data.counts;
            this.state.onOffer = data.onOffer;
            this.state.currency = data.currency;
            this.state.error = "";
        } catch (err) {
            this.state.error = this.message(err);
        } finally {
            this.state.loading = false;
        }
    }

    message(err) {
        return (
            err?.data?.message || err?.message?.data?.message || err?.message ||
            _t("We could not reach the shop.")
        );
    }

    /* Read-after-write, like every other screen in the suite. `live` and the
       tile numbers are the server's, and guessing them is how a panel starts
       lying about what shoppers can see. */
    async run(fn, ok) {
        if (this.state.busy) {
            return false;
        }
        this.state.busy = true;
        try {
            await fn();
            await this.load();
            if (ok) {
                this.notification.add(ok, { type: "success" });
            }
            return true;
        } catch (err) {
            this.notification.add(this.message(err), { type: "danger" });
            return false;
        } finally {
            this.state.busy = false;
        }
    }

    get shown() {
        const tab = this.state.tab;
        return this.state.deals.filter((d) => {
            if (tab === "live") return d.live;
            if (tab === "scheduled") return d.active && !d.live && d.startsOn;
            if (tab === "off") return !d.active;
            return true;
        });
    }

    tileCount(tile) {
        return this.state.counts?.[tile.key] ?? 0;
    }

    pick(tab) {
        this.state.tab = tab;
    }

    // ------------------------------------------------------------- writing

    /** Tapping a card opens it for editing. */
    open(deal) {
        this.dialog.add(DealDialog, {
            deal: deal || null,
            currency: this.state.currency,
            onSaved: async (message) => {
                await this.load();
                this.notification.add(message, { type: "success" });
            },
        });
    }

    toggle(deal) {
        return this.run(
            () => this.orm.write(M.deal, [deal.id], { active: !deal.active }),
            deal.active
                ? _t('"%s" switched off. Every price it touched is back.', deal.name)
                : _t('"%s" switched on.', deal.name)
        );
    }

    remove(deal) {
        this.dialog.add(ConfirmationDialog, {
            title: _t('Remove "%s"?', deal.name),
            body: this.state.trashDays
                ? _t(
                    "It stops discounting straight away and waits in the Trash " +
                        "for %s days, where you can put it back.",
                    this.state.trashDays
                )
                : _t(
                    "It stops discounting straight away and waits in the Trash, " +
                        "where you can put it back."
                ),
            confirmLabel: _t("Remove deal"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(() => this.orm.call(M.deal, "action_trash", [[deal.id]]),
                         _t("Moved to the Trash.")),
            cancel: () => {},
        });
    }

    // -------------------------------------------------------------- the Trash

    openTrash() {
        this.state.trashOpen = !this.state.trashOpen;
    }

    restore(deal) {
        return this.run(
            () => this.orm.call(M.deal, "action_restore", [[deal.id]]),
            _t('"%s" is back.', deal.name)
        );
    }

    /* Gone now rather than in thirty days. Only offered from the Trash, so
       nothing is destroyed without having been visible there first. */
    forget(deal) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete for good?"),
            body: _t(
                '"%s" goes now. Orders already placed keep what they were ' +
                    "charged - the price was frozen onto the line at the time - " +
                    "so only this record goes.",
                deal.name
            ),
            confirmLabel: _t("Delete for good"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(() => this.orm.unlink(M.deal, [deal.id]), _t("Deleted.")),
            cancel: () => {},
        });
    }

    /* The list and the form are still there for grouping, export and
       everything this screen deliberately does not do. */
    allViews() {
        this.action.doAction("mart369_cart.action_mart369_deals");
    }

    // ------------------------------------------------------------ printing

    money(amount) {
        return format(amount, this.state.currency);
    }

    when(value) {
        return value ? value.slice(0, 16).replace(" ", " · ") : "";
    }

    /* Why a deal is not running, in the words somebody would use asking. */
    why(deal) {
        if (!deal.active) return _t("Switched off");
        if (deal.live) {
            return deal.endsOn ? _t("On now, until %s", this.when(deal.endsOn)) : _t("On now");
        }
        if (deal.startsOn) return _t("Starts %s", this.when(deal.startsOn));
        return _t("Finished");
    }

    worth(deal) {
        // One per cent sign: JS _t does no printf unescaping, so "%%" would
        // reach the screen as two characters.
        return deal.kind === "percent"
            ? _t("%s% off", deal.value)
            : _t("%s off", this.money(deal.value));
    }
}

registry.category("actions").add("mart369_cart.deals", DealDesk);
