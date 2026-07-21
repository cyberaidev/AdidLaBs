import { COPY } from "../copy.js";
import { Wordmark } from "./Wordmark.jsx";

// Black footer (§5.16). .on-dark scope flips wordmark glyphs white (amber L/B stay).
// The no-affiliation disclaimer is mandatory and always visible.
export function Footer() {
  const f = COPY.footer;
  return (
    <footer className="footer on-dark">
      <div className="container">
        <div className="footer-top">
          <div>
            <Wordmark className="footer-word" />
          </div>
          {Object.entries(f.columns).map(([heading, links]) => (
            <div key={heading} className="footer-col">
              <h4>{heading}</h4>
              <ul>
                {links.map((link) =>
                  f.columnLinks?.[link] ? (
                    <li key={link}>
                      <a href={f.columnLinks[link]} target="_blank" rel="noreferrer">
                        {link}
                      </a>
                    </li>
                  ) : (
                    <li key={link}>
                      <a href="#" onClick={(e) => e.preventDefault()}>
                        {link}
                      </a>
                    </li>
                  )
                )}
              </ul>
            </div>
          ))}
        </div>

        <div className="footer-meta">
          <p>{f.buildLine}</p>
          <p className="footer-disclaimer">{f.disclaimer}</p>
          <p>
            {f.license}{" "}
            <a href={f.repoUrl} target="_blank" rel="noreferrer">
              {f.repoLabel}
            </a>
          </p>
          <p>{f.dataAttribution}</p>
        </div>
      </div>
    </footer>
  );
}
