import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, ApiError } from '../api';
import { artifactLabel, eventLabel, formatDateTime } from '../clinical';
import type { Artifact, ClinicalTask, CurrentIdentity, Event, Span, TaskProvenance, TaskStatus } from '../types';

function exactFirstSpan(artifact: Artifact): Span | null {
  const segments = artifact.content.segments;
  if (Array.isArray(segments)) {
    const segment = segments.find((item) => typeof item?.index === 'number' && typeof item?.text === 'string' && item.text.length);
    if (segment) return { kind: 'segment', index: segment.index, offset: [0, segment.text.length] };
  }
  const messages = artifact.content.messages;
  if (Array.isArray(messages)) {
    const index = messages.findIndex((item) => typeof item?.text === 'string' && item.text.length);
    if (index >= 0) return { kind: 'message', index: index + 1, offset: [0, messages[index].text.length] };
  }
  for (const [key, value] of Object.entries(artifact.content)) {
    if (typeof value === 'string' && value.length) return { kind: 'section', index: key, offset: [0, value.length] };
  }
  return null;
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
  const span = sourceArtifact ? exactFirstSpan(sourceArtifact) : null;

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
        source_artifact_id: sourceArtifact && span ? sourceArtifact.artifact_id : null,
        source_span: sourceArtifact && span ? span : null,
      });
      setTitle('');
      setDescription('');
      setDueAt('');
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
        {sourceArtifact && span
          ? <span>Exact source: {artifactLabel(sourceArtifact)}</span>
          : <span>Event-level provenance</span>}
      </div>
      <label>Task title<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={255} /></label>
      <label>Clinic description<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} /></label>
      <div className="task-form-row">
        <label>Assign to<select value={assignedRole} onChange={(event) => setAssignedRole(event.target.value as typeof assignedRole)}><option value="patient">Patient</option><option value="staff">Staff queue</option><option value="clinician">Clinician queue</option></select></label>
        <label>Due<input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label>
      </div>
      {sourceArtifact && !span && <div className="form-error">This Artifact has no resolvable exact text span. The Task will use Event provenance only.</div>}
      <div className="inline-actions"><button className="primary-button" disabled={busy || !title.trim()} onClick={create}>{busy ? 'Creating…' : 'Create Task'}</button>{error && <span className="error-inline">{error}</span>}</div>
    </div>
  );
}

export default function ClinicalTasksView({
  patientId,
  events,
  identity,
  refreshKey,
  onChanged,
  onOpenEvent,
}: {
  patientId: string;
  events: Event[];
  identity: CurrentIdentity;
  refreshKey: number;
  onChanged: () => void;
  onOpenEvent: (event: Event) => void;
}) {
  const [tasks, setTasks] = useState<ClinicalTask[]>([]);
  const [selectedEventId, setSelectedEventId] = useState(events[events.length - 1]?.event_id ?? '');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<TaskProvenance | null>(null);

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

  async function viewSource(task: ClinicalTask) {
    try {
      setProvenance(await api.getTaskProvenance(task.task_id));
    } catch (sourceError: any) {
      setError(String(sourceError.message ?? sourceError));
    }
  }

  return (
    <section className="clinical-view tasks-view" aria-labelledby="tasks-heading">
      <div className="view-title-row"><div><p className="eyebrow">Who must do what next</p><h2 id="tasks-heading">Care Tasks</h2></div><span className="record-count">{tasks.length} tasks</span></div>
      {error && <div className="form-error">{error}</div>}
      <div className="task-create-card">
        <h3>Create from Event</h3>
        <select value={selectedEvent?.event_id ?? ''} onChange={(event) => setSelectedEventId(event.target.value)}>
          {events.map((event) => <option key={event.event_id} value={event.event_id}>{formatDateTime(event.started_at)} · {eventLabel(event)}</option>)}
        </select>
        {selectedEvent && <TaskCreateForm event={selectedEvent} onCreated={() => { load(); onChanged(); }} />}
      </div>
      {loading && <div className="loading-card">Loading care tasks…</div>}
      {!loading && tasks.length === 0 && <div className="empty-state"><h3>No care tasks</h3><p>Create an evidence-linked action from a real Event.</p></div>}
      <div className="clinical-task-list">
        {tasks.map((task) => (
          <article key={task.task_id} className={`clinical-task task-${task.status}`}>
            <header><div><span className="task-status">{task.status.replace('_', ' ')}</span><h3>{task.title}</h3></div>{task.due_at && <small>Due {formatDateTime(task.due_at)}</small>}</header>
            {task.description && <p>{task.description}</p>}
            <div className="task-meta">Assigned: {task.assigned_role}{task.patient_visible ? ' · patient visible' : ' · internal'} · Origin {task.event_id}{task.source_artifact_id ? ` / ${task.source_artifact_id}` : ''}</div>
            {task.status === 'reported_done' && <div className="verification-callout">Patient/clinic reported done · clinic verification required</div>}
            <div className="task-actions">
              {task.status === 'open' && task.assigned_role === identity.role && (!task.assigned_user_id || task.assigned_user_id === identity.user_id) && <button disabled={pendingId === task.task_id} onClick={() => transition(task, 'in_progress')}>Start</button>}
              {(task.status === 'open' || task.status === 'in_progress') && <button disabled={pendingId === task.task_id} onClick={() => transition(task, 'reported_done')}>Report done</button>}
              {task.status === 'reported_done' && <button disabled={pendingId === task.task_id} onClick={() => transition(task, 'completed')}>Verify complete</button>}
              {['open', 'in_progress', 'reported_done'].includes(task.status) && <button disabled={pendingId === task.task_id} onClick={() => transition(task, 'cancelled')}>Cancel</button>}
              <button onClick={() => onOpenEvent(events.find((event) => event.event_id === task.event_id) ?? selectedEvent!)}>Open Event</button>
              <button onClick={() => viewSource(task)}>View source</button>
            </div>
          </article>
        ))}
      </div>
      {provenance && <div className="task-provenance"><button className="link-btn" onClick={() => setProvenance(null)}>Close</button><strong>Task source</strong><span>{provenance.event.event_type} · {provenance.event.event_id}</span>{provenance.source_artifact && <span>{provenance.source_artifact.artifact_type} · {provenance.source_artifact.artifact_id}</span>}{provenance.quote && <blockquote>{provenance.quote}</blockquote>}</div>}
    </section>
  );
}
