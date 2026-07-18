// Static catalog fallback so the product rail renders before any backend deploy
// or when GET /api/agents-surfaced catalog data is unreachable. Synthetic prices in EUR.
// Images are inline SVG data URIs (fictional, trademark-free) so the build has zero
// external image dependencies. Concept demo — all products fictional.

// Neutral square placeholder tile with the category label baked in.
function tile(label, hex) {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">` +
    `<rect width="400" height="400" fill="${hex}"/>` +
    `<rect x="20" y="20" width="360" height="360" fill="none" stroke="#0A0A0A" stroke-width="2"/>` +
    `<text x="200" y="210" font-family="Oswald, sans-serif" font-size="30" font-weight="500" ` +
    `letter-spacing="4" text-anchor="middle" fill="#0A0A0A">${label}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export const FALLBACK_CATALOG = [
  {
    item_id: "sh-001",
    category: "SHOES",
    title: "Stratus Trail Runner",
    price: 129.0,
    deal_price: 89.0,
    image: tile("SHOES", "#EDEEF0"),
  },
  {
    item_id: "jk-001",
    category: "JACKET",
    title: "Downpour Shell Jacket",
    price: 189.0,
    deal_price: null,
    image: tile("JACKET", "#E7E9EC"),
  },
  {
    item_id: "jm-001",
    category: "JUMPER",
    title: "Coldfront Knit Jumper",
    price: 99.0,
    deal_price: 69.0,
    image: tile("JUMPER", "#EDEEF0"),
  },
  {
    item_id: "pa-001",
    category: "PANTS",
    title: "Gale Tapered Trouser",
    price: 79.0,
    deal_price: null,
    image: tile("PANTS", "#E7E9EC"),
  },
  {
    item_id: "ts-001",
    category: "TSHIRT",
    title: "Airflow Cotton Tee",
    price: 39.0,
    deal_price: 25.0,
    image: tile("TSHIRT", "#EDEEF0"),
  },
  {
    item_id: "ac-001",
    category: "ACCESSORY",
    title: "Horizon Weatherproof Cap",
    price: 34.0,
    deal_price: null,
    image: tile("ACCESSORY", "#E7E9EC"),
  },
  {
    item_id: "sh-002",
    category: "SHOES",
    title: "Puddle Rain Boot",
    price: 149.0,
    deal_price: 109.0,
    image: tile("SHOES", "#E7E9EC"),
  },
  {
    item_id: "jk-002",
    category: "JACKET",
    title: "Breeze Packable Windbreaker",
    price: 119.0,
    deal_price: null,
    image: tile("JACKET", "#EDEEF0"),
  },
];
