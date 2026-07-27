/** GSM brand lockup — leaf logo + wordmark. `compact` hides the wordmark (icon rail / mobile). */
import { Leaf } from "lucide-react";
import "./brand-mark.css";

export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand-mark">
      <span className="brand-mark__logo" aria-hidden="true">
        <Leaf size={18} strokeWidth={2.4} />
      </span>
      {!compact && (
        <span className="brand-mark__text">
          <span className="brand-mark__title">GSM</span>
          <span className="brand-mark__sub">Trợ lý ẩm thực</span>
        </span>
      )}
    </div>
  );
}
