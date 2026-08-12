import { useEffect, useState, useMemo } from 'react';
import { fetchProcessedPolicies, type PolicyDocumentItem } from '../api/merchantProfileApi';

interface MarkdownSection {
  id: string;
  level: number; // 1, 2, 3
  title: string;
  contentLines: string[];
  subSections: MarkdownSection[];
}

/** Parse raw canonical markdown lines into structured collapsible sections by header level (#, ##, ###). */
function parseCollapsibleMarkdown(markdown: string): MarkdownSection[] {
  if (!markdown) return [];
  const lines = markdown.split('\n');
  const rootSections: MarkdownSection[] = [];
  let currentSection: MarkdownSection | null = null;
  let sectionCounter = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    const h1Match = trimmed.match(/^#\s+(.+)$/);
    const h2Match = trimmed.match(/^##\s+(.+)$/);
    const h3Match = trimmed.match(/^###\s+(.+)$/);

    if (h1Match || h2Match || h3Match) {
      sectionCounter++;
      const level = h1Match ? 1 : h2Match ? 2 : 3;
      const title = (h1Match || h2Match || h3Match)![1];
      const newSec: MarkdownSection = {
        id: `sec-${sectionCounter}`,
        level,
        title,
        contentLines: [],
        subSections: [],
      };

      if (level === 1) {
        rootSections.push(newSec);
        currentSection = newSec;
      } else if (level === 2) {
        if (rootSections.length > 0) {
          rootSections[rootSections.length - 1].subSections.push(newSec);
        } else {
          rootSections.push(newSec);
        }
        currentSection = newSec;
      } else {
        // level 3
        const parentRoot = rootSections[rootSections.length - 1];
        if (parentRoot && parentRoot.subSections.length > 0) {
          parentRoot.subSections[parentRoot.subSections.length - 1].subSections.push(newSec);
        } else if (parentRoot) {
          parentRoot.subSections.push(newSec);
        } else {
          rootSections.push(newSec);
        }
        currentSection = newSec;
      }
    } else {
      if (currentSection) {
        currentSection.contentLines.push(line);
      } else if (rootSections.length > 0) {
        rootSections[rootSections.length - 1].contentLines.push(line);
      } else {
        sectionCounter++;
        const defaultSec: MarkdownSection = {
          id: `sec-${sectionCounter}`,
          level: 1,
          title: 'Tổng quan chính sách',
          contentLines: [line],
          subSections: [],
        };
        rootSections.push(defaultSec);
        currentSection = defaultSec;
      }
    }
  }
  return rootSections;
}

export function PolicyDocumentsPage() {
  const [documents, setDocuments] = useState<PolicyDocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDocId, setSelectedDocId] = useState<string>('');
  const [collapsedMap, setCollapsedMap] = useState<Record<string, boolean>>({});
  const [search, setSearch] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchProcessedPolicies()
      .then((res) => {
        if (active) {
          const docs = res.documents || [];
          setDocuments(docs);
          if (docs.length > 0) {
            setSelectedDocId(docs[0].document_id);
          }
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const activeDoc = useMemo(() => {
    return documents.find((d) => d.document_id === selectedDocId) || documents[0];
  }, [documents, selectedDocId]);

  const parsedSections = useMemo(() => {
    if (!activeDoc?.document_text) return [];
    return parseCollapsibleMarkdown(activeDoc.document_text);
  }, [activeDoc]);

  const toggleCollapse = (id: string) => {
    setCollapsedMap((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const expandAll = () => setCollapsedMap({});
  const collapseAll = () => {
    const map: Record<string, boolean> = {};
    const walk = (secs: MarkdownSection[]) => {
      for (const s of secs) {
        map[s.id] = true;
        walk(s.subSections);
      }
    };
    walk(parsedSections);
    setCollapsedMap(map);
  };

  const renderSection = (sec: MarkdownSection) => {
    const isCollapsed = !!collapsedMap[sec.id];
    const hasSub = sec.subSections.length > 0;
    const bodyText = sec.contentLines.join('\n').trim();

    if (search && !sec.title.toLowerCase().includes(search.toLowerCase()) && !bodyText.toLowerCase().includes(search.toLowerCase())) {
      return null;
    }

    return (
      <div key={sec.id} className="border-l-2 border-[#00a398]/30 pl-3 py-1 space-y-2">
        {/* Section Header Bar */}
        <div
          onClick={() => toggleCollapse(sec.id)}
          className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-all ${
            sec.level === 1
              ? 'bg-white border border-slate-200 hover:border-[#00a398]/60 shadow-sm'
              : sec.level === 2
              ? 'bg-slate-50 border border-slate-200 hover:bg-slate-100'
              : 'bg-white/60 hover:bg-slate-100'
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="text-[#00a398] text-xs font-bold w-4 text-center">
              {isCollapsed ? '▶' : '▼'}
            </span>
            <span
              className={`font-bold ${
                sec.level === 1 ? 'text-slate-900 text-base' : sec.level === 2 ? 'text-slate-800 text-sm' : 'text-slate-700 text-xs'
              }`}
            >
              {sec.title}
            </span>
          </div>

          <span className="text-[10px] font-bold text-slate-500 px-2 py-0.5 rounded bg-slate-100 border border-slate-200">
            H{sec.level}
          </span>
        </div>

        {/* Section Body Content */}
        {!isCollapsed && (
          <div className="space-y-3 pl-2">
            {bodyText && (
              <div className="text-slate-700 text-sm leading-relaxed whitespace-pre-line bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
                {bodyText}
              </div>
            )}

            {/* Nested Subsections */}
            {hasSub && <div className="space-y-2 pt-1">{sec.subSections.map((sub) => renderSection(sub))}</div>}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full overflow-y-auto chat-scrollbar bg-[#f8fafc] p-6 pb-20 space-y-6">
      {/* Page Header - Xanh SM Theme */}
      <div className="bg-gradient-to-r from-[#00a398] to-[#007a73] rounded-2xl p-6 text-white shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-teal-100 uppercase tracking-wider mb-1">
            <span>TÀI LIỆU CHÍNH THỨC</span>
            <span>•</span>
            <span>CHÍNH SÁCH GREEN SM</span>
          </div>
          <h1 className="text-2xl font-extrabold text-white flex items-center gap-2">
            <span>📜 Trung Tâm Quy Định & Điều Khoản</span>
          </h1>
          <p className="text-teal-50 text-sm mt-1">
            Tra cứu toàn bộ tài liệu chính sách đã chuẩn hóa, cho phép thu gọn/mở rộng theo tiêu đề H1, H2, H3.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-500 animate-pulse">Đang tải danh sách chính sách...</div>
      ) : documents.length === 0 ? (
        <div className="text-center py-12 bg-white border border-slate-200 rounded-xl text-slate-500">
          Chưa có tài liệu chính sách nào được xử lý trong cơ sở dữ liệu.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Left Sidebar Document Selector */}
          <div className="lg:col-span-1 space-y-2">
            <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider px-1 mb-2">
              DANH SÁCH TÀI LIỆU ({documents.length})
            </h2>
            <div className="space-y-1.5">
              {documents.map((doc) => (
                <button
                  key={doc.document_id}
                  type="button"
                  onClick={() => setSelectedDocId(doc.document_id)}
                  className={`w-full text-left p-3 rounded-xl border text-xs font-semibold transition-all ${
                    selectedDocId === doc.document_id
                      ? 'bg-[#00a398] text-white border-[#00a398] shadow-sm font-bold'
                      : 'bg-white text-slate-700 border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <div className="truncate font-bold">{doc.title}</div>
                  <div className="text-[10px] opacity-80 font-mono mt-0.5">{doc.document_id}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Right Main Viewer */}
          <div className="lg:col-span-3 space-y-4">
            {/* Action Bar */}
            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col md:flex-row items-center justify-between gap-4">
              <input
                type="text"
                placeholder="Tìm từ khóa trong tài liệu này..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full md:w-80 bg-slate-50 border border-slate-300 rounded-lg px-4 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#00a398]"
              />

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={expandAll}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-100 hover:bg-slate-200 text-slate-700"
                >
                  Mở tất cả
                </button>
                <button
                  type="button"
                  onClick={collapseAll}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-100 hover:bg-slate-200 text-slate-700"
                >
                  Thu gọn tất cả
                </button>
              </div>
            </div>

            {/* Document Details Header */}
            {activeDoc && (
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-extrabold text-slate-900">{activeDoc.title}</h2>
                  <a
                    href={activeDoc.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-[#00a398] font-semibold hover:underline flex items-center gap-1 mt-0.5"
                  >
                    <span>🌐 Nguồn chính thức: {activeDoc.source_url}</span>
                  </a>
                </div>
                <span className="px-2.5 py-1 rounded bg-teal-50 text-teal-700 border border-teal-200 text-xs font-bold">
                  {activeDoc.category}
                </span>
              </div>
            )}

            {/* Collapsible Sections Container */}
            <div className="bg-slate-50/60 border border-slate-200 rounded-xl p-5 space-y-4 max-h-[70vh] overflow-y-auto chat-scrollbar">
              {parsedSections.map((sec) => renderSection(sec))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
