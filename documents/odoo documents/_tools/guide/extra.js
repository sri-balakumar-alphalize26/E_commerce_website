// New text for the combined guide, written in the same HTML classes the
// module manuals use, so one converter turns everything into Word.
const A = '<span class="arr">→</span>';

const simple = {
  mart369: `<p>This is the <b>base</b> of the whole shop. It puts the <b>369 Mart</b> menu on the main menu and keeps a few settings every other part reads.</p>
<p><b>Example:</b> the logo picker you use for a category comes from here. You set this up once and rarely come back.</p>`,
  mart369_catalog: `<p>A <b>category</b> is an aisle in your shop, like <i>Clothing</i> or <i>Keyboards</i>. A <b>sub-category</b> is a shelf inside it, like <i>T-Shirts</i> inside <i>Clothing</i>.</p>
<p><b>Example:</b> make <i>Clothing</i> first, then <i>T-Shirts</i> under it. Every product you add goes on one or more of these shelves, so customers can find it by browsing, not only by searching.</p>`,
  mart369_product: `<p>A <b>product</b> is one thing you sell, such as a <i>Cotton T-Shirt</i>. An <b>attribute</b> is a choice the customer makes, such as <i>Colour</i> or <i>Size</i>. Each answer, such as <i>Red</i> or <i>Large</i>, is a <b>value</b>.</p>
<p>A <b>variant</b> is one exact version the customer can buy. <b>Example:</b> a T-shirt in 3 colours and 3 sizes makes 3 × 3 = <b>9 variants</b>, and each can have its own photo, price extra and stock. Chapter 6 walks through this exact example.</p>`,
  mart369_home: `<p>The <b>home page</b> is the first screen a customer sees: banners, round category tiles and rows of products.</p>
<p><b>Example:</b> keep an everyday home page, and make a <i>Diwali Sale</i> page with dates. It takes over on its own during the sale and hands back when the sale ends.</p>`,
  mart369_pages: `<p>The <b>footer</b> is the strip at the bottom of every page, with links like <i>Terms</i>, <i>Privacy</i>, <i>FAQs</i> and <i>Contact us</i>. You write those pages here.</p>
<div class="note warn"><span class="lbl">Watch out:</span> The ready-made FAQ says refunds go "back to where you paid from". The shop actually refunds everything to the customer's <b>369 Wallet</b>. Change that FAQ answer before the shop goes live.</div>`,
  mart369_cart: `<p>This chapter decides <b>where you deliver, how fast, and what it costs</b>. There are two kinds of delivery: <b>Quick</b> (in minutes, from a nearby branch that has the stock) and <b>Express</b> (in days, to a wider area).</p>
<p><b>Example:</b> Quick costs 30 below 499 and is free above it. Express costs 49 below 999. You also set the time slots customers pick at checkout, and the deals and coupons that lower the bill.</p>
<div class="note good"><span class="lbl">Good to know:</span> When the <b>Quick or Express</b> app is installed, this same Delivery desk saves into that app's rules, so the website and WhatsApp always charge the same. A basket that mixes Quick and Express items then pays <b>one</b> Express fee.</div>`,
  mart369_address: `<p>Customers keep their <b>delivery addresses</b> here: Home, Work, or any name they like. One of them is the default.</p>
<p><b>Example:</b> before a rider leaves, staff can see that an address has no pincode or no map pin, and fix it. An address an order already went to is never changed afterwards.</p>`,
  mart369_payment: `<p>This chapter is about <b>how customers pay</b>: cash on delivery, the 369 Wallet, and card or UPI through a payment company. Money counts as <b>Paid</b> only when the bank confirms it, or when the rider has collected the cash.</p>
<p><b>Example:</b> a customer pays 600 by UPI. The bank confirms it and the payment shows as <i>Paid</i>. If the order is cancelled, the 600 goes back to the customer's 369 Wallet. Chapter 13 has every payment setup step in one list.</p>`,
  mart369_auth: `<p>Customers <b>sign in with their mobile number</b> and a 6-digit code sent on WhatsApp, so there's no password to forget. The phone number is who they are.</p>
<p><b>Example:</b> a new customer types their number, gets a code on WhatsApp, types it in, and their account is made. Staff see every customer on the <b>Customers</b> desk, marked New, Active or Dormant.</p>`,
  mart369_roles: `<p>Every staff member gets one <b>role</b> that says what job they do: <b>Owner</b>, <b>Manager</b>, <b>Packer</b> or <b>User</b>. The <b>Rider</b> and <b>Accountant</b> ticks can be added on top.</p>
<p><b>Example:</b> give your delivery person the <b>Rider</b> tick so orders can be handed to them. Only the Owner can hand out roles.</p>
<div class="note good"><span class="lbl">Good to know:</span> Today <b>Packer</b> and <b>Accountant</b> only give a plain staff login. Nothing extra checks for them yet.</div>`,
  mart369_order: `<p>The <b>Orders</b> desk is where staff move every order along: <b>Order placed</b> ${A} <b>Packed</b> (Quick) or <b>Shipped</b> (Express) ${A} <b>Out for delivery</b> ${A} <b>Delivered</b>.</p>
<p><b>Example:</b> an item ran out after the customer ordered it. Staff press <b>Remove</b>, or <b>Replace</b> to offer something similar, and the customer chooses on their phone. Only the customer's 6-digit <b>door code</b> can mark an order delivered.</p>`,
  mart369_store_board: `<p>The <b>Counter</b> is the shop's "new orders" screen. When a paid order comes in, an <b>alarm rings</b> and keeps ringing until someone presses <b>Accept</b>.</p>
<p><b>Example:</b> the alarm rings. Staff press <b>Accept</b>, pack the bag, then press <b>Packed - call the rider</b>, and a rider is called automatically.</p>
<div class="note imp"><span class="lbl">Important:</span> The Counter stays empty when <b>Shop Confirms Orders</b> is switched off, because the rider is then called the moment an order is paid. See Chapter 10, step 7.</div>`,
  mart369_whatsapp_bridge: `<p>The shop sells through <b>two doors</b>: the website and app, and WhatsApp chats. This part joins them into <b>one shop</b>, with one list of orders, one customer per phone number, and one price.</p>
<p><b>Example:</b> a website customer gets WhatsApp messages at each step ("Order placed", "Out for delivery"…), their invoice, and the door code for the rider.</p>`,
  mart369_account: `<p>This chapter covers the customer's own things: <b>reviews</b>, <b>referrals</b> (inviting friends), <b>scratch-card rewards</b> and <b>notifications</b>.</p>
<p><b>Example:</b> a review that contains a phone number or a rude word waits for staff to approve it. Other reviews go live straight away.</p>`,
  mart369_support: `<p>This is the <b>help chat</b>. A bot called <b>Mitra</b> answers first, and a person takes over when the customer asks for one.</p>
<p><b>Example:</b> a customer gives a 1-star rating. A support ticket opens on its own, so the team calls them back.</p>`,
  mart369_loyalty: `<p>Customers <b>earn points</b> on every order and can <b>spend them</b> later as money off. By default the points are added once the order is <b>Delivered</b>.</p>
<p><b>Example:</b> points from the shop counter and from online orders sit on the same card, because the card is found by the customer's mobile number.</p>
<div class="note good"><span class="lbl">Good to know:</span> "Points are earned when" and the loyalty on/off switches are set only in the staff console, under <b>Settings ${A} Loyalty</b>.</div>`,
  pos_loyalty_card: `<p>The <b>loyalty card</b> itself: one card per mobile number, the points rule (how many points a purchase earns and what a point is worth) and the points history.</p>
<p><b>Example:</b> you can print or email a customer their card. A deleted card goes to a bin first, so it can be brought back.</p>
<div class="note warn"><span class="lbl">Watch out:</span> <b>Reset to Default</b> resets more than its message says: the card number format, mobile length, welcome message and email server settings. <b>Generate Loyalty Cards</b> also turns Draft and Suspended cards back to Active.</div>`,
  mart369_parts_demo: `<p>Sample products for <b>demos and testing only</b>: a made-up computer parts shop with 92 products. Never install it on the real shop.</p>`,
};

