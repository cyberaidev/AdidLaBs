// Shared brand wordmark (design.md §1.1). Rendered as styled spans (no <img>) so it
// stays crisp and themeable. Reads ADID·L·A·B·S with amber serif-italic L and B —
// and the L and B lie FALLEN flat on the baseline while the other letters stand
// (the lab experiment knocked them over).
export function Wordmark({ className }) {
  return (
    <span className={`adidlabs-wordmark ${className ?? ""}`} aria-label="AdidLaBs">
      <span className="wm-anton">ADID</span>
      <span className="wm-serif wm-fallen">L</span>
      <span className="wm-anton">A</span>
      <span className="wm-serif wm-fallen">B</span>
      <span className="wm-anton">S</span>
    </span>
  );
}
