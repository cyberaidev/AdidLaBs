import { forwardRef } from "react";
import { COPY } from "../copy.js";
import { ProductCard } from "./ProductCard.jsx";

// PICKED FOR YOUR FORECAST rail (§5.7). Fed by catalog data (live or fallback).
// forwardRef so the hero SHOP NOW button can scroll to it.
export const ProductRail = forwardRef(function ProductRail(
  { items, wishlist, onToggleHeart, onAddToBag },
  ref
) {
  const heartedIds = new Set(wishlist.map((i) => i.item_id));
  return (
    <section className="section container" ref={ref} id="forecast-rail">
      <h2 className="section-heading">{COPY.rail.heading}</h2>
      <p className="section-sub">{COPY.rail.sub}</p>
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
