/** @odoo-module */

/**
 * =========================================================================
 * LOYALTY REDEMPTION UI (integrated from File 2 for Payment Section Popup)
 * =========================================================================
 * 
 * This file contains the Payment section Loyalty Card popup UI components.
 * Components are used via XML templates in loyalty_redemption.xml
 */

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Dialog } from "@web/core/dialog/dialog";


// ============================================
// Validation Utilities
// ============================================
const ValidationUtils = {
    isValidMobile(phone) {
        if (!phone) return false;
        const cleaned = phone.replace(/[\s\-\(\)]/g, '');
        const patterns = [
            /^[6-9]\d{9}$/,
            /^91[6-9]\d{9}$/,
            /^\+91[6-9]\d{9}$/,
            /^0[6-9]\d{9}$/,
        ];
        return patterns.some(p => p.test(cleaned));
    },
    
    isValidCardNumber(cardNumber) {
        if (!cardNumber) return false;
        const cleaned = cardNumber.trim().toUpperCase();
        return /^LC\d{6,}$/.test(cleaned) || /^\d{6,}$/.test(cleaned);
    },
    
    getInputType(input) {
        if (!input) return 'unknown';
        const cleaned = input.replace(/[\s\-\(\)]/g, '');
        if (this.isValidMobile(cleaned)) return 'mobile';
        if (this.isValidCardNumber(cleaned)) return 'card';
        if (/^\d+$/.test(cleaned) && cleaned.length >= 10) return 'mobile';
        return 'unknown';
    },
    
    formatPhone(phone) {
        if (!phone) return '';
        const cleaned = phone.replace(/[\s\-\(\)+]/g, '');
        if (cleaned.length === 10) {
            return `${cleaned.slice(0, 5)} ${cleaned.slice(5)}`;
        }
        if (cleaned.length === 12 && cleaned.startsWith('91')) {
            return `+91 ${cleaned.slice(2, 7)} ${cleaned.slice(7)}`;
        }
        return phone;
    }
};


