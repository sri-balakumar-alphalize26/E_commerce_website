/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { waText } from "./wa_text";

class WaChatView extends Component {
    static template = "whatsapp_employee_tracker.ChatView";
    static props = { "*": true };

    setup() {
        this.messagesRef = useRef("messagesContainer");
        this.bus = useService("bus_service");
        this._opened = {};
        this._onNew = () => {
            clearTimeout(this._soon);
            this._homeAt = this._repliesAt = 0;
            this._soon = setTimeout(() => this._refreshQuietly(), 300);
        };
        this._onAway = (ev) => {
            if (this.state.drop && !(ev.target.closest && ev.target.closest(".wa-drop"))) this.state.drop = false;
        };
        this._onEsc = (ev) => {
            if (ev.key === "Escape" && this.state.drop) this.state.drop = false;
            if (ev.key === "Escape" && this.state.viewer) {
                ev.stopPropagation();
                this.closeViewer();
            }
        };
        this._onSeen = () => {
            if (!document.hidden) this._refreshQuietly();
        };

        this.state = useState({
            conversations: [],
            messages: [],
            selectedConvId: null,
            searchQuery: "",
            loading: false,
            employees: [],
            employeeId: null,       // null: everybody
            numberId: null,         // an employee session; null: all numbers
            phone: false,           // the list is the phone's own
            phoneDown: false,
            showOld: false,         // chats older than 48 hours too
            limit: 40,
            more: false,            // older messages of the opened chat
            loadingOlder: false,
            media: {},              // opened pictures and voice notes
            viewer: null,           // the picture or video in the popup
            reply: "",
            replyError: "",
            replies: [],            // how each employee replies
            home: false,            // the chats of everybody; false: not for this user
            picked: 0,              // only this number's chats
            classic: false,         // the full history, as before
            drop: false,            // the employees, opened
            checking: 0,
            now: Date.now(),
        });

        // Priority: context > localStorage
        const context = (this.props.action && this.props.action.context) || {};
        this._openSession = context.active_employee_session_id || null;
        this._openAll = !!context.wa_all_numbers;
        this._saved = { employee: this._read("wa_tracker_employee"), number: this._read("wa_tracker_number"),
                        conv: this._read("wa_tracker_conv_id") };
        this._pendingConvId = this._saved.conv.includes("@") ? this._saved.conv : parseInt(this._saved.conv) || null;

        onWillStart(async () => {
            await this.loadEmployeeSessions();
            this._loadReplies();
            this._loadHome();
            if (!this._openSession) this.state.numberId = null;
            await this.loadConversations();
        });

        onWillUnmount(() => {
            clearInterval(this._timer);
            clearTimeout(this._soon);
            clearInterval(this._clock);
            window.removeEventListener("keydown", this._onEsc, true);
            window.removeEventListener("pointerdown", this._onAway, true);
            this.bus.unsubscribe("wa_tracker_new", this._onNew);
            document.removeEventListener("visibilitychange", this._onSeen);
        });
        onMounted(() => {
            this.bus.subscribe("wa_tracker_new", this._onNew);
            this._clock = setInterval(() => (this.state.now = Date.now()), 5000);
            this.bus.start();
            document.addEventListener("visibilitychange", this._onSeen);
            window.addEventListener("keydown", this._onEsc, true);
            window.addEventListener("pointerdown", this._onAway, true);
            this._timer = setInterval(() => this._refreshQuietly(), 8000);
            if (this._pendingConvId) {
                const id = this._pendingConvId;
                if (this.state.conversations.find(c => c.id === id)) {
                    this.selectConversation(id);
                }
            }
        });
    }

