/**
 * Decorative GSM canvas: green gradient wash + slow-floating blurred orbs (emerald +
 * one warm amber accent) behind the glass surfaces. Purely presentational (aria-hidden);
 * sits at the back of a position:relative parent. Light/dark aware; perf-tuned (fewer,
 * smaller orbs on mobile; motion disabled for reduced-motion users).
 */
import "./ambient-background.css";

export function AmbientBackground({ variant = "default" }: { variant?: "default" | "hero" }) {
  return (
    <div className={`cust-ambient cust-ambient--${variant}`} aria-hidden="true">
      <span className="cust-orb cust-orb--emerald" />
      <span className="cust-orb cust-orb--teal" />
      <span className="cust-orb cust-orb--amber" />
      <div className="cust-ambient__grain" />
    </div>
  );
}
