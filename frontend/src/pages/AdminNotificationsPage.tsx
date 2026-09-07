import { useEffect, useState } from 'react';
import { resultRequest } from '../api';
type Settings = { enabled: boolean; revision: number; timezone: string; review_hours: number; communication_hours: number; verification_hours: number; escalation_hours: number };
type Jobs = { pending_count: number; failed_count: number; oldest_pending_at: string | null; last_sweep_at: string | null; blocked_without_clinician_count: number; failures: { job_id: string; attempts: number; error_code: string; stage: string }[] };

export default function AdminNotificationsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [jobs, setJobs] = useState<Jobs | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function load() { const [s, j] = await Promise.all([resultRequest<Settings>('/admin/notification-settings'), resultRequest<Jobs>('/admin/notification-jobs')]); setSettings(s); setJobs(j); }
  useEffect(() => { void load().catch(() => setError('Could not load reminder operations.')); }, []);
  return <section className="admin-notifications"><p className="panel-help">In-app delivery operations. Clinical reports and conclusions remain in the care workspace.</p>{error && <p className="form-error" role="alert">{error}</p>}
    {jobs && <><div className="reminder-stats"><article><strong>{jobs.pending_count}</strong><span>Pending</span></article><article><strong>{jobs.failed_count}</strong><span>Failed</span></article><article><strong>{jobs.blocked_without_clinician_count}</strong><span>No available clinician</span></article></div><p>Last successful sweep: {jobs.last_sweep_at || 'Not yet run'} · Oldest pending: {jobs.oldest_pending_at || 'None'} (UTC)</p></>}
    {settings && <form className="result-card" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); const f = new FormData(e.currentTarget); try { await resultRequest('/admin/notification-settings', { expected_revision: settings.revision, timezone: f.get('timezone'), ...Object.fromEntries(['review_hours', 'communication_hours', 'verification_hours', 'escalation_hours'].map(k => [k, Number(f.get(k))])) }, 'PUT'); await load(); } catch { setError('Settings were not saved. Refresh if another administrator changed them.'); } finally { setBusy(false); } }}>
      <h2>Reminder policy</h2><p>Delivery is {settings.enabled ? 'enabled' : 'disabled by the deployment feature switch'}. These demonstration intervals require clinic confirmation.</p>
      <label>Clinic timezone<input name="timezone" defaultValue={settings.timezone} required /></label>
      {([['review_hours', 'Report review'], ['communication_hours', 'Patient communication'], ['verification_hours', 'Patient completion verification'], ['escalation_hours', 'Escalation after overdue']] as const).map(([key, label]) => <label key={key}>{label} (hours)<input type="number" name={key} min={1} max={720} required defaultValue={settings[key]} /></label>)}
      <button className="primary-button" disabled={busy}>Save policy</button>
    </form>}
    <section className="result-card"><h2>Failed deliveries</h2>{jobs?.failures.length === 0 && <p>No exhausted delivery jobs.</p>}{jobs?.failures.map(j => <article key={j.job_id}><strong>{j.stage} · {j.attempts} attempts</strong><p>{j.error_code}</p><button onClick={() => void resultRequest(`/admin/notification-jobs/${j.job_id}/retry`, {}).then(load).catch(() => setError('Retry was not scheduled. Refresh the job state.'))}>Retry delivery</button></article>)}<button onClick={() => void load().catch(() => setError('Refresh failed.'))}>Refresh operations</button></section>
  </section>;
}
