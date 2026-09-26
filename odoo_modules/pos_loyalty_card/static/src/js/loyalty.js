/** @odoo-module */

import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted, onWillStart } from "@odoo/owl";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { useBarcodeReader } from "@point_of_sale/app/hooks/barcode_reader_hook";


/**
 * Patch ProductScreen to clean orphaned loyalty discount lines.
 * When user applies a coupon in payment screen then goes to backend
 * and returns, the discount line persists. This cleanup runs when
 * the product screen mounts so the user never sees stale discount lines.
 */
patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);

        onMounted(() => {
            this._cleanLoyaltyDiscountLines();
        });
    },

    _cleanLoyaltyDiscountLines() {
        try {
            const order = this.pos.getOrder();
            if (!order) return;

            const lines = order.lines || [];
            if (lines.length === 0) return;

            const linesToRemove = [];

            for (const line of lines) {
                // Detect by persistent customer_note marker
                const note = line.customer_note || "";
                if (note === "LOYALTY_DISCOUNT") {
                    linesToRemove.push(line);
                    continue;
                }
                // Also detect by JS flag (same session)
                if (line.loyalty_discount_line) {
                    linesToRemove.push(line);
                    continue;
                }
            }

            if (linesToRemove.length > 0) {
                console.log("LOYALTY_PRODUCT_SCREEN: Removing", linesToRemove.length, "orphaned discount line(s)");
                for (const line of linesToRemove) {
                    try {
                        if (typeof line.delete === "function") {
                            line.delete();
                        }
                    } catch (e) {
                        console.warn("LOYALTY_PRODUCT_SCREEN: Could not remove line:", e);
                    }
                }
            }
        } catch (e) {
            console.error("LOYALTY_PRODUCT_SCREEN: Error:", e);
        }
    },
});


/**
 * Loyalty Card Search/Create Popup
 * When loyaltyMode=true: Full loyalty flow (search card, show points, create card)
 * When loyaltyMode=false: Customer Details mode (search by phone, create customer, no loyalty UI)
 */
export class LoyaltyCardPopup extends Component {
    static template = "pos_loyalty_card.LoyaltyCardPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
        loyaltyMode: { type: Boolean, optional: true },
        mobileDigits: { type: Number, optional: true },
        countryDialCode: { type: [String, Number], optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // Country-configurable mobile validation (Configuration > Loyalty > Loyalty Settings).
        // Seed from props (cached POS config) so we render immediately, but ALWAYS refetch the
        // active settings live from the server in onWillStart below, so the popup reflects the
        // current configured country/length even if the POS session was opened before it changed
        // (no POS reload needed).
        this.mobileDigits = Number(this.props.mobileDigits) > 0 ? Number(this.props.mobileDigits) : 10;
        this.countryDialCode = String(this.props.countryDialCode || "").replace(/[^0-9]/g, "");
        onWillStart(async () => {
            try {
                const cfg = await this.orm.call("pos.loyalty.card.settings", "get_mobile_config", []);
                if (cfg) {
                    if (Number(cfg.length) > 0) {
                        this.mobileDigits = Number(cfg.length);
                    }
                    this.countryDialCode = String(cfg.dial || "").replace(/[^0-9]/g, "");
                }
            } catch (e) {
                // Fall back to the props/cached values if the live lookup fails.
                console.warn("Loyalty: live mobile-config lookup failed, using cached config", e);
            }
        });
        // Scanner support: while this popup is open, any scanned barcode is used to
        // look up the loyalty card and auto-select it (works for hardware and
        // keyboard-emulation scanners). Exclusive so product scanning is paused.
        useBarcodeReader(
            {
                product: this._onScan,
                client: this._onScan,
                quantity: this._onScan,
                price: this._onScan,
                weight: this._onScan,
                discount: this._onScan,
                gs1: this._onScan,
            },
            true
        );
        this.state = useState({
            mode: "search",
            searchTerm: "",
            searching: false,
            cardData: null,
            newName: "",
            newPhone: "",
            newEmail: "",
            creating: false,
            error: "",
        });
    }

    get isLoyaltyMode() {
        return this.props.loyaltyMode !== false;
    }

    /**
     * Called when a barcode is scanned while this popup is open. Uses the
     * scanned code to look up the loyalty card and auto-selects it if found.
     */
    async _onScan(parsed) {
        let code = "";
        if (Array.isArray(parsed)) {
            code = (parsed[0] && (parsed[0].code || parsed[0].base_code)) || "";
        } else if (parsed) {
            code = parsed.code || parsed.base_code || "";
        }
        code = String(code).trim();
        if (!code) {
            return;
        }
        this.state.mode = "search";
        this.state.searchTerm = code;
        await this.doSearch();
        // Found a card -> select/validate it straight away (scan = one step).
        if (this.state.cardData) {
            this.selectCard();
        }
    }

    get invalidPhoneMessage() {
        return `Please enter a valid ${this.mobileDigits}-digit mobile number`;
    }

    get phonePlaceholder() {
        return `Enter ${this.mobileDigits}-digit mobile number`;
    }

    get newPhoneDigits() {
        return (this.state.newPhone || "").replace(/[^0-9]/g, "");
    }

    // True once the New Card mobile field holds exactly the configured digits.
    get isNewPhoneValid() {
        return this.newPhoneDigits.length === this.mobileDigits;
    }

    // Show the red (invalid) state while something is typed but not yet complete.
    get showPhoneInvalid() {
        return this.newPhoneDigits.length > 0 && !this.isNewPhoneValid;
    }

    // Red invalid border on the SEARCH box: a numeric (mobile) entry is typed but
    // does not yet have the exact configured length. Card numbers (with letters)
    // never trigger it.
    get showSearchInvalid() {
        const term = (this.state.searchTerm || "").trim();
        if (!term) return false;
        const check = this._validatePhoneInput(term);
        return check.isPhone && !check.valid;
    }

