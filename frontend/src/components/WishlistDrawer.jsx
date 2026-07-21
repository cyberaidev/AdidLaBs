import { COPY } from "../copy.js";
import { Drawer } from "./Drawer.jsx";

function usd(n) {
  return `$${Number(n).toFixed(2)}`;
}

// Wishlist drawer (§5.15). Hearted items; move-to-bag posts POST /api/bag (App handler).
export function WishlistDrawer({ items, onMoveToBag, onRemove, onClose }) {
  return (
    <Drawer titleId="wishlist-title" onClose={onClose}>
      <div className="drawer-head">
        <span className="drawer-title" id="wishlist-title">
          {COPY.wishlist.title}
        </span>
        <button
          type="button"
          className="drawer-close"
          aria-label="Close wishlist"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <div className="drawer-body">
        {items.length === 0 ? (
          <p className="drawer-empty">{COPY.wishlist.empty}</p>
        ) : (
          items.map((item) => (
            <div key={item.item_id} className="line-item">
              {item.image && <img src={item.image} alt="" />}
              <div className="line-item-info">
                <span className="line-item-title">{item.title}</span>
                <span className="line-item-price">
                  {usd(item.deal_price ?? item.price)}
                </span>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button
                    type="button"
                    className="move-btn"
                    onClick={() => onMoveToBag(item)}
                  >
                    {COPY.wishlist.moveToBag}
                  </button>
                  <button
                    type="button"
                    className="line-item-remove"
                    onClick={() => onRemove(item.item_id)}
                  >
                    Remove
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </Drawer>
  );
}