// ============================================
// POPUP 1: Customer Identification
// ============================================
export class LoyaltyIdentifyPopup extends Component {
    static template = "pos_loyalty_card.LoyaltyIdentifyPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
    };
    
    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.state = useState({
            searchTerm: "",
            isSearching: false,
            searchDone: false,
            cardFound: false,
            cardData: null,
            inputType: "unknown",
            showNewForm: false,
            newName: "",
            newPhone: "",
            newEmail: "",
            isCreating: false,
            errorMessage: "",
            validationMessage: "",
        });
    }
    
    validateInput() {
        const input = this.state.searchTerm.trim();
        if (!input) {
            this.state.validationMessage = "";
            this.state.inputType = "unknown";
            return false;
        }
        const inputType = ValidationUtils.getInputType(input);
        this.state.inputType = inputType;
        if (inputType === 'mobile' && !ValidationUtils.isValidMobile(input)) {
            this.state.validationMessage = _t("Please enter a valid 10-digit mobile number");
            return false;
        }
        if (inputType === 'card' && !ValidationUtils.isValidCardNumber(input)) {
            this.state.validationMessage = _t("Please enter a valid card number (e.g., LC000001)");
            return false;
        }
        if (input.length < 6) {
            this.state.validationMessage = _t("Enter mobile number or card number to search");
            return false;
        }
        this.state.validationMessage = "";
        return true;
    }
    
    async searchCard() {
        if (!this.state.searchTerm.trim()) {
            this.state.errorMessage = _t("Please enter mobile number or card number");
            return;
        }
        if (!this.validateInput()) {
            this.state.errorMessage = this.state.validationMessage;
            return;
        }
        this.state.isSearching = true;
        this.state.errorMessage = "";
        this.state.cardFound = false;
        this.state.cardData = null;
        this.state.searchDone = false;
        
        try {
            const result = await this.orm.call("pos.loyalty.card", "search_card_for_pos", [this.state.searchTerm.trim()]);
            this.state.searchDone = true;
            if (result.error) {
                this.state.cardFound = false;
                if (this.state.inputType === 'mobile') {
                    this.state.newPhone = this.state.searchTerm.trim();
                }
            } else {
                this.state.cardFound = true;
                this.state.cardData = result;
            }
        } catch (error) {
            this.state.searchDone = true;
            this.state.cardFound = false;
            if (this.state.inputType === 'mobile') {
                this.state.newPhone = this.state.searchTerm.trim();
            }
        }
        this.state.isSearching = false;
    }
    
    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
        this.state.errorMessage = "";
        this.validateInput();
    }
    
    onSearchKeyup(ev) {
        if (ev.key === "Enter") this.searchCard();
    }
    
    showNewCustomerForm() {
        this.state.showNewForm = true;
        this.state.errorMessage = "";
    }
    
    onNameInput(ev) {
        this.state.newName = ev.target.value;
        this.state.errorMessage = "";
    }
    
    onPhoneInput(ev) {
        this.state.newPhone = ev.target.value;
        this.state.errorMessage = "";
    }
    
    onEmailInput(ev) {
        this.state.newEmail = ev.target.value;
    }
    
    validateNewCustomer() {
        if (!this.state.newName.trim()) {
            this.state.errorMessage = _t("Customer name is required");
            return false;
        }
        if (!this.state.newPhone.trim()) {
            this.state.errorMessage = _t("Phone number is required");
            return false;
        }
        if (!ValidationUtils.isValidMobile(this.state.newPhone)) {
            this.state.errorMessage = _t("Please enter a valid 10-digit mobile number");
            return false;
        }
        return true;
    }
    
    async createNewCustomer() {
        if (!this.validateNewCustomer()) return;
        this.state.isCreating = true;
        this.state.errorMessage = "";
        
        try {
            const result = await this.orm.call("pos.loyalty.card", "create_from_pos", [{
                name: this.state.newName.trim(),
                phone: this.state.newPhone.trim(),
                email: this.state.newEmail.trim() || false,
            }]);
            
            if (result.error) {
                this.state.errorMessage = result.error;
            } else {
                this.notification.add(_t("Loyalty card created successfully: %s", result.card_number), { type: "success" });
                if (this.props.getPayload) {
                    this.props.getPayload({
                        type: 'new_customer',
                        card_number: result.card_number,
                        name: result.name,
                        phone: result.phone,
                        id: result.id,
                        total_points: 0,
                        can_redeem: false,
                    });
                }
                this.props.close();
            }
        } catch (error) {
            this.state.errorMessage = _t("Error creating customer. Please try again.");
        }
        this.state.isCreating = false;
    }
    
    continueWithCustomer() {
        if (this.props.getPayload && this.state.cardData) {
            this.props.getPayload({ type: 'existing_customer', ...this.state.cardData });
        }
        this.props.close();
    }
    
    skip() {
        if (this.props.getPayload) this.props.getPayload(null);
        this.props.close();
    }
    
    cancelNewForm() {
        this.state.showNewForm = false;
        this.state.errorMessage = "";
    }
    
    get formattedPhone() {
        return this.state.cardData?.phone ? ValidationUtils.formatPhone(this.state.cardData.phone) : '';
    }
}


