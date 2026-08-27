import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { Highlight, ProvenanceResult } from '../types';

function riskColor(h: Highlight): string {
  if (h.feature_flags.explicit_risk) return '#dc2626';
  if (h.feature_flags.symptom_change) return '#f59e0b';
  if (h.feature_flags.unresolved_task) return '#2563eb';
  return '#9ca3af';
}

export default function GlancePanel({
  patientId,
  onViewSource,
  onOpenTasks,
}: {
  patientId: string;
  onViewSource: (p: ProvenanceResult) => void;
  onOpenTasks?: (taskId: string) => void;
}) {
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      setHighlights((await api.getGlance(patientId, signal)).highlights);
      setError(null);
    } catch (e: any) {
      if (e?.name !== 'AbortError') setError(String(e));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  async function setStatus(id: string, status: string) {
    try {
      await api.setStatus(id, status);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function viewSource(id: string) {
    try {
      onViewSource(await api.getProvenance(id));
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <section className="glance-panel clinical-view" aria-labelledby="glance-heading">
      <div className="view-title-row">
        <div><p className="eyebrow">What matters now</p><h2 id="glance-heading">Glance</h2></div>
        <span className="record-count">Top {highlights.length}</span>
      </div>
      {loading && <div className="loading-card">Loading precomputed priorities…</div>}
      {error && <div className="form-error">{error}</div>}
      {!loading && highlights.length === 0 && <div className="empty-state"><h3>No current highlights</h3><p>Nothing has been prioritized for this patient.</p></div>}
      {highlights.map((h) => (
        <div key={h.highlight_id} className={`highlight-card ${h.status}`}>
          <span className="risk-dot" style={{ background: riskColor(h) }} aria-hidden="true" />
          <div className="highlight-body">
            <div className="highlight-text">{h.text}</div>
            <div className="highlight-reason">{h.risk_reason}</div>
            <div className="highlight-actions">
              {h.task_id ? (
                <button
                  className="source-action"
                  onClick={() => onOpenTasks?.(h.task_id!)}
                >
                  Open Task <span aria-hidden="true">→</span>
                </button>
              ) : (
                <button className="source-action" onClick={() => viewSource(h.highlight_id)}>View source <span aria-hidden="true">→</span></button>
              )}
              {h.task_id == null && h.feature_flags.unresolved_task && onOpenTasks && (
                <span className="unresolved-tag">Unresolved task</span>
              )}
              <button className="feedback-action" onClick={() => setStatus(h.highlight_id, 'accepted')} aria-label={`Accept ${h.text}`} title="Accept">✓ Accept</button>
              <button className="feedback-action" onClick={() => setStatus(h.highlight_id, 'rejected')} aria-label={`Reject ${h.text}`} title="Reject">✗ Reject</button>
              <button className="feedback-action" onClick={() => setStatus(h.highlight_id, 'pinned')} aria-label={`Pin ${h.text}`} title="Pin">⌖ Pin</button>
              {h.feature_flags.clinician_confirmed && (
                <span className="confirmed-tag">Clinician-confirmed</span>
              )}
              {h.review_status === 'needs_review' && (
                <span className="needs-review-tag">Needs review</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}
