/* Sample catalogue. In production pass the same shape from /api/products.
   `images` = product photos in display order (card shows arrows + dots when there
   are 2 or more). The sample photos live in /public/images and are generated from
   art.jsx by `npm run images` — replace the files with real photos, same names. */

const pics = (id, n) => Array.from({ length: n }, (_, k) => `/images/products/${id}-${k + 1}.svg`);

export const TABS = [
  { key: "home", label: "My Home", icon: "bag" },
  { key: "grocery", label: "Groceries", icon: "basket" },
  { key: "fruits", label: "Fruits & Veg", icon: "leaf" },
  { key: "electronics", label: "Electronics", icon: "plug" },
  { key: "kitchen", label: "Home & Kitchen", icon: "pot" },
  { key: "stationery", label: "Stationery", icon: "pen" },
  { key: "coupons", label: "Coupons", icon: "ticket" },
];

export const BANNERS = [
  { id: "b1", kicker: "Fresh fruit week", title: "Fruits picked this morning", note: "Up to 30% off", tone: "green", art: ["Apple", "Orange", "Banana"] },
  { id: "b2", kicker: "Tech week", title: "Audio & chargers", note: "Up to 46% off", tone: "navy", art: ["Headphones", "Speaker"] },
  { id: "b3", kicker: "Festive gifting", title: "Dry fruit delights", note: "Up to 40% off", tone: "brown", art: ["Box", "Jar"] },
  { id: "b4", kicker: "Back to office", title: "Desk & stationery", note: "From ₹49", tone: "orange", art: ["Lamp", "Flask"] },
];

export const CATEGORIES = [
  { key: "fruits", image: "/images/categories/q-fruits.svg", label: "Fresh fruits", art: "Apple", bg: "#fdecec" },
  { key: "veg", image: "/images/categories/q-veg.svg", label: "Vegetables", art: "Grapes", bg: "#eef7e4" },
  { key: "staples", image: "/images/categories/q-staples.svg", label: "Atta & staples", art: "Pack", color: "#b0662a", t: "ATTA", bg: "#fbf0e4" },
  { key: "oil", image: "/images/categories/q-oil.svg", label: "Oils & ghee", art: "Bottle", color: "#d4a017", t: "OIL", bg: "#fdf6dd" },
  { key: "snacks", image: "/images/categories/q-snacks.svg", label: "Chocolates", art: "Bar", color: "#5a2e1c", t: "70%", bg: "#f5ece6" },
  { key: "audio", image: "/images/categories/q-audio.svg", label: "Audio", art: "Headphones", bg: "#e8f1f8" },
  { key: "kitchen", image: "/images/categories/q-kitchen.svg", label: "Kitchen", art: "Plates", bg: "#fbefe6" },
  { key: "stationery", image: "/images/categories/q-stationery.svg", label: "Office desk", art: "Lamp", bg: "#fff1e2" },
];

