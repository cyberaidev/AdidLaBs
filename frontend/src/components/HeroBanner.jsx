import { COPY } from "../copy.js";

export function HeroBanner({ onShopNow }) {
  return (
    <section className="hero hdr-hero">
      <div className="hero-atmosphere" aria-hidden="true" />
      <div className="container hdr-hero-inner">
        <div className="hero-copy hdr-copy">
          <div className="hero-kicker">AI FORECAST INTELLIGENCE</div>
          <h2 className="hero-command">PREDICT.<br/>DESIGN.<br/>LAUNCH.</h2>
          <p className="hero-intro">AI-powered forecasting for fashion, weather and retail demand.</p>
          <div className="hero-actions">
            <button type="button" className="shop-now primary-cta" onClick={onShopNow}>BUILD MY LOOK <span aria-hidden="true">→</span></button>
            <button type="button" className="shop-now secondary-cta" onClick={() => document.querySelector('.agents-panel')?.scrollIntoView({ behavior: 'smooth' })}>VIEW AGENT ACTIVITY</button>
          </div>
        </div>

        <div className="hero-brand-lockup" aria-label="AdidLaBs — Agentic Demo, Intelligent Decisions">
          <h1 className="hero-h1 hero-brandword">
            <span className="wm-anton">ADID</span><span className="wm-serif falling-l">L</span><span className="wm-anton">A</span><span className="wm-serif falling-b">B</span><span className="wm-anton">S</span>
          </h1>
          <div className="brand-rule"><span />AGENTIC DEMO <b>•</b> INTELLIGENT DECISIONS<span /></div>
          <div className="brand-stack">LITELLM <b>•</b> AWS <b>•</b> BEDROCK <b>•</b> SERVICES</div>
        </div>

        <div className="hero-weather-stack" aria-label="Weather conditions the lab dresses you for">
          {COPY.hero.media.map((m, i) => (
            <figure className={`season season-${i}`} key={m.label}>
              <img src={m.src} alt={m.alt} loading="lazy" />
              <figcaption className="season-tag"><span className="amber">{m.temp}</span> {m.label}</figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  );
}
