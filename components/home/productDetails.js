/* Sample product-detail content. In production return these fields from your
   API (Odoo product.template + attributes). getDetails() fills anything missing
   with category-appropriate sample text so every product page is complete. */

const hash = (s) => [...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

const KIND = {
  f: "fresh", x: "fresh", v: "fresh", d: "grocery", s: "grocery", n: "grocery",
  p: "care", q: "care",
  t: "tech", e: "tech", a: "tech", h: "home", b: "home", k: "home", c: "office", o: "office",
};

const BASE = {
  fresh: {
    category: "Fresh fruits",
    soldBy: "369 Mart Fresh",
    origin: "India",
    manufacturer: "369 Mart Farm Partners",
    address: "Collection Centre, Market Road, Ernakulam, Kerala 682018",
    features: [
      "Hand-picked and quality checked before packing",
      "Stored at the right temperature from farm to your door",
      "Weight may vary slightly as produce is natural",
    ],
    returnable: true,
    returnText: "Not happy with freshness? Report it within 24 hours of delivery for a replacement or refund.",
    shelf: "3–5 days, refrigerated",
  },
  grocery: {
    category: "Daily essentials",
    soldBy: "369 Mart Retail",
    origin: "India",
    manufacturer: "369 Mart Foods Pvt Ltd",
    address: "Plot 14, Food Park, Kanjikode, Palakkad, Kerala 678621",
    features: [
      "Sourced from certified suppliers",
      "Sealed pack for freshness and hygiene",
      "Store in a cool, dry place away from sunlight",
    ],
    returnable: false,
    returnText: "This product is non-returnable. For damaged or wrong items, contact us within 48 hours of delivery.",
    shelf: "6 months from packing",
  },
  tech: {
    category: "Electronics",
    soldBy: "369 Mart Express",
    origin: "India",
    manufacturer: "Brand's authorised manufacturer",
    address: "Unit 7, Electronics Cluster, Sriperumbudur, Tamil Nadu 602105",
    features: [
      "1 year manufacturer warranty",
      "Genuine product with invoice",
      "Tested before dispatch",
    ],
    returnable: true,
    returnText: "7-day replacement for manufacturing defects. Keep the original box and accessories.",
    shelf: "",
  },
  home: {
    category: "Home & kitchen",
    soldBy: "369 Mart Express",
    origin: "India",
    manufacturer: "369 Mart Home Goods",
    address: "Warehouse 3, Logistics Park, Kalamassery, Kerala 683104",
    features: [
      "Durable, everyday-use materials",
      "Easy to clean",
      "Carefully packed to prevent damage in transit",
    ],
    returnable: true,
    returnText: "10-day return if the item is unused and in original packaging.",
    shelf: "",
  },
  care: {
    category: "Personal care",
    soldBy: "369 Mart Retail",
    origin: "India",
    manufacturer: "369 Mart Personal Care Partners",
    address: "Plot 22, KINFRA Park, Kakkanad, Kochi, Kerala 682042",
    features: ["Dermatologically tested", "Suitable for daily use", "Store in a cool, dry place"],
    returnable: false,
    returnText: "This product is non-returnable once opened. For damaged or wrong items, contact us within 48 hours of delivery.",
    shelf: "24 months from manufacture",
  },
  office: {
    category: "Stationery",
    soldBy: "369 Mart Express",
    origin: "India",
    manufacturer: "PaperNest Stationery Co.",
    address: "Industrial Estate, Aroor, Alappuzha, Kerala 688534",
    features: ["Smooth, consistent writing", "Acid-free paper and inks", "Great for school and office"],
    returnable: true,
    returnText: "10-day return if unused and in original packaging.",
    shelf: "",
  },
};

export function getDetails(p) {
  const kind = KIND[p.id?.[0]] || "grocery";
  const b = BASE[kind];
  const h = hash(p.id);
  const rating = p.rating ?? Math.round((3.8 + (h % 12) / 10) * 10) / 10; // 3.8 – 4.9
  const ratingCount = p.ratingCount ?? 120 + (h % 48000);
  const dist = (() => {
    const five = 0.45 + ((rating - 3.8) / 1.1) * 0.3;
    const four = 0.25, three = 0.12, two = 0.05;
    const one = Math.max(0.02, 1 - five - four - three - two);
    return [five, four, three, two, one].map((x) => Math.round(x * 100));
  })();
  const isFood = kind === "fresh" || kind === "grocery";
  const specs = p.specs || {
    ...(p.unit && isFood ? { "Net quantity": p.unit } : {}),
    ...(kind === "tech" ? { Brand: p.unit, Warranty: "1 year", "In the box": "Product, cable, user manual" } : {}),
    ...(kind === "home" || kind === "office" ? { Brand: p.unit, Material: kind === "office" ? "Paper / plastic" : "Mixed" } : {}),
    "Product type": p.subName || b.category,
    ...(b.shelf ? { "Shelf life": b.shelf } : {}),
  };
  return {
    brand: p.brand || (isFood ? "369 Mart Select" : p.unit),
    category: p.subName || b.category,
    rating,
    ratingCount,
    dist,
    features: p.features || b.features,
    info: p.info || [
      ["Brand", p.brand || (isFood ? "369 Mart Select" : p.unit)],
      ["Sold by", b.soldBy],
      ["Country of origin", b.origin],
      ["Manufacturer name", b.manufacturer],
      ["Manufacturer address", b.address],
      ["Article ID", String(490000000 + (h % 9999999))],
      ...(isFood ? [["Veg / non-veg", "veg"]] : []),
      ["Item height", `${8 + (h % 20)} cm`],
      ["Item length", `${4 + (h % 12)} cm`],
      ["Item width", `${6 + (h % 14)} cm`],
      ["Net weight", p.unit && /g|kg|L/.test(p.unit) ? p.unit : `${150 + (h % 900)} g`],
    ],
    specs,
    description: p.description ||
      `${p.name} from ${p.brand || (isFood ? "369 Mart Select" : p.unit)} is chosen for everyday quality and value. ` +
      (isFood
        ? "Each batch is checked for freshness and packed hygienically so it reaches you the way it left the source. Enjoy it at breakfast, as a snack between meals, or as part of your weekly cooking. "
        : kind === "care"
          ? "Gentle enough for everyday use, made with care and sealed for hygiene. "
          : "It is built for daily use, tested before dispatch and backed by a clear warranty and return policy. ") +
      "Product images are for illustration; actual packaging may vary slightly. Please read the label for complete information before use.",
    disclaimer: "While we work to ensure product information is correct, packaging and ingredients may be updated by the manufacturer. Always read the label before use.",
    returnable: b.returnable,
    returnText: p.returnText || b.returnText,
    reviews: p.reviews || [
      { name: "Anjali R.", stars: 5, when: "2 weeks ago", text: "Exactly as described and delivered well packed. Will order again.", helpful: 24 },
      { name: "Faisal K.", stars: 4, when: "1 month ago", text: "Good quality for the price. Delivery was on time.", helpful: 11 },
      { name: "Meera S.", stars: rating >= 4.3 ? 5 : 3, when: "2 months ago", text: rating >= 4.3 ? "Consistently good every time I buy it." : "Decent, but the pack I got was slightly different from the photo.", helpful: 6 },
    ],
  };
}
