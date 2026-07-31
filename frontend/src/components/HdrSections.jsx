import { COPY } from "../copy.js";
import { productTile } from "../data/fallbackCatalog.js";

// HDR redesign sections (2026-07-22 mockup): KPI stats strip, photo feature
// cards, and the autonomous-buying-agent banner. Presentation only — every
// click routes to functionality that already exists (rail, chat, agents,
// telemetry, bag).

const ICONS = {
  trend: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 17l5-5 4 4 8-8" />
      <path d="M15 8h5v5" />
    </svg>
  ),
  cloud: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.6-1.5A3.5 3.5 0 0 1 19 18H7z" />
      <path d="M4 6l1.5 1.5M12 3v2" />
    </svg>
  ),
  cube: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" />
      <path d="M12 12l8-4.5M12 12L4 7.5M12 12v9" />
    </svg>
  ),
  signal: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 19V9M9 19V5M14 19v-8M19 19V3" />
    </svg>
  ),
};

export function StatsStrip() {
  return (
    <section className="hdr-stats" aria-label="Lab performance metrics">
      <div className="container hdr-stats-row">
        {COPY.hdr.stats.map((s) => (
          <div className="hdr-stat" key={s.label}>
            <span className="hdr-stat-icon">{ICONS[s.icon]}</span>
            <div>
              <div className="hdr-stat-label">{s.label}</div>
              <div className="hdr-stat-value">{s.value}</div>
              <div className="hdr-stat-sub">{s.sub}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function FeatureCards({ onAction }) {
  return (
    <section className="hdr-features container" aria-label="Lab capabilities">
      {COPY.hdr.features.map((f) => (
        <button
          type="button"
          className="hdr-feature"
          key={f.title}
          onClick={() => onAction(f.action)}
        >
          <img src={f.img} alt={f.alt} loading="lazy" />
          <span className="hdr-feature-scrim" aria-hidden="true" />
          <span className="hdr-feature-body">
            <span className="hdr-feature-title">{f.title}</span>
            <span className="hdr-feature-sub">
              {f.sub}
              <b aria-hidden="true">→</b>
            </span>
          </span>
        </button>
      ))}
    </section>
  );
}

export function AgentBanner({ onLearnMore, onReview }) {
  const b = COPY.hdr.banner;
  return (
    <section className="hdr-banner container" aria-label="Autonomous buying agent">
      <div className="hdr-banner-left">
        <span className="hdr-banner-bot" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <rect x="5" y="8" width="14" height="10" />
            <path d="M12 8V4M9 4h6M9 12.5h.01M15 12.5h.01M9.5 15.5h5" />
          </svg>
        </span>
        <div>
          <div className="hdr-banner-kicker">{b.kicker}</div>
          <div className="hdr-banner-headline">{b.headline}</div>
          <button type="button" className="hdr-banner-link" onClick={onLearnMore}>
            {b.cta} <span aria-hidden="true">→</span>
          </button>
        </div>
      </div>
      <img
        className="hdr-banner-shoe"
        src={productTile("SHOES", "Forecast Runner")}
        alt=""
        aria-hidden="true"
      />
      <div className="hdr-banner-right">
        <div className="hdr-stat-label">{b.recLabel}</div>
        <div className="hdr-banner-rec">
          {b.recValue}
          <span className="hdr-stat-sub"> {b.recSub}</span>
        </div>
        <button type="button" className="hdr-banner-link" onClick={onReview}>
          {b.recCta} <span aria-hidden="true">→</span>
        </button>
      </div>
    </section>
  );
}
