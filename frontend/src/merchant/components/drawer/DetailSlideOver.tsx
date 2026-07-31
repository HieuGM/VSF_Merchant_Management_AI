import { useEffect, useMemo, useState } from 'react';
import { getMerchantMap } from '../../api/mapApi';
import { getRunTrace } from '../../api/traceApi';
import type { ChatMessage } from '../../types/merchantChat';
import type { AnalyzedMerchant } from '../../types/merchantChat';
import type { MerchantMapFeatureCollection, TraceEvent } from '../../types/monitoring';
import { MerchantMap } from '../map/MerchantMap';

type Tab = 'results' | 'map' | 'trace' | 'tools' | 'llm' | 'data';

function merchantsFromEvents(events: TraceEvent[]): AnalyzedMerchant[] {
  const collected = new Map<string, AnalyzedMerchant>();
  for (const event of events) {
    const result = event.outputSummary.result;
    if (!result || typeof result !== 'object' || Array.isArray(result)) continue;
    const payload = result as Record<string, unknown>;
    const rows = Array.isArray(payload.merchants)
      ? payload.merchants
      : Array.isArray(payload.competitors)
        ? payload.competitors
        : Array.isArray(payload.cohort_members)
          ? payload.cohort_members
          : [];
    for (const raw of rows) {
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue;
      const item = raw as Record<string, unknown>;
      if (!item.merchant_id || !item.name) continue;
      collected.set(String(item.merchant_id), {
        merchant_id: String(item.merchant_id),
        name: String(item.name),
        cuisine: typeof item.cuisine === 'string' ? item.cuisine : undefined,
        address: typeof item.address === 'string' ? item.address : undefined,
        rating: typeof item.rating === 'number' ? item.rating : undefined,
        distance_km: typeof item.distance_km === 'number' ? item.distance_km : undefined,
        sourceToolName: event.toolName ?? undefined,
      });
    }
  }
  return [...collected.values()];
}

export function DetailSlideOver({
  message,
  merchantId,
  onClose,
}: {
  message: ChatMessage | null;
  merchantId: string;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>('results');
  const [map, setMap] = useState<MerchantMapFeatureCollection | null>(null);
  const [mapError, setMapError] = useState('');
  const [persistedEvents, setPersistedEvents] = useState<TraceEvent[]>([]);
  const [traceError, setTraceError] = useState('');
  const events = persistedEvents.length > 0 ? persistedEvents : message?.traceEvents ?? [];
  const persistedCandidates = useMemo(() => merchantsFromEvents(events), [events]);
  const candidates = message?.analyzedMerchants?.length ? message.analyzedMerchants : persistedCandidates;
  const toolEvents = events.filter((event) => event.eventType === 'tool_finished');
  const llmEvents = events.filter((event) => event.eventType === 'crewai_llm_finished');
  const dataEvents = events.filter((event) => ['sql_query', 'cache', 'error', 'agent_error'].includes(event.eventType));

  useEffect(() => {
    setTab('results');
    setMap(null);
    setMapError('');
    setPersistedEvents([]);
    setTraceError('');
    if (!message?.traceId) return;
    let active = true;
    getRunTrace(message.traceId)
      .then((trace) => active && setPersistedEvents(trace.events))
      .catch((error) => active && setTraceError(error instanceof Error ? error.message : 'Không tải được persisted trace.'));
    return () => { active = false; };
  }, [message?.id, message?.traceId]);

  useEffect(() => {
    setMap(null);
    setMapError('');
    if (!message || candidates.length === 0) return;
    let active = true;
    getMerchantMap(merchantId, undefined, { candidateMerchantIds: candidates.map((item) => item.merchant_id) })
      .then((result) => active && setMap(result))
      .catch((error) => active && setMapError(error instanceof Error ? error.message : 'Không tải được bản đồ.'));
    return () => { active = false; };
  }, [message?.id, merchantId, candidates.map((item) => item.merchant_id).join(',')]);

  const tabs = useMemo(() => [
    ['results', `Kết quả ${candidates.length}`],
    ['map', 'Bản đồ'],
    ['trace', `Trace ${events.length}`],
    ['tools', `Tools ${toolEvents.length}`],
    ['llm', `LLM ${llmEvents.length}`],
    ['data', `Data ${dataEvents.length}`],
  ] as Array<[Tab, string]>, [candidates.length, events.length, toolEvents.length, llmEvents.length, dataEvents.length]);

  if (!message) return null;
  const renderEvents = (items: typeof events) => items.length === 0
    ? <div className="detail-empty">Backend không ghi nhận event loại này.</div>
    : <div className="raw-events">{items.map((event, index) => (
        <details key={event.eventId ?? index}>
          <summary><strong>{event.eventType}</strong><span>{event.agentName || event.toolName || event.status}</span></summary>
          <pre>{JSON.stringify(event.outputSummary, null, 2)}</pre>
        </details>
      ))}</div>;

  return (
    <>
      <button type="button" className="detail-scrim" onClick={onClose} aria-label="Đóng chi tiết" />
      <aside className="detail-pane" aria-label="Chi tiết response">
        <header>
          <div><p>RESPONSE INSPECTOR</p><h2>Run details</h2><code>{message.traceId ?? 'trace pending'}</code></div>
          <button type="button" onClick={onClose} aria-label="Đóng pane">×</button>
        </header>
        <nav className="detail-tabs" role="tablist">
          {tabs.map(([key, label]) => <button type="button" role="tab" aria-selected={tab === key} key={key} onClick={() => setTab(key)}>{label}</button>)}
        </nav>
        <div className="detail-content chat-scrollbar">
          {tab === 'results' && (
            <div className="result-list">
              {candidates.map((item, index) => (
                <article key={item.merchant_id}>
                  <span>{index + 1}</span>
                  <div><strong>{item.name}</strong><small>{[item.cuisine, item.address].filter(Boolean).join(' · ') || item.merchant_id}</small></div>
                  <dl>{item.rating != null && <><dt>Rating</dt><dd>{item.rating}</dd></>}{item.distance_km != null && <><dt>Distance</dt><dd>{item.distance_km} km</dd></>}</dl>
                </article>
              ))}
            </div>
          )}
          {tab === 'map' && (map ? <><MerchantMap featureCollection={map} /><div className="map-legend">{map.features.map((feature, index) => <div key={`${String(feature.properties.merchant_id)}-${index}`}><i className={`role-${String(feature.properties.role)}`} /><span>{String(feature.properties.name ?? feature.properties.role)}</span></div>)}</div></> : <div className="detail-empty">{mapError || 'Đang tải GeoJSON từ backend…'}</div>)}
          {tab === 'trace' && (traceError ? <div className="detail-empty">{traceError}</div> : renderEvents(events))}
          {tab === 'tools' && renderEvents(toolEvents)}
          {tab === 'llm' && renderEvents(llmEvents)}
          {tab === 'data' && renderEvents(dataEvents)}
        </div>
      </aside>
    </>
  );
}