// ============================================
// POPUP 2: Redemption Confirmation
// ============================================
export class LoyaltyRedeemConfirmPopup extends Component {
    static template = "pos_loyalty_card.LoyaltyRedeemConfirmPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
        orderTotal: { type: Number, optional: true },
        customerData: { type: Object, optional: true },
    };
    
    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        
        this.state = useState({
            searchTerm: this.props.customerData?.card_number || this.props.customerData?.phone || "",
            isSearching: false,
            cardFound: !!this.props.customerData?.id,
            cardData: this.props.customerData || null,
            inputType: "unknown",
            errorMessage: "",
            validationMessage: "",
        });
        
        if (this.props.customerData?.id) {
            this.state.cardFound = true;
            this.state.cardData = this.props.customerData;
        }
    }
    
    get orderTotal() { return this.props.orderTotal || 0; }
    
    get canProceedToRedeem() {
        return this.state.cardFound && this.state.cardData && this.state.cardData.can_redeem &&
               this.state.cardData.total_points >= (this.state.cardData.min_redemption_points || 0);
    }
    
    get insufficientPoints() {
        return this.state.cardFound && this.state.cardData && !this.state.cardData.can_redeem;
    }
    
    validateInput() {
        const input = this.state.searchTerm.trim();
        if (!input) {
            this.state.validationMessage = "";
            this.state.inputType = "unknown";
            return false;
        }
        const inputType = ValidationUtils.getInputType(input);
        this.state.inputType = inputType;
        if (inputType === 'mobile' && !ValidationUtils.isValidMobile(input)) {
            this.state.validationMessage = _t("Please enter a valid mobile number");
            return false;
        }
        if (inputType === 'card' && !ValidationUtils.isValidCardNumber(input)) {
            this.state.validationMessage = _t("Please enter a valid card number");
            return false;
        }
        this.state.validationMessage = "";
        return true;
    }
    
    async searchCard() {
        if (!this.state.searchTerm.trim()) {
            this.state.errorMessage = _t("Please enter card number or mobile number");
            return;
        }
        if (!this.validateInput()) {
            this.state.errorMessage = this.state.validationMessage;
            return;
        }
        this.state.isSearching = true;
        this.state.errorMessage = "";
        this.state.cardFound = false;
        this.state.cardData = null;
        
        try {
            const result = await this.orm.call("pos.loyalty.card", "search_card_for_pos", [this.state.searchTerm.trim()]);
            if (result.error) {
                this.state.errorMessage = result.error;
            } else {
                this.state.cardFound = true;
                this.state.cardData = result;
            }
        } catch (error) {
            this.state.errorMessage = _t("Error searching card. Please try again.");
        }
        this.state.isSearching = false;
    }
    
    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
        this.state.errorMessage = "";
        this.validateInput();
    }
    
    onSearchKeyup(ev) {
        if (ev.key === "Enter") this.searchCard();
    }
    
    async confirmRedeem() {
        if (!this.canProceedToRedeem) return;
        
        // === CHECK 24-HOUR ELIGIBILITY BEFORE PROCEEDING ===
        try {
            console.log("LOYALTY: Checking redemption eligibility for card ID:", this.state.cardData.id);
            const eligibility = await this.orm.call(
                "pos.loyalty.card",
                "check_redemption_eligibility",
                [this.state.cardData.id]
            );
            
            console.log("LOYALTY: Eligibility check result:", eligibility);
            
            if (!eligibility.eligible) {
                // BLOCKED: Show error and do NOT proceed
                this.state.errorMessage = eligibility.reason || "Redemption not allowed at this time.";
                this.notification.add(
                    eligibility.reason || "Redemption not allowed at this time.",
                    { type: "danger", sticky: true }
                );
                console.log("LOYALTY: Redemption blocked - not proceeding");
                return;
            }
        } catch (e) {
            console.error("LOYALTY: Error checking eligibility:", e);
            // On error, still allow (backend will re-validate)
        }
        
        this.props.close();
        this.dialog.add(LoyaltyRedeemDetailsPopup, {
            orderTotal: this.orderTotal,
            customerData: this.state.cardData,
            getPayload: (result) => {
                if (this.props.getPayload) this.props.getPayload(result);
            },
        });
    }
    
    cancel() { this.props.close(); }
    
    get formattedPhone() {
        return this.state.cardData?.phone ? ValidationUtils.formatPhone(this.state.cardData.phone) : '';
    }
}


