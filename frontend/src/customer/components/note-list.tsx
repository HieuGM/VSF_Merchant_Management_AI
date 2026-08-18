/**
 * Assistant memory notes list (Preference Center). Each note shows its durability —
 * "tạm thời — còn N ngày" (TTL from context_memory.note_expiries) or "lâu dài" —
 * plus a per-note delete (×). Deleting is optimistic with rollback: the backend also
 * drops the note's allergen twin, so a deleted allergy stops filtering at once.
 */
import { useState } from "react";
import { Clock3, Hourglass, StickyNote, X } from "lucide-react";

const MAX_NOTES = 8; // mirrors backend _MAX_NOTES (FIFO cap)

/** Days-until-expiry text for a temporary note; null when the ISO parse fails. */
function daysLeft(iso: string): number | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.ceil((t - Date.now()) / 86_400_000));
}

interface Props {
  notes: string[];
  expiries: Record<string, string>;
  onDelete: (note: string) => Promise<void>;
}

export function NoteList({ notes, expiries, onDelete }: Props) {
  const [busy, setBusy] = useState<string | null>(null);

  const remove = async (n: string) => {
    if (busy) return;
    setBusy(n);
    try {
      await onDelete(n);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <div className="cpref__card-head">
        <span className="cpref__card-icon" aria-hidden="true">
          <StickyNote size={18} />
        </span>
        <div className="cpref__notes-title">
          <b>Ghi nhớ của trợ lý</b>
          <p className="cpref__card-desc">Những điều lâu dài trợ lý ghi nhớ để gợi ý sát hơn.</p>
        </div>
        {notes.length > 0 && (
          <span
            className={`cpref__count ${notes.length >= MAX_NOTES ? "is-full" : ""}`}
            aria-label={`${notes.length} mục ghi nhớ`}
            title={
              notes.length >= MAX_NOTES
                ? `Đã đầy ${MAX_NOTES}/${MAX_NOTES} — ghi nhớ mới nhất sẽ thay mục cũ nhất`
                : `${notes.length}/${MAX_NOTES} mục`
            }
          >
            {notes.length}/{MAX_NOTES}
          </span>
        )}
      </div>

      {notes.length > 0 ? (
        <ul className="cpref__notes">
          {notes.map((n) => {
            const exp = expiries[n.toLowerCase()];
            const left = exp ? daysLeft(exp) : null;
            return (
              <li key={n} className="cpref__note-item">
                <span className="cpref__note-bar" aria-hidden="true" />
                <div className="cpref__note-main">
                  <span className="cpref__note-text">{n}</span>
                  {exp && left != null && (
                    <span className={`cpref__note-ttl ${left <= 1 ? "is-expiring" : ""}`}>
                      {left <= 1 ? <Hourglass size={11} /> : <Clock3 size={11} />}
                      tạm thời — {left <= 0 ? "sắp hết hạn" : left === 1 ? "còn ~1 ngày" : `còn ${left} ngày`}
                    </span>
                  )}
                  {!exp && (
                    <span className="cpref__note-ttl is-durable">
                      <Clock3 size={11} /> lâu dài
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  className="cpref__note-x"
                  onClick={() => remove(n)}
                  disabled={busy === n}
                  aria-label={`Xóa ghi nhớ "${n}"`}
                  title="Xóa ghi nhớ này"
                >
                  {busy === n ? "…" : <X size={13} />}
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="cpref__notes-empty">
          <p>
            Chưa có ghi nhớ nào. Khi bạn kể về dị ứng, chế độ ăn lâu dài hay sở thích đặc biệt,
            trợ lý sẽ tự ghi lại để gợi ý chuẩn hơn lần sau.
          </p>
        </div>
      )}
    </>
  );
}
