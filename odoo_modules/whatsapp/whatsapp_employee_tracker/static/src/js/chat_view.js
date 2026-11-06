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
            employeeSessionId: null,
            employeeSessions: [],
        });

        // Priority: context > localStorage
        const contextId = (this.props.action && this.props.action.context && this.props.action.context.active_employee_session_id) || null;
        let savedId = null;
        try { savedId = localStorage.getItem("wa_tracker_emp_session"); } catch(e) {}
        let savedConv = null;
        try { savedConv = localStorage.getItem("wa_tracker_conv_id"); } catch(e) {}

        this.state.employeeSessionId = contextId || (savedId ? parseInt(savedId) : null);
        this._pendingConvId = savedConv ? parseInt(savedConv) : null;

        // If opened from dashboard, save the employee session
        if (contextId) {
            try { localStorage.setItem("wa_tracker_emp_session", String(contextId)); } catch(e) {}
        }

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

    _saveState() {
        try {
            if (this.state.employeeSessionId) {
                localStorage.setItem("wa_tracker_emp_session", String(this.state.employeeSessionId));
            } else {
                localStorage.removeItem("wa_tracker_emp_session");
            }
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
            this.state.employeeSessions = result || [];

            // Auto-select if only one session exists
            if (!this.state.employeeSessionId && this.state.employeeSessions.length === 1) {
                this.state.employeeSessionId = this.state.employeeSessions[0].id;
                this._saveState();
            }
        } catch (e) {
            console.error("Failed to load employee sessions:", e);
        }
    }

    async loadConversations() {
        try {
            const result = await this._jsonRpc("/wa_tracker/conversations", {
                employee_session_id: this.state.employeeSessionId,
            });
            this.state.conversations = result || [];
        } catch (e) {
            console.error("Failed to load conversations:", e);
        }
    }

    async onEmployeeChange(ev) {
        const val = ev.target.value;
        this.state.employeeSessionId = val ? parseInt(val) : null;
        this.state.selectedConvId = null;
        this.state.messages = [];
        this._saveState();
        await this.loadConversations();
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
