import { COPY } from "../copy.js";

// Silver hero (§5.5). The giant ADIDLABS word uses the same brand device as the
// wordmark: standing Anton letters with the amber serif-italic L and B.
export function HeroBanner({ onShopNow }) {
  return (
    <section className="hero">
      <div className="container hero-inner">
        <div className="hero-labels">
          {COPY.hero.labelBoxes.map((box) => (
            <span key={box} className="hero-label">
              {box}
            </span>
          ))}
        </div>
        <h1 className="hero-h1 hero-brandword" aria-label={COPY.hero.line1}>
          <span className="wm-anton">ADID</span>
          <span className="wm-serif">L</span>
          <span className="wm-anton">A</span>
          <span className="wm-serif">B</span>
          <span className="wm-anton">S</span>
        </h1>
        <h2 className="hero-h2">{COPY.hero.line2}</h2>
        <button type="button" className="shop-now" onClick={onShopNow}>
          {COPY.hero.cta}
          <span aria-hidden="true">{COPY.hero.ctaArrow}</span>
        </button>
      </div>
    </section>
  );
}
