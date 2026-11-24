/** @odoo-module **/

// What every option does, in words, and a picture of the whole page. Only text
// is made here: `d` is a plain copy of the form's values.

export function esc(s) {
    return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
const n = (v) => Number(v) || 0;
const num = (v) => String(+n(v).toFixed(2));
export const pct = (v) => `${num(v)}%`;
export const money = (v, d) => `${n(v).toFixed(2)} ${d.sa_money || ""}`.trim();
const onOff = (a, b) => (v) => (v ? a : b);

// ------------------------------------------------------------------ the margin
export const rulesOf = (d) => (d.margin_rules_by === "group" ? d.margin_group_ids : d.margin_category_ids) || [];
export function marginUsed(d, t) {
    const rule = d.margin_rules_enabled ? rulesOf(d)[t.pick] : null;
    return rule ? n(rule.percent) : n(d.margin_percent);
}
const sellOf = (d, t) => t.cost * (1 + marginUsed(d, t) / 100);
function lastOf(d, t) {
    const sell = sellOf(d, t);
    const floor = t.cost * (1 + n(d.min_margin_percent) / 100);
    return Math.min(sell, Math.max(floor, sell * (1 - (n(d.bargain_max_steps) * n(d.bargain_step_percent)) / 100)));
}
const differs = (d, t) => d.price_approval_enabled && t.page > 0
    && Math.abs(t.page - sellOf(d, t)) > (t.page * n(d.price_approval_tolerance_percent)) / 100 + 0.005;

// ------------------------------------------------- one line for each option
export const LINES = {
    active: onOff("The AI reads the messages.", "Catalogue words are used instead."),
    provider: (v, d, l) => `${l} is asked.`,
    model_name: (v) => (v ? `Model: ${v}.` : "The default model is used."),
    timeout_seconds: (v) => `No answer in ${n(v)} seconds: catalogue words are used.`,
    shop_picks_vendors: onOff("An enquiry without stock waits at the counter.", "Every vendor of the category is asked at once."),
    shop_pick_window_minutes: (v) => `Nobody chose in ${n(v)} minutes: all are asked.`,
    shop_pick_customer_text: (v) => (/\{(product|ref|customer|shop)\}/.test(v || "") ? "Sent while the shop decides."
        : "Add {product} or {ref}, or WhatsApp may drop it as a repeat."),
    sourcing_window_minutes: (v, d) => (d.vendor_choice_mode === "manual" ? `You are reminded after ${n(v)} minutes.`
        : `Chosen after ${n(v)} minutes, or sooner when all answered.`),
    vendor_choice_mode: (v) => (v === "manual" ? "You choose on Store > Enquiries." : "The lowest price is taken."),
    vendor_money: (v) => (v === "country" ? "A vendor in another country is asked in that country's money." : "Every vendor is asked in the company's money."),
    price_escalation_phone: (v) => (v ? `${v} gets a WhatsApp with a link to type the price.` : "It only waits on Store > Enquiries."),
    margin_percent: (v, d) => `Vendor 100: the customer pays ${money(100 * (1 + n(v) / 100), d)}.`,
    margin_rules_enabled: onOff("A category or a group can have its own margin.", "The normal margin for everything."),
    margin_rules_by: (v) => (v === "group" ? "The customer's group decides. Categories are not looked at."
        : "The product's category decides. Groups are not looked at."),
    bargain_enabled: onOff("The customer can ask for a better price.", "The first price is final."),
    bargain_step_percent: (v, d, l, t) => `${money((sellOf(d, t) * n(v)) / 100, d)} less for each step.`,
    bargain_max_steps: (v) => (n(v) ? `The price can come down ${n(v)} time(s).` : "It never comes down."),
    min_margin_percent: (v, d, l, t) => `Never below ${money(t.cost * (1 + n(v) / 100), d)}.`,
    qty_bargain_all: onOff("The ranges are for every product.", "The ranges are for ticked products."),
    price_approval_enabled: onOff("A different page price: the customer waits for you.", "The customer is told at once."),
    price_approval_tolerance_percent: (v) => (n(v) ? `Up to ${pct(v)} difference is ignored.` : "Every difference asks you."),
    supply_mode: (v) => (v === "auto" ? "The lowest price is ordered by itself." : "You order from the vendor."),
    supply_auto_start: (v) => (v === "signed" ? "Ordered after the signature, before payment." : "Ordered after the payment. Cash does not count."),
    supply_auto_wait: (v) => (n(v) ? `Waits ${n(v)} minutes for a lower price.` : "Does not wait."),
    supply_auto_margin: (v, d) => `Vendor 100: needs a sale of ${money(100 + n(v), d)} or more.`,
    supply_auto_limit: (v) => (n(v) ? `Above ${num(v)} it asks you.` : "No limit."),
    supply_auto_days: (v) => (n(v) ? `Counted as here in ${n(v)} day(s) when the vendor gave no time.` : "Counted as here today."),
    customer_reply_minutes: (v) => (n(v) ? `Closed after ${n(v)} minutes without an answer.` : "Closed after 24 hours."),
    pay_remind_minutes: (v, d) => (n(v) && n(d.pay_remind_max) ? `A reminder after ${n(v)} minutes.` : "No reminder."),
    pay_remind_max: (v, d) => (n(v) && n(d.pay_remind_minutes) ? `At most ${n(v)}.` : "No reminder."),
    pay_link_in_stock: (v) => ({ sign: "Sent when the customer signs.", accept: "Sent when the shop presses Accept." }[v] || "Only when you press Send payment link."),
    pay_link_no_stock: (v) => ({ sign: "They pay before the goods are here.", accept: "Sent when the goods are here and the shop accepts." }[v] || "Only when you press Send payment link."),
    pincode_country_id: (v) => (v ? `Postcodes are read as in ${v}, unless the customer has a country.` : "Any reasonable postcode."),
    pincode_prefixes: (v) => (v ? `Only postcodes starting with ${v}.` : "Every correct postcode."),
    stale_after_minutes: (v) => `A YES after ${n(v) || 60} minutes is a new message.`,
    max_order_quantity: (v) => (n(v) ? `More than ${n(v)} is refused.` : "No limit."),
    address_link_enabled: onOff("A form link is sent for a new address.", "The address is asked in the group."),
    address_link_minutes: (v) => `Stops after ${n(v)} minutes or one use.`,
    link_group_note: onOff("The group is told that it went to the private chat.", "The group gets no note."),
    shop_contact_phone: (v) => (v ? `Customers are told ${v}.` : "The company phone, else the WhatsApp number."),
    chatter_action: (v) => (v === "reply" ? '"Thanks" is answered, once per person per minute.' : '"Thanks" gets no answer.'),
    chatter_reply_text: (v) => `Answer: ${v || ""}`,
    media_action: (v) => ({ reply: "The customer is asked for the product name.", discard: "Not answered and not stored." }[v] || "Not answered, but kept."),
    media_reply_text: (v) => `Answer: ${v || ""}`,
    notice_on: onOff("A panel on the right of every page.", 'Only the "Enquiries need you" note.'),
    finder_enabled: onOff("A general word opens polls.", "No polls for general words."),
    finder_max_options: (v) => `${n(v)} choices in a poll. WhatsApp allows 12; two are Back and Not listed.`,
    conduct_enabled: onOff("A listed word or phrase is removed.", "Nothing is removed."),
    conduct_links: onOff("Links with a listed part are removed.", "Links stay."),
    conduct_warn: (v) => ({ off: "The person is not told.", private: "Told in the private chat." }[v] || "Told in the same chat."),
    conduct_warn_text: (v) => `Text: ${v || ""}`,
    conduct_words: (v) => `${(v || "").split("\n").filter((x) => x.trim()).length} word(s). Exact match only.`,
    conduct_phrases: (v) => `${(v || "").split("\n").filter((x) => x.trim()).length} phrase(s). Exact match only.`,
    conduct_link_words: (v) => `${(v || "").split("\n").filter((x) => x.trim()).length} link part(s).`,
    takeover_enabled: onOff("You write: the assistant stops there.", "The assistant goes on answering."),
    takeover_minutes: (v) => `It answers again when you are quiet for ${num(v)} minute(s).`,
    takeover_numbers: (v) => ((v || "").trim() ? "These numbers count as the shopkeeper too." : "Only the shop's own phone."),
    wechat_enabled: onOff("WeChat vendors are asked.", "WeChat vendors are not asked."),
    wechat_stale_minutes: (v) => `No sign for ${n(v)} minutes: shown as down.`,
    wechat_manual_when_down: onOff("Down: the counter shows Copy / Sent by hand.", "Down: nothing to do by hand."),
    confirm_enabled: onOff("A picture page with ACCEPT / REJECT.", "A YES / NO poll in the chat."),
    confirm_vendor_enabled: onOff("Vendors get the page, then the price is asked.", "Vendors are asked for the price directly."),
    confirm_remind_minutes: (v) => `One reminder after ${n(v)} minutes.`,
    vendor_remind_minutes: (v, d) => (n(v) && n(d.vendor_remind_max) ? `Reminded after ${n(v)} minutes.` : "Never reminded."),
    vendor_remind_max: (v, d) => (n(v) && n(d.vendor_remind_minutes) ? `At most ${n(v)}.` : "Never reminded."),
    ai_enabled: onOff("The AI decides if a message is an enquiry.", "Only the words of your catalogue decide."),
    min_confidence: (v) => (n(v) ? `AI sure by less than ${Math.round(n(v) * 100)}%: noted, not answered.` : "Everything the AI calls a product is answered."),
    max_products: (v) => `At most ${n(v) || 5} products are looked at.`,
    require_confirmation: onOff("The customer confirms the product first.", "The best match is used at once."),
    use_virtual_stock: onOff("Goods on the way count as stock.", "Only goods on the shelf count."),
    dm_use_buttons: onOff("Private replies go with buttons. WhatsApp Web may not show them.", "Private replies go as text."),
    auto_confirm_order: onOff("The older private chat goes on to payment.", "The older private chat stops at the quotation."),
};
const LINKS = ["confirm", "address", "sign", "pay", "track", "map", "review", "web", "docs", "shop"].map((k) => `link_${k}`);
for (const f of LINKS) {
    LINES[f] = (v) => (v === "group" ? "Posted in the group, marked for the customer." : "Goes to the private chat. Not possible: to the group.");
}

// ------------------------------------------- the options of a page, in groups
export const GROUPS = {
    ai: [["Provider", ["active", "provider", "model_name", "timeout_seconds"]]],
    counter: [["The Shop Counter", ["shop_picks_vendors", "shop_pick_window_minutes", "shop_pick_customer_text"]]],
    vendor: [["1. Asking the vendors", ["sourcing_window_minutes", "vendor_choice_mode", "vendor_money", "price_escalation_phone"]],
        ["2. The price for the customer", ["margin_percent"]],
        ["Ordering from the vendor, after the sale order", ["supply_mode", "supply_auto_start", "supply_auto_wait", "supply_auto_margin", "supply_auto_limit", "supply_auto_days"]],
        ["3. Waiting for the customer", ["customer_reply_minutes"]], ["4. Orders not paid yet", ["pay_remind_minutes", "pay_remind_max"]]],
    margin: [["Margin", ["margin_percent", "margin_rules_enabled", "margin_rules_by"]],
        ["Bargaining", ["bargain_enabled", "bargain_step_percent", "bargain_max_steps", "min_margin_percent", "qty_bargain_all"]],
        ["Price differs from the product page", ["price_approval_enabled", "price_approval_tolerance_percent"]],
        ["Ordering from the vendor", ["supply_mode", "supply_auto_margin"]]],
    payments: [["When the payment link is sent", ["pay_link_in_stock", "pay_link_no_stock"]]],
    address: [["Delivery Address", ["pincode_country_id", "pincode_prefixes", "stale_after_minutes", "max_order_quantity", "address_link_enabled", "address_link_minutes"]]],
    links: [["Send to", LINKS], ["Around it", ["link_group_note"]], ["A product we don't sell", ["shop_contact_phone"]]],
    chatter: [["Messages", ["chatter_action", "chatter_reply_text", "media_action", "media_reply_text"]]],
    notify: [["Side Notifications", ["notice_on"]]],
    finder: [["Guided Finder", ["finder_enabled", "finder_max_options"]]],
    conduct: [["Switches", ["conduct_enabled", "conduct_links", "conduct_warn", "conduct_warn_text"]], ["Lists", ["conduct_words", "conduct_phrases", "conduct_link_words"]]],
    takeover: [["Human Takeover", ["takeover_enabled", "takeover_minutes", "takeover_numbers"]]],
    wechat: [["WeChat Bridge", ["wechat_enabled", "wechat_stale_minutes", "wechat_manual_when_down"]]],
    confirm: [["Who confirms on the page", ["confirm_enabled", "confirm_vendor_enabled", "confirm_remind_minutes", "vendor_remind_minutes", "vendor_remind_max"]]],
    group: [["Behaviour", ["ai_enabled", "min_confidence", "max_products", "require_confirmation", "use_virtual_stock"]], ["Advanced", ["dm_use_buttons", "auto_confirm_order"]]],
};
// an option that is shown only with another one
const auto = (d) => d.supply_mode === "auto";
const WHEN = {
    shop_pick_window_minutes: (d) => d.shop_picks_vendors, shop_pick_customer_text: (d) => d.shop_picks_vendors,
    supply_auto_start: auto, supply_auto_wait: auto, supply_auto_margin: auto, supply_auto_limit: auto, supply_auto_days: auto,
    margin_rules_by: (d) => d.margin_rules_enabled,
    bargain_step_percent: (d) => d.bargain_enabled, bargain_max_steps: (d) => d.bargain_enabled,
    min_margin_percent: (d) => d.bargain_enabled, qty_bargain_all: (d) => d.bargain_enabled,
    price_approval_tolerance_percent: (d) => d.price_approval_enabled,
    address_link_minutes: (d) => d.address_link_enabled,
    chatter_reply_text: (d) => d.chatter_action === "reply", media_reply_text: (d) => d.media_action === "reply",
    finder_max_options: (d) => d.finder_enabled,
    conduct_links: (d) => d.conduct_enabled, conduct_warn: (d) => d.conduct_enabled,
    conduct_warn_text: (d) => d.conduct_enabled && d.conduct_warn !== "off",
    conduct_words: (d) => d.conduct_enabled, conduct_phrases: (d) => d.conduct_enabled, conduct_link_words: (d) => d.conduct_enabled && d.conduct_links,
    takeover_minutes: (d) => d.takeover_enabled, takeover_numbers: (d) => d.takeover_enabled,
    vendor_remind_minutes: (d) => d.confirm_vendor_enabled, vendor_remind_max: (d) => d.confirm_vendor_enabled,
};
export const shown = (f, d) => f in d && (!WHEN[f] || Boolean(WHEN[f](d)));

// ------------------------------------------------------------------ the picture
// c customer, v vendor, b assistant, k shopkeeper, s a note between the messages
const WHO = { c: "Customer", v: "Vendor", k: "You" };
function chat(title, list) {
    return `<div class="sa_pv_phone"><div class="sa_pv_head"><i></i><div><b>${esc(title)}</b><small>Example</small></div></div><div class="sa_pv_chat">`
        + list.filter(Boolean).map(([w, t, who]) => (w === "s"
            ? `<div class="sa_pv_note${/^(You |The counter rings|No vendor answers)/.test(t) ? " sa_pv_you" : ""}"><span>${esc(t)}</span></div>`
            : `<div class="sa_pv_bub sa_pv_${w}">${who || WHO[w] ? `<b>${esc(who || WHO[w])}</b>` : ""}<span>${esc(t)}</span></div>`)).join("") + "</div></div>";
}
const result = (html) => `<div class="sa_pv_result"><b>Result</b>${html}</div>`;
const S = (t) => ["s", t];
const ITEM = "HP CQ40 keyboard";

function marginPicture(d, t) {
    const m = marginUsed(d, t);
    const sell = sellOf(d, t);
    const last = d.bargain_enabled ? lastOf(d, t) : sell;
    const need = t.cost * (1 + n(d.supply_auto_margin) / 100);
    const wait = differs(d, t);
    const rule = d.margin_rules_enabled ? rulesOf(d)[t.pick] : null;
    let html = "";
    const warn = [];
    if (d.bargain_enabled && n(d.margin_percent) < n(d.min_margin_percent)) {
        warn.push("Cannot be saved: the normal margin is below the lowest margin when bargaining.");
    }
    if (d.margin_rules_enabled && d.bargain_enabled) {
        for (const r of rulesOf(d).filter((x) => n(x.percent) < n(d.min_margin_percent))) {
            warn.push(`Cannot be saved: ${r.name} (${pct(r.percent)}) is below the lowest margin when bargaining (${pct(d.min_margin_percent)}).`);
        }
    }
    html += warn.map((w) => `<div class="alert alert-warning py-2 px-3 mb-2"><span>${esc(w)}</span></div>`).join("");
    return html + chat("Group chat", [["c", `${ITEM}?`], S("Not in stock: the vendors are asked"), ["v", money(t.cost, d), "Vendor B"],
        S(`Margin ${pct(m)}${rule ? ` (${rule.name})` : ""}: + ${money(sell - t.cost, d)}`),
        wait ? S(`You choose first: the product page says ${money(t.page, d)}`) : null, ["b", `${ITEM}: ${money(sell, d)}`],
        d.bargain_enabled ? ["c", "Better price?"] : S("The price is final"),
        d.bargain_enabled && n(d.bargain_max_steps) ? S(`Up to ${n(d.bargain_max_steps)} times ${pct(d.bargain_step_percent)} less, never below ${money(t.cost * (1 + n(d.min_margin_percent) / 100), d)}`) : null,
        d.bargain_enabled ? ["b", last < sell - 0.005 ? `Last price: ${money(last, d)}` : `This is the last price: ${money(sell, d)}`] : null,
        ["c", "OK"], "supply_mode" in d ? S(!auto(d) ? "You order from the vendor" : last < need - 0.005 ? `You are asked first: below ${money(need, d)}` : "Ordered from the vendor by itself") : null])
        + result(`<div class="sa_pv_big"><div><span>Customer pays</span><strong>${esc(money(last, d))}</strong></div><div><span>You pay the vendor</span><strong>${esc(money(t.cost, d))}</strong></div><div class="sa_pv_earn"><span>You earn</span><strong>${esc(money(last - t.cost, d))}</strong></div></div>`);
}

const PICTURES = {
    ai: (d, l) => chat("A message arrives", [["c", "any charger for lenovo g50?"],
        S(d.active ? `${l("provider")} reads it, at most ${n(d.timeout_seconds)} seconds` : "No AI"),
        S(d.active ? "Enquiry: charger Lenovo G50" : "Found only if the words are in your catalogue")]),
    counter: (d) => chat("Not in stock", [["c", "DC jack Acer 3680?"],
        d.shop_picks_vendors ? ["b", (d.shop_pick_customer_text || "").replace(/\{product\}/g, "DC jack Acer 3680").replace(/\{ref\}/g, "1GF").replace(/\{customer\}/g, "Priya").replace(/\{shop\}/g, "our shop")] : null,
        S(d.shop_picks_vendors ? "The counter rings. You pick the vendors." : "Every vendor is asked now."),
        d.shop_picks_vendors ? S(`Nobody in ${n(d.shop_pick_window_minutes)} minutes: every vendor is asked.`) : null]),
    vendor: (d, l) => chat("One enquiry", [["c", `${ITEM}?`], ["b", `(to the vendors) Your price, in ${d.vendor_money === "country" ? "your own money" : d.sa_money}?`],
        ["v", "110", "Vendor A"], ["v", "100", "Vendor B"],
        S(d.vendor_choice_mode === "manual" ? `You choose. Reminder after ${n(d.sourcing_window_minutes)} minutes.` : `Lowest wins: Vendor B, 100. We wait at most ${n(d.sourcing_window_minutes)} minutes.`),
        S(`Your margin ${pct(d.margin_percent)}: + ${money(n(d.margin_percent), d)}`), ["b", `${ITEM}: ${money(100 * (1 + n(d.margin_percent) / 100), d)}`],
        S(`Answer within ${n(d.customer_reply_minutes) ? `${n(d.customer_reply_minutes)} minutes` : "24 hours"}`),
        S(n(d.pay_remind_minutes) && n(d.pay_remind_max) ? `Not paid: a reminder every ${n(d.pay_remind_minutes)} minutes, at most ${n(d.pay_remind_max)}` : "Not paid: no reminder"),
        "supply_mode" in d ? S(auto(d) ? `${l("supply_auto_start")}: ordered from vendor B by itself after ${n(d.supply_auto_wait)} minutes${n(d.supply_auto_limit) ? `, up to ${num(d.supply_auto_limit)}` : ""}` : "You order from the vendor") : null,
        S(d.price_escalation_phone ? `No vendor answers: ${d.price_escalation_phone} is told` : "No vendor answers: it waits on Store > Enquiries")]),
    payments: (d) => [["pay_link_in_stock", "In stock"], ["pay_link_no_stock", "Not in stock"]].map(([f, title]) => {
        const pay = ["b", "Payment link for your order"];
        return chat(title, [S("Customer signs"), d[f] === "sign" ? pay : null, f === "pay_link_no_stock" ? S("Goods arrive") : null, S("Shop presses Accept"),
            d[f] === "accept" ? pay : null, d[f] === "never" ? S("You press Send payment link") : null, d[f] === "never" ? pay : null]);
    }).join(""),
    address: (d) => chat("A new address", [["b", d.address_link_enabled ? `Fill in your address: (link, ${n(d.address_link_minutes)} minutes, once)` : "Your house, street and postcode?"],
        S(d.pincode_prefixes ? `Postcode must start with ${d.pincode_prefixes}` : "Every correct postcode"), ["c", "I want 5000 pieces"],
        S(n(d.max_order_quantity) && 5000 > n(d.max_order_quantity) ? `Refused: more than ${n(d.max_order_quantity)}` : "Accepted"),
        S(`A YES after ${n(d.stale_after_minutes) || 60} minutes counts as new`)]),
    links: (d, l, label) => {
        const own = LINKS.filter((f) => d[f] !== "group");
        return chat("Private chat", own.length ? own.map((f) => ["b", label(f)]) : [S("Nothing")])
            + chat("Group", [...LINKS.filter((f) => d[f] === "group").map((f) => ["b", `${label(f)} (only for you)`]),
                d.link_group_note && own.length ? ["b", "I've sent it to your private chat."] : null,
                ["c", "Do you sell sofas?"], ["b", `Sorry, we don't have it. Please contact us on ${d.shop_contact_phone || "the company phone"}.`]]);
    },
    chatter: (d) => chat("In the group", [["c", "Thanks, good night"], d.chatter_action === "reply" ? ["b", d.chatter_reply_text || ""] : S("No answer"),
        ["c", "(photo)"], d.media_action === "reply" ? ["b", d.media_reply_text || ""] : S(d.media_action === "discard" ? "No answer, not stored" : "No answer, kept")]),
    notify: (d) => chat("On every page", [S(d.notice_on ? "Panel on the right: new order, vendor price, payment" : "Note: Enquiries need you")]),
    finder: (d) => chat("A general word", [["c", "laptop"], d.finder_enabled ? ["b", "Which brand?  " + ["HP", "Dell", "Acer", "Lenovo", "Asus", "Apple", "MSI", "Toshiba", "Samsung", "LG"]
        .slice(0, Math.max(1, n(d.finder_max_options) || 10)).map((x) => `○ ${x}`).join("  ")] : S("No poll. Only exact names get a price.")]),
    conduct: (d) => chat("In the group", [["c", "(message with a listed word)"], S(d.conduct_enabled ? "Removed" : "Stays"),
        d.conduct_enabled && d.conduct_warn !== "off" ? ["b", `${d.conduct_warn === "private" ? "(private) " : ""}${d.conduct_warn_text || ""}`] : null,
        ["c", "(adult link)"], S(d.conduct_enabled && d.conduct_links ? "Removed" : "Stays"), ["c", "(photo)"], S("Stays: photos are not checked")]),
    takeover: (d) => chat("In a chat", [["c", "Is it original?"], ["k", "Yes, it is original."], S(d.takeover_enabled ? "The assistant is quiet" : "The assistant goes on"),
        d.takeover_enabled ? S(`You are quiet for ${num(d.takeover_minutes)} minute(s)`) : null, ["c", "And the price?"], ["b", `${ITEM}: 120.00`]]),
    wechat: (d) => chat("A WeChat vendor", d.wechat_enabled ? [["b", `Price please: ${ITEM}`], ["v", "100"], S(`Bridge silent for ${n(d.wechat_stale_minutes)} minutes: down`),
        S(d.wechat_manual_when_down ? "Counter shows: Copy / Sent by hand / Type the price" : "Waits for the bridge")] : [S("WeChat vendors are not asked")]),
    confirm: (d) => chat("Customer", [["c", ITEM], ["b", d.confirm_enabled ? "Is this it? (page with picture: ACCEPT / REJECT)" : "Is this it?  ○ YES  ○ NO"],
        S(`Nothing pressed in ${n(d.confirm_remind_minutes)} minutes: one reminder`)])
        + chat("Vendor", d.confirm_vendor_enabled ? [["b", "Do you have this? (page: ACCEPT / REJECT)"], ["v", "ACCEPT"], ["b", "Your price?"], ["v", "100"],
            S(n(d.vendor_remind_minutes) && n(d.vendor_remind_max) ? `Reminded after ${n(d.vendor_remind_minutes)} minutes, at most ${n(d.vendor_remind_max)}` : "No reminder")] : [["b", "Price please"], ["v", "100"]]),
    group: (d) => (d.group_type === "vendor" ? chat("In the vendor group", [["b", `Price please: ${ITEM}`], ["v", "100"], S("Read as a price, never answered")])
        : chat("In the group", [["c", `Do you have a ${ITEM}?`], S(d.ai_enabled ? "The AI reads it" : "Catalogue words are searched"), S(`Up to ${n(d.max_products) || 5} products looked at`),
            d.require_confirmation ? ["b", `Is this the one? ${ITEM}`] : S("Not asked to confirm"), S(d.use_virtual_stock ? "Stock: shelf + on the way" : "Stock: shelf only"), ["b", `${ITEM}: 120.00`]])),
};

const SHORT = {
    ai: (d) => (d.active ? "The AI understands what customers write." : "Without AI: only exact catalogue words are understood."),
    counter: (d) => (d.shop_picks_vendors ? "YOU choose which vendors are asked." : "ALL vendors are asked by themselves."),
    vendor: (d) => `${d.vendor_choice_mode === "manual" ? "YOU choose" : "The LOWEST price wins"}, then ${pct(d.margin_percent)} is added.${"supply_mode" in d ? (auto(d) ? " The vendor order goes by itself." : " YOU order from the vendor.") : ""}`,
    payments: (d) => ({ sign: "In stock: the customer pays after signing.", accept: "In stock: the customer pays after you accept.", never: "In stock: YOU send the payment link." }[d.pay_link_in_stock] || ""),
    address: (d) => (d.address_link_enabled ? "The customer fills in a form for the address." : "The customer types the address in the group."),
    links: (d) => {
        const own = LINKS.filter((f) => d[f] !== "group").length;
        return `${own} of ${LINKS.length} links go to the private chat, ${LINKS.length - own} to the group.`;
    },
    chatter: (d) => (d.chatter_action === "reply" ? "Small talk IS answered." : "Small talk is NOT answered."),
    notify: (d) => (d.notice_on ? "You see a panel on the right of every page." : "You see only one small note."),
    finder: (d) => (d.finder_enabled ? "A general word is answered with choices to tap." : "A general word gets NO choices."),
    conduct: (d) => (d.conduct_enabled ? "Bad words ARE removed." : "Nothing is removed."),
    takeover: (d) => (d.takeover_enabled ? "When you write, the assistant stops." : "The assistant goes on, also when you write."),
    wechat: (d) => (d.wechat_enabled ? "WeChat vendors ARE asked." : "WeChat vendors are NOT asked."),
    confirm: (d) => (d.confirm_enabled ? "The customer confirms on a page with the picture." : "The customer confirms with YES / NO in the chat."),
    group: (d) => (d.group_type === "vendor" ? "This group gives prices." : "This group asks for products."),
};

export function fullHtml(page, d, t, fields) {
    const label = (f) => ((fields[f] && fields[f].string) || f).replace(/ \((%|minutes|s|days)\)$/, "");
    const say = (f, v = d[f]) => {
        const sel = fields[f] && fields[f].selection;
        const hit = sel && sel.find((x) => x[0] === v);
        return hit ? hit[1] : v === true ? "On" : v === false || v === "" || v === undefined || v === null ? (fields[f] && fields[f].type === "boolean" ? "Off" : "Empty")
            : typeof v === "number" ? num(v) : String(v).length > 60 ? `${String(v).slice(0, 60)}...` : String(v);
    };
    let html = page === "margin" ? marginPicture(d, t) : `<div class="sa_pv_short">${esc(SHORT[page](d))}</div>${PICTURES[page](d, say, label)}`;
    html += '<details class="sa_pv_all"><summary>All options</summary>';
    if (page === "group" && d.group_type === "vendor") {
        return html + '<div class="text-muted">Prices only. Nothing is answered here.</div></details>';
    }
    for (const [title, list] of GROUPS[page]) {
        const seen = list.filter((f) => shown(f, d));
        if (seen.length) {
            html += `<h4>${esc(title)}</h4><dl>` + seen.map((f) => `<div><dt>${esc(label(f))}</dt><dd><b class="sa_pv_tag ${d[f] === true ? "sa_pv_on" : fields[f] && fields[f].type === "boolean" ? "sa_pv_off" : ""}">${esc(say(f))}</b><span>${esc(LINES[f](d[f], d, say(f), t))}</span></dd></div>`).join("") + "</dl>";
        }
    }
    if (page === "margin" && d.margin_rules_enabled && rulesOf(d).length) {
        html += "<h4>Own margins</h4><dl>" + rulesOf(d).map((r) => `<div><dt>${esc(r.name)}</dt><dd><b class="sa_pv_tag">${esc(pct(r.percent))}</b><span>${esc(`Customer pays ${money(t.cost * (1 + n(r.percent) / 100), d)}`)}</span></dd></div>`).join("") + "</dl>";
    }
    return html + "</details>";
}

// ------------------------- highlight only the words that belong to an option
const pieces = (h) => h.split(/(<[^>]+>)/);
const words = (s) => s.split(/(\s+)/);

export function highlight(page, d, t, fields, names) {
    const html = fullHtml(page, d, t, fields);
    const parts = pieces(html);
    const mark = {};
    for (const f of names) {
        if (!(f in d)) {
            continue;
        }
        const v = d[f];
        const sel = fields[f] && fields[f].selection;
        const other = Array.isArray(v) ? v.map((r) => ({ ...r, percent: n(r.percent) + 1 })) : typeof v === "boolean" && fields[f].type === "boolean" ? !v
            : typeof v === "number" ? v + 1 : sel ? (sel.find((x) => x[0] !== v) || [v])[0] : v ? `${v}x` : "x";
        const texts = pieces(fullHtml(page, { ...d, [f]: other }, t, fields)).filter((x) => x && x[0] !== "<");
        const same = texts.length === parts.filter((x) => x && x[0] !== "<").length;
        let at = -1;
        parts.forEach((s, i) => {
            if (!s || s[0] === "<") {
                return;
            }
            at += 1;
            const w = words(s);
            let best = [];
            if (same) {
                best = words(texts[at]);
            } else {
                if (texts.includes(s)) {
                    return;
                }
                let score = -1;
                for (const q of texts) {
                    const qw = words(q);
                    const c = w.filter((a) => a.trim() && qw.includes(a)).length;
                    if (c > score) {
                        score = c;
                        best = qw;
                    }
                }
                if (score < w.filter((a) => a.trim()).length / 2) {
                    best = [];
                }
            }
            w.forEach((a, j) => {
                if (a.trim() && !best.includes(a)) {
                    (mark[i] = mark[i] || {})[j] = 1;
                }
            });
        });
    }
    return parts.map((s, i) => (mark[i] ? words(s).map((a, j) => (mark[i][j] ? `<mark>${a}</mark>` : a)).join("").replace(/<\/mark>(\s+)<mark>/g, "$1") : s)).join("");
}
