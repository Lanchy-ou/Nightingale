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

function prioritySymbol(h: Highlight): string {
  if (h.feature_flags.explicit_risk) return '!';
  if (h.feature_flags.unresolved_task) return '○';
  if (h.feature_flags.symptom_change) return '↗';
  return '◇';
}

function reviewState(h: Highlight, reviewRole: string): string {
  if (h.feature_flags.clinician_confirmed) return 'Clinician-reviewed';
  if (reviewRole === 'staff' && h.status === 'accepted') return 'Staff-reviewed';
  if (h.review_status === 'needs_review') return 'Needs review';
  return 'Suggested for review';
}

function patientReviewState(h: Highlight): string | null {
  const context = h.task_context;
  if (!context || context.attention_class !== 'priority_review') return null;
  if (context.verification_outcome === 'verified') return 'Patient-reported · Verified by Nurse';
  if (context.verification_outcome === 'corrected') return 'Patient-reported · Corrected by Nurse';
  if (context.verification_outcome === 'unable_to_verify') return 'Patient-reported · Nurse unable to verify';
  return 'Patient-reported · Unverified priority review';
}

function nextStepText(h: Highlight, reviewRole: string): string {
  const task = h.task_context;
  if (task?.task_kind === 'patient_report_review') {
    return 'Nurse: open the linked review and verify each patient-reported item against its exact source.';
  }
  if (task?.task_kind === 'clinician_priority_review') {
    return 'Clinician: open the linked review and either close it with no follow-up or create an owned follow-up Task.';
  }
  if (task?.status === 'reported_done') {
    return 'Clinic: verify the patient-reported completion before marking the linked Task complete.';
  }
  if (h.task_id) return 'Open the linked Task to see its owner, due date, source, and current workflow state.';
  if (h.review_status === 'needs_review') return 'Compare the conflicting source statements before recording a clinical decision.';
  if (h.feature_flags.clinician_confirmed) return 'No new action is implied. Open the source only if you need to verify the confirmed context.';
  if (/blood test|result.*not returned|pending/i.test(`${h.text} ${h.risk_reason}`)) return 'Check whether the result is available; if it is still missing, create a follow-up Task with an owner and due date.';
  if (h.feature_flags.explicit_risk) return 'Open the exact source, then decide whether this concern needs a follow-up Task.';
  if (h.feature_flags.symptom_change) {
    const reportedChange = h.assertion_value?.trim() || h.text;
    return `${reviewRole === 'staff' ? 'Review' : 'Compare'} “${reportedChange}” with the latest clinical record, then acknowledge it or open follow-up work.`;
  }
  return 'Open the exact source before deciding whether to confirm, keep visible, or hide this item.';
}

function evidenceText(h: Highlight): string {
  if (!h.source_span) return 'No exact source span is claimed for this item.';
  const kind = h.source_span.kind.replace(/_/g, ' ');
  return `An exact ${kind} is preserved in the source record. Open it to check the original wording, author, and date.`;
}

function learnedPriority(h: Highlight) {
  if (h.adaptive_adjustment === 0) return null;
  const sign = h.adaptive_adjustment > 0 ? '+' : '';
  const reviews = h.learning_metadata.review_count ?? 0;
  return (
    <div className="learned-priority" aria-label="Learned priority explanation">
      <strong>Learned priority {sign}{h.adaptive_adjustment}</strong>
      <span>Base {h.base_importance_score} {sign}{h.adaptive_adjustment} = final {h.importance_score}</span>
      <small>Based on {reviews} clinic review{reviews === 1 ? '' : 's'} of similar {h.learning_metadata.feedback_key ?? 'item'} suggestions.</small>
    </div>
  );
}

