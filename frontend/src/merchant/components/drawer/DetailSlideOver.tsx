import { useEffect, useMemo, useState } from 'react';
import { getMerchantMap } from '../../api/mapApi';
import type { ChatMessage } from '../../types/merchantChat';
import type { MerchantMapFeatureCollection } from '../../types/monitoring';
import { AgentThinkingAccordion } from '../chat/AgentThinkingAccordion';
import { MerchantMap } from '../map/MerchantMap';

type Tab = 'results' | 'map' | 'trace';

export function DetailSlideOver({
  message,
  merchantId,
  initialTab = 'results',
  onClose,
}: {
  message: ChatMessage | null;
  merchantId: string;
  initialTab?: Tab;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [map, setMap] = useState<MerchantMapFeatureCollection | null>(null);
  const [mapError, setMapError] = useState('');
  const candidates = useMemo(() => message?.analyzedMerchants ?? [], [message?.analyzedMerchants]);

  useEffect(() => {
    setTab(initialTab);
    setMap(null);
    setMapError('');
  }, [message?.id, initialTab]);

  useEffect(() => {
    if (!message) return;
    let active = true;
    const candidateIds = candidates
      .map((item) => item.merchant_id)
      .filter((id): id is string => Boolean(id));

    getMerchantMap(merchantId, undefined, { candidateMerchantIds: candidateIds })
      .then((result) => active && setMap(result))
      .catch((error) => active && setMapError(error instanceof Error ? error.message : 'Không tải được bản đồ.'));

    return () => { active = false; };
  }, [message?.id, merchantId, candidates]);

  if (!message) return null;
  return (
    <>
      <button type="button" className="detail-scrim" onClick={onClose} aria-label="Đóng chi tiết" />
      <aside className="detail-pane" aria-label="Chi tiết response">
        <header>
          <div><p>RESPONSE INSPECTOR</p><h2>Run details</h2><code>{message.traceId ?? 'trace pending'}</code></div>
          <button type="button" onClick={onClose} aria-label="Đóng pane">×</button>
        </header>
        <nav className="detail-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === 'results'} onClick={() => setTab('results')}>Kết quả {candidates.length}</button>
          <button type="button" role="tab" aria-selected={tab === 'map'} onClick={() => setTab('map')}>Bản đồ</button>
          <button type="button" role="tab" aria-selected={tab === 'trace'} onClick={() => setTab('trace')}>Trace</button>
        </nav>
        <div className="detail-content chat-scrollbar">
          {tab === 'results' && <div className="result-list">{candidates.map((item, index) => (
            <article key={item.merchant_id}><span>{index + 1}</span><div><strong>{item.name}</strong><small>{item.cuisine ?? item.merchant_id}</small></div></article>
          ))}</div>}
          {tab === 'map' && (map ? <MerchantMap featureCollection={map} /> : <div className="detail-empty">{mapError || 'Đang tải GeoJSON từ backend…'}</div>)}
          {tab === 'trace' && <AgentThinkingAccordion trace={message.trace} status={message.traceStatus} />}
        </div>
      </aside>
    </>
  );
}
