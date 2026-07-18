import { COPY } from "../copy.js";
import { Drawer } from "./Drawer.jsx";

// Architecture drawer (§5.14). Static stack list + region label + GitHub doc link.
// Non-interactive visual content.
export function ArchitectureDrawer({ onClose }) {
  const arch = COPY.architecture;
  return (
    <Drawer titleId="arch-title" onClose={onClose}>
      <div className="drawer-head">
        <span className="drawer-title" id="arch-title">
          {arch.title}
        </span>
        <button
          type="button"
          className="drawer-close"
          aria-label="Close architecture"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <div className="drawer-body">
        <p className="arch-region">Region · {arch.region}</p>
        <div className="arch-list">
          {arch.layers.map((layer, i) => (
            <div key={i} className="arch-node">
              {layer}
            </div>
          ))}
        </div>
        <a
          className="arch-link"
          href={arch.githubDocUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          View architecture.md on GitHub →
        </a>
      </div>
    </Drawer>
  );
}
