/** @odoo-module */

import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

/**
 * Loyalty Card Search/Create Popup
 */
export class LoyaltyCardPopup extends Component {
    static template = "pos_loyalty_card.LoyaltyCardPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
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

    async doSearch() {
        const term = this.state.searchTerm.trim();
        if (!term) {
            this.state.error = "Enter mobile or card number";
            return;
        }
        this.state.searching = true;
        this.state.error = "";
        this.state.cardData = null;

        try {
            const res = await this.orm.call("pos.loyalty.card", "search_by_phone_or_card", [term]);
            if (res.error) {
                this.state.error = res.error;
                this.state.newPhone = term;
            } else {
                this.state.cardData = res;
            }
        } catch (e) {
            console.error("LOYALTY: Search error:", e);
            this.state.error = "Search failed";
            this.state.newPhone = term;
        }
        this.state.searching = false;
    }

    onInput(ev) {
        this.state.searchTerm = ev.target.value;
        this.state.error = "";
    }

    onKeyup(ev) {
        if (ev.key === "Enter") {
            this.doSearch();
        }
    }

    onNameInput(ev) { this.state.newName = ev.target.value; }
    onPhoneInput(ev) { this.state.newPhone = ev.target.value; }
    onEmailInput(ev) { this.state.newEmail = ev.target.value; }

    showCreate() {
        this.state.mode = "create";
        this.state.error = "";
    }

    backToSearch() {
        this.state.mode = "search";
        this.state.error = "";
    }

    async doCreate() {
        if (!this.state.newName.trim() || !this.state.newPhone.trim()) {
            this.state.error = "Name and phone required";
            return;
        }
        this.state.creating = true;
        this.state.error = "";

        try {
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
 * Redeem Points Popup - Shows redemption calculation
 */
export class RedeemPopup extends Component {
    static template = "pos_loyalty_card.RedeemPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
        orderTotal: { type: Number, optional: true },
        cardData: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        const cd = this.props.cardData;
        const orderTotal = this.props.orderTotal || 0;
        const currencyPerPoint = cd ? (cd.currency_per_point || 0.10) : 0.10;
        const maxRedeemPercent = cd ? (cd.max_redeem_percent || 50) : 50;
        
        // Calculate max redeemable
        const maxByPercent = orderTotal * (maxRedeemPercent / 100);
        const maxByPoints = cd ? (cd.total_points * currencyPerPoint) : 0;
        const maxRedeemAmount = Math.min(maxByPercent, maxByPoints);
        const maxRedeemPoints = currencyPerPoint > 0 ? maxRedeemAmount / currencyPerPoint : 0;

        this.state = useState({
            searchTerm: cd ? cd.phone || cd.card_number || "" : "",
            searching: false,
            cardData: cd || null,
            verified: false,
            pointsToRedeem: 0,
            maxRedeemPoints: maxRedeemPoints,
            maxRedeemAmount: maxRedeemAmount,
            processing: false,
            error: "",
            orderTotal: orderTotal,
            currencyPerPoint: currencyPerPoint,
        });
    }

    get discountAmount() {
        return this.state.pointsToRedeem * this.state.currencyPerPoint;
    }
    
    get remainingToPay() {
        return Math.max(0, this.state.orderTotal - this.discountAmount);
    }
    
    get canRedeem() {
        const cd = this.state.cardData;
        if (!cd || !cd.can_redeem || !this.state.verified) return false;
        if (this.state.pointsToRedeem < (cd.min_redeem_points || 0)) return false;
        if (this.state.pointsToRedeem > this.state.maxRedeemPoints) return false;
        if (this.state.pointsToRedeem <= 0) return false;
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
                this.state.currencyPerPoint = res.currency_per_point || 0.10;
                
                // Recalculate max
                const maxByPercent = this.state.orderTotal * ((res.max_redeem_percent || 50) / 100);
                const maxByPoints = res.total_points * this.state.currencyPerPoint;
                this.state.maxRedeemAmount = Math.min(maxByPercent, maxByPoints);
                this.state.maxRedeemPoints = this.state.currencyPerPoint > 0 
                    ? this.state.maxRedeemAmount / this.state.currencyPerPoint : 0;
                this.state.pointsToRedeem = 0;
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
    }

    onPointsInput(ev) {
        let p = parseFloat(ev.target.value) || 0;
        if (p < 0) p = 0;
        if (p > this.state.maxRedeemPoints) p = this.state.maxRedeemPoints;
        this.state.pointsToRedeem = p;
    }

    setMin() {
        const cd = this.state.cardData;
        const minPts = cd ? (cd.min_redeem_points || 0) : 0;
        this.state.pointsToRedeem = Math.min(minPts, this.state.maxRedeemPoints);
    }
    
    setMax() {
        this.state.pointsToRedeem = this.state.maxRedeemPoints;
    }

    async confirm() {
        if (!this.canRedeem) return;
        this.state.processing = true;
        this.state.error = "";

        try {
            // Call backend to actually deduct points
            const res = await this.orm.call("pos.loyalty.card", "redeem_points", [
                this.state.cardData.id,
                this.state.pointsToRedeem,
                this.state.orderTotal,
            ]);
            
            if (res.error) {
                this.state.error = res.error;
            } else {
                this.notification.add(
                    `Redeemed ${res.points_redeemed.toFixed(0)} pts = ₹${res.discount_value.toFixed(2)}`,
                    { type: "success" }
                );
                
                // Return redemption info to payment screen
                if (this.props.getPayload) {
                    this.props.getPayload({
                        card_id: this.state.cardData.id,
                        card_data: this.state.cardData,
                        points_redeemed: res.points_redeemed,
                        discount_value: res.discount_value,
                        remaining_points: res.remaining_points,
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

    cancel() { 
        this.props.close(); 
    }
}
