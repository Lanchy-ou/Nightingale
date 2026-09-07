import { useEffect, useState } from 'react';
import { api } from '../api';
import { formatDateTime } from '../clinical';
import type { CurrentIdentity, WorkInboxResult } from '../types';

export default function WorkInboxPage({ identity, onOpenTask }: { identity: CurrentIdentity; onOpenTask: (patientId: string, taskId: string) => void }) {
  const [view, setView] = useState<'mine' | 'clinic'>('mine');
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<WorkInboxResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    api.getWorkInbox(view, offset, controller.signal).then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((caught) => { if (caught?.name !== 'AbortError') setError('Could not load the work inbox. Please retry.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [view, offset, refresh]);
  return <main className="workspace-main work-inbox-page">
    <header className="work-inbox-heading"><div><p className="eyebrow">{identity.clinic_name}</p><h1>Work inbox</h1><p>Review and follow up across your clinic’s patient records.</p></div><button className="secondary-button" onClick={() => setRefresh((value) => value + 1)} disabled={loading}>Refresh</button></header>
    <div className="work-inbox-toolbar"><nav aria-label="Inbox scope">{(['mine', 'clinic'] as const).map((scope) => <button key={scope} aria-pressed={view === scope} className={view === scope ? 'active' : ''} onClick={() => { setView(scope); setOffset(0); }}>{scope === 'mine' ? 'For my role' : 'All clinic work'}</button>)}</nav><span>{data && !loading ? `${data.total} active item${data.total === 1 ? '' : 's'}` : 'Loading…'}</span></div>
    <p className="panel-help">{view === 'mine' ? 'Your assignments, shared work for your role, and patient completion awaiting clinic verification.' : 'Active clinic work, including items assigned to other roles.'} Open an item to review its source and take action.</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    {loading && <p className="loading-card">Loading work inbox…</p>}
    {!loading && !error && data && <>
      {data.items.length === 0 ? <div className="empty-state"><h2>No active items in this view</h2><p>Refresh to check for new assignments or patient updates.</p></div> : <div className="work-inbox-list">{data.items.map((item) => <article className="work-inbox-item" key={item.task_id}>
        <div className="inbox-patient"><span className="patient-list-avatar" aria-hidden="true">{item.patient_name.slice(0, 1)}</span><div><strong>{item.patient_name}</strong><small>{item.patient_id}</small></div></div>
        <div className="inbox-task"><div className="inbox-item-meta"><span>{item.task_kind === 'patient_report_review' ? 'Patient report verification' : item.task_kind === 'clinician_priority_review' ? 'Clinician priority review' : item.task_kind === 'result_review' ? 'Result review' : item.task_kind === 'report_followup' ? 'Report follow-up' : item.task_kind === 'result_communication' ? 'Patient communication' : 'Care action'}</span>{item.overdue && <b>Overdue</b>}</div><h2>{item.title}</h2><p>{item.status === 'reported_done' ? 'Awaiting clinic verification' : item.status.replace(/_/g, ' ')} · Assigned to {item.assigned_role}{item.assigned_user_id === identity.user_id ? ' · You' : ''}</p><small>{item.due_at ? `Due ${formatDateTime(item.due_at)}` : 'No due date'} · {item.has_exact_source ? 'Exact source linked' : 'Event linked'}</small></div>
        <button className={item.actionable ? 'primary-button' : 'secondary-button'} onClick={() => item.test_order_id ? window.location.assign(`/clinical/patients/${item.patient_id}/tests?order=${item.test_order_id}`) : onOpenTask(item.patient_id, item.task_id)}>{item.actionable ? 'Review task' : 'View task'} <span aria-hidden="true">→</span></button>
      </article>)}</div>}
      <footer className="inbox-pagination"><button className="secondary-button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - data.limit))}>Previous</button><span>{data.total ? `${offset + 1}–${Math.min(offset + data.items.length, data.total)} of ${data.total}` : '0 items'}</span><button className="secondary-button" disabled={offset + data.limit >= data.total} onClick={() => setOffset(offset + data.limit)}>Next</button></footer>
    </>}
  </main>;
}