    /**
     * Validate whether the input looks like a phone number and whether it has
     * the configured number of digits (country dial code optional).
     */
    _validatePhoneInput(term) {
        const digits = term.replace(/[^0-9]/g, "");
        if (/[a-zA-Z]/.test(term)) {
            return { isPhone: false, valid: true, digits: digits };
        }
        if (digits.length === 0) {
            return { isPhone: false, valid: true, digits: "" };
        }
        const reqLen = this.mobileDigits;
        let coreDigits = digits;
        // Strip a leading country dial code when the number is longer than required.
        if (this.countryDialCode && coreDigits.length > reqLen && coreDigits.startsWith(this.countryDialCode)) {
            coreDigits = coreDigits.substring(this.countryDialCode.length);
        }
        return {
            isPhone: true,
            valid: coreDigits.length === reqLen,
            digits: coreDigits,
        };
    }

    async doSearch() {
        const term = this.state.searchTerm.trim();
        if (!term) {
            this.state.error = "Enter mobile number";
            return;
        }
        const check = this._validatePhoneInput(term);
        if (check.isPhone && !check.valid) {
            this.state.error = this.invalidPhoneMessage;
            return;
        }
        this.state.searching = true;
        this.state.error = "";
        this.state.cardData = null;

        try {
            if (this.isLoyaltyMode) {
                // Full loyalty search - find loyalty card
                const res = await this.orm.call("pos.loyalty.card", "search_by_phone_or_card", [term]);
                if (res.error) {
                    this.state.error = res.error;
                    this.state.newPhone = term;
                } else {
                    this.state.cardData = res;
                }
            } else {
                // Customer Details mode - search res.partner by phone/mobile
                const res = await this.orm.call("pos.loyalty.card", "search_customer_by_phone", [term]);
                if (res.error) {
                    this.state.error = res.error;
                    this.state.newPhone = term;
                } else {
                    this.state.cardData = res;
                }
            }
        } catch (e) {
            console.error("LOYALTY: Search error:", e);
            this.state.error = "Search failed";
            this.state.newPhone = term;
        }
        this.state.searching = false;
    }

    onInput(ev) {
        let value = ev.target.value;
        // For a purely-numeric entry (a phone), keep digits only and block typing
        // past the configured length (+ optional country dial code). Entries that
        // contain letters are treated as card numbers and left untouched.
        if (value && !/[a-zA-Z]/.test(value)) {
            // Country code is shown as a fixed prefix, so a numeric (mobile) entry is
            // hard-capped at exactly the configured length — no more can be typed.
            const cap = this.mobileDigits;
            value = value.replace(/[^0-9]/g, "").slice(0, cap);
            if (ev.target.value !== value) {
                ev.target.value = value;
            }
        }
        this.state.searchTerm = value;
        const term = value.trim();
        if (!term) {
            this.state.error = "";
            return;
        }
        const check = this._validatePhoneInput(term);
        if (check.isPhone && !check.valid) {
            this.state.error = this.invalidPhoneMessage;
        } else {
            this.state.error = "";
        }
    }

    onKeyup(ev) {
        if (ev.key === "Enter") {
            this.doSearch();
        }
    }

    onNameInput(ev) { this.state.newName = ev.target.value; }
    onPhoneInput(ev) {
        // Only digits, capped to the configured length. The country dial code is
        // shown as a fixed prefix, so this field holds just the local number.
        let value = (ev.target.value || "").replace(/[^0-9]/g, "").slice(0, this.mobileDigits);
        if (ev.target.value !== value) {
            ev.target.value = value;
        }
        this.state.newPhone = value;
    }
    onEmailInput(ev) { this.state.newEmail = ev.target.value; }

    showCreate() {
        this.state.mode = "create";
        this.state.error = "";
        // Carry the number the user already typed into the New Card form so
        // they don't have to type it again. Prefer the core digits (dial code
        // stripped); fall back to the raw search term.
        if (!this.state.newPhone) {
            const term = this.state.searchTerm.trim();
            if (term) {
                const check = this._validatePhoneInput(term);
                this.state.newPhone = check.digits || term;
            }
        }
    }

    backToSearch() {
        this.state.mode = "search";
        this.state.error = "";
    }

    async doCreate() {
        if (!this.state.newName.trim() || !this.state.newPhone.trim()) {
            this.state.error = "Name and mobile number are required";
            return;
        }
        // Block creation until the mobile number has exactly the configured digits.
        if (!this.isNewPhoneValid) {
            this.state.error = this.invalidPhoneMessage;
            return;
        }
        this.state.creating = true;
        this.state.error = "";

        try {
            if (this.isLoyaltyMode) {
                // Create loyalty card + partner
                const res = await this.orm.call("pos.loyalty.card", "create_new_card", [
                    this.state.newName.trim(),
                    this.state.newPhone.trim(),
                    this.state.newEmail.trim() || false,
                ]);
                if (res.error) {
                    this.state.error = res.error;
                } else {
                    this.notification.add("Card created: " + res.card_number, { type: "success" });
                    if (this.props.getPayload) {
                        this.props.getPayload(res);
                    }
                    this.props.close();
                }
            } else {
                // Customer Details mode: Create partner ONLY (no loyalty card)
                const res = await this.orm.call("pos.loyalty.card", "create_customer_only", [
                    this.state.newName.trim(),
                    this.state.newPhone.trim(),
                    this.state.newEmail.trim() || false,
                ]);
                if (res.error) {
                    this.state.error = res.error;
                } else {
                    this.notification.add("Customer created: " + res.name, { type: "success" });
                    if (this.props.getPayload) {
                        this.props.getPayload(res);
                    }
                    this.props.close();
                }
            }
        } catch (e) {
            console.error("LOYALTY: Create error:", e);
            this.state.error = "Failed to create";
        }
        this.state.creating = false;
    }

    selectCard() {
        if (this.props.getPayload) {
            this.props.getPayload(this.state.cardData);
        }
        this.props.close();
    }

    skip() {
        if (this.props.getPayload) {
            this.props.getPayload(null);
        }
        this.props.close();
    }
}


/**
 * Redeem Points Popup
 */
