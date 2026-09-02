import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, ApiError } from '../api';
import { artifactLabel, eventLabel, formatDateTime } from '../clinical';
import type { Artifact, ClinicalTask, CurrentIdentity, Event, PatientReviewCandidate, PatientReviewContext, ProvenanceResult, Span, TaskProvenance, TaskStatus } from '../types';

// ---------------------------------------------------------------------------
// Exact-source selection contract (D2 review fix):
// NEVER auto-mark the first segment of an Artifact as the Task source.
// The user must explicitly pick a quote AND confirm it; otherwise the Task is
// saved with Event-level provenance only (source_artifact_id/source_span null).
// ---------------------------------------------------------------------------
interface QuoteOption {
  key: string;
  span: Span;
  label: string;
  text: string;
}

function quoteOptions(artifact: Artifact): QuoteOption[] {
  const options: QuoteOption[] = [];
  const segments = artifact.content.segments;
  if (Array.isArray(segments)) {
    for (const item of segments) {
      if (
        item &&
        typeof item === 'object' &&
        typeof item.index === 'number' &&
        typeof item.text === 'string' &&
        item.text.trim().length > 0
      ) {
        options.push({
          key: `segment:${item.index}`,
          span: { kind: 'segment', index: item.index, offset: [0, item.text.length] },
          label: `Segment ${item.index}${item.speaker ? ` · ${item.speaker}` : ''}`,
          text: item.text,
        });
      }
    }
  }
  const messages = artifact.content.messages;
  if (Array.isArray(messages)) {
    messages.forEach((item, position) => {
      if (
        item &&
        typeof item === 'object' &&
        typeof item.text === 'string' &&
        item.text.trim().length > 0
      ) {
        const speaker = typeof item.speaker === 'string' ? item.speaker : '';
        options.push({
          key: `message:${position + 1}`,
          span: { kind: 'message', index: position + 1, offset: [0, item.text.length] },
          label: `Message ${position + 1}${speaker ? ` · ${speaker}` : ''}`,
          text: item.text,
        });
      }
    });
  }
  for (const [key, value] of Object.entries(artifact.content)) {
    if (typeof value === 'string' && value.trim().length > 0) {
      options.push({
        key: `section:${key}`,
        span: { kind: 'section', index: key, offset: [0, value.length] },
        label: `Section ${key}`,
        text: value,
      });
    }
  }
  return options;
}

