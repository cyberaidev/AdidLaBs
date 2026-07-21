// Static catalog fallback so the product rail renders before any backend deploy
// or when GET /api/agents-surfaced catalog data is unreachable. Synthetic prices in EUR.
// Images are inline SVG data URIs (fictional, trademark-free) so the build has zero
// external image dependencies. Real product photos are deliberately NOT used: the
// HuggingFace source images show real branded goods. Concept demo — all products
// fictional.

// Minimal flat garment silhouettes per category (single path each, ink on the
// tile background, amber accent bar). Deliberately generic — no brand devices.
const GLYPHS = {
  SHOES:
    '<path d="M70 252c0-16 26-22 58-28l62-24c22-9 38-20 46-33l14 4c8 22 28 36 58 41l4 26c0 8-8 12-20 12H84c-9 0-14-6-14-8z" fill="#14140F"/>' +
    '<path d="M64 270h276v10H64z" fill="#14140F"/>' +
    '<path d="M196 202l10 16M222 192l10 16M248 180l10 16" stroke="#EDEEF0" stroke-width="5" fill="none"/>',
  PANTS:
    '<path d="M142 84h116v34l12 200h-56l-14-132-14 132h-56l12-200z" fill="#14140F"/>' +
    '<path d="M142 106h116" stroke="#EDEEF0" stroke-width="6"/>',
  TSHIRT:
    '<path d="M158 84h84l56 36-24 44-26-16v158H152V148l-26 16-24-44z" fill="#14140F"/>' +
    '<path d="M176 84a24 16 0 0 0 48 0" fill="#EDEEF0"/>',
  JUMPER:
    '<path d="M156 88h88l58 32-14 128-34-6v64H146v-64l-34 6-14-128z" fill="#14140F"/>' +
    '<path d="M146 292h108M146 280h108" stroke="#EDEEF0" stroke-width="4"/>' +
    '<path d="M176 88a24 14 0 0 0 48 0" fill="#EDEEF0"/>',
  JACKET:
    '<path d="M152 82l34 10 14 22 14-22 34-10 56 36-16 138-32-8v58H144v-58l-32 8-16-138z" fill="#14140F"/>' +
    '<path d="M200 114v192" stroke="#EDEEF0" stroke-width="6"/>' +
    '<path d="M166 150v40M234 150v40" stroke="#EDEEF0" stroke-width="4"/>',
  ACCESSORY:
    '<path d="M124 218a76 76 0 0 1 152 0z" fill="#14140F"/>' +
    '<path d="M124 218l206 14-2 16-204-10z" fill="#14140F"/>' +
    '<circle cx="200" cy="150" r="7" fill="#EDEEF0"/>',
};

// Product tile: category silhouette + product title, so every item renders a
// distinct, correct image without any external asset.
function tile(category, title, hex) {
  const glyph = GLYPHS[category] || GLYPHS.ACCESSORY;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">` +
    `<rect width="400" height="400" fill="${hex}"/>` +
    `<rect x="16" y="16" width="368" height="368" fill="none" stroke="#0A0A0A" stroke-width="2"/>` +
    `<text x="32" y="52" font-family="Oswald, sans-serif" font-size="16" letter-spacing="3" fill="#6B6A64">${category}</text>` +
    `<rect x="32" y="62" width="34" height="5" fill="#BA7517"/>` +
    glyph +
    `<text x="200" y="352" font-family="Oswald, sans-serif" font-size="19" font-weight="500" ` +
    `letter-spacing="1.5" text-anchor="middle" fill="#0A0A0A">${title.toUpperCase()}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export const FALLBACK_CATALOG = [
  {
    item_id: "sh-001",
    category: "SHOES",
    title: "Stratus Trail Runner",
    price: 129.0,
    deal_price: 89.0,
    image: tile("SHOES", "Stratus Trail Runner", "#EDEEF0"),
  },
  {
    item_id: "jk-001",
    category: "JACKET",
    title: "Downpour Shell Jacket",
    price: 189.0,
    deal_price: null,
    image: tile("JACKET", "Downpour Shell Jacket", "#E7E9EC"),
  },
  {
    item_id: "jm-001",
    category: "JUMPER",
    title: "Coldfront Knit Jumper",
    price: 99.0,
    deal_price: 69.0,
    image: tile("JUMPER", "Coldfront Knit Jumper", "#EDEEF0"),
  },
  {
    item_id: "pa-001",
    category: "PANTS",
    title: "Gale Tapered Trouser",
    price: 79.0,
    deal_price: null,
    image: tile("PANTS", "Gale Tapered Trouser", "#E7E9EC"),
  },
  {
    item_id: "ts-001",
    category: "TSHIRT",
    title: "Airflow Cotton Tee",
    price: 39.0,
    deal_price: 25.0,
    image: tile("TSHIRT", "Airflow Cotton Tee", "#EDEEF0"),
  },
  {
    item_id: "ac-001",
    category: "ACCESSORY",
    title: "Horizon Weatherproof Cap",
    price: 34.0,
    deal_price: null,
    image: tile("ACCESSORY", "Horizon Weatherproof Cap", "#E7E9EC"),
  },
  {
    item_id: "sh-002",
    category: "SHOES",
    title: "Puddle Rain Boot",
    price: 149.0,
    deal_price: 109.0,
    image: tile("SHOES", "Puddle Rain Boot", "#E7E9EC"),
  },
  {
    item_id: "jk-002",
    category: "JACKET",
    title: "Breeze Packable Windbreaker",
    price: 119.0,
    deal_price: null,
    image: tile("JACKET", "Breeze Packable Windbreaker", "#EDEEF0"),
  },
];
