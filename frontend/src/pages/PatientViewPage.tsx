import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { PatientTask, PatientView, TaskStatus } from '../types';
import PatientCheckIn from '../components/PatientCheckIn';

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

type PatientTab = 'today' | 'care' | 'checkin' | 'summaries';

const PATIENT_TAB_PATHS: Record<PatientTab, string> = {
  today: '/patient/today',
  care: '/patient/care-plan',
  checkin: '/patient/check-in',
  summaries: '/patient/visit-summaries',
};

function patientTabFromPath(path = window.location.pathname): PatientTab {
  if (path.startsWith('/patient/care-plan')) return 'care';
  if (path.startsWith('/patient/check-in')) return 'checkin';
  if (path.startsWith('/patient/visit-summaries')) return 'summaries';
  return 'today';
}

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
  const [tab, setTab] = useState<PatientTab>(() => patientTabFromPath());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);

  const load = useCallback(() => {
    const controller = new AbortController();
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const v = await api.getPatientView(patientId, controller.signal);
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
      controller.abort();
    };
  }, [patientId]);

  useEffect(() => {
    return load();
  }, [load, roleKey, refreshKey]);

  useEffect(() => {
    // patient/session identity is a hard remount boundary. Clear every draft,
    // error and pending response even if a host reuses this component.
    setTaskError(null);
    setPendingTaskId(null);
    setTab(patientTabFromPath());
  }, [patientId, roleKey]);

  useEffect(() => {
    if (window.location.pathname === '/patient') {
      window.history.replaceState({}, '', PATIENT_TAB_PATHS.today);
    }
    const onPopState = () => setTab(patientTabFromPath());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  function navigateTab(next: PatientTab) {
    const nextPath = PATIENT_TAB_PATHS[next];
    if (window.location.pathname !== nextPath) window.history.pushState({}, '', nextPath);
    setTab(next);
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
            <button key={key} className={tab === key ? 'active' : ''} aria-current={tab === key ? 'page' : undefined} onClick={() => navigateTab(key)}>
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
                <button onClick={() => navigateTab('checkin')}>Start a Check-in <span aria-hidden="true">→</span></button>
              </section>
            </div>

            <section className="patient-surface patient-instructions-preview">
              <div className="patient-surface-head"><div><p>Patient-facing information</p><h2>Instructions from your care team</h2></div><button onClick={() => navigateTab('summaries')}>View all →</button></div>
              {view.visit_summaries.summaries.length === 0 ? <div className="patient-empty-compact">No visit summaries are available yet.</div> : (
                <div className="patient-instruction-list">
                  {view.visit_summaries.summaries.slice(0, 2).map((summary) => (
                    <button key={summary.artifact_id} onClick={() => navigateTab('summaries')}><span>{fmtLongDate(summary.event_time)}</span><div><strong>Care instruction</strong><p>{summary.instruction}</p></div><span aria-hidden="true">›</span></button>
                  ))}
                </div>
              )}
            </section>
          </>
        )}

        {tab === 'care' && (
          <>
            <header className="patient-view-heading"><p>Your care</p><h1>Care Plan</h1><span>Start your assigned actions, report when you are done, and wait for the clinic to confirm completion.</span></header>
            <div className="patient-task-authority-note"><strong>What “Report done” means</strong><span>Your report tells the clinic you finished the action. It does not mark the task clinically complete until the clinic confirms it.</span></div>
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
          <PatientCheckIn
            patientId={patientId}
            roleKey={roleKey}
            displayName={view.display_name}
            onBack={() => navigateTab('today')}
          />
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