export function TaskCreateForm({
  event,
  sourceArtifact,
  onCreated,
}: {
  event: Event;
  sourceArtifact?: Artifact | null;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [assignedRole, setAssignedRole] = useState<'patient' | 'staff' | 'clinician'>('patient');
  const [dueAt, setDueAt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Explicit exact-source state: pick a quote, then confirm it. Without BOTH,
  // provenance stays Event-level. Never auto-selected.
  const options = useMemo(
    () => (sourceArtifact ? quoteOptions(sourceArtifact) : []),
    [sourceArtifact],
  );
  const [selectedKey, setSelectedKey] = useState('');
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    // Artifact context changes reset any pending selection/confirmation.
    setSelectedKey('');
    setConfirmed(false);
  }, [sourceArtifact?.artifact_id, event.event_id]);

  const selected = options.find((option) => option.key === selectedKey) ?? null;
  const exactSource = selected && confirmed ? selected : null;

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await api.createTask(event.event_id, {
        title: title.trim(),
        description: description.trim(),
        assigned_role: assignedRole,
        assigned_user_id: null,
        patient_visible: assignedRole === 'patient',
        due_at: dueAt || null,
        source_artifact_id: exactSource && sourceArtifact ? sourceArtifact.artifact_id : null,
        source_span: exactSource ? exactSource.span : null,
      });
      setTitle('');
      setDescription('');
      setDueAt('');
      setSelectedKey('');
      setConfirmed(false);
      onCreated();
    } catch (createError: any) {
      setError(createError instanceof ApiError && createError.status === 409
        ? 'Task changed concurrently. Refresh and try again.'
        : String(createError.message ?? createError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="task-create-form">
      <div className="task-source-line">
        <strong>Origin</strong>
        <span>{eventLabel(event)} · {event.event_id}</span>
        {exactSource && sourceArtifact
          ? <span>Exact source (confirmed): {artifactLabel(sourceArtifact)}</span>
          : <span>Event-level provenance</span>}
      </div>
      <label>Task title<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={255} /></label>
      <label>Clinic description<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} /></label>
      <div className="task-form-row">
        <label>Assign to<select value={assignedRole} onChange={(event) => setAssignedRole(event.target.value as typeof assignedRole)}><option value="patient">Patient</option><option value="staff">Staff queue</option><option value="clinician">Clinician queue</option></select></label>
        <label>Due<input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label>
      </div>

      {sourceArtifact && (
        <div className="task-exact-source">
          <p className="eyebrow">Exact source (optional)</p>
          {options.length === 0 ? (
            <p className="muted">This Artifact has no selectable text segments — the Task will use Event provenance only.</p>
          ) : (
            <>
              <label htmlFor="task-quote">Choose a quote from {artifactLabel(sourceArtifact)}</label>
              <select
                id="task-quote"
                value={selectedKey}
                onChange={(event) => { setSelectedKey(event.target.value); setConfirmed(false); }}
              >
                <option value="">No exact source (Event-level provenance)</option>
                {options.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label} — {option.text.slice(0, 80)}{option.text.length > 80 ? '…' : ''}
                  </option>
                ))}
              </select>
              {selected && (
                <div className="task-quote-preview">
                  <blockquote>{selected.text}</blockquote>
                  <label className="task-quote-confirm">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      onChange={(event) => setConfirmed(event.target.checked)}
                    />
                    Confirm this exact quote as the Task source
                  </label>
                  {!confirmed && <p className="muted">Unconfirmed: the Task will be saved with Event-level provenance.</p>}
                </div>
              )}
            </>
          )}
        </div>
      )}

      <div className="inline-actions"><button className="primary-button" disabled={busy || !title.trim()} onClick={create}>{busy ? 'Creating…' : 'Create Task'}</button>{error && <span className="error-inline">{error}</span>}</div>
    </div>
  );
}

