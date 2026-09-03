import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { LearningStatus } from '../types';

function metricLabel(key: string): string {
  return key.replace(/_/g, ' ');
}

export default function AdminLearningPage() {
  const [status, setStatus] = useState<LearningStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setStatus(await api.getLearningStatus(signal));
    setError(null);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch((caught: any) => caught?.name !== 'AbortError' && setError(String(caught.message ?? caught))).finally(() => setLoading(false));
    return () => controller.abort();
  }, [load]);

  async function act(action: () => Promise<unknown>) {
    setPending(true);
    setError(null);
    try { await action(); await load(); }
    catch (caught: any) { setError(String(caught.message ?? caught)); }
    finally { setPending(false); }
  }

  if (loading) return <section className="admin-surface"><div className="loading-card">Loading Shadow Learning status…</div></section>;
  return (
    <section className="admin-surface admin-learning-page" aria-labelledby="admin-learning-heading">
      <div className="admin-section-head"><div><p className="eyebrow">Auditable ranking research</p><h2 id="admin-learning-heading">Shadow Learning</h2></div><button className="secondary-button" onClick={() => load().catch((caught) => setError(String(caught)))}>Refresh</button></div>
      <div className="shadow-only-banner"><strong>Serving: base-only</strong><span>No model or adaptive feedback can change the formal Glance Top 5 in F_A1.</span></div>
      {error && <div className="form-error">{error}</div>}
      {status && <>
        <div className="admin-metric-grid learning-status-grid">
          <article><span>Active Shadow policy</span><strong>{status.active_policy}</strong><small>Serving stays {status.serving_mode}</small></article>
          <article><span>Signal state</span><strong>{status.frozen ? 'Frozen' : 'Collecting'}</strong><small>{status.signal_cutoff_at ? `Cutoff ${new Date(status.signal_cutoff_at).toLocaleString()}` : 'No cutoff'}</small></article>
          <article><span>Latest replay</span><strong>{status.latest_evaluation ? status.latest_evaluation.metrics.run_count : 'Not run'}</strong><small>{status.latest_evaluation ? 'ranking runs evaluated' : 'Run an offline replay'}</small></article>
        </div>
        <div className="learning-admin-actions">
          <button className="primary-button" disabled={pending} onClick={() => act(() => api.replayLearning())}>Run base vs Shadow replay</button>
          <button className="secondary-button" disabled={pending} onClick={() => act(() => api.freezeLearning(status.frozen, !status.frozen))}>{status.frozen ? 'Resume Shadow signals' : 'Freeze Shadow signals'}</button>
        </div>
        <section className="learning-policy-list"><h3>Shadow policy rollback</h3><p>Switching policies changes offline comparison only.</p>{status.policies.map((policy) => <button key={policy.version_name} disabled={pending || policy.active} onClick={() => act(() => api.activateLearningPolicy(policy.version_name))}><strong>{policy.version_name}</strong><span>{policy.active ? 'Active' : 'Activate for Shadow'}</span></button>)}</section>
        <section className="learning-metrics">
          <h3>SL2 frozen artifact evidence</h3>
          {!status.sl2_evidence.dataset || !status.sl2_evidence.artifacts || !status.sl2_evidence.evaluation
            ? <div className="form-error">SL2 artifacts unavailable: {(status.sl2_evidence.reason ?? 'unknown failure').replace(/_/g, ' ')}</div>
            : <>
              <dl>
                <div><dt>Frozen scenarios</dt><dd>{status.sl2_evidence.dataset.scenario_count} (15 staff / 15 clinician)</dd></div>
                <div><dt>Mechanism thresholds</dt><dd>{status.sl2_evidence.evaluation.all_thresholds_pass ? 'PASS' : 'FAIL'}</dd></div>
                <div><dt>Staff artifact</dt><dd>{status.sl2_evidence.artifacts.staff.valid ? 'valid' : 'invalid'} · {status.sl2_evidence.artifacts.staff.artifact_sha256.slice(0, 12)}</dd></div>
                <div><dt>Clinician artifact</dt><dd>{status.sl2_evidence.artifacts.clinician.valid ? 'valid' : 'invalid'} · {status.sl2_evidence.artifacts.clinician.artifact_sha256.slice(0, 12)}</dd></div>
                <div><dt>Staff validation strict accuracy</dt><dd>{Number(status.sl2_evidence.evaluation.role_metrics.staff.validation.strict_pair_accuracy.toFixed(3))}</dd></div>
                <div><dt>Test strict accuracy</dt><dd>staff {Number(status.sl2_evidence.evaluation.role_metrics.staff.test.strict_pair_accuracy.toFixed(3))} · clinician {Number(status.sl2_evidence.evaluation.role_metrics.clinician.test.strict_pair_accuracy.toFixed(3))}</dd></div>
              </dl>
              <p>Passing authorizes Shadow evaluation only. The lower staff validation result remains visible and is not a clinical-validity claim.</p>
            </>}
        </section>
        <section className="learning-metrics">
          <h3>Observed feedback training bridge</h3>
          <p>Feature extraction is automatic. Training remains an explicit offline operation and formal Glance stays base-only.</p>
          <dl>
            <div><dt>Source classification</dt><dd>{status.observed_feedback.source_classification.replace(/_/g, ' ')}</dd></div>
            <div><dt>Real clinician validation</dt><dd>{status.observed_feedback.real_clinician_validation}</dd></div>
            {(['staff', 'clinician'] as const).map((role) => {
              const evidence = status.observed_feedback.roles[role];
              return <div key={role}><dt>{role} readiness</dt><dd>{evidence.mechanism_minimum_met ? 'Ready for explicit offline training' : `Blocked · ${evidence.strict_pair_count} strict pairs · ${evidence.reviewer_count} reviewers`}</dd></div>;
            })}
          </dl>
          <p>No page control can train or serve a model. Unverified data is rejected by the local training command.</p>
        </section>
        {status.latest_evaluation && <section className="learning-metrics"><h3>Latest replay</h3><dl>{Object.entries(status.latest_evaluation.metrics).filter(([, value]) => value === null || ['string', 'number', 'boolean'].includes(typeof value)).map(([key, value]) => <div key={key}><dt>{metricLabel(key)}</dt><dd>{value === null ? 'Not enough labels' : typeof value === 'number' ? Number(value.toFixed?.(3) ?? value) : String(value)}</dd></div>)}</dl></section>}
      </>}
    </section>
  );
}
