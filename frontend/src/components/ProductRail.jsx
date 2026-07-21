import { forwardRef } from "react";
import { COPY } from "../copy.js";
import { ProductCard } from "./ProductCard.jsx";

// PICKED FOR YOUR FORECAST rail (§5.7). Fed by catalog data (live or fallback).
// forwardRef so the hero SHOP NOW button can scroll to it.
const BROWSE_CATEGORIES = ["SHOES", "PANTS", "TSHIRT", "JUMPER", "JACKET", "ACCESSORY"];

export const ProductRail = forwardRef(function ProductRail(
  { items, wishlist, onToggleHeart, onAddToBag, onBrowse },
  ref
) {
  const heartedIds = new Set(wishlist.map((i) => i.item_id));
  return (
    <section className="section container" ref={ref} id="forecast-rail">
      <h2 className="section-heading">{COPY.rail.heading}</h2>
      <p className="section-sub">{COPY.rail.sub}</p>
      {onBrowse && (
        <div className="browse-row">
          <span className="browse-label">{COPY.rail.browseLabel}</span>
          {BROWSE_CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              className="browse-link"
              onClick={() => onBrowse(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      )}
      <div className="rail-grid">
        {items.map((item) => (
          <ProductCard
            key={item.item_id}
            item={item}
            hearted={heartedIds.has(item.item_id)}
            onToggleHeart={onToggleHeart}
            onAddToBag={onAddToBag}
          />
        ))}
      </div>
    </section>
  );
});
