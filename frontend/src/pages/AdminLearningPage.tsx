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
        {status.latest_evaluation && <section className="learning-metrics"><h3>Latest evaluation</h3><dl>{Object.entries(status.latest_evaluation.metrics).map(([key, value]) => <div key={key}><dt>{metricLabel(key)}</dt><dd>{value === null ? 'Not enough labels' : typeof value === 'number' ? Number(value.toFixed?.(3) ?? value) : String(value)}</dd></div>)}</dl></section>}
      </>}
    </section>
  );
}
