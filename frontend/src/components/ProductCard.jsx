import { COPY } from "../copy.js";
import { HeartIcon } from "./icons.jsx";

function usd(n) {
  return `$${Number(n).toFixed(2)}`;
}

// Single catalog tile (§5.8): image, category tag, heart wishlist toggle, title,
// price/deal block, add-to-bag.
export function ProductCard({ item, hearted, onToggleHeart, onAddToBag }) {
  const hasDeal = item.deal_price != null && item.deal_price < item.price;
  const pct = hasDeal
    ? Math.round((1 - item.deal_price / item.price) * 100)
    : 0;

  return (
    <article className="card">
      <div className="card-media">
        <span className="card-tag">{item.category}</span>
        <button
          type="button"
          className={`heart ${hearted ? "active" : ""}`}
          aria-label={hearted ? "Remove from wishlist" : "Add to wishlist"}
          aria-pressed={hearted}
          onClick={() => onToggleHeart(item)}
        >
          <HeartIcon />
        </button>
        {item.image ? (
          <img src={item.image} alt={item.title} loading="lazy" />
        ) : (
          <div
            style={{
              width: "100%",
              height: "100%",
              background: "var(--tile)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 300,
              color: "var(--muted)",
            }}
          >
            {item.category}
          </div>
        )}
      </div>

      <div className="card-body">
        <h3 className="card-title">{item.title}</h3>
        <div className="price-row">
          {hasDeal ? (
            <>
              <span className="price-strike">{usd(item.price)}</span>
              <span className="price-deal">{usd(item.deal_price)}</span>
              <span className="deal-tag">-{pct}%</span>
            </>
          ) : (
            <span className="price">{usd(item.price)}</span>
          )}
        </div>
        <button type="button" className="add-bag" onClick={() => onAddToBag(item)}>
          {COPY.rail.addToBag}
        </button>
      </div>
    </article>
  );
}