// ============================================
// POPUP 3: Redemption Details (Select points amount)
// ============================================
export class LoyaltyRedeemDetailsPopup extends Component {
    static template = "pos_loyalty_card.LoyaltyRedeemDetailsPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
        orderTotal: { type: Number, optional: true },
        customerData: { type: Object, optional: true },
    };
    
    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        
        const cardData = this.props.customerData || {};
        const maxDiscount = this.orderTotal * ((cardData.max_redemption_percent || 100) / 100);
        const maxPointsFromOrder = maxDiscount * (cardData.points_per_unit || 10);
        const maxRedeemablePoints = Math.min(cardData.total_points || 0, maxPointsFromOrder);
        
        this.state = useState({
            cardData: cardData,
            isVerified: false,
            pointsToRedeem: Math.min(cardData.min_redemption_points || 0, maxRedeemablePoints),
            maxRedeemablePoints: maxRedeemablePoints,
            discountValue: 0,
            errorMessage: "",
            isProcessing: false,
        });
        
        this.updateDiscountValue();
    }
    
    get orderTotal() { return this.props.orderTotal || 0; }
    
    get canRedeem() {
        return this.state.isVerified && this.state.cardData &&
               this.state.pointsToRedeem >= (this.state.cardData.min_redemption_points || 0) &&
               this.state.pointsToRedeem <= this.state.maxRedeemablePoints && this.state.pointsToRedeem > 0;
    }
    
    get remainingAfterRedeem() {
        return (this.state.cardData?.total_points || 0) - this.state.pointsToRedeem;
    }
    
    get finalOrderAmount() {
        return Math.max(0, this.orderTotal - this.state.discountValue);
    }
    
    onVerificationChange(ev) { this.state.isVerified = ev.target.checked; }
    
    onPointsInput(ev) {
        let points = parseFloat(ev.target.value) || 0;
        if (points < 0) points = 0;
        if (points > this.state.maxRedeemablePoints) points = this.state.maxRedeemablePoints;
        this.state.pointsToRedeem = points;
        this.updateDiscountValue();
    }
    
    updateDiscountValue() {
        if (this.state.cardData && this.state.cardData.points_per_unit > 0) {
            this.state.discountValue = this.state.pointsToRedeem / this.state.cardData.points_per_unit;
        } else {
            this.state.discountValue = 0;
        }
    }
    
    setMaxPoints() {
        this.state.pointsToRedeem = this.state.maxRedeemablePoints;
        this.updateDiscountValue();
    }
    
    setMinPoints() {
        if (this.state.cardData) {
            this.state.pointsToRedeem = Math.min(this.state.cardData.min_redemption_points || 0, this.state.maxRedeemablePoints);
            this.updateDiscountValue();
        }
    }
    
    async confirmRedemption() {
        if (!this.canRedeem) {
            this.state.errorMessage = _t("Please verify customer identity and check redemption requirements");
            return;
        }
        this.state.isProcessing = true;
        this.state.errorMessage = "";
        
        try {
            const result = await this.orm.call("pos.loyalty.card", "process_pos_redemption", [
                this.state.cardData.id,
                this.state.pointsToRedeem,
                this.orderTotal,
                null
            ]);
            
            if (result.error) {
                this.state.errorMessage = result.error;
                this.state.isProcessing = false;
                return;
            }
            
            result.original_amount = this.orderTotal;
            result.final_amount = this.orderTotal - result.discount_value;
            
            this.props.close();
            
            this.dialog.add(LoyaltyRedeemSummaryPopup, {
                redemptionResult: result,
                onConfirm: () => {
                    if (this.props.getPayload) this.props.getPayload(result);
                },
            });
        } catch (error) {
            this.state.errorMessage = _t("Error processing redemption. Please try again.");
            this.state.isProcessing = false;
        }
    }
    
    cancel() { this.props.close(); }
    
    get formattedPhone() {
        return this.state.cardData?.phone ? ValidationUtils.formatPhone(this.state.cardData.phone) : '';
    }
}


// ============================================
// POPUP 4: Redemption Summary (Success)
// ============================================
export class LoyaltyRedeemSummaryPopup extends Component {
    static template = "pos_loyalty_card.LoyaltyRedeemSummaryPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        redemptionResult: { type: Object, optional: true },
        onConfirm: { type: Function, optional: true },
    };
    
    setup() {
        this.result = this.props.redemptionResult || {};
    }
    
    get originalAmount() { return this.result.original_amount || 0; }
    get discountAmount() { return this.result.discount_value || 0; }
    get finalAmount() { return this.result.final_amount || 0; }
    get pointsRedeemed() { return this.result.points_redeemed || 0; }
    get remainingPoints() { return this.result.remaining_points || 0; }
    get customerName() { return this.result.customer_name || ''; }
    get cardNumber() { return this.result.card_number || ''; }
    
    proceedToPayment() {
        if (this.props.onConfirm) this.props.onConfirm();
        this.props.close();
    }
}


