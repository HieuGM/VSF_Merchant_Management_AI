/**
 * Decorative GSM canvas (fe reference): soft green gradient wash + a few slow-floating
 * blurred orbs, PLUS low-opacity LEAF shapes in the four corners. Purely presentational
 * (aria-hidden); sits at the back of a position:relative parent. Light/dark aware;
 * motion disabled for reduced-motion users.
 */
import { Leaf } from "lucide-react";
import "./ambient-background.css";

export function AmbientBackground({ variant = "default" }: { variant?: "default" | "hero" }) {
  return (
    <div className={`cust-ambient cust-ambient--${variant}`} aria-hidden="true">
      <span className="cust-orb cust-orb--emerald" />
      <span className="cust-orb cust-orb--teal" />
      <Leaf className="cust-leaf cust-leaf--tl" size={150} strokeWidth={1.2} />
      <Leaf className="cust-leaf cust-leaf--tr" size={190} strokeWidth={1.2} />
      <Leaf className="cust-leaf cust-leaf--bl" size={170} strokeWidth={1.2} />
      <Leaf className="cust-leaf cust-leaf--br" size={210} strokeWidth={1.2} />
      <div className="cust-ambient__grain" />
    </div>
  );
}
