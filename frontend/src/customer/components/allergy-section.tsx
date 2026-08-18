/**
 * Allergy section (Preference Center) — the user's durable allergy/avoid list.
 * Backed by the backend `allergens` store (GET/PATCH /profile, set-replace, no FIFO
 * cap) which the constraint layer hard-filters on EVERY search. Unlike the preset
 * cuisine chips, each allergen is a free-text sentence → removable chip + add input.
 */
import { useState } from "react";
import { Plus, ShieldAlert } from "lucide-react";

interface Props {
  allergens: string[];
  onChange: (next: string[]) => void;
}

export function AllergySection({ allergens, onChange }: Props) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const a = draft.trim();
    if (!a || allergens.includes(a)) return;
    onChange([...allergens, a]);
    setDraft("");
  };
  const remove = (a: string) => onChange(allergens.filter((x) => x !== a));

  return (
    <section className="cpref__card cust-glass cpref__allergy-card">
      <div className="cpref__card-head">
        <span className="cpref__card-icon cpref__card-icon--danger" aria-hidden="true">
          <ShieldAlert size={18} />
        </span>
        <div>
          <b>Dị ứng / cần tránh</b>
          <p className="cpref__card-desc">
            Trợ lý sẽ loại món/quán có nguy cơ chứa những thứ này khỏi mọi gợi ý.
          </p>
        </div>
      </div>

      {allergens.length > 0 ? (
        <div className="cpref__chips cpref__chips--danger">
          {allergens.map((a) => (
            <span key={a} className="cust-chip is-selected cpref__allergy-chip">
              {a}
              <button
                type="button"
                className="cpref__allergy-x"
                onClick={() => remove(a)}
                aria-label={`Bỏ "${a}" khỏi danh sách dị ứng`}
                title="Bỏ khỏi danh sách"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="cpref__allergy-empty">
          Chưa có gì. Kể về dị ứng trong trò chuyện hoặc thêm ở đây để được lọc tự động.
        </p>
      )}

      <div className="cpref__allergy-add">
        <input
          className="cust-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="VD: đậu phộng, hải sản…"
          aria-label="Thêm thứ cần tránh"
        />
        <button
          type="button"
          className="cust-btn cust-btn-ghost"
          onClick={add}
          disabled={!draft.trim()}
        >
          <Plus size={15} /> Thêm
        </button>
      </div>
    </section>
  );
}
