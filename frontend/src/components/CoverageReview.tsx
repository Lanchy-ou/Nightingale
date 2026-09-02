import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { CoverageDecision, CoverageReview as CoverageReviewType, CurrentIdentity, ProvenanceResult } from '../types';

const DEMOTION_REASONS = [
  ['duplicate_or_redundant', 'Duplicate or redundant'],
  ['already_resolved_or_stale', 'Already resolved or stale'],
  ['not_actionable_for_viewer_role', 'Not actionable for this role'],
  ['lower_than_other_active_work', 'Lower than other active work'],
] as const;

const QUALITY_REASONS = [
  ['extraction_incorrect', 'Extraction is incorrect'],
  ['source_mismatch', 'Source does not support this'],
  ['wrong_role_route', 'Routed to the wrong role'],
] as const;

function DecisionCard({
  item,
  identity,
  pending,
  onSource,
  onSignal,
}: {
  item: CoverageDecision;
  identity: CurrentIdentity;
  pending: boolean;
  onSource: (item: CoverageDecision) => void;
  onSignal: (item: CoverageDecision, type: 'explicit_demotion' | 'quality_issue', reason: string) => void;
}) {
  const [demotionReason, setDemotionReason] = useState(DEMOTION_REASONS[0][0]);
  const [qualityReason, setQualityReason] = useState(QUALITY_REASONS[0][0]);
  const [confirmed, setConfirmed] = useState(false);
  return (
    <article className="coverage-decision-card">
      <header><span>Band {item.priority_band} · base rank {item.base_rank ?? 'excluded'}</span><strong>{item.source_binding_status}</strong></header>
      <h4>{item.text}</h4>
      <p>
        Base {item.base_score}
        {item.sl2_model_score !== null
          ? ` · Shadow simulation rank ${item.shadow_rank ?? 'excluded'} · model score ${item.sl2_model_score.toFixed(3)}`
          : item.shadow_artifact_version
            ? ` · Shadow simulation rank ${item.shadow_rank ?? 'excluded'} · base-preserved`
          : ` · Shadow ${item.shadow_score} (${item.shadow_adjustment >= 0 ? '+' : ''}${item.shadow_adjustment})`}
        {item.shadow_fallback_reason ? ` · fallback: ${item.shadow_fallback_reason.replace(/_/g, ' ')}` : ''}
        {item.exclusion_reason ? ` · ${item.exclusion_reason.replace(/_/g, ' ')}` : ''}
      </p>
      <div className="coverage-card-actions"><button disabled={item.source_binding_status === 'not_applicable'} onClick={() => onSource(item)}>{item.source_binding_status === 'not_applicable' ? 'Event / Task-level source' : 'Open exact source'}</button></div>
      <details className="coverage-signal-form">
        <summary>Review this decision</summary>
        {identity.role === 'clinician' && <label>Shadow demotion reason<select value={demotionReason} onChange={(event) => setDemotionReason(event.target.value as typeof demotionReason)}>{DEMOTION_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
        <label>Quality / routing issue<select value={qualityReason} onChange={(event) => setQualityReason(event.target.value as typeof qualityReason)}>{QUALITY_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="coverage-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I understand this is recorded for Shadow evaluation only.</label>
        <div className="coverage-card-actions">
          {identity.role === 'clinician' && <button disabled={!confirmed || pending} onClick={() => onSignal(item, 'explicit_demotion', demotionReason)}>Lower similar context in Shadow</button>}
          <button disabled={!confirmed || pending} onClick={() => onSignal(item, 'quality_issue', qualityReason)}>Report quality issue</button>
        </div>
      </details>
    </article>
  );
}

export default function CoverageReview({
  patientId,
  identity,
  onViewSource,
}: {
  patientId: string;
  identity: CurrentIdentity;
  onViewSource: (source: ProvenanceResult) => void;
}) {
  const role = identity.role as 'staff' | 'clinician';
  const [coverage, setCoverage] = useState<CoverageReviewType | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    const next = await api.getCoverageReview(patientId, role, signal);
    setCoverage(next);
    setError(null);
  }, [patientId, role]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    load(controller.signal).catch((caught: any) => caught?.name !== 'AbortError' && setError(String(caught.message ?? caught))).finally(() => setLoading(false));
    return () => controller.abort();
  }, [load]);

  async function viewSource(item: CoverageDecision) {
    try { onViewSource(await api.getProvenance(item.highlight_id)); }
    catch (caught: any) { setError(String(caught.message ?? caught)); }
  }

  async function submit(item: CoverageDecision, type: 'explicit_demotion' | 'quality_issue', reason: string) {
    setPendingId(item.decision_id);
    setError(null);
    setMessage(null);
    try {
      const signal = await api.submitLearningSignal(item.decision_id, type, reason);
      setMessage(signal.eligible_for_shadow
        ? 'Recorded for Shadow replay. Formal Glance remains base-only.'
        : `Recorded as non-ranking evidence: ${(signal.ineligibility_reason ?? 'not eligible').replace(/_/g, ' ')}.`);
      await load();
    } catch (caught: any) {
      setError(String(caught.message ?? caught));
    } finally {
      setPendingId(null);
    }
  }

  const section = (title: string, description: string, items: CoverageDecision[]) => (
    <section className="coverage-group"><header><div><h3>{title}</h3><p>{description}</p></div><strong>{items.length}</strong></header>{items.length === 0 ? <div className="empty-state">No candidates in this group.</div> : <div className="coverage-grid">{items.map((item) => <DecisionCard key={item.decision_id} item={item} identity={identity} pending={pendingId === item.decision_id} onSource={viewSource} onSignal={submit} />)}</div>}</section>
  );

  return (
    <section className="clinical-view coverage-review" aria-labelledby="coverage-heading">
      <div className="view-title-row"><div><p className="eyebrow">Blind-spot review</p><h2 id="coverage-heading">Coverage Review</h2><p className="view-subtitle">Inspect what the deterministic Top 5 did and did not show.</p></div>{coverage && <span className="record-count">Run {coverage.run_id}</span>}</div>
      <div className="shadow-only-banner"><strong>Shadow only</strong><span>Serving Glance remains base-only. Feedback here cannot immediately change the formal Top 5.</span></div>
      {loading && <div className="loading-card">Loading ranking decisions…</div>}
      {error && <div className="form-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}
      {coverage && <>
        <p className="coverage-meta">{coverage.viewer_role} projection · run policy {coverage.run_policy_version} · Shadow simulation only · evaluated {new Date(coverage.evaluated_at).toLocaleString()}</p>
        {section('Eligible but not shown', 'Candidates ranked below the formal Top 5.', coverage.eligible_unsurfaced)}
        {section('Formal Top 5', 'The deterministic A2 serving result.', coverage.base_top_five)}
        {section('Excluded', 'Candidates retained for audit with an explicit exclusion reason.', coverage.excluded)}
      </>}
    </section>
  );
}
