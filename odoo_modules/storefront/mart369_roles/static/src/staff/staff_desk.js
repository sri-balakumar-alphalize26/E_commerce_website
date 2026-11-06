/**
 * Staff & roles - who works at 369 Mart and what each person may do.
 *
 * The twin of the console's /admin/staff. Both call the same model methods
 * (`mart369_staff_list`, `mart369_staff_set`, `mart369_staff_invite`), which set
 * the same groups the user form's Role line sets - so this page, the console
 * and Settings > Users can never disagree about someone's role.
 *
 * Owner only: the model refuses anyone else, and the menu is only shown to
 * Owners.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369/ui/icon";
import { Search } from "@mart369/ui/search";

const MODEL = "res.users";

const ROLES = [
    { key: "user", label: _t("User") },
    { key: "packer", label: _t("Packer") },
    { key: "manager", label: _t("Manager") },
    { key: "owner", label: _t("Owner") },
];
const TONE = { user: "grey", packer: "orange", manager: "blue", owner: "violet" };

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

function ago(ms) {
    if (!ms) {
        return _t("Not signed in yet");
    }
    const days = Math.floor((Date.now() - ms) / 86400000);
    if (days < 1) {
        return _t("Today");
    }
    if (days === 1) {
        return _t("Yesterday");
    }
    return _t("%s days ago", days);
}

export class StaffDesk extends Component {
    static template = "mart369_roles.StaffDesk";
    static components = { Layout, Icon, Search };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.ROLES = ROLES;
        this.state = useState({
            q: "",
            rows: [],
            counts: {},
            companies: [],
            help: {},
            loading: true,
            error: "",
            edit: null,     // {id?, name, email, role, accountant, rider, companies:[ids], invite}
            busy: false,
            formError: "",
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const page = await this.orm.call(MODEL, "mart369_staff_list", [], { q: this.state.q || null });
            this.state.rows = page.rows || [];
            this.state.counts = page.counts || {};
            this.state.companies = page.companies || [];
            this.state.help = page.help || {};
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    onSearch(q) {
        this.state.q = q;
        this.load();
    }

    roleLabel(key) {
        return (ROLES.find((r) => r.key === key) || ROLES[0]).label;
    }

    tone(key) {
        return TONE[key] || "grey";
    }

    ago(ms) {
        return ago(ms);
    }

    // ---------------------------------------------------------------- panel

    open(row) {
        this.state.formError = "";
        this.state.edit = {
            id: row.id, name: row.name, email: row.email, role: row.role,
            accountant: row.accountant, rider: row.rider,
            companies: row.companies.map((c) => c.id), me: row.me, invite: false,
        };
    }

    invite() {
        this.state.formError = "";
        this.state.edit = {
            name: "", email: "", role: "packer", accountant: false, rider: false,
            companies: [], invite: true,
        };
    }

    close() {
        this.state.edit = null;
    }

    toggleCompany(id) {
        const list = this.state.edit.companies;
        const i = list.indexOf(id);
        if (i >= 0) {
            list.splice(i, 1);
        } else {
            list.push(id);
        }
    }

    async save() {
        const e = this.state.edit;
        this.state.busy = true;
        this.state.formError = "";
        try {
            if (e.invite) {
                await this.orm.call(MODEL, "mart369_staff_invite",
                    [e.name, e.email, e.role, e.accountant, e.rider]);
                this.notification.add(_t("%s added. An email to set a password is on its way.", e.name), { type: "success" });
            } else {
                await this.orm.call(MODEL, "mart369_staff_set",
                    [e.id, e.role, e.accountant, e.rider, e.companies]);
                this.notification.add(_t("Saved: %s is now %s.", e.name, this.roleLabel(e.role)), { type: "success" });
            }
            this.state.edit = null;
            await this.load();
        } catch (err) {
            this.state.formError = message(err);
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("mart369_roles.staff", StaffDesk);