const start = `
<h2>What 369 Mart is</h2>
<p><span class="k">369 Mart</span> is your online shop: a website and a shop app where customers browse, order and pay. Behind it, your team works from the backend. They add products, pack orders at the <b>Counter</b>, and hand them to <b>riders</b>. The customer gets a WhatsApp message at each step.</p>
<div class="flow">
  <div class="card"><b>1. Set up the shop</b><span>Store details, staff, delivery and payments</span></div><span class="to">→</span>
  <div class="card"><b>2. Add products</b><span>Categories, products, choices (variants), photos and stock</span></div><span class="to">→</span>
  <div class="card"><b>3. Customers order</b><span>On the website or app, or on WhatsApp</span></div><span class="to">→</span>
  <div class="card"><b>4. Pack and deliver</b><span>The Counter rings, the shop packs, the rider delivers</span></div>
</div>

<h2>How to read this guide</h2>
<p>Each chapter starts with an <b>In simple words</b> box: what the part is for, with an everyday example. The full steps follow, numbered in orange. Coloured boxes point out what matters:</p>
<div class="note simple"><span class="lbl">In simple words:</span> the short, plain explanation at the top of every chapter.</div>
<div class="note start"><span class="lbl">Before you start:</span> what must be ready before you begin a chapter.</div>
<div class="note tip"><span class="lbl">Tip:</span> a quicker or better way to do something.</div>
<div class="note good"><span class="lbl">Good to know:</span> useful background, nothing to fix.</div>
<div class="note warn"><span class="lbl">Watch out:</span> a common mistake, or something that can't be undone easily.</div>
<div class="note imp"><span class="lbl">Important:</span> a rule the shop always follows.</div>
<p>Menu paths are written like <b>369 Mart ${A} Store ${A} Settings</b>: open <b>369 Mart</b> from the main menu, then <b>Store</b>, then <b>Settings</b>.</p>

<h2>Before you start: what must be installed</h2>
<p>An administrator installs these once, from the <b>Apps</b> screen, <b>in this order</b>. Installing the first one brings in all the 369 Mart parts and the standard pieces they need: website, sales, stock, payments and delivery.</p>
<table>
<thead><tr><th style="width:6%">#</th><th style="width:34%">Install this (name in Apps)</th><th>What it brings</th><th style="width:16%">Needed?</th></tr></thead>
<tbody>
<tr><td>1</td><td>369 Mart Suite<br>(mart369_all)</td><td>All 14 shop parts: home page, products, catalogue, sign-in, addresses, delivery and pricing, payments, orders, roles, account, support, footer pages and loyalty.</td><td>Yes</td></tr>
<tr><td>2</td><td>Sales Automation - Product Confirmation Page<br>(sales_automation_confirm)</td><td>Brings five more with it: WhatsApp Groups (the base), Delivery (riders and tracking), Store Screen (the shop counter queue), Insights and WeChat Vendors.</td><td>Yes</td></tr>
<tr><td>3</td><td>WhatsApp Sales Automation - Quick or Express<br>(sales_automation_quick_express)</td><td>One set of delivery areas, fees and slots for the website and WhatsApp.</td><td>Recommended</td></tr>
<tr><td>4</td><td>369 Mart: New Orders Board<br>(mart369_store_board)</td><td>The Counter with the new-order alarm.</td><td>Yes</td></tr>
<tr><td>5</td><td>369 Mart: WhatsApp Bridge<br>(mart369_whatsapp_bridge)</td><td>WhatsApp messages for every order, the door code, sign-in by WhatsApp code, and riders for website orders.</td><td>Yes</td></tr>
<tr><td>—</td><td>Sales Automation - User Manual</td><td>Help pages only.</td><td>No</td></tr>
<tr><td>—</td><td>369 Mart Sample Catalogue - Computer Parts</td><td>Made-up products for demos.</td><td>Never on the real shop</td></tr>
</tbody></table>
<div class="note warn"><span class="lbl">Watch out:</span> The live database has <b>Store Screen 19.0.9.0.1</b>, but the 369 Mart parts were tested with <b>19.0.6.3.1</b>. Ask the developer to confirm the Counter and the WhatsApp/rider steps on the newer version before going live. A few screen names in Chapter 10 may also look slightly different on it.</div>

<h2>Your setup checklist, in order</h2>
<p>Work down this list once. Each line points to the chapter with the full steps.</p>
<div class="note tip"><span class="lbl">Tip:</span> Do steps 1–3 before adding any products. A product needs a category, and invoices need the store details.</div>
<table>
<thead><tr><th style="width:6%">#</th><th>Do this</th><th style="width:34%">Where</th><th style="width:12%">Chapter</th></tr></thead>
<tbody>
<tr><td>1</td><td>Fill in the store's name, phone, address and GSTIN.</td><td>Store ${A} Settings ${A} Store tab</td><td>12</td></tr>
<tr><td>2</td><td>Give each staff member a role. Give riders the Rider tick.</td><td>Store ${A} Staff &amp; roles</td><td>15</td></tr>
<tr><td>3</td><td>Build the category tree: main categories, then sub-categories.</td><td>Catalogue ${A} Catalog</td><td>4</td></tr>
<tr><td>4</td><td>Decide what every product page shows.</td><td>Store ${A} Product Page</td><td>5</td></tr>
<tr><td>5</td><td>Add products with attributes, variants, photos and stock.</td><td>Store ${A} Product pages</td><td>5 and 6</td></tr>
<tr><td>6</td><td>Build the home page.</td><td>Store ${A} Home Page</td><td>7</td></tr>
<tr><td>7</td><td>Write the footer and the info pages (Terms, Privacy, FAQs…).</td><td>Page building</td><td>8</td></tr>
<tr><td>8</td><td>Set up delivery: fees, areas, slots, branches, shops and riders.</td><td>Store ${A} Delivery, and the Delivery app</td><td>9 and 10</td></tr>
<tr><td>9</td><td>Set up payments: cash on delivery, the 369 Wallet, card and UPI.</td><td>Store ${A} Settings ${A} Payments tab</td><td>12 and 13</td></tr>
<tr><td>10</td><td>Choose the WhatsApp number that sends updates, and the message words.</td><td>Store ${A} Settings</td><td>18</td></tr>
<tr><td>11</td><td>Write the support bot's answers.</td><td>Store ${A} Bot answers</td><td>20</td></tr>
<tr><td>12</td><td>Switch loyalty on and check the points rule.</td><td>Loyalty Card, and the staff console</td><td>21 and 22</td></tr>
<tr><td>13</td><td>Place one test order from start to finish.</td><td>The website</td><td>2</td></tr>
</tbody></table>
`;