export class RedeemPopup extends Component {
    static template = "pos_loyalty_card.RedeemPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
        orderTotal: { type: Number, optional: true },
        cardData: { optional: true },
        applyDiscount: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.pos = usePos();

        let currentOrderTotal = this.props.orderTotal || 0;
        const cd = this.props.cardData;
        const maxPts = cd ? this._maxPoints(cd, currentOrderTotal) : 0;

        // Restore verify checkbox + entered points from before a browser refresh.
        let restored = {};
        try {
            restored = JSON.parse(window.localStorage.getItem("pos_loyalty_redeem_state") || "{}") || {};
        } catch (e) {
            restored = {};
        }

        this.state = useState({
            searchTerm: cd ? cd.phone || cd.card_number || "" : "",
            searching: false,
            cardData: cd || null,
            verified: !!restored.verified,
            points: restored.points != null
                ? Math.min(restored.points, maxPts)
                : Math.min(cd ? cd.min_redeem_points || 0 : 0, maxPts),
            maxPoints: maxPts,
            processing: false,
            error: "",
            currentOrderTotal: currentOrderTotal,
        });
    }

    _saveState() {
        try {
            window.localStorage.setItem("pos_loyalty_redeem_state", JSON.stringify({
                verified: this.state.verified,
                points: this.state.points,
            }));
        } catch (e) {
            /* noop */
        }
    }

    /**
     * Max points that can be redeemed on this order:
     *   min( points on the card, orderTotal x pointsPerCurrency x maxRedeem% )
     * so the configured "Max Redeem %" is respected.
     */
    _maxPoints(cd, orderTotal) {
        if (!cd) return 0;
        const ppc = cd.points_per_currency || 10;
        const pct = (cd.max_redeem_percent != null ? cd.max_redeem_percent : 100) / 100;
        const byOrder = (orderTotal || 0) * ppc * pct;
        return Math.max(0, Math.floor(Math.min(cd.total_points || 0, byOrder)));
    }

    get orderTotal() { return this.state.currentOrderTotal || this.props.orderTotal || 0; }
    get ppc() { return this.state.cardData ? (this.state.cardData.points_per_currency || 10) : 10; }
    get maxRedeemValue() { return this.ppc > 0 ? this.state.maxPoints / this.ppc : 0; }
    get cardTotalPoints() { return this.state.cardData ? (this.state.cardData.total_points || 0) : 0; }
    get isCapped() { return !!this.state.cardData && this.state.maxPoints < this.cardTotalPoints; }
    get minRedeemPoints() { return this.state.cardData ? (this.state.cardData.min_redeem_points || 0) : 0; }
    // Order too small: the max we can redeem is below the required minimum.
    get belowMinimum() { return !!this.state.cardData && this.state.maxPoints < this.minRedeemPoints; }
    
    get discount() {
        const ppc = this.state.cardData ? this.state.cardData.points_per_currency || 10 : 10;
        return ppc > 0 ? this.state.points / ppc : 0;
    }
    
    get finalAmount() { return Math.max(0, this.orderTotal - this.discount); }
    
    get canRedeem() {
        const cd = this.state.cardData;
        if (!cd || !cd.can_redeem || !this.state.verified) return false;
        if (this.state.points < (cd.min_redeem_points || 0)) return false;
        if (this.state.points > this.state.maxPoints) return false;
        if (this.state.points <= 0) return false;
        return true;
    }

    async doSearch() {
        const term = this.state.searchTerm.trim();
        if (!term) {
            this.state.error = "Enter phone or card";
            return;
        }
        this.state.searching = true;
        this.state.error = "";
        this.state.cardData = null;

        try {
            const res = await this.orm.call("pos.loyalty.card", "search_by_phone_or_card", [term]);
            if (res.error) {
                this.state.error = res.error;
            } else {
                this.state.cardData = res;
                const maxPts = this._maxPoints(res, this.orderTotal);
                this.state.maxPoints = maxPts;
                this.state.points = Math.min(res.min_redeem_points || 0, maxPts);
            }
        } catch (e) {
            this.state.error = "Search failed";
        }
        this.state.searching = false;
    }

    onInput(ev) { this.state.searchTerm = ev.target.value; }
    onKeyup(ev) { if (ev.key === "Enter") this.doSearch(); }
    
    onVerify(ev) {
        this.state.verified = ev.target.checked;
        if (this.state.cardData) {
            this.state.maxPoints = this._maxPoints(this.state.cardData, this.orderTotal);
        }
        this._saveState();
    }

    onPoints(ev) {
        let p = parseFloat(ev.target.value) || 0;
        if (p < 0) p = 0;
        if (p > this.state.maxPoints) {
            this.notification.add(
                "You can redeem at most " + Math.round(this.state.maxPoints) +
                " points (₹" + this.maxRedeemValue.toFixed(2) + ") on this order.",
                { type: "warning" }
            );
            p = this.state.maxPoints;
            ev.target.value = p;
        }
        this.state.points = p;
        this._saveState();
    }

    setMin() {
        const cd = this.state.cardData;
        this.state.points = Math.min(cd ? cd.min_redeem_points || 0 : 0, this.state.maxPoints);
        this._saveState();
    }

    setMax() { this.state.points = this.state.maxPoints; this._saveState(); }

    async confirm() {
        if (!this.canRedeem) return;
        this.state.processing = true;
        this.state.error = "";

        try {
            const res = await this.orm.call("pos.loyalty.card", "redeem_points", [
                this.state.cardData.id,
                this.state.points,
                this.orderTotal,
            ]);
            if (res.error) {
                this.state.error = res.error;
            } else {
                this.notification.add(
                    "Redeemed " + res.points_redeemed + " pts = ₹" + res.discount_value.toFixed(2),
                    { type: "success" }
                );
                
                if (this.props.applyDiscount) {
                    this.props.applyDiscount(res.discount_value, res.points_redeemed);
                }
                
                if (this.props.getPayload) {
                    this.props.getPayload({
                        ...res,
                        card_id: this.state.cardData.id,
                    });
                }
                this.props.close();
            }
        } catch (e) {
            console.error("LOYALTY: Redemption error:", e);
            this.state.error = "Redemption failed";
        }
        this.state.processing = false;
    }

    cancel() { this.props.close(); }
}


