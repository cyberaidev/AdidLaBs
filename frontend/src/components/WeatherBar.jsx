import { COPY } from "../copy.js";
import { LockIcon } from "./icons.jsx";

// Open-Meteo weathercode → glyph mapping (§5.6).
// https://open-meteo.com/en/docs — WMO weather interpretation codes.
function weatherEmoji(code) {
  if (code === 0) return "☀️"; // clear
  if (code >= 1 && code <= 2) return "🌤️"; // mainly clear / partly cloudy
  if (code === 3) return "☁️"; // overcast
  if (code >= 45 && code <= 48) return "🌫️"; // fog
  if (code >= 51 && code <= 67) return "🌧️"; // drizzle / rain
  if (code >= 71 && code <= 77) return "❄️"; // snow
  if (code >= 80 && code <= 82) return "🌦️"; // rain showers
  if (code >= 85 && code <= 86) return "🌨️"; // snow showers
  if (code >= 95) return "⛈️"; // thunderstorm
  return "🌡️";
}

// Black weather strip — GATED. Before auth shows a locked placeholder; after login
// renders location + local time + three day chips fed by /api/session + /api/weather.
export function WeatherBar({ authed, session, weather }) {
  if (!authed) {
    return (
      <div className="weather-bar locked" role="status">
        <LockIcon />
        {COPY.weatherBar.lockedText}
      </div>
    );
  }

  const parts = [];
  if (session) {
    if (session.city) {
      parts.push(`📍 ${session.city}${session.region ? `, ${session.region}` : ""}`);
    }
    if (session.localTime) {
      parts.push(`${session.localTime}${session.tz ? ` ${session.tz}` : ""}`);
    }
  }

  // Rounds a temp to a whole-number string, guarding against a malformed live
  // payload that omits the temp field (renders `—°` instead of `NaN°`).
  function temp(v) {
    const n = Number(v);
    return Number.isFinite(n) ? `${Math.round(n)}°` : "—°";
  }

  const days = Array.isArray(weather) ? weather.slice(0, 3) : [];
  const dayChips = days.map((d, i) => {
    const label = d.day || d.date || `DAY ${i + 1}`;
    const emoji = weatherEmoji(d.weathercode ?? d.code);
    const hi = d.hi ?? d.tempMax ?? d.temp_max;
    const lo = d.lo ?? d.tempMin ?? d.temp_min;
    return `${String(label).toUpperCase()} ${emoji} ${temp(hi)}/${temp(lo)}`;
  });

  const segments = [...parts, ...dayChips];

  return (
    <div className="weather-bar" role="status">
      {segments.length ? (
        segments.map((seg, i) => (
          <span key={i}>
            {i > 0 && <span className="sep">·</span>}
            {seg}
          </span>
        ))
      ) : (
        <span>Loading your forecast…</span>
      )}
    </div>
  );
}