function rankingExplanation(h: Highlight) {
  const explanation = h.glance_explanation;
  const score = explanation?.score;
  if (!explanation || !score) return null;
  const factors = Object.entries(score.base_factors ?? {}) as [string, number][];
  return (
    <details className="glance-ranking-explanation">
      <summary>Why this is in Glance</summary>
      <div>
        <p><strong>Priority band {explanation.priority_band}</strong> · {(explanation.priority_reasons ?? []).join(' · ') || 'deterministic fallback band'}</p>
        <p>Score: {score.base_total} + {score.adaptive_adjustment} adaptive + {score.decay_adjustment} decay = <strong>{score.final_total}</strong></p>
        <dl>{factors.map(([name, value]) => <div key={name}><dt>{name.replace(/_/g, ' ')}</dt><dd>{value}</dd></div>)}</dl>
        <small>Ranking rule {h.ranking_rule_version ?? 'unknown'} · score rule {score.rule_version ?? h.score_rule_version}</small>
      </div>
    </details>
  );
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
  const [safetyContext, setSafetyContext] = useState<Highlight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedHighlightId, setSelectedHighlightId] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await api.getGlance(patientId, signal);
      const nextHighlights = response.highlights;
      setHighlights(nextHighlights);
      setSafetyContext(response.safety_context);
      setSelectedHighlightId((current) => (
        current && nextHighlights.some((highlight) => highlight.highlight_id === current)
          ? current
          : nextHighlights[0]?.highlight_id ?? null
      ));
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

  function sourceAction(h: Highlight, primary = false) {
    return h.task_id ? (
      <button className={`source-action${primary ? ' primary' : ''}`} onClick={() => onOpenTasks?.(h.task_id!)}>{primary ? 'Open linked task' : 'Open task'}</button>
    ) : (
      <button className={`source-action${primary ? ' primary' : ''}`} onClick={() => viewSource(h.highlight_id)}>{primary ? 'View exact source' : 'View source'}</button>
    );
  }

  function reviewMenu(h: Highlight) {
    return (
      <details className="glance-review-menu">
        <summary>Review</summary>
        <div>
          <button onClick={() => setStatus(h.highlight_id, 'accepted')}>{reviewRole === 'staff' ? 'Acknowledge' : 'Confirm'}</button>
          <button onClick={() => setStatus(h.highlight_id, 'pinned')}>{reviewRole === 'staff' ? 'Keep visible' : 'Keep on top'}</button>
          <button onClick={() => setStatus(h.highlight_id, 'rejected')}>Hide from Glance</button>
        </div>
      </details>
    );
  }

  const selectedHighlight = highlights.find((highlight) => highlight.highlight_id === selectedHighlightId) ?? highlights[0] ?? null;

  return (
    <section className="glance-panel clinical-view" aria-labelledby="glance-heading">
      <div className="view-title-row glance-navigator-heading">
        <div>
          <p className="eyebrow">Patient summary</p>
          <h2 id="glance-heading">Glance</h2>
          <p className="view-subtitle">What matters now · select a priority to inspect without losing Glance context.</p>
        </div>
        <div className="glance-heading-tools">
          <div className="authority-legend" aria-label="Artifact authority legend">
            <span className="raw">RAW</span>
            <span className="ai">AI</span>
            <span className="clinician">CLINICIAN</span>
            <span className="staff">STAFF</span>
          </div>
          <span className="record-count">{highlights.length} current items</span>
        </div>
      </div>
      <details className="glance-review-help"><summary>How review controls work</summary><p>{reviewRole === 'staff' ? <><strong>Acknowledge</strong> records Staff review, <strong>Keep visible</strong> pins the item, and <strong>Hide</strong> removes only this item from Glance. Staff review never becomes clinician confirmation.</> : <><strong>Confirm</strong> marks this priority as clinician-reviewed, <strong>Keep on top</strong> pins it, and <strong>Hide</strong> removes only this item from Glance.</>} These controls do not teach future ranking. Explicit teaching and quality feedback live in Coverage Review and remain Shadow-only.</p></details>
      {safetyContext.length > 0 && <section className="glance-safety-context" aria-label="Confirmed safety context"><strong>Confirmed allergy context</strong>{safetyContext.map((item) => <span key={item.highlight_id}>{item.text}</span>)}</section>}
      {loading && <div className="loading-card">Loading precomputed priorities…</div>}
      {error && <div className="form-error">{error}</div>}
      {!loading && highlights.length === 0 && <div className="empty-state"><h3>No current highlights</h3><p>Nothing has been prioritized for this patient.</p></div>}
      {!loading && selectedHighlight && (
        <div className="glance-navigator">
          <section className="glance-index-panel" aria-label="Glance priority index">
            <header>
              <div><span>Priority index</span><small>Stable Glance index</small></div>
              <strong>{highlights.length}</strong>
            </header>
            <div className="glance-index-list">
              {highlights.map((highlight, index) => {
                const selected = highlight.highlight_id === selectedHighlight.highlight_id;
                return (
                  <article key={highlight.highlight_id} className={`glance-index-item ${highlight.status} ${selected ? 'selected' : ''}`}>
                    <span className="glance-index-risk" style={{ background: riskColor(highlight) }} aria-hidden="true" />
                    <button
                      type="button"
                      className="glance-index-select"
                      aria-current={selected ? 'true' : undefined}
                      onClick={() => setSelectedHighlightId(highlight.highlight_id)}
                    >
                      <span className="glance-index-kicker"><b>{prioritySymbol(highlight)} {priorityLabel(highlight)}</b><em>{String(index + 1).padStart(2, '0')}</em></span>
                      <strong>{highlight.text}</strong>
                      <small>{patientReviewState(highlight) ?? reviewState(highlight, reviewRole)}</small>
                    </button>
                    <div className="glance-index-actions">{sourceAction(highlight)}{reviewMenu(highlight)}</div>
                  </article>
                );
              })}
            </div>
          </section>

          <article className={`glance-detail-panel ${selectedHighlight.status}`}>
            <section className="glance-detail-summary" aria-live="polite">
              <header className="glance-detail-head">
                <span className="glance-detail-type"><b>{prioritySymbol(selectedHighlight)}</b>{priorityLabel(selectedHighlight)}</span>
                <span className={`glance-detail-state ${selectedHighlight.feature_flags.clinician_confirmed ? 'reviewed' : ''}`}>{reviewState(selectedHighlight, reviewRole)}</span>
              </header>
              <h3>{selectedHighlight.text}</h3>
              <p className="glance-detail-reason">{selectedHighlight.risk_reason}</p>
            </section>

            <section className="glance-detail-next-step">
              <div><span>Recommended action</span><p>{nextStepText(selectedHighlight, reviewRole)}</p></div>
              <div className="glance-detail-actions">
                {sourceAction(selectedHighlight, true)}
                {reviewMenu(selectedHighlight)}
                {selectedHighlight.review_status === 'needs_review' && <span className="needs-review-tag">Needs review</span>}
              </div>
            </section>

            {selectedHighlight.task_context && <section className="glance-detail-workflow"><span>Workflow</span><p>{selectedHighlight.task_context.creation_method === 'system_routed' ? 'Routed from patient Check-in' : 'Human-created task'} · {selectedHighlight.task_context.verification_outcome.replace(/_/g, ' ')}{selectedHighlight.task_context.verification_overdue ? ' · Nurse verification overdue' : ''}</p></section>}

            <section className="glance-detail-provenance">
              <div className="glance-detail-evidence">
                <span>Evidence</span>
                <p>{evidenceText(selectedHighlight)}</p>
                <small>Event {selectedHighlight.event_id} · Source {selectedHighlight.source_artifact_id ?? selectedHighlight.artifact_id ?? 'unavailable'}</small>
                {selectedHighlight.task_id && <button className="glance-evidence-link" onClick={() => viewSource(selectedHighlight.highlight_id)}>View exact source</button>}
              </div>
              <div className="glance-detail-authority"><span>Review status</span><p>{selectedHighlight.feature_flags.clinician_confirmed ? 'Confirmed by a clinician. The original source and generated summary remain separate.' : 'Not clinician-confirmed. Reading the source does not accept or change this item.'}</p></div>
            </section>

            <div className="glance-detail-explainability">
              {rankingExplanation(selectedHighlight)}
              {learnedPriority(selectedHighlight)}
            </div>
          </article>
        </div>
      )}
    </section>
  );
}
