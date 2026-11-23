/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";

class WaChatView extends Component {
    static template = "whatsapp_employee_tracker.ChatView";
    static props = { "*": true };

    setup() {
        this.messagesRef = useRef("messagesContainer");

        this.state = useState({
            conversations: [],
            messages: [],
            selectedConvId: null,
            searchQuery: "",
            loading: false,
            employees: [],
            employeeId: null,       // null: everybody
            numberId: null,         // an employee session; null: all numbers
        });

        // Priority: context > localStorage
        const context = (this.props.action && this.props.action.context) || {};
        this._openSession = context.active_employee_session_id || null;
        this._openAll = !!context.wa_all_numbers;
        this._saved = { employee: this._read("wa_tracker_employee"), number: this._read("wa_tracker_number"),
                        conv: this._read("wa_tracker_conv_id") };
        this._pendingConvId = parseInt(this._saved.conv) || null;

        onWillStart(async () => {
            await this.loadEmployeeSessions();
            await this.loadConversations();
        });

        onMounted(() => {
            if (this._pendingConvId) {
                const id = this._pendingConvId;
                if (this.state.conversations.find(c => c.id === id)) {
                    this.selectConversation(id);
                }
            }
        });
    }

    _read(key) {
        try {
            return localStorage.getItem(key) || "";
        } catch {
            return "";
        }
    }

    _saveState() {
        try {
            localStorage.setItem("wa_tracker_employee", String(this.state.employeeId || ""));
            localStorage.setItem("wa_tracker_number", this.state.employeeId && !this.state.numberId ? "all" : String(this.state.numberId || ""));
            if (this.state.selectedConvId) {
                localStorage.setItem("wa_tracker_conv_id", String(this.state.selectedConvId));
            } else {
                localStorage.removeItem("wa_tracker_conv_id");
            }
        } catch(e) {}
    }

    async _jsonRpc(url, params) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                id: Date.now(),
                params: params || {},
            }),
        });
        const data = await response.json();
        if (data.error) {
            console.error("RPC Error:", data.error);
            return [];
        }
        return data.result;
    }

    async loadEmployeeSessions() {
        try {
            const result = await this._jsonRpc("/wa_tracker/employee_sessions", {});
            const people = (this.state.employees = result || []);
            const owner = (id) => people.find((p) => p.numbers.some((n) => n.id === id));
            if (this._openSession && owner(this._openSession)) {
                this.state.employeeId = owner(this._openSession).id;
                this.state.numberId = this._openAll ? null : this._openSession;
            } else if (people.find((p) => p.id === parseInt(this._saved.employee))) {
                this.state.employeeId = parseInt(this._saved.employee);
                const number = parseInt(this._saved.number) || null;
                const mine = this.selectedEmployee.numbers.find((n) => n.id === number);
                // a choice that no longer exists falls back to the number of now
                this.state.numberId = this._saved.number === "all" ? null : mine ? number : this._currentNumber();
            } else if (people.length === 1) {
                this.state.employeeId = people[0].id;
                this.state.numberId = this._currentNumber();
            }
            this._openSession = null;
            this._saveState();
        } catch (e) {
            console.error("Failed to load employee sessions:", e);
        }
    }

    async loadConversations() {
        try {
            const result = await this._jsonRpc("/wa_tracker/conversations", {
                employee_session_id: this.state.numberId,
                employee_id: this.state.employeeId,
            });
            this.state.conversations = result || [];
        } catch (e) {
            console.error("Failed to load conversations:", e);
        }
    }

    async onEmployeeChange(ev) {
        const val = ev.target.value;
        this.state.employeeId = val ? parseInt(val) : null;
        this.state.numberId = this._currentNumber();
        await this._changed();
    }

    async onNumberChange(ev) {
        this.state.numberId = parseInt(ev.target.value) || null;
        await this._changed();
    }

    async _changed() {
        this.state.selectedConvId = null;
        this.state.messages = [];
        this._saveState();
        await this.loadConversations();
    }

    get selectedEmployee() {
        return this.state.employees.find((p) => p.id === this.state.employeeId) || { numbers: [] };
    }
    _currentNumber() {
        const numbers = this.selectedEmployee.numbers;
        const now = numbers.find((n) => n.current) || numbers[0];
        return now ? now.id : null;
    }
    numberLabel(n) {
        if (n.current) {
            return n.number + " (now)";
        }
        const day = (text) => this.formatDay(text);
        const from = day(n.first), to = day(n.last);
        return n.number + (from ? " (" + (from === to ? from : from + " - " + to) + ")" : "");
    }
    formatDay(text) {
        const d = text ? new Date(text.replace(" ", "T")) : null;
        return d && !isNaN(d.getTime()) ? d.toLocaleDateString([], { day: "numeric", month: "short" }) : "";
    }

    async selectConversation(convId) {
        this.state.selectedConvId = convId;
        this.state.loading = true;
        this._saveState();

        try {
            const result = await this._jsonRpc("/wa_tracker/messages", {
                conversation_id: convId,
            });
            this.state.messages = result || [];
            setTimeout(() => {
                const container = this.messagesRef.el;
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            }, 100);
        } catch (e) {
            console.error("Failed to load messages:", e);
        }
        this.state.loading = false;
    }

    async refreshMessages() {
        if (this.state.selectedConvId) {
            await this.selectConversation(this.state.selectedConvId);
        }
    }

    get filteredConversations() {
        const q = (this.state.searchQuery || "").toLowerCase();
        if (!q) return this.state.conversations;
        return this.state.conversations.filter(
            (c) =>
                (c.contact_name || "").toLowerCase().includes(q) ||
                (c.phone || "").includes(q)
        );
    }

    get selectedConvName() {
        const conv = this.state.conversations.find(c => c.id === this.state.selectedConvId);
        return conv ? conv.contact_name : "";
    }

    get selectedConvPhone() {
        const conv = this.state.conversations.find(c => c.id === this.state.selectedConvId);
        return conv ? conv.phone : "";
    }

    get selectedConvOwn() {
        const conv = this.state.conversations.find(c => c.id === this.state.selectedConvId);
        return conv ? conv.own_number : "";
    }

    get selectedConvEmployee() {
        const conv = this.state.conversations.find(c => c.id === this.state.selectedConvId);
        return conv ? conv.employee_name : "";
    }

    formatTime(dateStr) {
        if (!dateStr || dateStr === "False" || dateStr === "false") return "";
        try {
            const d = new Date(dateStr.replace(" ", "T"));
            if (isNaN(d.getTime())) return "";
            const now = new Date();
            const isToday = d.toDateString() === now.toDateString();
            if (isToday) {
                return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            }
            const yesterday = new Date(now);
            yesterday.setDate(yesterday.getDate() - 1);
            if (d.toDateString() === yesterday.toDateString()) {
                return "Yesterday";
            }
            return d.toLocaleDateString([], { month: "short", day: "numeric" });
        } catch {
            return "";
        }
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }
}

registry.category("actions").add("wa_chat_split_view", WaChatView);
