import { useState } from 'react';
import type { RunTrace, TraceObservation } from '../../types/monitoring';

function ObservationNode({
  observation,
  children,
}: {
  observation: TraceObservation;
  children: Map<string | null, TraceObservation[]>;
}) {
  const [showDetails, setShowDetails] = useState(false);
  const nested = children.get(observation.id) ?? [];
  const metadataParts = [
    observation.type,
    observation.model,
    observation.promptVersion != null ? `Prompt v${observation.promptVersion}` : null,
  ].filter(Boolean);

  return (
    <li className="trace-row-compact">
      <div
        className={`trace-row-main ${showDetails ? 'is-expanded' : ''}`}
        onClick={() => setShowDetails((prev) => !prev)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            setShowDetails((prev) => !prev);
          }
        }}
      >
        <div className="trace-row-copy">
          <strong>{observation.name}</strong>
          <span className="trace-row-desc">{metadataParts.join(' · ')}</span>
        </div>

        <div className="trace-row-right">
          {observation.totalTokens != null && observation.totalTokens > 0 && (
            <span>{observation.totalTokens} tokens</span>
          )}
          {observation.latencyMs != null && (
            <span className="trace-row-time">{Math.round(observation.latencyMs)} ms</span>
          )}
          {observation.costUsd != null && observation.costUsd > 0 && (
            <span>${observation.costUsd.toFixed(4)}</span>
          )}
        </div>
      </div>

      {showDetails && (
        <div className="trace-row-details">
          {observation.model && <div><strong>Model:</strong> <code>{observation.model}</code></div>}
          {observation.promptName && (
            <div>
              <strong>Prompt:</strong> {observation.promptName} {observation.promptVersion != null ? `(v${observation.promptVersion})` : ''}
            </div>
          )}
          {observation.timeToFirstTokenMs != null && <div><strong>TTFT:</strong> {Math.round(observation.timeToFirstTokenMs)} ms</div>}
          {observation.inputTokens != null && observation.inputTokens > 0 && (
            <div><strong>Tokens:</strong> {observation.inputTokens} in / {observation.outputTokens ?? 0} out ({observation.totalTokens ?? 0} total)</div>
          )}
          {observation.costUsd != null && <div><strong>Cost:</strong> ${observation.costUsd.toFixed(6)}</div>}
        </div>
      )}

      {nested.length > 0 && (
        <ol className="trace-row-nested">
          {nested.map((item) => (
            <ObservationNode key={item.id} observation={item} children={children} />
          ))}
        </ol>
      )}
    </li>
  );
}

export function AgentThinkingAccordion({
  trace,
  status,
  isStreaming = false,
}: {
  trace?: RunTrace;
  status?: 'processing' | 'ready' | 'unavailable';
  isStreaming?: boolean;
}) {
  // Default is CLOSED (false) unless processing/streaming
  const [open, setOpen] = useState(isStreaming || status === 'processing');

  const children = new Map<string | null, TraceObservation[]>();
  for (const observation of trace?.observations ?? []) {
    const siblings = children.get(observation.parentId) ?? [];
    siblings.push(observation);
    children.set(observation.parentId, siblings);
  }

  for (const siblings of children.values()) {
    siblings.sort((left, right) => (left.startedAt ?? '').localeCompare(right.startedAt ?? ''));
  }

  const roots =
    children.get(null) ??
    (trace?.observations.filter(
      (item) => !trace.observations.some((candidate) => candidate.id === item.parentId)
    ) ?? []);

  const label = isStreaming
    ? 'AI is working through the request'
    : status === 'processing'
      ? 'Trace is processing'
      : status === 'unavailable'
        ? 'Trace unavailable'
        : trace
          ? `AI completed ${trace.observations.length} observations`
          : 'Trace is processing';

  return (
    <section className="trace-card" aria-label="AI execution trace">
      <button
        type="button"
        className="trace-card__header"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className={`trace-card-icon ${isStreaming || status === 'processing' ? 'is-running' : ''}`} aria-hidden="true">
          ◇
        </span>
        <span className="trace-card-title-group">
          <strong>{label}</strong>
        </span>

        {trace && trace.totals && (
          <div className="trace-card-header-stats">
            {trace.totals.totalTokens != null && trace.totals.totalTokens > 0 && (
              <span>{trace.totals.totalTokens} tokens</span>
            )}
            {trace.totals.latencyMs != null && (
              <span>{Math.round(trace.totals.latencyMs)} ms</span>
            )}
            {trace.totals.totalCostUsd != null && trace.totals.totalCostUsd > 0 && (
              <span>${trace.totals.totalCostUsd.toFixed(4)}</span>
            )}
          </div>
        )}

        <span className="trace-card__toggle" aria-hidden="true">
          {open ? '−' : '+'}
        </span>
      </button>

      {open && trace && (
        <div className="trace-card__body">
          <ol className="trace-timeline">
            {roots.map((root) => (
              <ObservationNode key={root.id} observation={root} children={children} />
            ))}
          </ol>
          <div className="trace-totals">
            {trace.totals.totalTokens != null && <span>{trace.totals.totalTokens} tokens</span>}
            {trace.totals.latencyMs != null && <span>{Math.round(trace.totals.latencyMs)} ms</span>}
            {trace.totals.totalCostUsd != null && <span>${trace.totals.totalCostUsd.toFixed(4)}</span>}
          </div>
        </div>
      )}
    </section>
  );
}