const flow = `
<p>This is the whole life of one order, from the moment a customer finds a product to the moment it reaches their door.</p>
<div class="flow">
  <div class="card"><b>1. Customer orders</b><span>Finds, chooses, signs in, pays</span></div><span class="to">→</span>
  <div class="card"><b>2. Shop packs</b><span>Alarm rings, Accept, pack</span></div><span class="to">→</span>
  <div class="card"><b>3. Rider delivers</b><span>Pick-up, on the way, door code</span></div><span class="to">→</span>
  <div class="card"><b>4. After delivery</b><span>Rating, points, support</span></div>
</div>

<div class="part">Stage 1 — The customer orders</div>
<table>
<thead><tr><th style="width:6%">#</th><th style="width:26%">Step</th><th>What happens</th></tr></thead>
<tbody>
<tr><td>1</td><td>Finds the product</td><td>By searching, from a category page, or from the home page. Each product shows its price, its old price (MRP, struck through) when there's a discount, and Quick or Express.</td></tr>
<tr><td>2</td><td>Picks a choice</td><td>Colour, size and so on (the <b>variants</b>). The photo, price and "Only N left" change with the choice. Then <b>Add to cart</b>.</td></tr>
<tr><td>3</td><td>Signs in</td><td>Types a mobile number and gets a 6-digit code on WhatsApp. No password is needed.</td></tr>
<tr><td>4</td><td>Delivery address</td><td>Picks a saved address, or adds one with <b>Use my current location</b> and a map pin.</td></tr>
<tr><td>5</td><td>Quick or Express</td><td><b>Quick</b> when a branch close enough has every item in stock. Otherwise <b>Express</b>. The delivery fee and the time slots follow from that.</td></tr>
<tr><td>6</td><td>Coupon, points, wallet</td><td>Can add a coupon code, take loyalty points off, or use money in the 369 Wallet.</td></tr>
<tr><td>7</td><td>Pays</td><td>UPI, card or net banking (when a payment company is set up), cash on delivery (up to the limit), or the 369 Wallet.</td></tr>
<tr><td>8</td><td>Order placed</td><td>WhatsApp: <b>"Order placed"</b>. The customer's app holds the 6-digit <b>door code</b>.</td></tr>
</tbody></table>

<div class="part">Stage 2 — The shop packs</div>
<table>
<thead><tr><th style="width:6%">#</th><th style="width:26%">Step</th><th>What happens</th></tr></thead>
<tbody>
<tr><td>9</td><td>The alarm rings</td><td>On the <b>Counter</b>, and on any backend screen, until someone accepts. There is one alarm for the whole waiting queue.</td></tr>
<tr><td>10</td><td>Accept</td><td>Staff choose which company's stock it comes from. If nobody has it, <b>No stock anywhere - order from supplier</b> asks suppliers on WhatsApp. The customer is told the order is approved and being packed.</td></tr>
<tr><td>11</td><td>Pack</td><td>Staff collect the items. A <b>Picklist</b> for several orders saves walking.</td></tr>
<tr><td>12</td><td>Packed - call the rider</td><td>The customer is told it's packed, and a rider is called automatically.</td></tr>
</tbody></table>
<div class="note tip"><span class="lbl">Tip:</span> Missing one item? Use <b>Remove</b>, or <b>Replace</b> to offer something similar. Cancel the whole order only when nothing can go (Chapter 16).</div>

<div class="part">Stage 3 — The rider delivers</div>
<table>
<thead><tr><th style="width:6%">#</th><th style="width:26%">Step</th><th>What happens</th></tr></thead>
<tbody>
<tr><td>13</td><td>Job offered</td><td>Riders who are <b>On Duty</b> are offered the job on WhatsApp or in the rider app. Your own riders come before outside couriers.</td></tr>
<tr><td>14</td><td>Pick-up</td><td>The shop's WhatsApp number receives a <b>pickup code</b>. Staff read it to the rider when handing over the parcel, which proves the rider collected it.</td></tr>
<tr><td>15</td><td>Out for delivery</td><td>WhatsApp to the customer: <b>"Out for delivery"</b>, with a link to follow the rider on a live map.</td></tr>
<tr><td>16</td><td>At the door</td><td>The customer reads out the 6-digit <b>door code</b>. Only this code marks the order <b>Delivered</b>. Cash on delivery is collected at this point.</td></tr>
</tbody></table>
<div class="note imp"><span class="lbl">Important:</span> Staff never see the door code. A wrong or already-used code always gets the same answer, "That delivery code is not right.", so it can't be guessed.</div>

<div class="part">Stage 4 — After delivery</div>
<table>
<thead><tr><th style="width:6%">#</th><th style="width:26%">Step</th><th>What happens</th></tr></thead>
<tbody>
<tr><td>17</td><td>Delivered</td><td>WhatsApp: <b>"Delivered"</b>, with the invoice. The goods leave stock.</td></tr>
<tr><td>18</td><td>Points</td><td>Loyalty points are added (by default when the order is Delivered).</td></tr>
<tr><td>19</td><td>Rating</td><td>The customer rates the order. A 1- or 2-star rating opens a <b>support ticket</b> on its own.</td></tr>
<tr><td>20</td><td>Returns</td><td>The customer can ask for a refund or a replacement. The money always goes to the <b>369 Wallet</b>.</td></tr>
</tbody></table>

<h2>The order's status, step by step</h2>
<table>
<thead><tr><th style="width:24%">Status</th><th>Meaning</th><th style="width:30%">What moves it on</th></tr></thead>
<tbody>
<tr><td>Order placed</td><td>Paid, or cash on delivery accepted.</td><td>Accept on the Counter, or Start packing / Mark shipped</td></tr>
<tr><td>Packed</td><td>Quick orders: packed in the store.</td><td>Send out / Packed - call the rider</td></tr>
<tr><td>Shipped</td><td>Express orders: sent from the store.</td><td>Send out</td></tr>
<tr><td>Out for delivery</td><td>With the rider.</td><td>Mark delivered (door code), or Couldn't deliver?</td></tr>
<tr><td>Delivered</td><td>Closed with the customer's door code.</td><td>— (returns go through the Returns desk)</td></tr>
<tr><td>Cancelled</td><td>Cancelled before leaving, or returned to the store.</td><td>—</td></tr>
</tbody></table>

<h2>Which WhatsApp message goes when</h2>
<table>
<thead><tr><th style="width:28%">Message</th><th>Sent when</th></tr></thead>
<tbody>
<tr><td>Sign-in code</td><td>The customer signs in or signs up with their number.</td></tr>
<tr><td>Order placed</td><td>The order is paid, or cash on delivery is accepted.</td></tr>
<tr><td>Packed / Shipped</td><td>The shop finishes packing (Quick) or sends it out (Express).</td></tr>
<tr><td>Out for delivery</td><td>The rider has the parcel. Includes the tracking link.</td></tr>
<tr><td>Delivered + invoice</td><td>The door code was accepted.</td></tr>
<tr><td>Cancelled</td><td>The order is cancelled. Any money paid goes back to the 369 Wallet.</td></tr>
</tbody></table>
<p>The words of each message can be changed, and each one can be switched off, in Chapter 18, step 3.</p>

<h2>Test it yourself: one test order</h2>
<ul class="f">
  <li><b>1.</b> On the website, add one in-stock product to the cart and sign in with a test mobile number.</li>
  <li><b>2.</b> Pick an address inside a service area, and choose a slot.</li>
  <li><b>3.</b> Pay with <b>Cash on delivery</b>.</li>
  <li><b>4.</b> In the backend, check that the Counter rings. Press <b>Accept</b>, then <b>Packed - call the rider</b>.</li>
  <li><b>5.</b> Check that a rider who is On Duty gets the job.</li>
  <li><b>6.</b> Mark it delivered with the door code from the customer's app, and check that the cash shows as collected.</li>
  <li><b>7.</b> Check that the WhatsApp messages arrived at every step.</li>
</ul>
`;