/**
 * Patch PaymentScreen
 */
patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.loyaltyCard = useState({ data: null });
        this.customerInfo = useState({ data: null });
        this.redemption = useState({ data: null, applied: false });
        this.loyaltySkip = useState({ value: false });
        // Redeemed points that will be credited back on THIS refund order.
        this.returnRedeem = useState({ points: 0, value: 0 });
        this._popupShown = false;
        this.loyaltyOrm = useService("orm");
        this.loyaltyNotification = useService("notification");

        onMounted(async () => {
            // RESET PAYMENT LINES: Clear all payment lines when entering Payment screen
            this._resetPaymentLines();
            // If this is a refund of an order that redeemed points, preview how many
            // points will be credited back (for display in the payment summary).
            this._loadReturnRedeemPreview();

            // FIX: Clean up orphaned loyalty discount lines before showing popup.
            this._cleanOrphanedDiscountLines();

            // If a loyalty card is already linked on this order (e.g. after a
            // browser refresh), restore it instead of re-asking for the number.
            const restored = await this._restoreLoyaltyCard();

            // Reopen whichever loyalty popup was open before the refresh.
            const flag = this._getPopupFlag();
            if (flag === "redeem") {
                setTimeout(() => this.openRedeemPopup(), 300);
            } else if (flag === "loyalty") {
                this._popupShown = false;
                setTimeout(() => this._showLoyaltyPopup(), 300);
            } else if (!restored) {
                setTimeout(() => this._showLoyaltyPopup(), 300);
            }
        });
    },

    async _restoreLoyaltyCard() {
        const order = this.currentOrder;
        const cardId = order && order.loyalty_card_id;
        if (!cardId) {
            return false;
        }
        try {
            const res = await this.loyaltyOrm.call(
                "pos.loyalty.card", "get_card_pos_data", [cardId]
            );
            if (res && !res.error) {
                this.loyaltyCard.data = res;
                this.customerInfo.data = {
                    name: res.name || '',
                    phone: res.phone || '',
                    partner_id: res.partner_id || false,
                    has_loyalty_card: true,
                };
                this.loyaltySkip.value = false;
                this._popupShown = true; // don't auto-open, card already linked
                return true;
            }
        } catch (e) {
            // fall back to the popup
        }
        return false;
    },

    // --- Remember which loyalty popup is open, so it reopens after a refresh ---
    _popupFlagKey() {
        const o = this.currentOrder;
        const uid = o ? (o.uuid || o.uid || o.id || "x") : "x";
        return "pos_loyalty_popup_" + uid;
    },
    _setPopupFlag(v) { try { window.localStorage.setItem(this._popupFlagKey(), v); } catch (e) { /* noop */ } },
    _getPopupFlag() { try { return window.localStorage.getItem(this._popupFlagKey()) || ""; } catch (e) { return ""; } },
    _clearPopupFlag() { try { window.localStorage.removeItem(this._popupFlagKey()); } catch (e) { /* noop */ } },

    /**
     * Check if loyalty cards are enabled for this POS config
     */
    get loyaltyEnabled() {
        const c = this.pos.config;
        if (c.loyalty_active !== undefined) return c.loyalty_active !== false;
        return c.enable_loyalty_cards !== false;
    },

    /**
     * Reset/clear all payment lines on the current order
     * Called when Payment screen is opened to ensure no pre-selected payment method
     */
    _resetPaymentLines() {
        try {
            const order = this.currentOrder;
            if (!order) {
                console.log("PAYMENT_RESET: No current order");
                return;
            }

            // Get payment lines - try different accessors for Odoo 19 compatibility
            let paymentLines = [];
            
            if (order.payment_ids && order.payment_ids.length > 0) {
                paymentLines = [...order.payment_ids];
            } else if (order.paymentlines && order.paymentlines.length > 0) {
                paymentLines = [...order.paymentlines];
            } else if (typeof order.get_paymentlines === "function") {
                paymentLines = [...order.get_paymentlines()];
            }

            if (paymentLines.length === 0) {
                console.log("PAYMENT_RESET: No payment lines to clear");
                return;
            }

            console.log("PAYMENT_RESET: Clearing", paymentLines.length, "payment line(s)");

            // Remove each payment line
            for (const line of paymentLines) {
                try {
                    if (typeof line.delete === "function") {
                        line.delete();
                    } else if (typeof order.remove_paymentline === "function") {
                        order.remove_paymentline(line);
                    } else if (typeof order.removePaymentline === "function") {
                        order.removePaymentline(line);
                    } else if (this.pos.data && this.pos.data.models["pos.payment"]) {
                        this.pos.data.models["pos.payment"].delete(line);
                    }
                } catch (e) {
                    console.warn("PAYMENT_RESET: Could not remove payment line:", e);
                }
            }

            // Clear selected payment method state if exists
            if (this.selectedPaymentMethod !== undefined) {
                this.selectedPaymentMethod = null;
            }
            
            // Also clear payment method on order if stored there
            if (order.selected_paymentline !== undefined) {
                order.selected_paymentline = null;
            }

            console.log("PAYMENT_RESET: Payment lines cleared successfully");
        } catch (e) {
            console.error("PAYMENT_RESET: Error clearing payment lines:", e);
        }
    },

    _showLoyaltyPopup() {
        if (!this.loyaltyEnabled) return;
        if (this._popupShown) return;
        this._popupShown = true;

        const self = this;
        const loyaltyMode = this.loyaltyEnabled;
        this._setPopupFlag("loyalty");
        this.dialog.add(LoyaltyCardPopup, {
            loyaltyMode: loyaltyMode,
            mobileDigits: this.pos.config.loyalty_mobile_number_length,
            countryDialCode: this.pos.config.loyalty_country_dial_code,
            getPayload: async function (card) {
                if (card) {
                    self.loyaltySkip.value = false;
                    // Always store card/customer data for validateOrder to link partner
                    self.loyaltyCard.data = card;
                    // Store customer info for display in payment screen
                    self.customerInfo.data = {
                        name: card.name || '',
                        phone: card.phone || '',
                        partner_id: card.partner_id || false,
                        has_loyalty_card: loyaltyMode || card.has_loyalty_card || false,
                    };
                    await self._linkCardToOrder(card);
                } else {
                    // Cashier skipped the loyalty card -> flag it (red note shows).
                    self.loyaltySkip.value = true;
                }
            },
        }, { onClose: () => self._clearPopupFlag() });
    },

    async _linkCardToOrder(card) {
        if (!card || !this.currentOrder) return;
        
        // Link loyalty card ID only if it exists (not in customer-only mode)
        if (card.id) {
            this.currentOrder.loyalty_card_id = card.id;
        }

        // Store card display info for receipt rendering (only if loyalty mode)
        if (this.loyaltyEnabled && card.card_number) {
            this.currentOrder._loyalty_card_number = card.card_number || '';
            this.currentOrder._loyalty_member_name = card.name || '';
            this.currentOrder._loyalty_total_points_before = card.total_points || 0;
            this.currentOrder._loyalty_points_per_currency = card.points_per_currency || 10;
        }
        
        // Always link partner to the order (for both loyalty and customer-only modes)
        if (card.partner_id) {
            try {
                let partner = this.pos.models["res.partner"].get(card.partner_id);
                
                // Partner not in POS cache (newly created on server) - load it
                if (!partner) {
                    console.log("LOYALTY: Partner ID", card.partner_id, "not in POS cache, loading from server...");
                    try {
                        await this.pos.data.read("res.partner", [card.partner_id]);
                        partner = this.pos.models["res.partner"].get(card.partner_id);
                        console.log("LOYALTY: Partner loaded into cache:", partner ? partner.name : "FAILED");
                    } catch (loadErr) {
                        console.warn("LOYALTY: Could not load partner from server:", loadErr);
                    }
                }
                
                if (partner) {
                    this.currentOrder.setPartner(partner);
                    console.log("LOYALTY: Partner set on order:", partner.name, "(ID:", card.partner_id, ")");
                } else {
                    console.warn("LOYALTY: Partner ID", card.partner_id, "could not be resolved");
                }
            } catch (e) {
                console.log("LOYALTY: Could not set partner:", e);
            }
        }
    },

    _getOrderTotal() {
        try {
            const order = this.currentOrder;
            if (!order) return 0;
            
            if (typeof order.get_total_with_tax === "function") {
                return order.get_total_with_tax();
            }
            if (typeof order.getTotalDue === "function") {
                return order.getTotalDue();
            }
            if (order.totalDue !== undefined) {
                return order.totalDue;
            }
            
            return 0;
        } catch (e) {
            console.error("LOYALTY: Error getting total:", e);
            return 0;
        }
    },

    /**
     * Find a product to use for discount line
     * Returns the product.product record (which proxies to product_tmpl_id for taxes_id)
     */
    _findDiscountProduct() {
        try {
            // Get products from the data models
            const allProducts = this.pos.models["product.product"]?.getAll() || [];
            
            console.log("LOYALTY: Total products available:", allProducts.length);
            
            // PRIORITY 1: Find our dedicated "Loyalty Points Redemption" product (exact match)
            let product = allProducts.find(p => 
                p.display_name === "Loyalty Points Redemption"
            );
            if (product) {
                console.log("LOYALTY: Found dedicated loyalty product:", product.display_name);
                return product;
            }

            // PRIORITY 2: Find by name containing "loyalty" (for custom-named products)
            product = allProducts.find(p => 
                p.display_name && 
                p.display_name.toLowerCase().includes("loyalty")
            );
            if (product) {
                console.log("LOYALTY: Found loyalty product:", product.display_name);
                return product;
            }

            // PRIORITY 3: Find by name containing "discount"
            product = allProducts.find(p => 
                p.display_name && 
                p.display_name.toLowerCase().includes("discount")
            );
            if (product) {
                console.log("LOYALTY: Found discount product:", product.display_name);
                return product;
            }
            
            // PRIORITY 4: Find any service product
            product = allProducts.find(p => p.type === "service" && p.available_in_pos);
            if (product) {
                console.log("LOYALTY: Using service product:", product.display_name);
                return product;
            }
            
            // PRIORITY 5: Just use any available product
            product = allProducts.find(p => p.available_in_pos);
            if (product) {
                console.log("LOYALTY: Using first available product:", product.display_name);
                return product;
            }
            
            console.error("LOYALTY: No product found!");
            return null;
        } catch (e) {
            console.error("LOYALTY: Error finding product:", e);
            return null;
        }
    },

    /**
     * Apply discount using Odoo 19 POS addLineToCurrentOrder
     * Key: Must pass product_tmpl_id (product template), not product_id
     */
    async _applyLoyaltyDiscount(discountAmount, pointsRedeemed) {
        if (!discountAmount || discountAmount <= 0) return false;

        const order = this.currentOrder;
        if (!order) {
            console.error("LOYALTY: No current order");
            return false;
        }

        console.log("LOYALTY: Applying discount:", discountAmount);

        // First remove any existing discount
        this._removeLoyaltyDiscount();
        
        const product = this._findDiscountProduct();
        if (!product) {
            this.loyaltyNotification.add("No product available for discount", { type: "danger" });
            return false;
        }

        console.log("LOYALTY: Product found:", product.display_name);
        console.log("LOYALTY: Product ID:", product.id);
        console.log("LOYALTY: Product template ID:", product.product_tmpl_id?.id);

        try {
            // Get the product template - this is what addLineToCurrentOrder expects
            const productTemplate = product.product_tmpl_id;
            
            if (!productTemplate) {
                console.error("LOYALTY: No product template found");
                this.loyaltyNotification.add("Product configuration error", { type: "danger" });
                return false;
            }

            console.log("LOYALTY: Using template:", productTemplate.display_name || productTemplate.name);
            console.log("LOYALTY: Template taxes_id:", productTemplate.taxes_id);

            // Use addLineToCurrentOrder with product_tmpl_id and negative price_unit
            // configure=false to skip popups/configurators
            const line = await this.pos.addLineToCurrentOrder(
                {
                    product_tmpl_id: productTemplate,
                    price_unit: -discountAmount,
                    qty: 1,
                },
                { merge: false },
                false  // configure = false to skip dialogs
            );

            if (line) {
                // Mark as loyalty discount line — JS flag for current session
                line.loyalty_discount_line = true;
                line.loyalty_points_redeemed = pointsRedeemed;
                // PERSISTENT MARKER: Set customer_note so this line can be
                // identified even after a backend round-trip (DB save/reload).
                line.customer_note = "LOYALTY_DISCOUNT";

                // RECEIPT FIX: Override full_product_name so the receipt shows
                // "Loyalty Points Redemption" instead of the carrier product name.
                line.full_product_name = "Loyalty Points Redemption";
                
                this.redemption.applied = true;
                console.log("LOYALTY: Discount line added successfully!");
                console.log("LOYALTY: New order total:", this._getOrderTotal());
                return true;
            } else {
                console.error("LOYALTY: addLineToCurrentOrder returned no line");
                return false;
            }

        } catch (e) {
            console.error("LOYALTY: Error applying discount:", e);
            this.loyaltyNotification.add("Failed to apply discount: " + e.message, { type: "danger" });
            return false;
        }
    },

    /**
     * Clean orphaned loyalty discount lines from the order.
     * Detects lines by persistent customer_note = "LOYALTY_DISCOUNT" marker.
     * This works even after backend round-trips where JS-only flags are lost.
     */
    _cleanOrphanedDiscountLines() {
        const order = this.currentOrder;
        if (!order) return;

        try {
            const lines = order.lines || [];
            if (lines.length === 0) return;

            const linesToRemove = [];

            for (const line of lines) {
                // Check persistent marker (survives backend round-trip)
                const note = line.customer_note || "";
                if (note === "LOYALTY_DISCOUNT") {
                    console.log("LOYALTY_CLEANUP: Found orphaned discount line via customer_note");
                    linesToRemove.push(line);
                    continue;
                }
                // Also check JS-only flag (current session, not yet saved)
                if (line.loyalty_discount_line) {
                    console.log("LOYALTY_CLEANUP: Found discount line via JS flag");
                    linesToRemove.push(line);
                    continue;
                }
            }

            if (linesToRemove.length > 0) {
                console.log("LOYALTY_CLEANUP: Removing", linesToRemove.length, "orphaned discount line(s)");
                for (const line of linesToRemove) {
                    try {
                        if (typeof line.delete === "function") {
                            line.delete();
                        } else if (this.pos.data && this.pos.data.models["pos.order.line"]) {
                            this.pos.data.models["pos.order.line"].delete(line);
                        }
                    } catch (e) {
                        console.warn("LOYALTY_CLEANUP: Could not remove line:", e);
                    }
                }
            }
        } catch (e) {
            console.error("LOYALTY_CLEANUP: Error:", e);
        }
    },

    _removeLoyaltyDiscount() {
        const order = this.currentOrder;
        if (!order) return;

        try {
            const lines = order.lines || [];
            const linesToRemove = [];
            
            for (const line of lines) {
                // Match by JS flag (current session)
                if (line.loyalty_discount_line) {
                    linesToRemove.push(line);
                    continue;
                }
                // Match by persistent customer_note marker (after backend round-trip)
                const note = line.customer_note || "";
                if (note === "LOYALTY_DISCOUNT") {
                    linesToRemove.push(line);
                    continue;
                }
            }
            
            for (const line of linesToRemove) {
                if (typeof line.delete === "function") {
                    line.delete();
                } else if (this.pos.data && this.pos.data.models["pos.order.line"]) {
                    this.pos.data.models["pos.order.line"].delete(line);
                }
            }
            
            this.redemption.applied = false;
            console.log("LOYALTY: Removed", linesToRemove.length, "discount lines");
        } catch (e) {
            console.error("LOYALTY: Error removing discount:", e);
        }
    },

    get loyaltyCardInfo() { return this.loyaltyEnabled ? this.loyaltyCard.data : null; },
    get loyaltyWasSkipped() { return this.loyaltyEnabled && this.loyaltySkip.value && !this.loyaltyCard.data; },
    get customerDetails() { return this.customerInfo.data; },
    get hasRedemption() { return this.loyaltyEnabled && this.redemption.data && this.redemption.data.discount_value > 0; },
    get redemptionInfo() { return this.redemption.data; },
    get redemptionApplied() { return this.redemption.applied; },

    // --- Refund / return: redeemed-points credit-back display ---
    get isReturnOrder() {
        const order = this.currentOrder;
        if (!order) return false;
        try {
            // Any orderline that refunds an original line marks this as a return.
            for (const line of order.lines || []) {
                if (line.refunded_orderline_id) return true;
            }
        } catch (e) { /* noop */ }
        return this._getOrderTotal() < 0;
    },
    get hasReturnRedeem() {
        return this.loyaltyEnabled && this.returnRedeem.points > 0;
    },

    // Find the original order id for this refund (from the refunded orderline link).
    _getRefundOriginalOrderId() {
        const order = this.currentOrder;
        if (!order) return null;
        try {
            for (const line of order.lines || []) {
                const rl = line.refunded_orderline_id;
                if (rl && rl.order_id) {
                    return rl.order_id.id || rl.order_id;
                }
            }
        } catch (e) { /* noop */ }
        return null;
    },

    async _loadReturnRedeemPreview() {
        this.returnRedeem.points = 0;
        this.returnRedeem.value = 0;
        if (!this.loyaltyEnabled || !this.isReturnOrder) return;
        const origId = this._getRefundOriginalOrderId();
        if (!origId) return;
        const refundAmount = Math.abs(this._getOrderTotal());
        try {
            const res = await this.loyaltyOrm.call(
                "pos.order", "get_return_redeem_preview", [origId, refundAmount]
            );
            if (res && res.points > 0) {
                this.returnRedeem.points = res.points;
                this.returnRedeem.value = res.value;
            }
        } catch (e) {
            // Non-blocking: just don't show the preview line.
        }
    },

    // NEW: Get original order total (before discount was applied)
    get originalTotal() {
        const order = this.currentOrder;
        if (!order) return 0;
        
        // If redemption is applied, add back the discount to get original
        if (this.redemption.data && this.redemption.data.discount_value > 0) {
            return this._getOrderTotal() + this.redemption.data.discount_value;
        }
        return this._getOrderTotal();
    },
    
    // NEW: Get remaining amount to pay (after loyalty discount)
    get remainingAmount() {
        return this._getOrderTotal();
    },

    openLoyaltyPopup() {
        if (!this.loyaltyEnabled) return;
        const self = this;
        this._setPopupFlag("loyalty");
        this.dialog.add(LoyaltyCardPopup, {
            loyaltyMode: true,
            mobileDigits: this.pos.config.loyalty_mobile_number_length,
            countryDialCode: this.pos.config.loyalty_country_dial_code,
            getPayload: async function (card) {
                if (card) {
                    self.loyaltySkip.value = false;
                    self.loyaltyCard.data = card;
                    self.customerInfo.data = {
                        name: card.name || '',
                        phone: card.phone || '',
                        partner_id: card.partner_id || false,
                        has_loyalty_card: true,
                    };
                    await self._linkCardToOrder(card);
                } else {
                    self.loyaltySkip.value = true;
                }
            },
        }, { onClose: () => self._clearPopupFlag() });
    },

    async openRedeemPopup() {
        if (!this.loyaltyEnabled) return;
        const self = this;
        const orderTotal = this._getOrderTotal();
        console.log("LOYALTY: Opening redeem, total:", orderTotal);
        
        // Check if we have a loyalty card selected
        const cardData = this.loyaltyCard.data;
        if (!cardData || !cardData.id) {
            // No card selected - open popup normally to allow search
            this._setPopupFlag("redeem");
            this.dialog.add(RedeemPopup, {
                orderTotal: orderTotal,
                cardData: null,
                applyDiscount: function(amount, points) {
                    self._applyLoyaltyDiscount(amount, points);
                },
                getPayload: function (res) {
                    if (res) self.redemption.data = res;
                },
            }, { onClose: () => { self._clearPopupFlag(); self._clearRedeemState(); } });
            return;
        }

        // === ORDER TOO SMALL: show red message and do NOT open the popup ===
        {
            const ppc = cardData.points_per_currency || 10;
            const pct = (cardData.max_redeem_percent != null ? cardData.max_redeem_percent : 100) / 100;
            const maxPts = Math.floor(Math.min(cardData.total_points || 0, orderTotal * ppc * pct));
            const minPts = cardData.min_redeem_points || 0;
            if (maxPts < minPts) {
                this.loyaltyNotification.add(
                    "This order is too small to redeem. Minimum " + Math.round(minPts) +
                    " pts (₹" + (minPts / ppc).toFixed(2) + ") required, but this order allows only " +
                    Math.round(maxPts) + " pts (₹" + (maxPts / ppc).toFixed(2) + ").",
                    { type: "danger", sticky: true }
                );
                return;
            }
        }

        // === CHECK 24-HOUR ELIGIBILITY BEFORE OPENING POPUP ===
        try {
            console.log("LOYALTY: Checking redemption eligibility for card ID:", cardData.id);
            const eligibility = await this.loyaltyOrm.call(
                "pos.loyalty.card",
                "check_redemption_eligibility",
                [cardData.id]
            );
            
            console.log("LOYALTY: Eligibility check result:", eligibility);
            
            if (!eligibility.eligible) {
                // BLOCKED: Show error notification and do NOT open popup
                this.loyaltyNotification.add(
                    eligibility.reason || "Redemption not allowed at this time.",
                    { 
                        type: "danger",
                        sticky: true,
                    }
                );
                console.log("LOYALTY: Redemption blocked - not opening popup");
                return;
            }
        } catch (e) {
            console.error("LOYALTY: Error checking eligibility:", e);
            // On error, still allow opening popup (backend will re-validate)
        }
        
        // ELIGIBLE: Open Redeem Points popup normally
        this._setPopupFlag("redeem");
        this.dialog.add(RedeemPopup, {
            orderTotal: orderTotal,
            cardData: cardData,
            applyDiscount: function(amount, points) {
                self._applyLoyaltyDiscount(amount, points);
            },
            getPayload: function (res) {
                if (res) self.redemption.data = res;
            },
        }, { onClose: () => { self._clearPopupFlag(); self._clearRedeemState(); } });
    },

    _clearRedeemState() {
        try { window.localStorage.removeItem("pos_loyalty_redeem_state"); } catch (e) { /* noop */ }
    },

    removeRedemption() {
        this._removeLoyaltyDiscount();
        this.redemption.data = null;
        this.redemption.applied = false;
        this.loyaltyNotification.add("Redemption removed", { type: "info" });
    },

    removeCustomerDetails() {
        // Remove customer details from the payment screen
        this.customerInfo.data = null;
        this.loyaltyCard.data = null;
        // Also unlink partner from order
        try {
            const order = this.currentOrder;
            if (order) {
                order.loyalty_card_id = false;
                if (typeof order.setPartner === "function") {
                    order.setPartner(false);
                }
            }
        } catch (e) {
            console.warn("LOYALTY: Could not unlink partner:", e);
        }
        this.loyaltyNotification.add("Customer details removed", { type: "info" });
    },

    async validateOrder(isForceValidate) {
        const cardData = this.loyaltyCard.data;
        const card = this.loyaltyEnabled ? cardData : null;
        const redemptionData = this.loyaltyEnabled ? this.redemption.data : null;
        const orderToValidate = this.currentOrder;
        
        // Store order name BEFORE validation (order might change after)
        const orderName = orderToValidate?.name || orderToValidate?.pos_reference || 'POS Order';
        
        // When loyalty OFF but card data exists, still link customer for WhatsApp receipt
        if (!this.loyaltyEnabled && cardData && orderToValidate) {
            try {
                if (cardData.id) {
                    orderToValidate.loyalty_card_id = cardData.id;
                }
                if (cardData.partner_id) {
                    try {
                        let partner = this.pos.models["res.partner"].get(cardData.partner_id);
                        if (!partner) {
                            try {
                                await this.pos.data.read("res.partner", [cardData.partner_id]);
                                partner = this.pos.models["res.partner"].get(cardData.partner_id);
                            } catch (loadErr) {
                                console.warn("LOYALTY: Could not load partner in validateOrder:", loadErr);
                            }
                        }
                        if (partner) {
                            orderToValidate.setPartner(partner);
                        }
                    } catch (e) {
                        console.log("LOYALTY: Could not set partner (loyalty OFF):", e);
                    }
                }
            } catch (e) {
                console.error("LOYALTY: Error linking customer data (non-blocking):", e);
            }
        }
        
        if (card && orderToValidate) {
            try {
                orderToValidate.loyalty_card_id = card.id;
                
                // Store redemption info on order for backend processing
                if (redemptionData && redemptionData.points_redeemed > 0) {
                    orderToValidate.loyalty_points_redeemed = redemptionData.points_redeemed;
                    orderToValidate.loyalty_discount_amount = redemptionData.discount_value;
                }

                // =====================================================
                // RECEIPT DATA: Compute loyalty receipt info BEFORE
                // super.validateOrder() which triggers receipt display
                // =====================================================
                try {
                    const pointsRedeemed = (redemptionData && redemptionData.points_redeemed > 0)
                        ? redemptionData.points_redeemed : 0;

                    let pointsEarned = 0;
                    try {
                        const ruleData = await this.loyaltyOrm.call(
                            "pos.loyalty.card",
                            "get_receipt_data",
                            [card.id, this._getOrderTotal(), pointsRedeemed]
                        );
                        if (ruleData && !ruleData.error) {
                            pointsEarned = ruleData.points_earned || 0;
                            const pointBalance = ruleData.point_balance || 0;

                            orderToValidate._loyalty_receipt_data = {
                                card_number: ruleData.card_number || card.card_number || '',
                                member_name: ruleData.member_name || card.name || '',
                                points_earned: pointsEarned,
                                points_redeemed: pointsRedeemed,
                                point_balance: pointBalance,
                            };
                            console.log("LOYALTY RECEIPT: Data stored:", orderToValidate._loyalty_receipt_data);
                        }
                    } catch (rpcErr) {
                        console.warn("LOYALTY RECEIPT: Could not fetch receipt data from server, using estimates:", rpcErr);
                        const totalPtsBefore = card.total_points || 0;
                        const estimatedBalance = totalPtsBefore - (redemptionData ? redemptionData.points_redeemed : 0);

                        orderToValidate._loyalty_receipt_data = {
                            card_number: card.card_number || '',
                            member_name: card.name || '',
                            points_earned: 0,
                            points_redeemed: redemptionData ? redemptionData.points_redeemed : 0,
                            point_balance: Math.max(0, estimatedBalance),
                        };
                    }
                } catch (e) {
                    console.error("LOYALTY RECEIPT: Error preparing receipt data (non-blocking):", e);
                }
            } catch (e) {
                console.error("LOYALTY: Error preparing order data (non-blocking):", e);
            }
        }
        
        // Call parent validateOrder - THIS MUST NEVER BE BLOCKED BY LOYALTY ERRORS
        let result;
        try {
            result = await super.validateOrder(...arguments);
        } catch (e) {
            // If the error is loyalty-related, try again without loyalty data
            const errStr = String(e.message || e || '');
            if (errStr.includes('loyalty') || errStr.includes('Loyalty') || errStr.includes('loyalty_card_id')) {
                console.error("LOYALTY: Payment blocked by loyalty error, retrying without loyalty data:", e);
                try {
                    // Clear loyalty data from order and retry
                    if (orderToValidate) {
                        orderToValidate.loyalty_card_id = false;
                    }
                    result = await super.validateOrder(...arguments);
                    this.loyaltyNotification.add("Payment processed (loyalty linking skipped due to error)", { type: "warning" });
                } catch (retryErr) {
                    // Re-throw the original error if retry also fails
                    throw retryErr;
                }
            } else {
                throw e;
            }
        }
        
        // AFTER validation, confirm the redemption (actually deduct points and create history)
        if (redemptionData && redemptionData.points_redeemed > 0 && card) {
            try {
                console.log("LOYALTY: Confirming redemption after payment:", redemptionData.points_redeemed, "points for order:", orderName);
                
                const confirmResult = await this.loyaltyOrm.call("pos.loyalty.card", "confirm_redemption", [
                    card.id,
                    redemptionData.points_redeemed,
                    orderName,
                ]);
                
                if (confirmResult.error) {
                    console.error("LOYALTY: Redemption confirmation error:", confirmResult.error);
                } else {
                    console.log("LOYALTY: Redemption confirmed successfully - history created, points deducted");
                }
                
                // Clear redemption data after confirming
                this.redemption.data = null;
                this.redemption.applied = false;
            } catch (e) {
                console.error("LOYALTY: Error confirming redemption (non-blocking):", e);
                // Don't block the order, just log the error
            }
        }
        
        return result;
    },
});


/**
 * Patch PosOrder
 */
patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.loyalty_card_id = vals.loyalty_card_id || false;
        this.loyalty_points_redeemed = vals.loyalty_points_redeemed || 0;
        this.loyalty_discount_amount = vals.loyalty_discount_amount || 0;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(...arguments);
        // Only include loyalty_card_id if it's a valid positive integer
        if (this.loyalty_card_id && Number.isInteger(this.loyalty_card_id) && this.loyalty_card_id > 0) {
            data.loyalty_card_id = this.loyalty_card_id;
        }
        if (this.loyalty_points_redeemed) {
            data.loyalty_points_redeemed = this.loyalty_points_redeemed;
        }
        if (this.loyalty_discount_amount) {
            data.loyalty_discount_amount = this.loyalty_discount_amount;
        }
        return data;
    },
});
