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
}: {
  patientId: string;
  onViewSource: (p: ProvenanceResult) => void;
}) {
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setHighlights((await api.getGlance(patientId)).highlights);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [patientId]);

  useEffect(() => {
    refresh();
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
    <div className="glance-panel">
      <h2>Glance</h2>
      {error && <div className="error">{error}</div>}
      {highlights.length === 0 && <p className="muted">No highlights.</p>}
      {highlights.map((h) => (
        <div key={h.highlight_id} className={`highlight-card ${h.status}`}>
          <span className="risk-dot" style={{ background: riskColor(h) }} />
          <div className="highlight-body">
            <div className="highlight-text">{h.text}</div>
            <div className="highlight-reason">{h.risk_reason}</div>
            <div className="highlight-actions">
              <button onClick={() => viewSource(h.highlight_id)}>View source</button>
              <button onClick={() => setStatus(h.highlight_id, 'accepted')} title="Accept">✓</button>
              <button onClick={() => setStatus(h.highlight_id, 'rejected')} title="Reject">✗</button>
              <button onClick={() => setStatus(h.highlight_id, 'pinned')} title="Pin">📌</button>
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
    </div>
  );
}