const example = `
<p>This chapter sets up one real product from start to finish, so you can see how <b>categories</b>, <b>products</b>, <b>attributes</b> and <b>variants</b> fit together. The example is a <i>Cotton T-Shirt</i> in 3 colours and 3 sizes.</p>
<div class="flow">
  <div class="card"><b>1. Category</b><span>Clothing, with T-Shirts under it</span></div><span class="to">→</span>
  <div class="card"><b>2. Product</b><span>Cotton T-Shirt: name, price, photos</span></div><span class="to">→</span>
  <div class="card"><b>3. Attributes</b><span>Colour and Size</span></div><span class="to">→</span>
  <div class="card"><b>4. Variants</b><span>9 versions, each with its photo and stock</span></div>
</div>

<h2>The four words, side by side</h2>
<table>
<thead><tr><th style="width:20%">Word</th><th>What it means</th><th style="width:34%">In this example</th></tr></thead>
<tbody>
<tr><td>Category</td><td>An aisle or shelf in the shop.</td><td>Clothing ${A} T-Shirts</td></tr>
<tr><td>Product</td><td>One thing you sell, with one page in the shop.</td><td>Cotton T-Shirt</td></tr>
<tr><td>Attribute</td><td>A choice the customer makes.</td><td>Colour, Size</td></tr>
<tr><td>Value</td><td>One answer to that choice.</td><td>Red, Blue, Black · S, M, L</td></tr>
<tr><td>Variant</td><td>One exact version that can be bought, with its own stock.</td><td>Red / M (one of 9)</td></tr>
</tbody></table>

<h3 class="step"><span class="n">1</span>Make the category</h3>
<p>Open <b>369 Mart ${A} Catalogue ${A} Catalog</b> and press <b>New category</b>.</p>
<ul class="f">
  <li><b>Name</b> — type <i>Clothing</i>. Leave <b>Under</b> on <b>None - a top-level category</b>. Press <b>Create</b>.</li>
  <li>Press <b>New category</b> again. <b>Name</b>: <i>T-Shirts</i>. <b>Under</b>: <i>Clothing</i>. Press <b>Create</b>.</li>
</ul>
<div class="note good"><span class="lbl">Good to know:</span> Each category also makes a matching product <b>Category</b>, which you'll pick on the product in step 2. The two always stay in step.</div>

<h3 class="step"><span class="n">2</span>Add the product</h3>
<p>Open <b>369 Mart ${A} Store ${A} Product pages</b> and press <b>New product</b>. Fill in <b>Basics</b>:</p>
<ul class="f">
  <li><b>Name</b> — <i>Cotton T-Shirt</i> (required).</li>
  <li><b>Category</b> — <i>T-Shirts</i> (required: every product needs one).</li>
  <li><b>Categories</b> — tick <i>T-Shirts</i>. These are the aisles customers browse.</li>
  <li><b>Price</b> — <i>499</i>. <b>MRP</b> — <i>699</i> (the old, struck-through price; leave it empty if there's no discount). <b>Cost</b> — <i>250</i> (customers never see it).</li>
  <li><b>Photographs</b> — press <b>Add</b>. The first photo is the one on the product card.</li>
</ul>
<p>Press <b>Create product</b>, or <b>Ctrl+S</b>. A product made here is published straight away.</p>

<h3 class="step"><span class="n">3</span>Add the attributes (the choices)</h3>
<p>Still in the product, find <b>Attributes &amp; Variants</b> (<i>What the customer chooses</i>).</p>
<ul class="f">
  <li>Press <b>+ Add an attribute</b> and pick <b>Colour</b>. Tap <i>Red</i>, <i>Blue</i> and <i>Black</i> to pick them. If a value isn't there, type it in <b>+ value</b>.</li>
  <li>To make Black cost more, type <i>50</i> in its <b>+</b> box. Black then sells for 549.</li>
  <li>Press <b>+ Add an attribute</b> again and pick <b>Size</b>, with <i>S</i>, <i>M</i> and <i>L</i>.</li>
  <li>An attribute marked <i>Information only - makes no variants</i> (for example <i>Material</i>) is shown on the page but gives no choice.</li>
</ul>
<p>Press <b>Save</b>. The shop now makes the variants: 3 colours × 3 sizes = <b>9 variants</b>.</p>
<div class="note warn"><span class="lbl">Watch out:</span> Adding or deleting an attribute deletes the variants and makes them again. Finish all the choices <b>before</b> you add photos and stock to each variant.</div>

<h3 class="step"><span class="n">4</span>Give each variant its photo and stock</h3>
<p>Under <b>Variants</b>, each of the 9 rows shows its price. Open one, for example <i>Red / M</i>:</p>
<ul class="f">
  <li><b>Image</b> — a photo of the red T-shirt. A variant without its own photo uses the product's general picture.</li>
  <li><b>On hand</b> — how many you have, for example <i>20</i>. It is saved as a stock adjustment.</li>
</ul>
<p>Repeat for each variant. When the customer picks <i>Red</i> and <i>M</i>, they see that photo and that stock.</p>

<h3 class="step"><span class="n">5</span>Fill in the rest of the page</h3>
<ul class="f">
  <li><b>About this item</b> — bullet points, typed like a Word page. Shoppers see the first 5.</li>
  <li><b>Product details</b> — short label and value lines, such as <i>Material: Cotton</i> or <i>Warranty: 1 year</i>.</li>
  <li><b>Trust badges</b> — tick <b>Returns</b>, <b>Cash on delivery</b> and so on to show them on this product.</li>
  <li><b>Website only</b> — <b>Badge</b> (New, Bestseller, Sale…), <b>Warn when stock reaches</b> (the "Only N left" level) and <b>Pack size</b>.</li>
</ul>

<h3 class="step"><span class="n">6</span>Check how shoppers see it</h3>
<p>On the right, <b>How shoppers see it</b> shows the real shop page. Switch between <b>Desktop</b> and <b>Phone</b>, and press <b>Refresh</b> after saving. Tap any part of the preview to jump to the box that fills it.</p>
<p>Finally, open the website and check: the T-shirt appears under <b>Clothing ${A} T-Shirts</b>, all 9 choices work, and Black shows 549.</p>
<div class="note tip"><span class="lbl">Tip:</span> Use <b>369 Mart ${A} Catalogue ${A} Products</b> to watch stock afterwards. Low-stock rows turn amber, and out-of-stock rows turn red.</div>
`;

