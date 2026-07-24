/** Compact star rating (0–5) with a half-star; label shows the numeric value. */
export function StarRating({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(5, value));
  return (
    <span className="cust-stars" title={`${clamped.toFixed(1)} / 5`}>
      {[0, 1, 2, 3, 4].map((i) => {
        const fill = Math.max(0, Math.min(1, clamped - i));
        return (
          <span key={i} className="cust-star">
            <span className="cust-star__bg">★</span>
            <span className="cust-star__fg" style={{ width: `${fill * 100}%` }}>
              ★
            </span>
          </span>
        );
      })}
    </span>
  );
}
