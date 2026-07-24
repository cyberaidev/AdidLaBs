import { COPY } from "../copy.js";

// Silver hero (§5.5, banner mockup 2026-07-22): original copy on the left —
// the giant ADIDLABS word with the amber serif-italic L and B — plus a 2×2
// weather-conditions photo panel on the right (sunny / raining / snow /
// windy), each tile tagged with an amber temperature.
export function HeroBanner({ onShopNow }) {
  return (
    <section className="hero">
      <div className="container hero-inner hero-grid">
        <div className="hero-copy">
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

        <div className="hero-media" aria-label="Weather conditions the lab dresses you for">
          {COPY.hero.media.map((m) => (
            <figure className="season" key={m.label}>
              <img src={m.src} alt={m.alt} loading="lazy" />
              <figcaption className="season-tag">
                <span className="amber">{m.temp}</span> {m.label}
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  );
}