const delivery = `
<p>This chapter puts <b>every delivery setting in one order</b>, from "where do we deliver" to "which rider gets the job". Steps 1–4 are on the 369 Mart <b>Delivery</b> desk (full detail in Chapter 9). Steps 5–8 are in the <b>Delivery</b> app, where shops and riders are set up.</p>
<div class="flow">
  <div class="card"><b>1. Where</b><span>Service areas (pincodes) and branches</span></div><span class="to">→</span>
  <div class="card"><b>2. How much</b><span>Fees, minimum order, free-delivery amount</span></div><span class="to">→</span>
  <div class="card"><b>3. When</b><span>Slots and promised times</span></div><span class="to">→</span>
  <div class="card"><b>4. Who</b><span>Shops, riders, counter alarm</span></div>
</div>
<div class="note start"><span class="lbl">Before you start:</span> You need the <b>Owner</b> or <b>Manager</b> role for the Delivery desk, and Delivery manager rights for the Delivery app's <b>Configuration</b> menu. Each branch must exist as a warehouse.</div>

<h3 class="step"><span class="n">1</span>Mark the pincodes you deliver to</h3>
<p>Open <b>369 Mart ${A} Store ${A} Delivery ${A} Service areas</b>. Add one row per pincode, or per pincode start (for example <i>68</i> covers everything that starts with 68). For each row, switch <b>Quick delivery</b> and <b>Express delivery</b> on or off, and type the <b>Delivery promise</b>. (Chapter 9, step 3.)</p>
<div class="note warn"><span class="lbl">Watch out:</span> Remove the sample areas <b>67, 68 and 69</b> unless you really deliver there. With no area at all, every pincode is told "We don't deliver to this pincode yet."</div>

<h3 class="step"><span class="n">2</span>Set the delivery fees</h3>
<p>Open the <b>Fees</b> tab. For <b>Quick</b> and for <b>Express</b>, fill in <b>Shown as</b>, <b>Delivery promise</b>, <b>Minimum order</b>, <b>Free delivery above</b> and <b>Delivery fee</b>, then press <b>Save Quick</b> or <b>Save Express</b>. (Chapter 9, step 2.)</p>
<table>
<thead><tr><th style="width:30%">Starting numbers</th><th>Quick</th><th>Express</th></tr></thead>
<tbody>
<tr><td>Delivery promise</td><td>Delivery in 13 mins</td><td>Delivery in 2–3 days</td></tr>
<tr><td>Minimum order</td><td>99</td><td>0 (none)</td></tr>
<tr><td>Free delivery above</td><td>499</td><td>999</td></tr>
<tr><td>Delivery fee</td><td>30</td><td>49</td></tr>
</tbody></table>

<h3 class="step"><span class="n">3</span>Set the delivery slots</h3>
<p>Open the <b>Slots</b> tab. Check the starting slots (Now, Today 6 – 8 PM, Tomorrow 8 – 10 AM, Tomorrow 6 – 8 PM for Quick, and Standard and Priority for Express). Edit their hours, <b>Stop offering after</b>, <b>Extra fee</b> and <b>Orders per slot</b>. (Chapter 9, step 4.)</p>
<div class="note tip"><span class="lbl">Tip:</span> Each storefront needs at least one slot switched on, or it has nothing to offer at checkout.</div>

<h3 class="step"><span class="n">4</span>Switch on Quick delivery at each branch</h3>
<p>Open the <b>Branches</b> tab and press <b>Edit</b> on a branch. Switch <b>Quick delivery</b> on, set <b>Reach (km)</b>, and paste the branch's <b>Latitude / Longitude</b> from Google Maps. A branch without a map pin or reach shows <b>Not ready</b>. (Chapter 9, step 5.)</p>

<h3 class="step"><span class="n">5</span>Add your shops</h3>
<p>Open the <b>Delivery</b> app from the main menu, then <b>Configuration ${A} Shops</b>, and press <b>New</b>. One row per place a rider collects from:</p>
<ul class="f">
  <li><b>Shop</b> — the shop's name (required).</li>
  <li><b>Warehouse</b> — where the stock leaves from (required).</li>
  <li><b>Address</b> — where the rider collects. Leave it empty to use the warehouse's address.</li>
  <li><b>Shop WhatsApp Number</b> — receives the <b>pickup code</b>. Staff read it to the rider when handing over the parcel.</li>
  <li><b>Service Areas</b> — the areas this shop covers, separated by commas (for example <i>ruwi, qurum, azaiba</i>). Leave it empty and the shop is chosen only by distance, or as the fallback.</li>
  <li><b>Riders and Couriers</b> — who may deliver from this shop.</li>
</ul>
<div class="note good"><span class="lbl">Good to know:</span> The shop at the top of the list is the fallback, used when an address matches no area and nothing can be measured. Drag the rows to change the order.</div>

<h3 class="step"><span class="n">6</span>Add your riders</h3>
<p>Open <b>Configuration ${A} Riders &amp; Couriers</b> and press <b>New</b>:</p>
<ul class="f">
  <li><b>Name</b> — the rider's name (required).</li>
  <li><b>Kind</b> — <b>Own Rider</b> or <b>Delivery Partner</b> (an outside courier). Own riders are always offered a job first.</li>
  <li><b>WhatsApp Number</b> — digits with the country code, for example <i>96891234567</i> (required). Jobs go to this number, and only replies from it count.</li>
  <li><b>Shops Served</b> — leave it empty to serve every shop.</li>
  <li><b>On Duty</b> — only riders on duty are offered new work. A rider who goes off duty keeps the jobs already in hand.</li>
  <li><b>Timezone</b>, <b>Contact</b> and <b>Notes</b> — optional.</li>
</ul>
<p>Also give the same person the <b>Rider</b> tick in <b>Store ${A} Staff &amp; roles</b> (Chapter 15), so website orders can be handed to them.</p>

<h3 class="step"><span class="n">7</span>Delivery Settings: times, the counter and its alarm</h3>
<p>Open <b>Configuration ${A} Delivery Settings</b>. There is only one of these, for the whole business:</p>
<table>
<thead><tr><th style="width:36%">Setting</th><th style="width:14%">Starts at</th><th>What it does</th></tr></thead>
<tbody>
<tr><td>Offer Quick Delivery</td><td>On</td><td>When every item is in stock at the chosen shop, the customer is promised the Quick time below.</td></tr>
<tr><td>Quick Delivery Within (hours)</td><td>4</td><td>The promised time when the goods are on the shelf. Set what a rider really needs, not the best case.</td></tr>
<tr><td>Express Delivery Within (days)</td><td>3</td><td>The promised time when something has to be ordered in from a supplier first. Include the supplier's own time.</td></tr>
<tr><td>Same-Day Cut-off (hour, 0-23)</td><td>16</td><td>An in-stock order confirmed after this hour is promised for the next day. 16 means after 4 PM. 0 means never roll over.</td></tr>
<tr><td>Tell the Customer the Date</td><td>On</td><td>Puts the promised date in the WhatsApp message and on the tracking page.</td></tr>
<tr><td>Shop Confirms Orders</td><td>On</td><td><b>On:</b> a paid order waits on the Counter until staff accept it and say it's packed, and only then is a rider called. <b>Off:</b> the rider is called the moment it's paid, and the Counter stays empty.</td></tr>
<tr><td>Ring For (seconds)</td><td>30</td><td>How long one ring of the new-order alarm lasts.</td></tr>
<tr><td>Alarm Repeats Every (s)</td><td>10</td><td>The rest between rings. It keeps ringing until every waiting order is accepted.</td></tr>
<tr><td>No-Reply alarm (ring, repeat, stop after)</td><td>30 s, 2 min, 10 min</td><td>The alarm when no supplier has answered a price request.</td></tr>
<tr><td>Remind About Waiting Stock At (hour)</td><td>9</td><td>Each morning, each shop gets one WhatsApp listing what it is still waiting for from suppliers.</td></tr>
<tr><td>Keep Reminding For (days)</td><td>0</td><td>0 keeps reminding until the goods are marked arrived.</td></tr>
<tr><td>Enquiry alarm (ring, repeat, stop after)</td><td>30 s, 10 s, 1 min</td><td>The alarm for new WhatsApp enquiries waiting for a supplier choice.</td></tr>
<tr><td>Return OTPs in the API (testing only)</td><td>Off</td><td>For developers only.</td></tr>
</tbody></table>
<div class="note warn"><span class="lbl">Watch out:</span> Keep <b>Return OTPs in the API (testing only)</b> <b>off</b> on the real shop. When it's on, the code that proves a customer received their parcel can be read by anyone holding a rider's login.</div>
<div class="note imp"><span class="lbl">Important:</span> If <b>Shop Confirms Orders</b> is off, the <b>Counter</b> (Chapter 17) stays empty.</div>

<h3 class="step"><span class="n">8</span>Check cash on delivery is allowed</h3>
<p>Cash on delivery is offered only when the order's delivery method allows cash. In the backend's shipping methods, open <b>Standard delivery</b> and make sure <b>Cash on Delivery</b> is ticked. The cash limit itself is set in Chapter 13, step 3.</p>

<h3 class="step"><span class="n">9</span>Watch deliveries every day</h3>
<p>The Delivery app's <b>Deliveries</b> menu lists jobs by stage:</p>
<table>
<thead><tr><th style="width:30%">Menu</th><th>Shows</th></tr></thead>
<tbody>
<tr><td>To Dispatch</td><td>Packed and waiting for a rider. A job no rider took can be handed out by hand here.</td></tr>
<tr><td>In Progress</td><td>Offered, accepted, picked up, or out for delivery.</td></tr>
<tr><td>Same Day Delivery / Express Delivery</td><td>Jobs split by delivery speed.</td></tr>
<tr><td>Delivered</td><td>Finished jobs.</td></tr>
<tr><td>Failed</td><td>Couldn't be delivered: follow up with the customer.</td></tr>
<tr><td>All Deliveries</td><td>Everything.</td></tr>
<tr><td>Reporting ${A} Delivery Analysis</td><td>Numbers per rider, shop and day.</td></tr>
</tbody></table>
<p>The stages a job goes through: <b>To Dispatch</b> ${A} <b>Offered</b> ${A} <b>Accepted</b> ${A} <b>Picked Up</b> ${A} <b>Out for Delivery</b> ${A} <b>Delivered</b>. It can also end as <b>Coming Back</b> / <b>Returned to Shop</b>, <b>Cancelled</b> or <b>Failed</b>.</p>

<h2>Delivery checklist</h2>
<ul class="tips">
  <li>Every pincode you serve is on <b>Service areas</b>, and the sample ones are removed.</li>
  <li>Quick and Express fees are checked and saved.</li>
  <li>At least one slot is on for Quick and one for Express.</li>
  <li>Every Quick branch shows <b>Ready</b> (it has a pin and a reach above 0).</li>
  <li>Every shop has a warehouse and a Shop WhatsApp Number.</li>
  <li>Every rider has a WhatsApp number, is <b>On Duty</b> when working, and has the <b>Rider</b> tick.</li>
  <li><b>Shop Confirms Orders</b> is on, and the test-only OTP switch is off.</li>
  <li>A test order went all the way to <b>Delivered</b> (Chapter 2).</li>
</ul>
`;

