/**
 * Restaurant result card. Renders one candidate from the agent (or merchant search):
 * cuisine gradient avatar, name, meta, rating stars, distance, and a match-score ring.
 */
import type { CSSProperties } from "react";
import { StarRating } from "./star-rating";
import type { RestaurantResult } from "../api/customer-agent-client";
import "./restaurant-card.css";

/** Emoji glyph + gradient hue picked from the cuisine text (stable, decorative). */
const CUISINE_GLYPH: Array<[RegExp, string]> = [
  [/phở|bún|việt|viet/i, "🍜"],
  [/cơm|com|rice/i, "🍚"],
  [/nhật|japan|sushi/i, "🍣"],
  [/hàn|korea/i, "🍲"],
  [/ý|italia|pizza|pasta/i, "🍕"],
  [/burger|mỹ|american/i, "🍔"],
  [/trà|tea|cà phê|coffee|drink/i, "🧋"],
  [/chay|vegan/i, "🥗"],
];

function glyphFor(cuisine?: string | null): string {
  if (!cuisine) return "🍽️";
  for (const [re, glyph] of CUISINE_GLYPH) if (re.test(cuisine)) return glyph;
  return "🍽️";
}

export function RestaurantCard({
  item,
  rank,
}: {
  item: RestaurantResult;
  rank?: number;
}) {
  const match = item.match_score != null ? Math.round(item.match_score * 100) : null;
  return (
    <article className="rcard cust-rise">
      <div className="rcard__avatar">
        <span>{glyphFor(item.cuisine)}</span>
        {rank != null && <span className="rcard__rank">#{rank}</span>}
      </div>

      <div className="rcard__body">
        <h3 className="rcard__name">{item.name}</h3>
        <p className="rcard__meta">
          {[item.cuisine, item.address].filter(Boolean).join(" · ") || "Quán ăn"}
        </p>
        <div className="rcard__stats">
          {item.avg_rating != null && (
            <span className="rcard__stat">
              <StarRating value={item.avg_rating} />
              <b>{item.avg_rating.toFixed(1)}</b>
            </span>
          )}
          {item.distance_km != null && (
            <span className="rcard__stat rcard__stat--muted">
              📍 {item.distance_km.toFixed(1)} km
            </span>
          )}
        </div>
      </div>

      {match != null && (
        <div
          className="rcard__match"
          style={{ "--pct": match } as CSSProperties}
          title={`Độ phù hợp ${match}%`}
        >
          <span className="rcard__match-num">{match}</span>
          <span className="rcard__match-lbl">match</span>
        </div>
      )}
    </article>
  );
}