    /** New messages without pressing anything; the place scrolled to stays. */
    async _refreshQuietly() {
        if (document.hidden) return;
        this._loadReplies();
        this._loadHome();
        if (this._busy) {
            this._again = true;
            return;
        }
        this._busy = true;
        const { numberId, employeeId, selectedConvId } = this.state;
        const same = () => numberId === this.state.numberId && employeeId === this.state.employeeId;
        try {
            const wasPhone = this.state.phone;
            if (!(await this._loadPhone())) {
                const rows = await this._jsonRpc("/wa_tracker/conversations", { employee_session_id: numberId, employee_id: employeeId });
                if (Array.isArray(rows) && rows.length && same()) this.state.conversations = rows;
            }
            if (wasPhone !== this.state.phone) {
                // the ids of the two lists are not the same
                this.state.selectedConvId = null;
                this.state.messages = [];
                return;
            }
            if (selectedConvId) {
                const answer = wasPhone ? await this._phonePage()
                    : await this._jsonRpc("/wa_tracker/messages", { conversation_id: selectedConvId });
                const messages = wasPhone ? answer && answer.messages : answer;
                const box = this.messagesRef.el;
                const atEnd = box && box.scrollHeight - box.scrollTop - box.clientHeight < 80;
                if (Array.isArray(messages) && messages.length && same() && selectedConvId === this.state.selectedConvId) {
                    if (wasPhone) this._merge(messages);
                    else this.state.messages = messages;
                    if (atEnd) {
                        setTimeout(() => {
                            const el = this.messagesRef.el;
                            if (el) el.scrollTop = el.scrollHeight;
                        }, 100);
                    }
                }
            }
        } catch {
            // the next round tries again
        } finally {
            this._busy = false;
            if (this._again) {
                this._again = false;
                this._onNew();
            }
        }
    }

