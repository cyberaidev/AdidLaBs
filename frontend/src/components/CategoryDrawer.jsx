import { useEffect, useMemo, useState } from "react";
import { Drawer } from "./Drawer.jsx";
import { getCatalog } from "../api.js";
import { productTile } from "../data/fallbackCatalog.js";

function usd(n) {
  return `$${Number(n).toFixed(2)}`;
}

// Full-category browse drawer: every catalog item for one category (from
// GET /api/catalog), with a manual search filter and ADD TO BAG per row —
// the hand-picked counterpart to the AI-matched rail.
export function CategoryDrawer({ category, onAddToBag, onClose }) {
  const [items, setItems] = useState(null); // null = loading
  const [queryText, setQueryText] = useState("");

  useEffect(() => {
    let alive = true;
    setItems(null);
    getCatalog(category.toLowerCase(), 120).then((data) => {
      if (alive) setItems(data?.items || []);
    });
    return () => {
      alive = false;
    };
  }, [category]);

  const visible = useMemo(() => {
    if (!items) return [];
    const q = queryText.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) =>
      [i.title, i.colour, i.article_type, i.gender, i.season]
        .filter(Boolean)
        .some((f) => String(f).toLowerCase().includes(q))
    );
  }, [items, queryText]);

  return (
    <Drawer titleId="browse-title" className="browse" onClose={onClose}>
      <div className="drawer-head">
        <span className="drawer-title" id="browse-title">
          BROWSE · {category}
        </span>
        <button
          type="button"
          className="drawer-close"
          aria-label="Close browse"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <div className="drawer-body">
        <input
          type="search"
          className="browse-search"
          placeholder={`Search ${category.toLowerCase()}… (name, colour, season)`}
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          aria-label={`Search ${category}`}
        />
        {items === null ? (
          <p className="drawer-empty">Loading the full {category.toLowerCase()} list…</p>
        ) : visible.length === 0 ? (
          <p className="drawer-empty">No matches — try another search.</p>
        ) : (
          <>
            <p className="browse-count">
              {visible.length} of {items.length} items
            </p>
            {visible.map((item) => (
              <div key={item.item_id} className="line-item">
                <img src={productTile(item.category, item.title)} alt="" />
                <div className="line-item-info">
                  <span className="line-item-title">{item.title}</span>
                  <span className="browse-meta">
                    {[item.colour, item.article_type, item.season]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                  <span className="line-item-price">
                    {item.deal_price != null ? (
                      <>
                        <s>{usd(item.price)}</s> {usd(item.deal_price)}
                      </>
                    ) : (
                      usd(item.price)
                    )}
                  </span>
                  <button
                    type="button"
                    className="line-item-remove"
                    onClick={() =>
                      onAddToBag({
                        ...item,
                        image: productTile(item.category, item.title),
                      })
                    }
                  >
                    Add to bag
                  </button>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </Drawer>
  );
}
