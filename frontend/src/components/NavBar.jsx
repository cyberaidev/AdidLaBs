import { useState } from "react";
import { COPY } from "../copy.js";

// Centered uppercase condensed nav (§5.4). Single-page demo — items are non-routing,
// but the active highlight is driven by real selection state rather than a hard-coded
// index, so clicking a nav item moves the highlight. Defaults to the first item
// (SHOES) to match the v3 mockup's initial state.
export function NavBar() {
  const [active, setActive] = useState(COPY.nav[0]);
  return (
    <nav className="nav" aria-label="Primary">
      {COPY.nav.map((item) => (
        <a
          key={item}
          href="#"
          aria-current={item === active ? "page" : undefined}
          className={`${item === active ? "active" : ""} ${
            item === COPY.navRedItem ? "red" : ""
          }`}
          onClick={(e) => {
            e.preventDefault();
            setActive(item);
          }}
        >
          {item}
        </a>
      ))}
    </nav>
  );
}
