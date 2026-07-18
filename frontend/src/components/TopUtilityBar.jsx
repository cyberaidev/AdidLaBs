import { COPY } from "../copy.js";

// Thin black strip: decorative demo tagline + right meta (§5.1). No functional links.
export function TopUtilityBar() {
  return (
    <div className="utility">
      <div className="container">
        <span className="utility-left">{COPY.utility.left}</span>
        <span className="utility-right">
          {COPY.utility.right.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </span>
      </div>
    </div>
  );
}