// ============================================
// Legacy Redemption Popup (Fallback)
// ============================================
export class LoyaltyRedeemPopup extends Component {
    static template = "pos_loyalty_card.LoyaltyRedeemPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
        orderTotal: { type: Number, optional: true },
        customerData: { type: Object, optional: true },
    };
    
    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.state = useState({
            searchTerm: this.props.customerData?.card_number || "",
            isSearching: false,
            cardFound: false,
            cardData: null,
            isVerified: false,
            pointsToRedeem: 0,
            maxRedeemablePoints: 0,
            discountValue: 0,
            errorMessage: "",
        });
        
        if (this.props.customerData?.card_number) {
            this.searchCard();
        }
    }
    
    get orderTotal() { return this.props.orderTotal || 0; }
    
    get canRedeem() {
        return this.state.cardFound && this.state.isVerified && this.state.cardData &&
               this.state.cardData.can_redeem &&
               this.state.pointsToRedeem >= this.state.cardData.min_redemption_points &&
               this.state.pointsToRedeem <= this.state.cardData.total_points;
    }
    
    async searchCard() {
        if (!this.state.searchTerm.trim()) {
            this.state.errorMessage = _t("Please enter card number or phone.");
            return;
        }
        this.state.isSearching = true;
        this.state.errorMessage = "";
        this.state.cardFound = false;
        this.state.cardData = null;
        
        try {
            const result = await this.orm.call("pos.loyalty.card", "search_card_for_pos", [this.state.searchTerm.trim()]);
            if (result.error) {
                this.state.errorMessage = result.error;
            } else {
                this.state.cardFound = true;
                this.state.cardData = result;
                const maxDiscount = this.orderTotal * (result.max_redemption_percent / 100);
                const maxPointsFromOrder = maxDiscount * result.points_per_unit;
                this.state.maxRedeemablePoints = Math.min(result.total_points, maxPointsFromOrder);
                if (result.can_redeem) {
                    this.state.pointsToRedeem = Math.min(result.min_redemption_points, this.state.maxRedeemablePoints);
                    this.updateDiscountValue();
                }
            }
        } catch (error) {
            this.state.errorMessage = _t("Error searching card.");
        }
        this.state.isSearching = false;
    }
    
    onSearchInput(ev) { this.state.searchTerm = ev.target.value; }
    onSearchKeyup(ev) { if (ev.key === "Enter") this.searchCard(); }
    onVerificationChange(ev) { this.state.isVerified = ev.target.checked; }
    
    onPointsInput(ev) {
        let points = parseFloat(ev.target.value) || 0;
        if (points < 0) points = 0;
        if (points > this.state.maxRedeemablePoints) points = this.state.maxRedeemablePoints;
        this.state.pointsToRedeem = points;
        this.updateDiscountValue();
    }
    
    updateDiscountValue() {
        if (this.state.cardData && this.state.cardData.points_per_unit > 0) {
            this.state.discountValue = this.state.pointsToRedeem / this.state.cardData.points_per_unit;
        } else {
            this.state.discountValue = 0;
        }
    }
    
    setMaxPoints() {
        this.state.pointsToRedeem = this.state.maxRedeemablePoints;
        this.updateDiscountValue();
    }
    
    setMinPoints() {
        if (this.state.cardData) {
            this.state.pointsToRedeem = Math.min(this.state.cardData.min_redemption_points, this.state.maxRedeemablePoints);
            this.updateDiscountValue();
        }
    }
    
    async confirmRedemption() {
        if (!this.canRedeem) {
            this.state.errorMessage = _t("Cannot redeem. Check requirements.");
            return;
        }
        try {
            const result = await this.orm.call("pos.loyalty.card", "process_pos_redemption", [
                this.state.cardData.id,
                this.state.pointsToRedeem,
                this.orderTotal,
                null
            ]);
            if (result.error) {
                this.state.errorMessage = result.error;
                return;
            }
            result.original_amount = this.orderTotal;
            result.final_amount = this.orderTotal - result.discount_value;
            this.notification.add(_t("Redeemed %s points = ₹%s discount!", result.points_redeemed, result.discount_value.toFixed(2)), { type: "success" });
            if (this.props.getPayload) this.props.getPayload(result);
            this.props.close();
        } catch (error) {
            this.state.errorMessage = _t("Error processing redemption.");
        }
    }
    
    cancel() { this.props.close(); }
}