const payment = `
<p>This chapter lists <b>every payment step in order</b>: which ways of paying the checkout offers, how to switch on card and UPI, the cash limit, and the 369 Wallet. The screens are described in full in Chapter 12.</p>
<div class="flow">
  <div class="card"><b>1. Store details</b><span>Name and GSTIN for invoices</span></div><span class="to">→</span>
  <div class="card"><b>2. Card and UPI</b><span>Connect a payment company</span></div><span class="to">→</span>
  <div class="card"><b>3. Cash and wallet</b><span>Cash limit, wallet on</span></div><span class="to">→</span>
  <div class="card"><b>4. Test</b><span>One paid order, one cash order</span></div>
</div>
<div class="note start"><span class="lbl">Before you start:</span> You need <b>Administrator (Settings)</b> rights. For card and UPI, you also need an account with a payment company (for example Razorpay or Stripe) and the keys it gives you.</div>

<h2>The ways a customer can pay</h2>
<table>
<thead><tr><th style="width:24%">Way to pay</th><th>How it works</th><th style="width:28%">When it counts as paid</th></tr></thead>
<tbody>
<tr><td>UPI, card, net banking</td><td>Through a payment company (a "gateway"). Needs keys from that company.</td><td>When the bank confirms it.</td></tr>
<tr><td>Cash on delivery</td><td>The customer pays the rider at the door. Only up to the cash limit, and only if the delivery method allows cash.</td><td>When the cash is collected.</td></tr>
<tr><td>369 Wallet</td><td>The customer's balance in the shop. Refunds and rewards land here. Off until you switch it on.</td><td>At once, if the balance covers it.</td></tr>
<tr><td>Loyalty points and coupons</td><td>Not a way to pay, but they take money off the bill before paying.</td><td>—</td></tr>
</tbody></table>

<h3 class="step"><span class="n">1</span>Fill in the store's details</h3>
<p>Open <b>369 Mart ${A} Store ${A} Settings</b>, on the <b>Store</b> tab. Fill in <b>Store name</b> (required), <b>Phone</b>, <b>Email</b>, <b>Address</b>, <b>Area</b>, <b>City</b>, <b>PIN code</b> and <b>GSTIN</b>, then press <b>Save changes</b>. These print on every invoice.</p>

<h3 class="step"><span class="n">2</span>Switch on card and UPI (a payment company)</h3>
<p>Card and UPI can't be switched on from the Payments tab until the payment company's keys are in. Do this once:</p>
<ul class="f">
  <li><b>1. Open the list</b> — on <b>Store ${A} Settings ${A} Payments</b>, press <b>Open payment providers</b>.</li>
  <li><b>2. Pick your company</b> — for example <b>Razorpay</b> (popular in India for UPI) or <b>Stripe</b>. If its card shows <b>Install</b> or <b>Activate</b>, press it first.</li>
  <li><b>3. Enter the keys</b> — open it. On the <b>Credentials</b> tab, paste the keys from your payment company's dashboard (for example a key ID, a key secret and a webhook secret), or press its <b>Connect</b> button if it shows one.</li>
  <li><b>4. Start in test mode</b> — set <b>State</b> to <b>Test Mode</b> and save. Place a test order with the company's test card or UPI ID.</li>
  <li><b>5. Choose the methods</b> — on the <b>Configuration</b> tab, check which <b>Payment Methods</b> it offers (UPI, cards, net banking…), and remove any you don't want.</li>
  <li><b>6. Go live</b> — when the test works, set <b>State</b> to <b>Enabled</b> and make sure it is <b>Published</b>.</li>
  <li><b>7. Check the Payments tab</b> — back on <b>Store ${A} Settings ${A} Payments</b>, the gateway now shows with an <b>On</b> (or <b>Test mode</b>) tag.</li>
</ul>
<div class="note warn"><span class="lbl">Watch out:</span> The exact boxes on the Credentials tab are different for each payment company. Copy the keys exactly, and never share the secret key by chat or email.</div>
<div class="note good"><span class="lbl">Good to know:</span> Card details never touch the shop. The payment company handles them, and only the last four digits of a saved card are kept.</div>

<h3 class="step"><span class="n">3</span>Set cash on delivery and its limit</h3>
<p>On the <b>Payments</b> tab, switch <b>Cash on delivery</b> on and set the <b>Cash on delivery limit</b> (starts at 5,000). Orders above the limit must be paid another way. The limit is checked against the cash the rider would collect, after any wallet money is taken off.</p>
<div class="note warn"><span class="lbl">Watch out:</span> A limit of 0 means "no limit", but it is put back to 5,000 every time the payments part is updated. Check the limit after every update.</div>
<p>Also make sure the delivery method allows cash (Chapter 10, step 8). Staff can turn cash off for one customer from their order (Chapter 16).</p>

<h3 class="step"><span class="n">4</span>Switch on the 369 Wallet</h3>
<p>On the <b>Payments</b> tab, switch <b>369 Wallet</b> on. It starts <b>Off</b>, so a new shop never takes wallet money by surprise. Its fixed limits:</p>
<ul class="f">
  <li><b>Wallet limit</b> — 10,000, the most a wallet can hold from top-ups and rewards. A refund always lands, even in a full wallet.</li>
  <li><b>Smallest top-up</b> — 10.</li>
  <li><b>Never below zero</b> — a payment larger than the balance is refused.</li>
</ul>
<div class="note imp"><span class="lbl">Important:</span> Every refund, for a cancelled order, a removed item or a return, goes to the 369 Wallet, with a credit note. Switch the wallet on before the shop goes live.</div>

<h3 class="step"><span class="n">5</span>Set the alerts</h3>
<p>On the <b>Alerts</b> tab, keep <b>New orders</b> and <b>Low stock</b> on. They show as a badge and bell in the staff console.</p>

<h3 class="step"><span class="n">6</span>Every day: collect the cash</h3>
<p>When a rider brings back cash, open <b>Money ${A} Payments</b>, find the order, and press <b>Cash collected</b>. This is the only button that marks money as paid by hand. An order delivered with the door code is marked collected automatically.</p>

<h3 class="step"><span class="n">7</span>Test both ways of paying</h3>
<ul class="f">
  <li><b>Online</b> — place a test order with the gateway in Test Mode. On <b>Money ${A} Payments</b>, it should show <b>Paid</b>.</li>
  <li><b>Cash</b> — place a cash on delivery order under the limit. It should wait until delivered, then show collected.</li>
  <li><b>Over the limit</b> — try a cash order above the limit. Cash should not be offered.</li>
  <li><b>Refund</b> — cancel the paid test order. The money should appear in the customer's 369 Wallet.</li>
</ul>

<h2>Payments checklist</h2>
<ul class="tips">
  <li>Store name, address and GSTIN are filled in.</li>
  <li>The card/UPI gateway is <b>Enabled</b> and <b>Published</b>, not left in Test Mode.</li>
  <li>Cash on delivery is on, the limit is right, and Standard delivery allows cash.</li>
  <li>The 369 Wallet is <b>On</b>.</li>
  <li>The New orders and Low stock alerts are on.</li>
  <li>The online, cash and refund tests all worked.</li>
</ul>
`;

module.exports = { simple, start, flow, example, delivery, payment };
