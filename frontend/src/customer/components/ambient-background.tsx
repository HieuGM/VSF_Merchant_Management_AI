/**
 * Decorative warm canvas: a gradient wash + slow-floating blurred orbs behind the
 * glass surfaces. Purely presentational (aria-hidden); sits at the back of a
 * position:relative parent.
 */
import "./ambient-background.css";

export function AmbientBackground({ variant = "default" }: { variant?: "default" | "hero" }) {
  return (
    <div className={`cust-ambient cust-ambient--${variant}`} aria-hidden="true">
      <span className="cust-orb cust-orb--coral" />
      <span className="cust-orb cust-orb--amber" />
      <span className="cust-orb cust-orb--rose" />
      <div className="cust-ambient__grain" />
    </div>
  );
}
