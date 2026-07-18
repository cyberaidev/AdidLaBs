import { COPY } from "../copy.js";

// Silver hero (§5.5). The giant ADIDLABS word is monolithic Anton black (poster look);
// the serif-amber L/B treatment lives only in the <Wordmark> brand device elsewhere.
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
        <h1 className="hero-h1">{COPY.hero.line1}</h1>
        <h2 className="hero-h2">{COPY.hero.line2}</h2>
        <button type="button" className="shop-now" onClick={onShopNow}>
          {COPY.hero.cta}
          <span aria-hidden="true">{COPY.hero.ctaArrow}</span>
        </button>
      </div>
    </section>
  );
}
