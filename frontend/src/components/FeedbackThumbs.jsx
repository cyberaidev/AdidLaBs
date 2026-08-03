import { useState } from "react";
import { postFeedback } from "../api.js";

// Thumbs up/down on a product photograph. Works signed-out (POST
// /api/feedback is public); one vote per item per browser, remembered in
// localStorage. Optimistic counts — the server response reconciles them.

const LS_KEY = "adidlabs-photo-votes";

function readVotes() {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveVote(itemId, vote) {
  try {
    const votes = readVotes();
    votes[itemId] = vote;
    localStorage.setItem(LS_KEY, JSON.stringify(votes));
  } catch {
    /* private mode — vote still posts, just not remembered */
  }
}

function ThumbIcon({ down }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      style={down ? { transform: "rotate(180deg)" } : undefined}
    >
      <path d="M7 10v10H4a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1h3zm3 10a2 2 0 0 1-2-2v-8.4L11.6 4a1.8 1.8 0 0 1 3.2 1.1L14 9h5a2 2 0 0 1 2 2.4l-1.3 6.5A2.6 2.6 0 0 1 17.1 20H10z" />
    </svg>
  );
}

export function FeedbackThumbs({ item }) {
  const [voted, setVoted] = useState(() => readVotes()[item.item_id] || null);
  const [counts, setCounts] = useState({
    up: Number(item.feedback_up) || 0,
    down: Number(item.feedback_down) || 0,
  });

  async function vote(kind) {
    if (voted) return; // one vote per browser
    setVoted(kind);
    saveVote(item.item_id, kind);
    setCounts((c) => ({ ...c, [kind]: c[kind] + 1 }));
    const resp = await postFeedback(item.item_id, kind);
    if (resp && Number.isFinite(resp.up)) {
      setCounts({ up: resp.up, down: resp.down });
    }
  }

  return (
    <span className="fb-thumbs" aria-label="Photo feedback">
      <button
        type="button"
        className={`fb-thumb ${voted === "up" ? "active" : ""}`}
        aria-label="Good photo"
        aria-pressed={voted === "up"}
        disabled={Boolean(voted)}
        onClick={(e) => {
          e.stopPropagation();
          vote("up");
        }}
      >
        <ThumbIcon />
        {counts.up > 0 && <i>{counts.up}</i>}
      </button>
      <button
        type="button"
        className={`fb-thumb ${voted === "down" ? "active" : ""}`}
        aria-label="Wrong or poor photo"
        aria-pressed={voted === "down"}
        disabled={Boolean(voted)}
        onClick={(e) => {
          e.stopPropagation();
          vote("down");
        }}
      >
        <ThumbIcon down />
        {counts.down > 0 && <i>{counts.down}</i>}
      </button>
    </span>
  );
}
