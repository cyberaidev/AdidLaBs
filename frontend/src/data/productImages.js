// Product photograph resolution. Priority:
//   1. image_url from the API (backend derives it or DynamoDB stores it)
//   2. image already attached to the row (bag rows persist it)
//   3. derived site-relative path — data/fetch_images.py rehosts every
//      hf-<id> catalog photo to <site>/catalog-img/hf-<id>.jpg, so the SPA
//      can resolve images even before the backend redeploy ships image_url
//   4. photographic category fallback (unbranded editorial shots) when an
//      individual source image fails to load (wired via onError)

const CATEGORY_FALLBACKS = {
  SHOES:
    "https://images.unsplash.com/photo-1560769629-975ec94e6a86?auto=format&fit=crop&w=1000&q=88",
  JACKET:
    "https://images.unsplash.com/photo-1551028719-00167b16eac5?auto=format&fit=crop&w=1000&q=88",
  JUMPER:
    "https://images.unsplash.com/photo-1434389677669-e08b4cac3105?auto=format&fit=crop&w=1000&q=88",
  PANTS:
    "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?auto=format&fit=crop&w=1000&q=88",
  TSHIRT:
    "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=1000&q=88",
  ACCESSORY:
    "https://images.unsplash.com/photo-1521369909029-2afed882baee?auto=format&fit=crop&w=1000&q=88",
};

export function imageForItem(item = {}) {
  if (item.image_url) return item.image_url;
  if (item.image) return item.image;
  const match = String(item.item_id || "").match(/^hf-(\d+)$/i);
  if (match) return `/catalog-img/hf-${match[1]}.jpg`;
  return fallbackForCategory(item.category);
}

export function fallbackForCategory(category) {
  const key = String(category || "ACCESSORY").toUpperCase();
  return CATEGORY_FALLBACKS[key] || CATEGORY_FALLBACKS.ACCESSORY;
}
