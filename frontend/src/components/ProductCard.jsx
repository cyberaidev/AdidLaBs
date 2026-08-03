import { COPY } from "../copy.js";
import { HeartIcon } from "./icons.jsx";
import { fallbackForCategory, imageForItem } from "../data/productImages.js";
import { FeedbackThumbs } from "./FeedbackThumbs.jsx";

function usd(n) {
  return `$${Number(n || 0).toFixed(2)}`;
}

export function ProductCard({ item, hearted, onToggleHeart, onAddToBag, contextLine }) {
  const hasDeal = item.deal_price != null && item.deal_price < item.price;
  const pct = hasDeal ? Math.round((1 - item.deal_price / item.price) * 100) : 0;

  return (
    <article className="card editorial-card">
      <div className="card-media">
        <img
          src={imageForItem(item)}
          alt={item.title}
          loading="lazy"
          onError={(event) => {
            event.currentTarget.onerror = null;
            event.currentTarget.src = fallbackForCategory(item.category);
          }}
        />
        <div className="card-image-overlay" aria-hidden="true" />
        <span className="card-tag">{item.category}</span>
        {item.ai_pick && <span className="card-ai-tag">{item.ai_note || "AGENT PICK"}</span>}
        <FeedbackThumbs item={item} />
        <button
          type="button"
          className={`heart ${hearted ? "active" : ""}`}
          aria-label={hearted ? "Remove from wishlist" : "Add to wishlist"}
          aria-pressed={hearted}
          onClick={() => onToggleHeart(item)}
        >
          <HeartIcon />
        </button>
      </div>

      <div className="card-body">
        {contextLine && <div className="card-context">{contextLine}</div>}
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
          {COPY.rail.addToBag} <span aria-hidden="true">→</span>
        </button>
      </div>
    </article>
  );
}
