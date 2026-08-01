// Static catalog fallback so the product rail renders before any backend deploy
// or when GET /api/catalog is unreachable. Synthetic prices in USD.
// Fallback items use generic editorial product photography (unbranded Unsplash
// shots, vetted for third-party marks). Live DynamoDB rows carry image_url —
// the corresponding HuggingFace catalog photograph rehosted on the site's own
// CloudFront by data/fetch_images.py.

import { fallbackForCategory } from "./productImages.js";

export const FALLBACK_CATALOG = [
  {
    item_id: "sh-001",
    category: "SHOES",
    title: "Stratus Trail Runner",
    price: 129.0,
    deal_price: 89.0,
    image: fallbackForCategory("SHOES"),
  },
  {
    item_id: "jk-001",
    category: "JACKET",
    title: "Downpour Shell Jacket",
    price: 189.0,
    deal_price: null,
    image: fallbackForCategory("JACKET"),
  },
  {
    item_id: "jm-001",
    category: "JUMPER",
    title: "Coldfront Knit Jumper",
    price: 99.0,
    deal_price: 69.0,
    image: fallbackForCategory("JUMPER"),
  },
  {
    item_id: "pa-001",
    category: "PANTS",
    title: "Gale Tapered Trouser",
    price: 79.0,
    deal_price: null,
    image: fallbackForCategory("PANTS"),
  },
  {
    item_id: "ts-001",
    category: "TSHIRT",
    title: "Airflow Cotton Tee",
    price: 39.0,
    deal_price: 25.0,
    image: fallbackForCategory("TSHIRT"),
  },
  {
    item_id: "ac-001",
    category: "ACCESSORY",
    title: "Horizon Weatherproof Cap",
    price: 34.0,
    deal_price: null,
    image: fallbackForCategory("ACCESSORY"),
  },
  {
    item_id: "sh-002",
    category: "SHOES",
    title: "Puddle Rain Boot",
    price: 149.0,
    deal_price: 109.0,
    image: fallbackForCategory("SHOES"),
  },
  {
    item_id: "jk-002",
    category: "JACKET",
    title: "Breeze Packable Windbreaker",
    price: 119.0,
    deal_price: null,
    image: fallbackForCategory("JACKET"),
  },
];