    /** At most every half minute; a failure leaves what is shown. */
    async _loadReplies() {
        this.state.now = Date.now();
        if (this._repliesAt && this.state.now - this._repliesAt < 30000) return;
        this._repliesAt = this.state.now;
        try {
            const answer = await this._jsonRpc("/wa_tracker/reply_status");
            if (answer && answer.rows) this.state.replies = answer.rows;
        } catch {
            // the next round tries again
        }
    }
    async checkNumber(row) {
        this.state.checking = row.id;
        try {
            await this._jsonRpc("/wa_tracker/check_number", { employee_session_id: row.id });
        } catch {
            // what is shown stays
        }
        this.state.checking = 0;
        this._repliesAt = 0;
        await this._loadReplies();
    }
    /** Everybody's chats, private and groups; at most every ten seconds. */
    async _loadHome() {
        if (this._homeBusy || (this._homeAt && Date.now() - this._homeAt < 10000)) return;
        this._homeBusy = true;
        this._homeAt = Date.now();
        try {
            const answer = await this._jsonRpc("/wa_tracker/home");
            if (answer && answer.chats !== undefined) this.state.home = answer.chats;
        } catch {
            // the next round tries again
        }
        this._homeBusy = false;
    }
    get showHome() {
        return !!this.state.home && !this.state.classic;
    }
    get pickedRow() {
        return this.state.replies.find((r) => r.id === this.state.picked);
    }
    cardName(chat) {
        const row = this.state.replies.find((r) => r.id === chat.card);
        return row ? row.name : "";
    }
    /** As WhatsApp Web lists them: one list, the newest on top. */
    get homeRows() {
        const q = (this.state.searchQuery || "").trim().toLowerCase();
        return this.state.home.filter((c) => (!this.state.picked || c.card === this.state.picked)
            && (!q || c.name.toLowerCase().includes(q) || (c.preview || "").toLowerCase().includes(q)))
            .sort((a, b) => b.date.localeCompare(a.date));
    }
    /** The state of the last message as the chat knows it, else as the list does. */
    listTick(chat) {
        const open = this.state.numberId === chat.card && this.state.selectedConvId === chat.id ? this.state.messages : null;
        const found = (open || this._kept(chat.card, chat.id) || []).find((m) => m.id === chat.last);
        return found ? found.status : chat.tick;
    }
    /** Today the time, then Yesterday, the day of the week, the date. */
    listTime(text) {
        const d = this._date(text);
        if (!d) return "";
        const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
        const days = Math.round((day(new Date(this.state.now)) - day(d)) / 86400000);
        if (days <= 0) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
        if (days === 1) return "Yesterday";
        return days < 7 ? d.toLocaleDateString([], { weekday: "long" }) : d.toLocaleDateString();
    }
    /** What the opened chat is: said there, not in the list. */
    get openState() {
        const c = this.openChat;
        if (!c || c.state === "old") return "";
        return c.state === "no" ? `Not replied, ${this._long(this._minutes(c.date) || 0)}` : "Replied";
    }
    /** Waiting chats of one employee, or of all. */
    waitingOf(row) {
        return this.state.home.filter((c) => c.state === "no" && (!row || c.card === row.id));
    }
    oldestOf(row) {
        const dates = this.waitingOf(row).map((c) => c.date).sort();
        return dates.length ? this._long(this._minutes(dates[0]) || 0) : "";
    }
    isLate(row) {
        const dates = this.waitingOf(row).map((c) => c.date).sort();
        return !!dates.length && (this._minutes(dates[0]) || 0) >= 30;
    }
    toggleDrop() {
        this.state.drop = !this.state.drop;
    }
    choose(row) {
        this.state.drop = false;
        this.state.picked = row ? row.id : 0;
        this.state.selectedConvId = null;
        this.state.messages = [];
        this._saveState();
    }
    get allToday() {
        const n = this.state.replies.reduce((sum, r) => sum + r.replies, 0);
        const minutes = this.state.replies.reduce((sum, r) => sum + r.replies * r.average, 0);
        return n ? `${n} replies today, in ${this._long(Math.round(minutes / n))}` : "No replies yet today";
    }
    count(row, state) {
        return this.state.home ? this.state.home.filter((c) => c.card === row.id && c.state === state).length
            : state === "no" ? row.waiting : 0;
    }
    wrongCount(row) {
        return (this.state.home || []).filter((c) => c.card === row.id && c.wrong).length;
    }
    /** The words of the alert rules, in a message of the employee. */
    isWrong(msg) {
        const chat = this.openChat;
        return !!(chat && chat.wrong && msg.direction === "outgoing" && chat.wrong.texts.includes(msg.message_text));
    }
    /** Who has something open comes first. */
    get board() {
        const rank = (r) => this.wrongCount(r) * 1000 + this.count(r, "no");
        return [...this.state.replies].sort((a, b) => rank(b) - rank(a) || a.name.localeCompare(b.name));
    }
    async _openNumber(row) {
        this.state.employeeId = row.employee_id;
        this.state.numberId = row.id;
        await this._changed();
    }
    async openHomeChat(chat) {
        const row = this.state.replies.find((r) => r.id === chat.card);
        if (!row) return;
        this.state.employeeId = row.employee_id;
        this.state.numberId = row.id;
        this.state.showOld = true;
        this._homeNumber();                 // nothing to wait for
        await this.selectConversation(chat.id);
    }
    get openChat() {
        return this.state.home && this.state.home.find((c) => c.card === this.state.numberId && c.id === this.state.selectedConvId);
    }
    toggleClassic() {
        this.state.classic = !this.state.classic;
    }
    letter(name) {
        const found = (name || "").match(/[\p{L}\p{N}]/u);
        return found ? found[0].toUpperCase() : "";
    }
    _minutes(text) {
        const d = this._date(text);
        return d ? Math.max(0, Math.floor((this.state.now - d.getTime()) / 60000)) : null;
    }
    _long(minutes) {
        if (minutes < 60) return `${minutes} min`;
        if (minutes < 1440) return `${Math.floor(minutes / 60)} h`;
        return minutes < 2880 ? "1 day" : `${Math.floor(minutes / 1440)} days`;
    }
    /** When they last wrote something. */
    activeText(row) {
        if (!row.connected) return "Number not connected";
        const mine = (this.state.home || []).filter((c) => c.card === row.id && c.mine).map((c) => c.date);
        const last = [row.last || "", ...mine].sort().pop();
        return last ? `Replied ${this.ago(last)}` : "No replies yet";
    }
    ago(text) {
        const m = this._minutes(text);
        if (m === null) return "";
        if (m < 1) return "just now";
        return m < 60 ? `${m} min ago` : this.formatTime(text);
    }
    /** The employee of the number shown. */
    get chatOwner() {
        return this.state.replies.find((row) => row.id === this.state.numberId);
    }
    initials(name) {
        return (name || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    }
    exactTime(text) {
        const d = this._date(text);
        return d ? d.toLocaleString() : "";
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

    _unread(chat) {
        if (chat.id === this.state.selectedConvId) this._opened[chat.id] = chat.date;
        return (this._opened[chat.id] || "") >= chat.date ? 0 : chat.unread;
    }

    /** This number's chats, out of the list of everybody. */
    _homeNumber() {
        const own = this.state.home.filter((c) => c.card === this.state.numberId);
        this.state.phone = true;
        this.state.phoneDown = false;
        this.state.conversations = own.map((c) => ({
            id: c.id, contact_name: c.name, phone: c.phone, total_messages: 0, last_message_date: c.date, group: c.group,
            last_message_preview: c.preview, employee_name: this.cardName(c), own_number: "", own_current: true,
        }));
    }
    /** The chats as the phone has them; false: the saved ones are shown. */
    async _loadPhone() {
        const numberId = this.state.numberId;
        if (!numberId) {
            this.state.phone = this.state.phoneDown = false;
            return false;
        }
        if (this.showHome) {
            this._homeNumber();
            return true;
        }
        const result = await this._jsonRpc("/wa_tracker/phone_chats", { employee_session_id: numberId });
        if (numberId !== this.state.numberId) return true;
        this.state.phoneDown = !!(result && result.down);
        if (!result || !result.chats) {
            this.state.phone = false;
            return false;
        }
        const number = this.selectedEmployee.numbers.find((n) => n.id === numberId) || {};
        this.state.phone = true;
        this.state.conversations = result.chats.map((c) => ({
            id: c.id, contact_name: c.name, phone: c.phone, total_messages: this._unread(c), last_message_date: c.date, group: c.group,
            last_message_preview: (c.from_me ? "\u2197 " : "") + c.preview, employee_name: this.selectedEmployee.name || "",
            own_number: number.number || "", own_current: true,
        }));
        return true;
    }

    async loadConversations() {
        try {
            if (await this._loadPhone()) return;
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

    get canReply() {
        const chat = this.state.conversations.find((c) => c.id === this.state.selectedConvId);
        return this.state.phone && !!chat && !chat.group && !!chat.phone;
    }
    onReplyKey(ev) {
        if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.sendReply();
        }
    }
    /** In the chat at once, with a clock; one after the other, in the order typed. */
    sendReply() {
        const text = this.state.reply.trim();
        if (!text) return;
        const one = {
            id: "sending-" + (this._sent = (this._sent || 0) + 1), message_text: text, direction: "outgoing", status: "pending",
            message_date: new Date().toISOString().slice(0, 19).replace("T", " "), is_flagged: false, sender: "", media: false,
        };
        const chat = this.state.selectedConvId, number = this.state.numberId;
        this.state.reply = this.state.replyError = "";
        this.state.messages.push(one);
        setTimeout(() => {
            const el = this.messagesRef.el;
            if (el) el.scrollTop = el.scrollHeight;
        }, 0);
        this._sendLine = (this._sendLine || Promise.resolve()).then(() => this._sendOne(one, chat, number));
    }
    /** What became of it: its real id, or gone and the text back in the box. */
    _sendDone(one, chat, id) {
        if (chat !== this.state.selectedConvId) return;
        const rows = this.state.messages;
        if (!id || rows.some((m) => m.id === id)) {
            this.state.messages = rows.filter((m) => m.id !== one.id);
        } else {
            this.state.messages = rows.map((m) => (m.id === one.id ? { ...m, id, status: "sent" } : m));
        }
    }
    _sendFailed(one, chat, error, again) {
        this._sendDone(one, chat, false);
        if (chat !== this.state.selectedConvId) return;
        this.state.replyError = error;
        if (again && !this.state.reply.trim()) this.state.reply = one.message_text;
    }
    async _sendOne(one, chat, number) {
        const text = one.message_text;
        try {
            const answer = await this._jsonRpc("/wa_tracker/phone_reply", {
                employee_session_id: number, chat_id: chat, text });
            if (!answer || answer.error || answer.paused === undefined) {
                this._sendFailed(one, chat, (answer && answer.error) || "Not sent.", true);
            } else if (chat === this.state.selectedConvId) {
                this._sendDone(one, chat, answer.id);
                if (!answer.paused) this.state.replyError = "Sent. The assistant is not paused: Shopkeeper takes over is off in the settings.";
                this._onNew();
            }
        } catch {
            this._sendFailed(one, chat, "It is not known whether it was sent. Look in the chat before sending again.", false);
        }
    }

    mediaUrl(msg) {
        return `/wa_tracker/phone_media/${this.state.numberId}/${encodeURIComponent(msg.id)}`;
    }
    openMedia(msg) {
        if (msg.media.kind === "image" || msg.media.kind === "video") {
            this.state.viewer = msg;
            return;
        }
        this.state.media[msg.id] = "open";
    }
    closeViewer() {
        this.state.viewer = null;
    }
    viewerFailed() {
        if (this.state.viewer) this.state.media[this.state.viewer.id] = "failed";
        this.state.viewer = null;
    }
    /** The text in pieces; the picture itself is below, so "Image:" is not said again. */
    pieces(msg) {
        let text = msg.message_text || "";
        if (msg.media) text = text.replace(/^(\u{1F4F7} Image|\u{1F3AC} Video|\u{1F3A4} Voice note|\u{1F4C4} Document|Sticker)(: |$)/u, "");
        return waText(text);
    }
    mediaFailed(msg) {
        this.state.media[msg.id] = "failed";
    }
    showOlderChats() {
        this.state.showOld = true;
    }
    onListScroll(ev) {
        const box = ev.currentTarget;
        if (box.scrollHeight - box.scrollTop - box.clientHeight < 200) this.state.limit += 40;
    }
    async onMessagesScroll(ev) {
        const box = ev.currentTarget;
        const id = this.state.selectedConvId;
        if (Date.now() < (this._settling || 0)) return;
        if (box.scrollTop > 60 || !this.state.phone || !this.state.more || this.state.loadingOlder) return;
        this.state.loadingOlder = true;
        try {
            const page = this._page + 1;
            const result = await this._jsonRpc("/wa_tracker/phone_messages", { employee_session_id: this.state.numberId, chat_id: id, page });
            if (id === this.state.selectedConvId && result && result.messages) {
                this._page = page;
                const before = box.scrollHeight;
                this._merge(result.messages);
                this.state.more = result.more;
                setTimeout(() => (box.scrollTop += box.scrollHeight - before), 50);
            }
        } finally {
            this.state.loadingOlder = false;
        }
    }
    _merge(messages) {
        const all = new Map(this.state.messages.map((m) => [m.id, m]));
        messages.forEach((m) => all.set(m.id, m));
        this.state.messages = [...all.values()].sort((a, b) => a.message_date.localeCompare(b.message_date));
    }
    async _phonePage() {
        return this._jsonRpc("/wa_tracker/phone_messages", { employee_session_id: this.state.numberId, chat_id: this.state.selectedConvId, page: 1 });
    }

    async onNumberChange(ev) {
        this.state.numberId = parseInt(ev.target.value) || null;
        await this._changed();
    }

    async _changed() {
        this.state.selectedConvId = null;
        this.state.messages = [];
        this.state.more = this.state.showOld = false;
        this.state.limit = 40;
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
    /** Odoo's times are UTC; the viewer reads their own. */
    _date(text) {
        if (!text || text === "False" || text === "false") return null;
        const d = new Date(text.slice(0, 19).replace(" ", "T") + "Z");
        return isNaN(d.getTime()) ? null : d;
    }
    isNewDay(index) {
        const day = (m) => {
            const d = m && this._date(m.message_date);
            return d ? d.toDateString() : "";
        };
        const now = day(this.state.messages[index]);
        return !!now && now !== day(this.state.messages[index - 1]);
    }
    dayLabel(text) {
        const d = this._date(text);
        if (!d) return "";
        const other = new Date();
        if (d.toDateString() === other.toDateString()) return "Today";
        other.setDate(other.getDate() - 1);
        if (d.toDateString() === other.toDateString()) return "Yesterday";
        return d.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
    }
    formatClock(text) {
        const d = this._date(text);
        return d ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
    }
    tick(status) {
        const grey = "#667781";
        return {
            sent: { icons: ["fa-check"], color: grey },
            delivered: { icons: ["fa-check", "fa-check"], color: grey },
            read: { icons: ["fa-check", "fa-check"], color: "#53bdeb" },
            failed: { icons: ["fa-exclamation-circle"], color: "#dc3545" },
        }[status] || { icons: ["fa-clock-o"], color: grey };
    }
    formatDay(text) {
        const d = this._date(text);
        return d ? d.toLocaleDateString([], { day: "numeric", month: "short" }) : "";
    }

    _kept(number, convId) {
        return this._seen && this._seen.get(number + "/" + convId);
    }
    /** The last thirty chats, in this page only. */
    _keep(number, convId, messages) {
        this._seen = this._seen || new Map();
        const key = number + "/" + convId;
        this._seen.delete(key);
        this._seen.set(key, messages.filter((m) => !String(m.id).startsWith("sending-")));
        if (this._seen.size > 30) this._seen.delete(this._seen.keys().next().value);
    }
    /** To the newest message, also after its pictures have come. */
    _toEnd(convId) {
        this._settling = Date.now() + 1200;         // going there is not scrolling up for older ones
        for (const wait of [0, 100, 400, 900]) {
            setTimeout(() => {
                const el = this.messagesRef.el;
                if (el && convId === this.state.selectedConvId && !this._left) el.scrollTop = el.scrollHeight;
            }, wait);
        }
    }
    async selectConversation(convId) {
        this._left = false;
        if (convId !== this.state.selectedConvId) {
            this.state.reply = this.state.replyError = "";
        }
        this.state.selectedConvId = convId;
        this.state.loading = true;
        const opened = this.state.phone && this.state.conversations.find((c) => c.id === convId);
        if (opened) {
            this._opened[convId] = opened.last_message_date;
            opened.total_messages = 0;
        }
        this._saveState();

        try {
            let result;
            if (this.state.phone) {
                const number = this.state.numberId, kept = this._kept(number, convId);
                this.state.messages = kept ? [...kept] : [];
                this._toEnd(convId);
                this._page = 1;
                const answer = await this._phonePage();
                if (convId !== this.state.selectedConvId || number !== this.state.numberId) return;
                if (answer && answer.messages) {
                    result = answer.messages;
                    this._keep(number, convId, result);
                } else {
                    result = kept || [];
                }
                this.state.more = !!(answer && answer.more);
            } else {
                this.state.more = false;
                result = await this._jsonRpc("/wa_tracker/messages", { conversation_id: convId });
                if (convId !== this.state.selectedConvId) return;
            }
            this.state.messages = result || [];
            this._toEnd(convId);
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
        if (!q && this.state.phone) {
            const since = Date.now() - 48 * 3600 * 1000;
            const recent = (c) => { const d = this._date(c.last_message_date); return d && d.getTime() >= since; };
            return this.state.conversations.filter((c) => this.state.showOld || recent(c) || c.id === this.state.selectedConvId)
                .slice(0, this.state.limit);
        }
        if (!q) return this.state.conversations;
        return this.state.conversations.filter(
            (c) =>
                (c.contact_name || "").toLowerCase().includes(q) ||
                (c.phone || "").includes(q)
        );
    }

    get hasOlderChats() {
        return this.state.phone && !this.state.showOld && !this.state.searchQuery;
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
        const d = this._date(dateStr);
        if (!d) return "";
        try {
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