export const SECTIONS = [
  {
    key: "fruits",
    title: "Fresh fruits",
    subtitle: "Handpicked, delivered in minutes",
    items: [
      { id: "f1", images: pics("f1", 3), name: "Yelakki Banana", unit: "500 g", price: 79, veg: true, art: "Banana" },
      { id: "f2", images: pics("f2", 3), name: "Robusta Banana 1 kg", unit: "1 kg", price: 69, perUnit: "₹17.25 / 250 g", veg: true, art: "Banana" },
      { id: "f3", images: pics("f3", 3), name: "Shimla Apple 1 kg", unit: "1 kg", price: 229, mrp: 279, veg: true, art: "Apple" },
      { id: "f4", images: pics("f4", 3), name: "Pomegranate Bhagwa 400 g", unit: "400 g", price: 89, mrp: 109, veg: true, art: "Pomegranate" },
      { id: "f5", images: pics("f5", 3), name: "Royal Gala Apple 2 pcs", unit: "2 pieces", price: 139, note: "Approx 250–400 g", veg: true, art: "Apple", color: "#e0453a" },
      { id: "f6", images: pics("f6", 3), name: "Kinnow Orange 1 kg", unit: "1 kg", price: 119, mrp: 149, veg: true, art: "Orange" },
      { id: "f7", images: pics("f7", 2), name: "Green Seedless Grapes", unit: "500 g", price: 99, mrp: 129, veg: true, art: "Grapes", stock: 0 },
    ],
  },
  {
    key: "daily",
    title: "Daily essentials",
    subtitle: "Staples you reorder every week",
    items: [
      { id: "d1", images: pics("d1", 3), name: "Cold Pressed Groundnut Oil", unit: "1 L", price: 299, mrp: 349, veg: true, art: "Bottle", color: "#d4a017", label: "OIL" },
      { id: "d2", images: pics("d2", 3), name: "Organic Whole Wheat Atta", unit: "5 kg", price: 359, mrp: 499, veg: true, art: "Pack", color: "#b0662a", label: "ATTA" },
      { id: "d3", images: pics("d3", 3), name: "Arabica Coffee Beans", unit: "500 g", price: 649, mrp: 899, veg: true, art: "Pack", color: "#3b2a22", label: "BEANS" },
      { id: "d4", images: pics("d4", 3), name: "Assorted Dry Fruits Gift Box", unit: "750 g", price: 1199, mrp: 1699, veg: true, art: "Box", color: "#8a4b2a" },
      { id: "d5", images: pics("d5", 3), name: "Himalayan Pink Salt", unit: "1 kg", price: 149, mrp: 199, veg: true, art: "Jar", color: "#e59aa8", label: "SALT" },
      { id: "d6", images: pics("d6", 3), name: "Dark Chocolate 70% Cocoa", unit: "100 g", price: 249, mrp: 299, veg: true, art: "Bar", color: "#5a2e1c", label: "70%", low: 2 },
      { id: "d7", images: pics("d7", 3), name: "Green Tea Bags, Pack of 100", unit: "200 g", price: 429, mrp: 599, veg: true, art: "Pack", color: "#2e7d4f", label: "TEA" },
    ],
  },
  { banner: ["b3", "b4"] },
  {
    key: "tech",
    title: "Top deals on tech",
    subtitle: "Biggest savings right now",
    items: [
      { id: "t1", images: pics("t1", 4), name: "Wireless Noise-Cancelling Headphones", unit: "AudioCore", price: 4499, mrp: 8299, art: "Headphones" },
      { id: "t2", images: pics("t2", 4), name: "Bluetooth Speaker 20W", unit: "AudioCore", price: 1899, mrp: 2599, art: "Speaker" },
      { id: "t3", images: pics("t3", 4), name: "65W GaN Fast Charger, Dual USB-C", unit: "VoltEdge", price: 1299, mrp: 1799, art: "Charger" },
      { id: "t4", images: pics("t4", 4), name: "Portable SSD 1TB", unit: "DataVault", price: 6499, mrp: 8999, art: "Ssd" },
      { id: "t5", images: pics("t5", 4), name: "1080p Webcam with Privacy Shutter", unit: "ClearView", price: 2499, mrp: 3299, art: "Webcam", stock: 0 },
      { id: "t6", images: pics("t6", 4), name: "LED Desk Lamp with Wireless Charging", unit: "Lumen", price: 2799, art: "Lamp", tag: "New" },
    ],
  },
  {
    key: "home",
    title: "For your home",
    subtitle: "",
    items: [
      { id: "h1", images: pics("h1", 3), name: "Ceramic Dinner Set, 18 Piece", unit: "TerraLiving", price: 3299, mrp: 4499, art: "Plates" },
      { id: "h2", images: pics("h2", 3), name: "Cotton Bath Towels, Pack of 4", unit: "SoftWeave", price: 899, mrp: 1149, art: "Towels" },
      { id: "h3", images: pics("h3", 3), name: "Stainless Steel Vacuum Flask 1L", unit: "ThermaCore", price: 749, mrp: 949, art: "Flask" },
      { id: "h4", images: pics("h4", 3), name: "Bamboo Cutting Board Set", unit: "TerraLiving", price: 999, mrp: 1299, art: "Board" },
      { id: "h5", images: pics("h5", 3), name: "Storage Basket, Woven Large", unit: "SoftWeave", price: 1099, mrp: 1399, art: "Basket" },
    ],
  },
];

/* ---------------- Express (marketplace, 2–5 day delivery) ---------------- */
export const ALL_TABS = [
  { key: "foryou", label: "For you", icon: "grid" },
  { key: "electronics", label: "Electronics", icon: "plug" },
  { key: "kitchen", label: "Home & Kitchen", icon: "pot" },
  { key: "fashion", label: "Fashion", icon: "shirt" },
  { key: "stationery", label: "Stationery", icon: "pen" },
  { key: "books", label: "Books", icon: "book" },
  { key: "offers", label: "Offers", icon: "ticket" },
];

export const ALL_BANNERS = [
  { id: "ab1", kicker: "Big tech savings", title: "Audio, storage & more", note: "Up to 40% off", tone: "navy", art: ["Headphones", "Ssd"] },
  { id: "ab2", kicker: "Home makeover", title: "Dinnerware & linen", note: "From ₹499", tone: "teal", art: ["Plates", "Towels"] },
  { id: "ab3", kicker: "Work from home", title: "Desk setup deals", note: "Up to 35% off", tone: "indigo", art: ["Lamp", "Webcam"] },
  { id: "ab4", kicker: "Kitchen upgrade", title: "Flasks & serving boards", note: "Buy 2, save 10%", tone: "brown", art: ["Flask", "Board"] },
];

