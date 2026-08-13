/**
 * Conversation-history list for the sidebar (ChatGPT-style). A search-filtered list of the
 * user's past conversations; each row reopens on click, with inline rename (pencil) and a
 * delete (trash → confirm dialog). Kept as its own component so app-sidebar stays lean.
 *
 * Search is client-side (filter the loaded list by title substring) — sufficient for a single
 * user's ≤100 sessions; no backend call per keystroke.
 */
import { useMemo, useState } from "react";
import { Check, Pencil, Search, Trash2, X } from "lucide-react";
import type { SessionSummary } from "../api/customer-agent-client";
import "./session-history-list.css";

interface Props {
  sessions: SessionSummary[];
  activeSessionId: string;
  loading: boolean;
  onOpen: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
  onRename: (sessionId: string, title: string) => void;
}

/** Compact Vietnamese relative-time ("vừa xong" / "5 phút trước" / "hôm qua" / dd/mm). */
function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const sec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (sec < 60) return "vừa xong";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} phút trước`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} giờ trước`;
  const day = Math.floor(hr / 24);
  if (day === 1) return "hôm qua";
  if (day < 7) return `${day} ngày trước`;
  const d = new Date(iso);
  return `${d.getDate().toString().padStart(2, "0")}/${(d.getMonth() + 1)
    .toString()
    .padStart(2, "0")}`;
}

export function SessionHistoryList({
  sessions,
  activeSessionId,
  loading,
  onOpen,
  onDelete,
  onRename,
}: Props) {
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => (s.title ?? "").toLowerCase().includes(q));
  }, [sessions, query]);

  const startEdit = (s: SessionSummary) => {
    setEditingId(s.session_id);
    setDraft(s.title ?? "");
  };
  const commitEdit = () => {
    const id = editingId;
    const title = draft.trim();
    if (id && title) onRename(id, title);
    setEditingId(null);
    setDraft("");
  };
  const cancelEdit = () => {
    setEditingId(null);
    setDraft("");
  };
  const confirmDelete = (s: SessionSummary) => {
    const label = s.title?.trim() || "hội thoại này";
    if (window.confirm(`Xóa "${label}"? Không thể hoàn tác.`)) onDelete(s.session_id);
  };

  return (
    <div className="session-history">
      <div className="session-history__search">
        <Search size={14} className="session-history__search-icon" />
        <input
          type="text"
          className="session-history__search-input"
          placeholder="Tìm hội thoại…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Tìm hội thoại"
        />
      </div>

      <div className="session-history__list cust-scroll">
        {loading && sessions.length === 0 ? (
          <p className="session-history__empty">Đang tải…</p>
        ) : filtered.length === 0 ? (
          <p className="session-history__empty">
            {query ? "Không tìm thấy hội thoại." : "Chưa có hội thoại nào."}
          </p>
        ) : (
          filtered.map((s) => {
            const active = s.session_id === activeSessionId;
            const editing = s.session_id === editingId;
            return (
              <div
                key={s.session_id}
                className={`session-history__item ${active ? "is-active" : ""}`}
              >
                {editing ? (
                  <div className="session-history__rename">
                    <input
                      autoFocus
                      className="session-history__rename-input"
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEdit();
                        if (e.key === "Escape") cancelEdit();
                      }}
                    />
                    <button
                      type="button"
                      className="cust-btn cust-btn-icon"
                      onClick={commitEdit}
                      aria-label="Lưu tên"
                    >
                      <Check size={14} />
                    </button>
                    <button
                      type="button"
                      className="cust-btn cust-btn-icon"
                      onClick={cancelEdit}
                      aria-label="Hủy đổi tên"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <>
                    <button
                      type="button"
                      className="session-history__open"
                      onClick={() => onOpen(s.session_id)}
                      title={s.title ?? "Hội thoại không tên"}
                    >
                      <span className="session-history__title">
                        {s.title?.trim() || "Hội thoại không tên"}
                      </span>
                      <span className="session-history__time">
                        {relativeTime(s.updated_at)}
                      </span>
                    </button>
                    <div className="session-history__actions">
                      <button
                        type="button"
                        className="cust-btn cust-btn-icon"
                        onClick={() => startEdit(s)}
                        aria-label="Đổi tên hội thoại"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        type="button"
                        className="cust-btn cust-btn-icon"
                        onClick={() => confirmDelete(s)}
                        aria-label="Xóa hội thoại"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
