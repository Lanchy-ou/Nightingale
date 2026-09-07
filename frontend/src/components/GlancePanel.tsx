import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { eventLabel, formatDate } from '../clinical';
import type { Event, Highlight, ProvenanceResult } from '../types';

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
  events = [],
  onViewSource,
  onOpenTasks,
  reviewRole = 'clinician',
}: {
  patientId: string;
  events?: Event[];
  onViewSource: (p: ProvenanceResult) => void;
  onOpenTasks?: (taskId: string) => void;
  reviewRole?: string;
}) {
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [safetyContext, setSafetyContext] = useState<Highlight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await api.getGlance(patientId, signal);
      const nextHighlights = response.highlights;
      setHighlights(nextHighlights);
      setSafetyContext(response.safety_context);
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

  return (
    <section className="glance-panel clinical-view" aria-labelledby="glance-heading">
      <div className="view-title-row glance-navigator-heading">
        <div>
          <h2 id="glance-heading">Glance</h2>
          <p className="view-subtitle">What matters now, with the evidence to review it.</p>
        </div>
        <div className="glance-heading-tools">
          <span className="record-count">{highlights.length} current items</span>
        </div>
      </div>

      {safetyContext.length > 0 && <section className="glance-safety-context" aria-label="Confirmed safety context">
        <strong>Confirmed allergy context</strong>
        {safetyContext.map((item) => <div className="glance-safety-item" key={item.highlight_id}>
          <span>{item.text}</span>
          <button className="source-action" aria-label={`View source for ${item.text}`} onClick={() => viewSource(item.highlight_id)}>View source</button>
        </div>)}
      </section>}
      {loading && <div className="loading-card">Loading precomputed priorities…</div>}
      {error && <div className="form-error">{error}</div>}
      {!loading && highlights.length === 0 && <div className="empty-state"><h3>No current highlights</h3><p>Nothing has been prioritized for this patient.</p></div>}
      {!loading && highlights.length > 0 && (
        <div className="priority-list" aria-label="Current patient priorities">
          {highlights.map((highlight, index) => {
            const event = events.find((item) => item.event_id === highlight.event_id);
            return <article key={highlight.highlight_id} className={`priority-row ${highlight.status}`}>
              <span className="priority-number" style={{ color: riskColor(highlight) }} aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
              <div className="priority-body">
                <header className="priority-meta">
                  <span>{priorityLabel(highlight)}</span>
                  <span className={highlight.feature_flags.clinician_confirmed ? 'priority-confirmed' : ''}>{patientReviewState(highlight) ?? reviewState(highlight, reviewRole)}</span>
                  {highlight.status === 'pinned' && <span>Kept on top</span>}
                </header>
                <h3>{highlight.text}</h3>
                <p className="priority-reason">{highlight.risk_reason}</p>
                {event && <p className="priority-source-date">{eventLabel(event)} · {formatDate(event.started_at)}</p>}
                <div className="priority-actions">
                  {sourceAction(highlight, true)}
                  {highlight.task_id && <button className="source-action" onClick={() => viewSource(highlight.highlight_id)}>View exact source</button>}
                  {reviewMenu(highlight)}
                  <details className="priority-guidance"><summary>Details &amp; ranking</summary><p>{nextStepText(highlight, reviewRole)}</p>{rankingExplanation(highlight)}{learnedPriority(highlight)}</details>
                </div>
              </div>
            </article>;
          })}
        </div>
      )}
      <details className="glance-review-help"><summary>How review controls work</summary><p>{reviewRole === 'staff' ? <><strong>Acknowledge</strong> records Staff review, <strong>Keep visible</strong> pins the item, and <strong>Hide</strong> removes only this item from Glance. Staff review never becomes clinician confirmation.</> : <><strong>Confirm</strong> marks this priority as clinician-reviewed, <strong>Keep on top</strong> pins it, and <strong>Hide</strong> removes only this item from Glance.</>} These controls do not teach future ranking. Explicit teaching and quality feedback live in Coverage Review and remain Shadow-only.</p></details>
    </section>
  );
}