export const ALL_CATEGORIES = [
  { key: "audio", image: "/images/categories/a-audio.svg", label: "Audio", art: "Headphones", bg: "#e8f1f8" },
  { key: "storage", image: "/images/categories/a-storage.svg", label: "Storage", art: "Ssd", bg: "#e6eef6" },
  { key: "chargers", image: "/images/categories/a-chargers.svg", label: "Chargers", art: "Charger", bg: "#eef3f6" },
  { key: "cameras", image: "/images/categories/a-cameras.svg", label: "Webcams", art: "Webcam", bg: "#edf0f3" },
  { key: "dinner", image: "/images/categories/a-dinner.svg", label: "Dinnerware", art: "Plates", color: "#2d6a8a", bg: "#e9f1f5" },
  { key: "linen", image: "/images/categories/a-linen.svg", label: "Bath linen", art: "Towels", color: "#2d6a8a", bg: "#eef2f4" },
  { key: "lighting", image: "/images/categories/a-lighting.svg", label: "Lighting", art: "Lamp", bg: "#fff1e2" },
  { key: "baskets", image: "/images/categories/a-baskets.svg", label: "Storage baskets", art: "Basket", bg: "#f5eee2" },
];

export const ALL_SECTIONS = [
  {
    key: "all-tech",
    title: "Best of electronics",
    subtitle: "Free delivery on every order above ₹999",
    items: [
      { id: "a1", images: pics("a1", 4), name: "Portable SSD 2TB, USB-C", unit: "DataVault", price: 9499, mrp: 12999, art: "Ssd", delivery: "2–3 days" },
      { id: "a2", images: pics("a2", 4), name: "Party Speaker 60W with Lights", unit: "AudioCore", price: 5999, mrp: 8499, art: "Speaker", color: "#2b3a42", delivery: "2–3 days" },
      { id: "a3", images: pics("a3", 4), name: "4K Webcam with Ring Light", unit: "ClearView", price: 5499, mrp: 7299, art: "Webcam", delivery: "3–5 days" },
      { id: "a4", images: pics("a4", 4), name: "Over-Ear Studio Headphones", unit: "AudioCore", price: 6999, mrp: 9999, art: "Headphones", color: "#6b2d5c", delivery: "2–3 days", low: 3 },
      { id: "a5", images: pics("a5", 4), name: "100W GaN Charger, 4 Ports", unit: "VoltEdge", price: 2999, mrp: 3999, art: "Charger", delivery: "2–3 days" },
      { id: "a6", images: pics("a6", 4), name: "Smart LED Desk Lamp", unit: "Lumen", price: 1999, mrp: 2799, art: "Lamp", color: "#0a78ab", delivery: "3–5 days", tag: "New" },
    ],
  },
  {
    key: "all-home",
    title: "Home makeover",
    subtitle: "Dinnerware, linen and storage",
    items: [
      { id: "b1", images: pics("b1", 3), name: "Stoneware Dinner Set, 24 Piece", unit: "TerraLiving", price: 5499, mrp: 7999, art: "Plates", color: "#2d6a8a", delivery: "3–5 days" },
      { id: "b2", images: pics("b2", 3), name: "Egyptian Cotton Towels, Set of 6", unit: "SoftWeave", price: 1899, mrp: 2599, art: "Towels", color: "#2d6a8a", delivery: "2–3 days" },
      { id: "b3", images: pics("b3", 3), name: "Seagrass Laundry Basket", unit: "SoftWeave", price: 1499, mrp: 1999, art: "Basket", delivery: "3–5 days" },
      { id: "b4", images: pics("b4", 3), name: "Insulated Flask Pair, 750 ml", unit: "ThermaCore", price: 1299, mrp: 1699, art: "Flask", color: "#2d6a8a", delivery: "2–3 days" },
      { id: "b5", images: pics("b5", 2), name: "Acacia Serving Board", unit: "TerraLiving", price: 1199, mrp: 1599, art: "Board", delivery: "3–5 days", stock: 0 },
    ],
  },
  { banner: ["ab3", "ab4"] },
  {
    key: "all-office",
    title: "Office & stationery",
    subtitle: "Stock the desk for the month",
    items: [
      { id: "c1", images: pics("c1", 3), name: "A5 Ruled Notebooks, Set of 3", unit: "PaperNest", price: 399, mrp: 549, art: "Pack", color: "#0b4a6e", label: "A5", delivery: "2–3 days" },
      { id: "c2", images: pics("c2", 3), name: "Gel Pens, Pack of 10", unit: "PaperNest", price: 249, mrp: 320, art: "Pack", color: "#c8433a", label: "PENS", delivery: "2–3 days" },
      { id: "c3", images: pics("c3", 3), name: "Desk Organiser Box", unit: "PaperNest", price: 699, mrp: 899, art: "Box", color: "#4a5d6b", delivery: "3–5 days" },
      { id: "c4", images: pics("c4", 3), name: "Whiteboard Markers, Set of 4", unit: "PaperNest", price: 199, mrp: 260, art: "Jar", color: "#9ec7de", label: "MARK", delivery: "2–3 days" },
    ],
  },
];
