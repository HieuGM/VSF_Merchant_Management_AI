/** 0–5 star rating with fractional fill via a clipped overlay (Lucide Star). */
import { Star } from "lucide-react";
import "./star-rating.css";

interface Props {
  value: number;
  size?: number;
}

export function StarRating({ value, size = 14 }: Props) {
  const clamped = Math.max(0, Math.min(5, value || 0));
  const pct = (clamped / 5) * 100;
  return (
    <span className="star-rating" role="img" aria-label={`${clamped.toFixed(1)} trên 5 sao`}>
      <span className="star-rating__row star-rating__bg" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => (
          <Star key={i} size={size} strokeWidth={0} className="star-rating__muted" />
        ))}
      </span>
      <span
        className="star-rating__row star-rating__fg"
        style={{ width: `${pct}%` }}
        aria-hidden="true"
      >
        {[0, 1, 2, 3, 4].map((i) => (
          <Star key={i} size={size} strokeWidth={0} fill="currentColor" className="star-rating__on" />
        ))}
      </span>
    </span>
  );
}
