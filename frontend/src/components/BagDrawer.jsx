import { COPY } from "../copy.js";
import { Drawer } from "./Drawer.jsx";

function usd(n) {
  return `$${Number(n || 0).toFixed(2)}`;
}

// Bag drawer (§5.15). Rows from bag state; remove via DELETE /api/bag (App handler).
// AI-matched rows carry the AI CHOICE tag so the user can curate them alongside
// manual picks. CHECKOUT is a demo no-op — no payment is ever processed.
export function BagDrawer({ items, onRemove, onClose }) {
  const subtotal = items.reduce(
    (sum, i) => sum + Number(i.deal_price ?? i.price ?? 0),
    0
  );
  const hasAiPicks = items.some((i) => i.ai_pick);

  return (
    <Drawer titleId="bag-title" onClose={onClose}>
      <div className="drawer-head">
        <span className="drawer-title" id="bag-title">
          {COPY.bag.title}
        </span>
        <button
          type="button"
          className="drawer-close"
          aria-label="Close bag"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <div className="drawer-body">
        {hasAiPicks && <p className="ai-note">{COPY.bag.aiNote}</p>}
        {items.length === 0 ? (
          <p className="drawer-empty">{COPY.bag.empty}</p>
        ) : (
          items.map((item) => (
            <div key={item.item_id} className="line-item">
              {item.image && <img src={item.image} alt="" />}
              <div className="line-item-info">
                <span className="line-item-title">
                  {item.title}
                  {item.ai_pick && (
                    <span className="ai-badge">{item.ai_note || "AI CHOICE"}</span>
                  )}
                </span>
                <span className="line-item-price">
                  {usd(item.deal_price ?? item.price)}
                </span>
                <button
                  type="button"
                  className="line-item-remove"
                  onClick={() => onRemove(item.item_id)}
                >
                  Remove
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {items.length > 0 && (
        <div className="drawer-foot">
          <div className="subtotal-row">
            <span>{COPY.bag.subtotal}</span>
            <span>{usd(subtotal)}</span>
          </div>
          <button
            type="button"
            className="checkout-btn"
            onClick={() =>
              alert("Demo checkout — no payment is processed. All products fictional.")
            }
          >
            {COPY.bag.checkout}
          </button>
        </div>
      )}
    </Drawer>
  );
}
