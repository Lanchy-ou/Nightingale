import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { PatientTask, PatientView, TaskStatus } from '../types';
import VoiceCapture from '../components/VoiceCapture';

const EVENT_TYPE_LABELS: Record<string, string> = {
  patient_ai_preconsult: 'AI pre-consult',
  patient_followup: 'Recovery check-in',
};

function fmtLongDate(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  open: 'Not started',
  in_progress: 'In progress',
  reported_done: 'Awaiting clinic confirmation',
  completed: 'Clinic confirmed',
  cancelled: 'Cancelled',
};

export default function PatientViewPage({
  patientId,
  roleKey,
  onLogout,
}: {
  patientId: string;
  roleKey: string;
  onLogout?: () => void;
}) {
  const [view, setView] = useState<PatientView | null>(null);
  const [tab, setTab] = useState<'today' | 'care' | 'checkin' | 'summaries'>('today');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const v = await api.getPatientView(patientId);
        if (!cancelled) {
          setView(v);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  useEffect(() => {
    return load();
  }, [load, roleKey, refreshKey]);

  useEffect(() => {
    // patient/session identity is a hard remount boundary. Clear every draft,
    // error and pending response even if a host reuses this component.
    setMessage('');
    setSubmitError(null);
    setSubmitSuccess(false);
    setTaskError(null);
    setPendingTaskId(null);
    setTab('today');
  }, [patientId, roleKey]);

  async function send() {
    if (!message.trim()) return;
    setBusy(true);
    setSubmitError(null);
    setSubmitSuccess(false);
    try {
      await api.createSession(
        patientId,
        `sess-${Date.now()}`,
        'patient_followup',
        new Date().toISOString(),
        { messages: [{ id: 'm1', speaker: 'patient', text: message.trim() }] },
      );
      setMessage('');
      setSubmitSuccess(true);
      setRefreshKey((k) => k + 1);
    } catch (e: any) {
      setSubmitError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function transition(task: PatientTask, status: TaskStatus) {
    setPendingTaskId(task.task_id);
    setTaskError(null);
    try {
      await api.transitionTask(task.task_id, task.status, status);
      setRefreshKey((key) => key + 1);
    } catch (e: any) {
      setTaskError(e?.status === 409
        ? 'This care action changed elsewhere. We are refreshing the latest status.'
        : String(e.message ?? e));
      if (e?.status === 409) setRefreshKey((key) => key + 1);
    } finally {
      setPendingTaskId(null);
    }
  }

  if (error) return <div className="patient-app-state"><div className="form-error">We could not load your care plan: {error}</div></div>;
  if (!view || loading) return <div className="patient-app-state"><div className="loading-card">Loading your care plan…</div></div>;

  const taskGroups: { key: keyof PatientView['care_plan']; label: string }[] = [
    { key: 'open', label: 'Not started' },
    { key: 'in_progress', label: 'In progress' },
    { key: 'reported_done', label: 'Awaiting clinic confirmation' },
    { key: 'completed', label: 'Completed' },
  ];

  const navigation = [
    ['today', 'Today', '⌂'],
    ['care', 'Care Plan', '✓'],
    ['checkin', 'Check-in', '✦'],
    ['summaries', 'Visit Summaries', '▤'],
  ] as const;

  return (
    <div className="patient-app-shell">
      <header className="patient-topbar">
        <div className="patient-brand" aria-label="Nightingale patient portal">
          <span className="patient-brand-mark" aria-hidden="true">N</span>
          <span><strong>Nightingale</strong><small>My care</small></span>
        </div>
        <nav className="patient-navigation" aria-label="Patient experience sections">
          {navigation.map(([key, label, icon]) => (
            <button key={key} className={tab === key ? 'active' : ''} aria-current={tab === key ? 'page' : undefined} onClick={() => setTab(key)}>
              <span aria-hidden="true">{icon}</span>{label}
            </button>
          ))}
        </nav>
        <div className="patient-profile">
          <div className="patient-profile-avatar">{view.display_name.slice(0, 1).toUpperCase()}</div>
          <div><strong>{view.display_name}</strong><small>My profile</small></div>
          {onLogout && <button className="patient-logout" onClick={onLogout}>Log out</button>}
        </div>
      </header>

      <main className={`patient-main patient-main-${tab}`}>
        {taskError && <div className="form-error">{taskError}</div>}

        {tab === 'today' && (
          <>
            <header className="patient-welcome">
              <div><p>{new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}</p><h1>{greeting()}, {view.display_name}</h1><span>Here is what you need to know and do next.</span></div>
            </header>

            <div className="patient-focus-grid">
              <section className="patient-current-summary">
                <div className="patient-section-kicker"><span aria-hidden="true">i</span>What you need to know</div>
                {view.today.instruction ? (
                  <><h2>{view.today.instruction.instruction}</h2><p>Follow your current care instructions and use Check-in if anything changes.</p><small>Updated {fmtLongDate(view.today.instruction.event_time)}</small></>
                ) : <><h2>There are no new care instructions today.</h2><p>Your clinic will update this page when there is something you need to know.</p></>}
              </section>
              <section className="patient-followup-card">
                <span>Upcoming follow-up</span>
                {view.today.next_follow_up ? <><h2>Next step</h2><p>{view.today.next_follow_up}</p></> : <><h2>No follow-up listed</h2><p>Your clinic has not added a new follow-up instruction.</p></>}
                <div className="patient-care-team"><span aria-hidden="true">＋</span><div><strong>Your care team</strong><small>Nightingale Demo Clinic</small></div></div>
              </section>
            </div>

            <div className="patient-action-grid">
              <section className="patient-surface patient-next-steps">
                <div className="patient-surface-head"><div><p>Care actions</p><h2>Your next steps</h2></div><span>{view.today.tasks.length} active</span></div>
                {view.today.tasks.length === 0
                  ? <div className="patient-empty-compact">You have no care actions to complete right now.</div>
                  : view.today.tasks.map((task) => <PatientTaskCard key={task.task_id} task={task} pending={pendingTaskId === task.task_id} onTransition={transition} />)}
              </section>
              <section className="patient-checkin-cta">
                <div className="patient-checkin-icon" aria-hidden="true">✦</div>
                <h2>How are you feeling today?</h2>
                <p>Share what has changed. Your update will be organised for your care team without changing your clinical plan.</p>
                <button onClick={() => setTab('checkin')}>Start a Check-in <span aria-hidden="true">→</span></button>
              </section>
            </div>

            <section className="patient-surface patient-instructions-preview">
              <div className="patient-surface-head"><div><p>Patient-facing information</p><h2>Instructions from your care team</h2></div><button onClick={() => setTab('summaries')}>View all →</button></div>
              {view.visit_summaries.summaries.length === 0 ? <div className="patient-empty-compact">No visit summaries are available yet.</div> : (
                <div className="patient-instruction-list">
                  {view.visit_summaries.summaries.slice(0, 2).map((summary) => (
                    <button key={summary.artifact_id} onClick={() => setTab('summaries')}><span>{fmtLongDate(summary.event_time)}</span><div><strong>Care instruction</strong><p>{summary.instruction}</p></div><span aria-hidden="true">›</span></button>
                  ))}
                </div>
              )}
            </section>
          </>
        )}

        {tab === 'care' && (
          <>
            <header className="patient-view-heading"><p>Your care</p><h1>Care Plan</h1><span>Start your assigned actions, report when you are done, and wait for the clinic to confirm completion.</span></header>
            <div className="patient-care-grid">
              {taskGroups.map(({ key, label }) => (
                <section className={`patient-surface patient-care-group patient-care-${key}`} key={key}>
                  <div className="patient-surface-head"><h2>{label}</h2><span>{view.care_plan[key].length}</span></div>
                  {view.care_plan[key].length === 0 ? <div className="patient-empty-compact">No items</div> : view.care_plan[key].map((task) => (
                    <PatientTaskCard key={task.task_id} task={task} pending={pendingTaskId === task.task_id} onTransition={transition} />
                  ))}
                </section>
              ))}
            </div>
          </>
        )}

        {tab === 'checkin' && (
          <section className="patient-checkin-layout">
            <aside className="patient-checkin-history">
              <button className="patient-back-home" onClick={() => setTab('today')}>← Back to Today</button>
              <h2>Check-in</h2>
              <p>Your updates become patient conversation records for the care team. They do not change your doctor’s plan or complete a task.</p>
              <h3>Previous Check-ins</h3>
              {view.check_in.sessions.length === 0 ? <span className="patient-empty-compact">No previous updates</span> : view.check_in.sessions.map((session) => (
                <div className="patient-session-row" key={session.event_id}><strong>{fmtLongDate(session.started_at)}</strong><span>{EVENT_TYPE_LABELS[session.event_type] ?? 'Patient update'}</span></div>
              ))}
            </aside>
            <div className="patient-checkin-main">
              <header><span className="patient-online-dot" aria-hidden="true" /><div><strong>Nightingale Check-in</strong><small>For non-emergency recovery updates</small></div></header>
              <div className="patient-checkin-conversation" aria-live="polite">
                <div className="patient-assistant-message">Hi {view.display_name}. What has changed since your last update?</div>
                <div className="patient-quick-prompts">
                  {['My symptoms are improving', 'I still feel nauseous', 'I have a new symptom'].map((prompt) => <button key={prompt} onClick={() => { setMessage(prompt); setSubmitSuccess(false); }}>{prompt}</button>)}
                </div>
                {submitSuccess && <div className="patient-success-message">Your update was saved and is available for your care team to review.</div>}
              </div>
              <VoiceCapture
                boundaryKey={`${roleKey}:${patientId}:voice-checkin`}
                patientId={patientId}
                captureMode="patient_session"
                patientEventType="patient_followup"
                onProcessed={() => {
                  setSubmitSuccess(true);
                  setRefreshKey((key) => key + 1);
                }}
              />
              <div className="patient-checkin-composer">
                <textarea value={message} onChange={(event) => { setMessage(event.target.value); setSubmitSuccess(false); }} placeholder="Tell us how you are feeling…" rows={4} />
                <div><span>Do not use this for emergencies.</span><button onClick={send} disabled={busy || !message.trim()}>{busy ? 'Saving…' : submitError ? 'Retry' : 'Send update'} <span aria-hidden="true">↑</span></button></div>
                {busy && <small>Safely saving your original update…</small>}
                {submitError && <div className="form-error">Send failed: {submitError}. Your words are still here, so you can retry.</div>}
              </div>
            </div>
          </section>
        )}

        {tab === 'summaries' && (
          <>
            <header className="patient-view-heading"><p>Your record</p><h1>Visit Summaries</h1><span>Only patient-facing instructions from your care team appear here.</span></header>
            {view.visit_summaries.summaries.length === 0 ? <div className="patient-surface patient-empty-state">No patient-facing visit summaries are available yet.</div> : (
              <div className="patient-summary-list">{view.visit_summaries.summaries.map((summary) => (
                <article className="patient-surface patient-summary-card" key={summary.artifact_id}><time>{fmtLongDate(summary.event_time)}</time><div><h2>Care instruction</h2><p>{summary.instruction}</p>{summary.follow_up && <div className="patient-followup-note"><strong>Follow-up</strong><span>{summary.follow_up}</span></div>}</div></article>
              ))}</div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function PatientTaskCard({ task, pending, onTransition }: {
  task: PatientTask;
  pending: boolean;
  onTransition: (task: PatientTask, status: TaskStatus) => void;
}) {
  return (
    <article className={`patient-task patient-task-${task.status}`}>
      <div className="patient-task-state" aria-hidden="true">{task.status === 'completed' ? '✓' : task.status === 'reported_done' ? '…' : '○'}</div>
      <div className="patient-task-copy">
        <span className="patient-task-status">{TASK_STATUS_LABELS[task.status]}</span>
        <strong>{task.title}</strong>
        {task.due_at && <small>Due {fmtLongDate(task.due_at)}</small>}
      </div>
      <div className="patient-task-actions">
        {task.status === 'open' && <button disabled={pending} onClick={() => onTransition(task, 'in_progress')}>{pending ? 'Updating…' : 'Start'}</button>}
        {(task.status === 'open' || task.status === 'in_progress') && <button className="patient-task-primary" disabled={pending} onClick={() => onTransition(task, 'reported_done')}>Report done</button>}
        {task.status === 'reported_done' && <span className="patient-task-waiting">Waiting for clinic review</span>}
        {task.status === 'completed' && <span className="patient-task-complete">Confirmed</span>}
      </div>
    </article>
  );
}