export default function ClinicalTasksView({
  patientId,
  events,
  identity,
  refreshKey,
  focusTaskId,
  onFocusHandled,
  onChanged,
  onOpenEvent,
  onViewSource,
}: {
  patientId: string;
  events: Event[];
  identity: CurrentIdentity;
  refreshKey: number;
  focusTaskId?: string | null;
  onFocusHandled?: () => void;
  onChanged: () => void;
  onOpenEvent: (event: Event) => void;
  onViewSource: (source: ProvenanceResult) => void;
}) {
  const [tasks, setTasks] = useState<ClinicalTask[]>([]);
  const [selectedEventId, setSelectedEventId] = useState(events[events.length - 1]?.event_id ?? '');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<TaskProvenance | null>(null);
  const [focusedTaskId, setFocusedTaskId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [reviewContext, setReviewContext] = useState<PatientReviewContext | null>(null);
  const [correctionDrafts, setCorrectionDrafts] = useState<Record<string, string>>({});
  const [followUpTitle, setFollowUpTitle] = useState('Follow up on patient-reported update');
  const [followUpOwner, setFollowUpOwner] = useState<'clinician' | 'staff'>('clinician');
  const [followUpDue, setFollowUpDue] = useState('');
  const [followUpSensitivity, setFollowUpSensitivity] = useState<'routine' | 'time_sensitive'>('routine');

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      setTasks(await api.getTasks(patientId, signal));
      setError(null);
    } catch (loadError: any) {
      if (loadError?.name !== 'AbortError') setError(String(loadError.message ?? loadError));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    load(controller.signal);
    return () => controller.abort();
  }, [load, refreshKey]);

  const selectedEvent = useMemo(
    () => events.find((event) => event.event_id === selectedEventId) ?? events[events.length - 1] ?? null,
    [events, selectedEventId],
  );

  async function viewSource(task: ClinicalTask) {
    try {
      setProvenance(await api.getTaskProvenance(task.task_id));
    } catch (sourceError: any) {
      setError(String(sourceError.message ?? sourceError));
    }
  }

  async function openReview(task: ClinicalTask) {
    try {
      setReviewContext(await api.getPatientReviewContext(task.task_id));
      setProvenance(null);
    } catch (reviewError: any) {
      setError(String(reviewError.message ?? reviewError));
    }
  }

  async function viewCandidateSource(candidate: PatientReviewCandidate) {
    try {
      onViewSource(await api.getProvenance(candidate.highlight_id));
    } catch (sourceError: any) {
      setError(String(sourceError.message ?? sourceError));
    }
  }

  // Glance "Open Task" lands on the SPECIFIC task, not the generic list:
  // scroll to its card, highlight it and open its provenance.
  useEffect(() => {
    if (!focusTaskId || tasks.length === 0) return;
    const task = tasks.find((candidate) => candidate.task_id === focusTaskId);
    if (!task) {
      onFocusHandled?.();
      return;
    }
    setFocusedTaskId(focusTaskId);
    const element = document.getElementById(`task-card-${focusTaskId}`);
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (task.task_kind === 'patient_report_review' || task.task_kind === 'clinician_priority_review') {
      openReview(task);
    } else {
      viewSource(task);
    }
    onFocusHandled?.();
  }, [focusTaskId, tasks]);

  async function transition(task: ClinicalTask, status: TaskStatus) {
    setPendingId(task.task_id);
    setError(null);
    try {
      await api.transitionTask(task.task_id, task.status, status);
      await load();
      onChanged();
    } catch (transitionError: any) {
      setError(transitionError instanceof ApiError && transitionError.status === 409
        ? 'This Task changed concurrently. The latest state has been loaded.'
        : String(transitionError.message ?? transitionError));
      await load();
    } finally {
      setPendingId(null);
    }
  }

  async function verifyPatientReport(
    task: ClinicalTask,
    outcome: 'verified' | 'corrected' | 'unable_to_verify',
    route: 'close' | 'clinician_review',
  ) {
    setPendingId(task.task_id);
    try {
      await api.verifyPatientReport(task.task_id, task.status as 'open' | 'in_progress', outcome, route);
      setReviewContext(null);
      await load();
      onChanged();
    } catch (reviewError: any) {
      setError(String(reviewError.message ?? reviewError));
      await load();
    } finally {
      setPendingId(null);
    }
  }

  async function reviewCandidate(
    task: ClinicalTask,
    candidate: PatientReviewCandidate,
    outcome: 'verified' | 'corrected' | 'unable_to_verify',
  ) {
    setPendingId(candidate.review_item_id);
    setError(null);
    try {
      let correctionArtifactId: string | null = null;
      if (outcome === 'corrected') {
        const correction = (correctionDrafts[candidate.review_item_id] ?? '').trim();
        if (!correction) throw new Error('Write the correction before recording this item as corrected.');
        const note = await api.createNote(task.event_id, 'staff_note', {
          note: correction,
          patient_review_highlight_id: candidate.highlight_id,
        });
        correctionArtifactId = note.artifact_id;
      }
      await api.reviewPatientReportItem(
        task.task_id,
        candidate.review_item_id,
        candidate.review_outcome,
        outcome,
        correctionArtifactId,
      );
      setReviewContext(await api.getPatientReviewContext(task.task_id));
    } catch (reviewError: any) {
      setError(String(reviewError.message ?? reviewError));
      setReviewContext(await api.getPatientReviewContext(task.task_id).catch(() => reviewContext));
    } finally {
      setPendingId(null);
    }
  }

  async function completeClinicianReview(
    task: ClinicalTask,
    outcome: 'no_action' | 'monitor_or_record' | 'action_required',
    sensitivity: 'routine' | 'time_sensitive',
    followUpTaskId: string | null = null,
  ) {
    setPendingId(task.task_id);
    try {
      await api.completeClinicianReview(task.task_id, task.status as 'open' | 'in_progress', outcome, sensitivity, followUpTaskId);
      setReviewContext(null);
      await load();
      onChanged();
    } catch (reviewError: any) {
      setError(String(reviewError.message ?? reviewError));
      await load();
    } finally {
      setPendingId(null);
    }
  }

  async function createFollowUpAndComplete(task: ClinicalTask) {
    setPendingId(task.task_id);
    setError(null);
    try {
      if (!followUpTitle.trim()) throw new Error('A follow-up Task title is required.');
      if (followUpSensitivity === 'time_sensitive' && !followUpDue) {
        throw new Error('A time-sensitive follow-up needs a due time.');
      }
      const followUp = await api.createTask(task.event_id, {
        title: followUpTitle.trim(),
        description: 'Follow-up action created from clinician review of a patient-reported update.',
        assigned_role: followUpOwner,
        assigned_user_id: followUpOwner === 'clinician' ? identity.user_id : null,
        patient_visible: false,
        due_at: followUpDue || null,
        source_artifact_id: null,
        source_span: null,
      });
      await api.completeClinicianReview(
        task.task_id,
        task.status as 'open' | 'in_progress',
        'action_required',
        followUpSensitivity,
        followUp.task_id,
      );
      setReviewContext(null);
      await load();
      onChanged();
    } catch (reviewError: any) {
      setError(String(reviewError.message ?? reviewError));
      await load();
    } finally {
      setPendingId(null);
    }
  }

  const pendingReviewCount = reviewContext?.candidates.filter((candidate) => candidate.review_outcome === 'pending').length ?? 0;
  const aggregateReviewOutcome = reviewContext && pendingReviewCount === 0 && reviewContext.candidates.length > 0
    ? (reviewContext.candidates.some((candidate) => candidate.review_outcome === 'unable_to_verify')
      ? 'unable_to_verify'
      : reviewContext.candidates.some((candidate) => candidate.review_outcome === 'corrected')
        ? 'corrected'
        : 'verified')
    : null;

  return (
    <section className="clinical-view tasks-view" aria-labelledby="tasks-heading">
      <div className="view-title-row"><div><p className="eyebrow">Who must do what next</p><h2 id="tasks-heading">Care Tasks</h2><p className="view-subtitle">Review active work first; create a new task only when needed.</p></div><div className="view-title-actions"><span className="record-count">{tasks.length} tasks</span><button className="primary-button" onClick={() => setShowCreate((current) => !current)}>{showCreate ? 'Close form' : 'New task'}</button></div></div>
      <div className="task-authority-note"><strong>Task authority</strong><span>Patient “Report done” means reported_done and still requires explicit clinic verification before completion.</span></div>
      {error && <div className="form-error">{error}</div>}
      {showCreate && <div className="task-create-card">
        <div className="task-create-head"><div><p className="eyebrow">New follow-up action</p><h3>New task</h3><p>Choose the clinical Event this task belongs to.</p></div><button className="link-btn" onClick={() => setShowCreate(false)}>Close</button></div>
        <label className="task-event-picker">Linked clinical Event<select value={selectedEvent?.event_id ?? ''} onChange={(event) => setSelectedEventId(event.target.value)}>
          {events.map((event) => <option key={event.event_id} value={event.event_id}>{formatDateTime(event.started_at)} · {eventLabel(event)}</option>)}
        </select></label>
        {selectedEvent && <TaskCreateForm event={selectedEvent} onCreated={() => { load(); onChanged(); setShowCreate(false); }} />}
      </div>}
      {reviewContext && <section className="patient-review-workbench" aria-label="Patient report review">
        <header className="patient-review-head">
          <div><p className="eyebrow">Source-linked patient report</p><h3>{reviewContext.task.title}</h3><p>{reviewContext.degraded ? 'Deterministic fallback extraction' : `AI extraction · ${reviewContext.generation_method ?? 'provider mode unknown'}`}. Each item remains patient-reported until reviewed.</p></div>
          <button className="link-btn" onClick={() => setReviewContext(null)}>Close</button>
        </header>
        {reviewContext.candidates.length === 0 && <div className="empty-state"><h3>No extracted candidates</h3><p>The submitted Check-in still requires a session-level Nurse decision.</p></div>}
        <div className="patient-review-items">{reviewContext.candidates.map((candidate) => (
          <article key={candidate.review_item_id} className={`patient-review-item ${candidate.review_outcome}`}>
            <div className="patient-review-item-head"><span>{candidate.entity_type?.replace(/_/g, ' ') ?? 'patient update'}</span><strong>{candidate.review_outcome.replace(/_/g, ' ')}</strong></div>
            <p>{candidate.text}</p>
            <div className="patient-review-item-actions">
              <button onClick={() => viewCandidateSource(candidate)}>Open exact source</button>
              {identity.role === 'staff' && candidate.review_outcome === 'pending' && <>
                <button disabled={pendingId === candidate.review_item_id} onClick={() => reviewCandidate(reviewContext.task, candidate, 'verified')}>Verified</button>
                <button disabled={pendingId === candidate.review_item_id} onClick={() => reviewCandidate(reviewContext.task, candidate, 'unable_to_verify')}>Unable to verify</button>
              </>}
            </div>
            {identity.role === 'staff' && candidate.review_outcome === 'pending' && <div className="patient-review-correction">
              <label>Correction note<textarea rows={2} value={correctionDrafts[candidate.review_item_id] ?? ''} onChange={(event) => setCorrectionDrafts((current) => ({ ...current, [candidate.review_item_id]: event.target.value }))} placeholder="Record what the patient clarified; this is saved as a Staff Note." /></label>
              <button disabled={pendingId === candidate.review_item_id || !(correctionDrafts[candidate.review_item_id] ?? '').trim()} onClick={() => reviewCandidate(reviewContext.task, candidate, 'corrected')}>Save Staff Note + mark corrected</button>
            </div>}
            {candidate.correction_artifact_id && <small>Correction preserved in Staff Note {candidate.correction_artifact_id}</small>}
          </article>
        ))}</div>
        {identity.role === 'staff' && reviewContext.task.task_kind === 'patient_report_review' && ['open', 'in_progress'].includes(reviewContext.task.status) && <footer className="patient-review-completion">
          <span>{pendingReviewCount > 0 ? `${pendingReviewCount} candidate${pendingReviewCount === 1 ? '' : 's'} still pending` : `Session outcome: ${(aggregateReviewOutcome ?? 'verified').replace(/_/g, ' ')}`}</span>
          <button disabled={pendingReviewCount > 0 || pendingId === reviewContext.task.task_id} onClick={() => verifyPatientReport(reviewContext.task, aggregateReviewOutcome ?? 'verified', 'close')}>Complete Nurse review</button>
          <button disabled={pendingReviewCount > 0 || pendingId === reviewContext.task.task_id} onClick={() => verifyPatientReport(reviewContext.task, aggregateReviewOutcome ?? 'verified', 'clinician_review')}>Complete + clinician review</button>
        </footer>}
        {identity.role === 'clinician' && reviewContext.task.task_kind === 'clinician_priority_review' && ['open', 'in_progress'].includes(reviewContext.task.status) && <section className="clinician-review-decision">
          <div className="inline-actions">
            <button disabled={pendingId === reviewContext.task.task_id} onClick={() => completeClinicianReview(reviewContext.task, 'no_action', 'routine')}>No action · routine</button>
            <button disabled={pendingId === reviewContext.task.task_id} onClick={() => completeClinicianReview(reviewContext.task, 'monitor_or_record', 'routine')}>Monitor / record · routine</button>
            <button disabled={pendingId === reviewContext.task.task_id} onClick={() => completeClinicianReview(reviewContext.task, 'monitor_or_record', 'time_sensitive')}>Monitor / record · time-sensitive</button>
          </div>
          <div className="clinician-follow-up-form">
            <div><strong>Action required</strong><span>Create the executable follow-up before closing this review.</span></div>
            <label>Task title<input value={followUpTitle} onChange={(event) => setFollowUpTitle(event.target.value)} /></label>
            <label>Owner<select value={followUpOwner} onChange={(event) => setFollowUpOwner(event.target.value as typeof followUpOwner)}><option value="clinician">Assign to me (clinician)</option><option value="staff">Nurse queue</option></select></label>
            <label>Time sensitivity<select value={followUpSensitivity} onChange={(event) => setFollowUpSensitivity(event.target.value as typeof followUpSensitivity)}><option value="routine">Routine</option><option value="time_sensitive">Time-sensitive</option></select></label>
            <label>Due time<input type="datetime-local" value={followUpDue} onChange={(event) => setFollowUpDue(event.target.value)} required={followUpSensitivity === 'time_sensitive'} /></label>
            <button className="primary-button" disabled={pendingId === reviewContext.task.task_id || !followUpTitle.trim() || (followUpSensitivity === 'time_sensitive' && !followUpDue)} onClick={() => createFollowUpAndComplete(reviewContext.task)}>Create follow-up + complete review</button>
          </div>
        </section>}
      </section>}
      {loading && <div className="loading-card">Loading care tasks…</div>}
      {!loading && tasks.length === 0 && <div className="empty-state"><h3>No care tasks</h3><p>Create an evidence-linked action from a real Event.</p></div>}
      {!loading && tasks.length > 0 && <div className="clinical-task-table-wrap"><table className="clinical-task-table">
        <thead><tr><th>Task</th><th>Status</th><th>Owner</th><th>Due</th><th><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{tasks.map((task) => (
          <tr key={task.task_id} id={`task-card-${task.task_id}`} className={`task-${task.status}${focusedTaskId === task.task_id ? ' task-focused' : ''}`}>
            <td><strong>{task.title}</strong>{task.description && <span>{task.description}</span>}<small>Source: {eventLabel(events.find((event) => event.event_id === task.event_id) ?? selectedEvent!)}{task.source_artifact_id ? ' · source-linked Check-in' : ' · Event-level source'}</small>{task.creation_method === 'system_routed' && <em>Routed from patient Check-in · {task.verification_outcome.replace(/_/g, ' ')}</em>}{task.escalated_at && <em>Nurse review overdue · internally escalated</em>}{task.status === 'reported_done' && <em>Clinic verification required</em>}</td>
            <td><span className="task-status">{task.status.replace('_', ' ')}</span></td>
            <td>{task.assigned_role}<small>{task.patient_visible ? 'Patient visible' : 'Internal'}</small></td>
            <td>{task.due_at ? formatDateTime(task.due_at) : 'No due date'}</td>
            <td><details className="task-actions-menu"><summary>Actions</summary><div>
              {task.task_kind === 'patient_report_review' && identity.role === 'staff' && ['open', 'in_progress'].includes(task.status) && <>
                <button disabled={pendingId === task.task_id} onClick={() => openReview(task)}>Review candidates</button>
              </>}
              {task.task_kind === 'clinician_priority_review' && identity.role === 'clinician' && ['open', 'in_progress'].includes(task.status) && <>
                <button disabled={pendingId === task.task_id} onClick={() => openReview(task)}>Open clinician review</button>
              </>}
              {task.task_kind === 'care_action' && <>
              {task.status === 'open' && task.assigned_role === identity.role && (!task.assigned_user_id || task.assigned_user_id === identity.user_id) && <button disabled={pendingId === task.task_id} onClick={() => transition(task, 'in_progress')}>Start</button>}
              {(task.status === 'open' || task.status === 'in_progress') && <button disabled={pendingId === task.task_id} onClick={() => transition(task, 'reported_done')}>Report done</button>}
              {task.status === 'reported_done' && <button disabled={pendingId === task.task_id} onClick={() => transition(task, 'completed')}>Verify complete</button>}
              {['open', 'in_progress', 'reported_done'].includes(task.status) && <button disabled={pendingId === task.task_id} onClick={() => transition(task, 'cancelled')}>Cancel</button>}
              </>}
              <button onClick={() => onOpenEvent(events.find((event) => event.event_id === task.event_id) ?? selectedEvent!)}>Open Event</button>
              <button onClick={() => viewSource(task)}>View source</button>
            </div></details></td>
          </tr>
        ))}</tbody>
      </table></div>}
      {provenance && <div className="task-provenance"><button className="link-btn" onClick={() => setProvenance(null)}>Close</button><strong>Task source</strong><span>{provenance.event.event_type} · {provenance.event.event_id}</span>{provenance.source_artifact && <span>{provenance.source_artifact.artifact_type} · {provenance.source_artifact.artifact_id}</span>}{provenance.quote ? <blockquote>{provenance.quote}</blockquote> : <span className="muted">Event-level provenance (no exact source selected)</span>}</div>}
    </section>
  );
}
