import { useEffect, useState, useRef } from 'react';
import { api, resultRequest, downloadTestReport } from '../api';
import type { CurrentIdentity, Event, Artifact, ClinicalTask } from '../types';
import type { TestOrder, TestOrderDetail, ResultStage } from '../resultTypes';
import PatientInstructionComposer from '../components/PatientInstructionComposer';
import InstructionPublicationControl from '../components/InstructionPublicationControl';

const labels: Record<ResultStage, string> = { waiting_report: 'Awaiting report', waiting_review: 'Doctor review', waiting_communication: 'Inform patient', completed: 'Result handled', cancelled: 'Cancelled' };
function message(error: any) { return error?.body?.error?.message || error?.message || 'Could not save. Your input is preserved.'; }

export default function TestOrdersPage({ patientId, identity, events }: { patientId: string; identity: CurrentIdentity; events: Event[] }) {
  const [legacyTasks, setLegacyTasks] = useState<ClinicalTask[]>([]);
  const [orders, setOrders] = useState<TestOrder[]>([]);
  const [selected, setSelected] = useState(new URLSearchParams(location.search).get('order') || '');
  const [detail, setDetail] = useState<TestOrderDetail | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pendingOperation = useRef<{ fingerprint: string; key: string } | null>(null);
  const [draft, setDraft] = useState<Artifact | null>(null);
  const [outcome, setOutcome] = useState('no_action');
  const [team, setTeam] = useState<{ user_id: string; name: string; role: string }[]>([]);
  async function load(id = selected) {
    const list = await resultRequest<TestOrder[]>(`/patients/${patientId}/test-orders`); setOrders(list);
    if (id) { setDetail(await resultRequest<TestOrderDetail>(`/test-orders/${id}`)); setSelected(id); }
  }
  useEffect(() => { void Promise.all([load(), api.getTasks(patientId).then(setLegacyTasks), resultRequest<{ enabled: boolean }>('/test-results/capabilities').then(v => setEnabled(v.enabled)),
      resultRequest<{ user_id: string; name: string; role: string }[]>('/test-results/team').then(setTeam)]).catch(e => setError(message(e))); }, [patientId]);
  async function mutate(path: string, body: object, method = 'POST') {
    setBusy(true); setError('');
    const fingerprint = JSON.stringify([path, body, method]);
    if (pendingOperation.current?.fingerprint !== fingerprint) pendingOperation.current = { fingerprint, key: crypto.randomUUID() };
    try { const result = await resultRequest<{ order_id: string }>(path, { idempotency_key: pendingOperation.current.key, ...body }, method); await load(result.order_id); pendingOperation.current = null; }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  const revision = detail?.revision;
  const chooseOwner = (name: string, defaultValue: string, clinicianOnly = false) => <select key={`${name}:${defaultValue}:${team.length}`} name={name} defaultValue={defaultValue} required>{team.filter(u => !clinicianOnly || u.role === 'clinician').map(u => <option key={u.user_id} value={u.user_id}>{u.name} · {u.role === 'staff' ? 'Nurse' : 'Doctor'}</option>)}</select>;
  return <section className="test-orders-page"><header><p className="eyebrow">Connected follow-up</p><h2>Examinations</h2><p>Receive the report, review its meaning, and make the next step clear.</p></header>
    {!enabled && <p className="panel-help">New examination handling is disabled. Saved records remain available.</p>}
    {error && <p className="form-error" role="alert">{error} <button onClick={() => void load().catch(e => setError(message(e)))}>Refresh saved state</button></p>}
    {enabled && identity.role === 'clinician' && <details className="result-card"><summary>Order an examination</summary><form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void mutate(`/events/${f.get('event_id')}/test-orders`, { title: f.get('title'), reason: f.get('reason'), expected_at: f.get('expected_at'), coordinator_id: f.get('coordinator_id'), reviewer_id: f.get('reviewer_id'), legacy_task_id: f.get('legacy_task_id') || null }); }}>
      <label>Consultation<select name="event_id" required defaultValue={new URLSearchParams(location.search).get('event') || ''}><option value="">Select consultation</option>{events.filter(e => e.event_type === 'doctor_consult').map(e => <option key={e.event_id} value={e.event_id}>{e.started_at}</option>)}</select></label>
      <label>Link an existing care task (optional)<select name="legacy_task_id"><option value="">No existing task</option>{legacyTasks.filter(t => t.task_kind === 'care_action').map(t => <option key={t.task_id} value={t.task_id}>{t.title}</option>)}</select></label>
      <label>Examination<input name="title" required maxLength={255} /></label><label>Reason<textarea name="reason" required maxLength={4000} /></label>
      <label>Expected report (clinic time)<input type="datetime-local" name="expected_at" required /></label>
      <label>Follow-up owner{chooseOwner('coordinator_id', identity.user_id || '')}</label><label>Review doctor{chooseOwner('reviewer_id', identity.user_id || '', true)}</label>
      <button className="primary-button" disabled={busy}>Create examination</button></form></details>}
    <div className="result-layout"><div className="result-list">{(Object.keys(labels) as ResultStage[]).map(stage => <section key={stage}><h3>{labels[stage]}</h3>{orders.filter(o => o.stage === stage).map(o => <button className={selected === o.order_id ? 'selected' : ''} key={o.order_id} onClick={() => { setDraft(null); void load(o.order_id).catch(e => setError(message(e))); }}><strong>{o.title}</strong><small>Expected {o.expected_at} UTC</small></button>)}{!orders.some(o => o.stage === stage) && <small>No examinations</small>}</section>)}</div>
    {detail ? <article className="result-detail" key={detail.order_id}><header><span className="eyebrow">{labels[detail.stage]} · Revision {detail.revision}</span><h2>{detail.title}</h2><p>{detail.reason}</p><small>Follow-up: {team.find(u => u.user_id === detail.coordinator_id)?.name || detail.coordinator_id} · Review: {team.find(u => u.user_id === detail.reviewer_id)?.name || detail.reviewer_id}</small></header>
      {detail.stage === 'completed' && <p className="completion-banner success">Result explained and patient informed. Any follow-up tasks remain independently active.</p>}
      {detail.cancelled_reason && <p>Cancellation: {detail.cancelled_reason}</p>}
      {enabled && detail.stage !== 'cancelled' && <>
      <details className="result-card" open={detail.stage === 'waiting_report'}><summary>Upload report or correction</summary><form onSubmit={async e => { e.preventDefault(); const f = new FormData(e.currentTarget); const file = f.get('file') as File; if (!file || file.size > 10 * 1024 * 1024) { setError('Choose a PDF no larger than 10 MiB.'); return; } const reader = new FileReader(); reader.onload = () => void mutate(`/test-orders/${detail.order_id}/reports`, { expected_revision: revision, filename: file.name, content_type: 'application/pdf', file_base64: String(reader.result).split(',')[1], external_source: f.get('external_source'), issued_at: f.get('issued_at') }); reader.readAsDataURL(file); }}>
        <label>PDF report · maximum 10 MiB<input name="file" type="file" accept="application/pdf,.pdf" required /></label><label>External report source<input name="external_source" required /></label><label>Report issued (clinic time)<input name="issued_at" type="datetime-local" required /></label><p>Corrections reopen doctor review and invalidate linked older guidance.</p><button disabled={busy}>Upload report</button></form></details>
      {identity.role === 'clinician' && detail.current_report_id && <details className="result-card" open={detail.stage === 'waiting_review'}><summary>Doctor review</summary><form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void mutate(`/test-reports/${detail.current_report_id}/reviews`, { expected_revision: revision, conclusion: f.get('conclusion'), outcome,
          ...(outcome !== 'no_action' ? { follow_up_title: f.get('follow_up_title'), follow_up_owner_id: f.get('follow_up_owner_id'), follow_up_due_at: f.get('follow_up_due_at') } : {}) }); }}>
        <label>Review conclusion<textarea name="conclusion" required /></label><label>Next step<select value={outcome} onChange={e => setOutcome(e.target.value)}><option value="no_action">No further action</option><option value="monitor">Monitor / follow up</option><option value="action_required">Action required</option></select></label>
        {outcome !== 'no_action' && <><label>Follow-up task<input name="follow_up_title" required /></label><label>Responsible person{chooseOwner('follow_up_owner_id', identity.user_id || '')}</label><label>Deadline (clinic time)<input name="follow_up_due_at" type="datetime-local" required /></label></>}
        <button className="primary-button" disabled={busy}>Confirm review</button></form></details>}
      {detail.current_review_id && <section className="result-card"><h3>Inform the patient</h3>
        {identity.role === 'clinician' && detail.result_event_id && <details><summary>Write and publish patient guidance</summary><PatientInstructionComposer eventId={detail.result_event_id} onSaved={setDraft} />{draft && <InstructionPublicationControl artifact={draft} role="clinician" onChanged={() => void load()} />}</details>}
        <form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); const pub = f.get('publication_id'); void mutate(`/test-orders/${detail.order_id}/communications`, { expected_revision: revision, review_id: detail.current_review_id, method: f.get('method'), outcome: f.get('outcome'), performed_at: f.get('performed_at') || new Date().toISOString(), ...(pub ? { publication_id: pub } : {}) }); }}>
          <label>Communication method<select name="method"><option value="phone">Phone</option><option value="in_person">In person</option><option value="portal">Published guidance</option></select></label>
          <label>Communication time (clinic time; blank means now)<input name="performed_at" type="datetime-local" /></label>
          <label>Outcome<select name="outcome"><option value="delivered">Confirmed delivered</option><option value="not_reached">Not reached</option><option value="message_left">Message left</option><option value="unconfirmed">Delivery unconfirmed</option></select></label>
          <label>Published guidance (portal only)<select name="publication_id"><option value="">None</option>{detail.publications.map(p => <option key={p.publication_id} value={p.publication_id}>Guidance version {p.artifact_version} · {p.artifact_id}</option>)}</select></label>
          <p>Record only confirmed doctor conclusions. Unsuccessful contact leaves this result open.</p><button disabled={busy}>Record communication now</button></form>
      </section>}
      {identity.role === 'clinician' && <details className="result-card"><summary>Assignment, deadline and cancellation</summary><form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void mutate(`/test-orders/${detail.order_id}`, { expected_revision: revision, coordinator_id: f.get('coordinator_id'), reviewer_id: f.get('reviewer_id'), ...(f.get('expected_at') ? { expected_at: f.get('expected_at') } : {}), ...(f.get('cancel_reason') ? { cancel_reason: f.get('cancel_reason') } : {}) }, 'PATCH'); }}><label>Follow-up owner{chooseOwner('coordinator_id', detail.coordinator_id)}</label><label>Review doctor{chooseOwner('reviewer_id', detail.reviewer_id, true)}</label><label>New expected time<input name="expected_at" type="datetime-local" /></label><label>Cancel examination — reason (optional)<textarea name="cancel_reason" /></label><button disabled={busy}>Save changes</button></form></details>}
      </>}
      <section className="result-card"><h3>Report versions</h3>{detail.reports.map(r => <div key={r.report_id}><strong>Report v{r.version} · {r.external_source}</strong><p>Issued {r.issued_at} UTC · Uploaded by {team.find(u => u.user_id === r.uploaded_by)?.name || r.uploaded_by}</p><button onClick={() => void downloadTestReport(r.report_id).catch(e => setError(message(e)))}>Download version {r.version}</button>{r.withdrawn_reason && <p>Withdrawn: {r.withdrawn_reason}</p>}
        {enabled && identity.role === 'clinician' && !r.withdrawn_reason && <form onSubmit={e => { e.preventDefault(); void mutate(`/test-reports/${r.report_id}/withdraw`, { expected_revision: revision, reason: new FormData(e.currentTarget).get('reason') }); }}><label>Withdrawal reason<input name="reason" required /></label><button disabled={busy}>Withdraw this report</button></form>}</div>)}</section>
      <section className="result-card"><h3>Review and communication history</h3>{detail.reviews.map(r => <div key={r.review_id}><strong>{r.review_id === detail.current_review_id ? 'Current review' : 'Earlier review'} · {r.outcome.replace(/_/g, ' ')}</strong><p>{r.conclusion}</p>{r.follow_up_task_id && <a href={`/clinical/patients/${patientId}/tasks?task=${r.follow_up_task_id}`}>Open follow-up task</a>}</div>)}{detail.communications.map(c => <p key={c.communication_id}>{c.method} · {c.outcome.replace(/_/g, ' ')} · {c.performed_at} UTC</p>)}</section>
    </article> : <div className="empty-state">Select an examination to review its report and next step.</div>}</div>
  </section>;
}
