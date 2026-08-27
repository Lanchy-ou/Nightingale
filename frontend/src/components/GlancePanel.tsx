import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { Highlight, ProvenanceResult } from '../types';

function riskColor(h: Highlight): string {
  if (h.feature_flags.explicit_risk) return '#dc2626';
  if (h.feature_flags.symptom_change) return '#f59e0b';
  if (h.feature_flags.unresolved_task) return '#2563eb';
  return '#9ca3af';
}

function priorityLabel(h: Highlight): string {
  if (h.feature_flags.unresolved_task) return 'Open action';
  if (h.feature_flags.explicit_risk) return 'Current concern';
  if (h.feature_flags.symptom_change) return 'Recent change';
  return 'Clinical context';
}

export default function GlancePanel({
  patientId,
  onViewSource,
  onOpenTasks,
  reviewRole = 'clinician',
}: {
  patientId: string;
  onViewSource: (p: ProvenanceResult) => void;
  onOpenTasks?: (taskId: string) => void;
  reviewRole?: string;
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

  function sourceAction(h: Highlight) {
    return h.task_id ? (
      <button className="source-action" onClick={() => onOpenTasks?.(h.task_id!)}>Open task</button>
    ) : (
      <button className="source-action" onClick={() => viewSource(h.highlight_id)}>View exact source</button>
    );
  }

  function reviewMenu(h: Highlight) {
    return (
      <details className="glance-review-menu">
        <summary>Review</summary>
        <div>
          <button onClick={() => setStatus(h.highlight_id, 'accepted')}>{reviewRole === 'staff' ? 'Acknowledge' : 'Confirm'}</button>
          <button onClick={() => setStatus(h.highlight_id, 'pinned')}>{reviewRole === 'staff' ? 'Keep visible' : 'Keep on top'}</button>
          <button onClick={() => setStatus(h.highlight_id, 'rejected')}>Hide from Overview</button>
        </div>
      </details>
    );
  }

  const primary = highlights.slice(0, 2);
  const supporting = highlights.slice(2);

  return (
    <section className="glance-panel clinical-view" aria-labelledby="clinical-overview-heading">
      <div className="view-title-row">
        <div>
          <p className="eyebrow">Patient summary</p>
          <h2 id="clinical-overview-heading">Clinical Overview</h2>
          <p className="view-subtitle">Current priorities and recent changes, ordered for clinical review.</p>
        </div>
        <span className="record-count">Top {highlights.length}</span>
      </div>
      <details className="glance-review-help"><summary>How review controls work</summary><p>{reviewRole === 'staff' ? <><strong>Acknowledge</strong> records Staff review, <strong>Keep visible</strong> pins the item, and <strong>Hide</strong> removes it from the Overview. Staff review never becomes clinician confirmation.</> : <><strong>Confirm</strong> marks a priority as clinician-reviewed, <strong>Keep on top</strong> pins it, and <strong>Hide</strong> removes it from the Overview.</>} None of these actions creates or edits a clinical note.</p></details>
      {loading && <div className="loading-card">Loading precomputed priorities…</div>}
      {error && <div className="form-error">{error}</div>}
      {!loading && highlights.length === 0 && <div className="empty-state"><h3>No current highlights</h3><p>Nothing has been prioritized for this patient.</p></div>}
      {primary.length > 0 && <div className="glance-section-label"><span>Current priorities</span><small>{primary.length} to review</small></div>}
      {primary.map((h) => (
        <article key={h.highlight_id} className={`highlight-card highlight-primary ${h.status}`}>
          <span className="risk-dot" style={{ background: riskColor(h) }} aria-hidden="true" />
          <div className="highlight-body">
            <div className="highlight-kicker"><span>{priorityLabel(h)}</span>{h.feature_flags.clinician_confirmed ? <span className="confirmed-tag">Clinician-reviewed</span> : reviewRole === 'staff' && h.status === 'accepted' ? <span className="staff-reviewed-tag">Staff-reviewed</span> : null}</div>
            <div className="highlight-text">{h.text}</div>
            <div className="highlight-reason">{h.risk_reason}</div>
            <div className="highlight-actions">
              {sourceAction(h)}
              {h.task_id == null && h.feature_flags.unresolved_task && onOpenTasks && (
                <span className="unresolved-tag">Unresolved task</span>
              )}
              {reviewMenu(h)}
              {h.review_status === 'needs_review' && (
                <span className="needs-review-tag">Needs review</span>
              )}
            </div>
          </div>
        </article>
      ))}
      {supporting.length > 0 && <div className="glance-section-label supporting"><span>Additional findings</span><small>Each item retains its review status</small></div>}
      {supporting.length > 0 && <div className="glance-context-list">{supporting.map((h) => (
        <article key={h.highlight_id} className={`glance-context-row ${h.status}`}>
          <span className="context-risk-dot" style={{ background: riskColor(h) }} aria-hidden="true" />
          <div><div className="context-row-top"><span className="context-row-label">{priorityLabel(h)}</span><span className={`context-review-state ${h.feature_flags.clinician_confirmed ? 'reviewed' : ''}`}>{h.feature_flags.clinician_confirmed ? 'Clinician-reviewed' : 'Suggested for review'}</span></div><strong>{h.text}</strong><small>{h.risk_reason}</small></div>
          <div className="context-row-actions">{sourceAction(h)}{reviewMenu(h)}</div>
        </article>
      ))}</div>}
    </section>
  );
}
