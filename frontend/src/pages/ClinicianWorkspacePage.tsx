import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import { api } from '../api';
import { artifactLabel, formatDate } from '../clinical';
import type {
  Artifact,
  CopilotEvidence,
  CurrentIdentity,
  DoctorConsultResult,
  Event,
  Patient,
  ProvenanceResult,
} from '../types';
import AuditList from '../components/AuditList';
import ClinicalEventDetail, { type EventContextState } from '../components/ClinicalEventDetail';
import ClinicalNotesView from '../components/ClinicalNotesView';
import ClinicalTimeline from '../components/ClinicalTimeline';
import ClinicalTasksView from '../components/ClinicalTasksView';
import ClinicianSidebar from '../components/ClinicianSidebar';
import CommentThread from '../components/CommentThread';
import CopilotPanel from '../components/CopilotPanel';
import GlancePanel from '../components/GlancePanel';
import NewDoctorConsult from '../components/NewDoctorConsult';
import ProvenancePanel from '../components/ProvenancePanel';
import RevisionPanel from '../components/RevisionPanel';

type PatientTab = 'glance' | 'timeline' | 'notes' | 'tasks';
type ClinicalRoute =
  | { kind: 'dashboard' }
  | { kind: 'patient'; patientId: string; mode: PatientTab | 'new' | 'event'; eventId?: string };

function parseRoute(): ClinicalRoute {
  const parts = window.location.pathname.split('/').filter(Boolean);
  if (parts[0] !== 'clinical' || parts[1] !== 'patients' || !parts[2]) return { kind: 'dashboard' };
  const patientId = parts[2];
  if (parts[3] === 'consults' && parts[4] === 'new') return { kind: 'patient', patientId, mode: 'new' };
  if (parts[3] === 'events' && parts[4]) return { kind: 'patient', patientId, mode: 'event', eventId: parts[4] };
  if (['glance', 'timeline', 'notes', 'tasks'].includes(parts[3])) {
    return { kind: 'patient', patientId, mode: parts[3] as PatientTab };
  }
  return { kind: 'patient', patientId, mode: 'glance' };
}

function routePath(route: ClinicalRoute): string {
  if (route.kind === 'dashboard') return '/clinical';
  if (route.mode === 'new') return `/clinical/patients/${route.patientId}/consults/new`;
  if (route.mode === 'event') return `/clinical/patients/${route.patientId}/events/${route.eventId}`;
  return `/clinical/patients/${route.patientId}/${route.mode}`;
}

function patientTabLabel(tab: PatientTab): string {
  if (tab === 'glance') return 'Clinical Overview';
  return tab[0].toUpperCase() + tab.slice(1);
}

function ContextEmpty({ role }: { role?: string }) {
  const staff = role === 'staff';
  return (
    <div className="context-empty">
      <div className="context-empty-icon" aria-hidden="true">↗</div>
      <p className="eyebrow">{staff ? 'Clinical support context' : 'Review context'}</p>
      <h3>{staff ? 'Open an Event or source' : 'Select supporting detail'}</h3>
      <p>{staff ? 'Review evidence, add Staff Notes, coordinate Tasks, and collaborate without changing clinician-authored assessment.' : 'Open an Overview source or Event artifact without losing your place in the patient record.'}</p>
      <div className="context-capabilities" aria-label="Available context tools">
        <span>Sources</span>{staff && <span>Staff Notes</span>}<span>Comments</span><span>History</span>
      </div>
    </div>
  );
}

function clampPanelWidth(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function PanelResizer({
  label,
  value,
  min,
  max,
  direction,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  direction: 1 | -1;
  onChange: (value: number) => void;
}) {
  function beginResize(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = value;
    document.body.classList.add('resizing-clinical-panel');
    const move = (moveEvent: PointerEvent) => {
      onChange(clampPanelWidth(startWidth + ((moveEvent.clientX - startX) * direction), min, max));
    };
    const stop = () => {
      document.body.classList.remove('resizing-clinical-panel');
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop, { once: true });
  }

  function resizeWithKeyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const positionDelta = event.key === 'ArrowRight' ? 16 : -16;
    onChange(clampPanelWidth(value + (positionDelta * direction), min, max));
  }

  return (
    <div
      className="panel-resizer"
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      tabIndex={0}
      onPointerDown={beginResize}
      onKeyDown={resizeWithKeyboard}
    >
      <span aria-hidden="true" />
    </div>
  );
}

function PatientWorkspace({
  patientId,
  route,
  onNavigate,
  identity,
  contextWidth,
  onContextWidthChange,
}: {
  patientId: string;
  route: Extract<ClinicalRoute, { kind: 'patient' }>;
  onNavigate: (route: ClinicalRoute) => void;
  identity: CurrentIdentity;
  contextWidth: number;
  onContextWidthChange: (width: number) => void;
}) {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [eventRefreshKey, setEventRefreshKey] = useState(0);
  const [provenance, setProvenance] = useState<ProvenanceResult | null>(null);
  const [copilotEvidence, setCopilotEvidence] = useState<CopilotEvidence | null>(null);
  const [contextTab, setContextTab] = useState<'copilot' | 'source' | 'comments' | 'history'>(identity.role === 'clinician' ? 'copilot' : 'source');
  const [eventContext, setEventContext] = useState<EventContextState>({ artifacts: [], selectedArtifact: null });
  const [initialArtifactId, setInitialArtifactId] = useState<string | null>(null);
  const [completion, setCompletion] = useState<DoctorConsultResult | null>(null);
  // Glance "Open Task" target: lands on the SPECIFIC task in the Tasks view.
  const [taskFocusId, setTaskFocusId] = useState<string | null>(null);

  const load = useCallback((signal?: AbortSignal) => {
    return Promise.all([
      api.getPatient(patientId, signal),
      api.getEvents(patientId, signal),
    ]).then(([nextPatient, nextEvents]) => {
      setPatient(nextPatient);
      setEvents(nextEvents);
      setError(null);
    });
  }, [patientId]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    load(controller.signal)
      .catch((loadError: any) => {
        if (active && loadError?.name !== 'AbortError') setError(String(loadError.message ?? loadError));
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
      controller.abort();
    };
  }, [load, refreshKey]);

  useEffect(() => {
    // patientId is a remount boundary, and route transitions clear context that
    // does not belong to the newly opened mode.
    if (route.mode !== 'event') setEventContext({ artifacts: [], selectedArtifact: null });
    if (route.mode === 'glance' || route.mode === 'timeline' || route.mode === 'notes' || route.mode === 'tasks' || route.mode === 'new') {
      setInitialArtifactId(null);
    }
  }, [route.mode]);

  useEffect(() => {
    // patient/role/session identity is a strict state boundary. The outer key
    // unmounts on logout; this also handles an in-place identity transition.
    setProvenance(null);
    setCopilotEvidence(null);
    setEventContext({ artifacts: [], selectedArtifact: null });
    setInitialArtifactId(null);
    setTaskFocusId(null);
    setCompletion(null);
    setContextTab(identity.role === 'clinician' ? 'copilot' : 'source');
  }, [patientId, identity.role, identity.user_id]);

  const selectedEvent = useMemo(
    () => events.find((event) => event.event_id === route.eventId) ?? null,
    [events, route.eventId],
  );
  const latestEvent = events.length ? [...events].sort((a, b) => b.started_at.localeCompare(a.started_at))[0] : null;

  const updateContextState = useCallback((state: EventContextState) => {
    setEventContext(state);
  }, []);

  function openTab(tab: PatientTab) {
    setCompletion(null);
    setProvenance(null);
    setCopilotEvidence(null);
    setContextTab(identity.role === 'clinician' ? 'copilot' : 'source');
    onNavigate({ kind: 'patient', patientId, mode: tab });
  }

  function openEvent(event: Event, artifactId: string | null = null) {
    setInitialArtifactId(artifactId);
    setContextTab('comments');
    onNavigate({ kind: 'patient', patientId, mode: 'event', eventId: event.event_id });
  }

  function handleOpenTask(taskId: string) {
    setTaskFocusId(taskId);
    setProvenance(null);
    setCopilotEvidence(null);
    setContextTab(identity.role === 'clinician' ? 'copilot' : 'source');
    onNavigate({ kind: 'patient', patientId, mode: 'tasks' });
  }

  function handleViewSource(next: ProvenanceResult) {
    setProvenance(next);
    setCopilotEvidence(null);
    setContextTab('source');
  }

  function handleOpenCopilotEvidence(next: CopilotEvidence) {
    setCopilotEvidence(next);
    setProvenance(null);
    setInitialArtifactId(next.artifact_id);
    setContextTab('source');
    onNavigate({ kind: 'patient', patientId, mode: 'event', eventId: next.event_id });
  }

  function changed() {
    setEventRefreshKey((value) => value + 1);
    setRefreshKey((value) => value + 1);
  }

  function completed(result: DoctorConsultResult) {
    setCompletion(result);
    setInitialArtifactId(result.ai_summary_artifact_id);
    setEvents((current) => [...current.filter((event) => event.event_id !== result.event.event_id), result.event]
      .sort((a, b) => a.started_at.localeCompare(b.started_at)));
    setRefreshKey((value) => value + 1);
    setContextTab('comments');
    onNavigate({ kind: 'patient', patientId, mode: 'event', eventId: result.event.event_id });
  }

  const workspaceStyle = { '--context-width': `${contextWidth}px` } as CSSProperties;

  if (loading) {
    return <div className="workspace-area" style={workspaceStyle}><main className="workspace-main"><div className="loading-card">Loading clinical workspace…</div></main><PanelResizer label="Resize clinical context" value={contextWidth} min={280} max={520} direction={-1} onChange={onContextWidthChange} /><aside className="context-panel"><ContextEmpty role={identity.role ?? undefined} /></aside></div>;
  }
  if (error || !patient) {
    return <div className="workspace-area" style={workspaceStyle}><main className="workspace-main"><div className="form-error">Failed to load patient workspace: {error}</div></main><PanelResizer label="Resize clinical context" value={contextWidth} min={280} max={520} direction={-1} onChange={onContextWidthChange} /><aside className="context-panel"><ContextEmpty role={identity.role ?? undefined} /></aside></div>;
  }

  const selectedArtifact = eventContext.selectedArtifact;
  const hasVersions = selectedArtifact && ['clinician_note', 'staff_note'].includes(selectedArtifact.artifact_type);
  const contextMode = contextTab !== 'copilot';

  function openContextMode() {
    if (provenance || copilotEvidence) setContextTab('source');
    else setContextTab(selectedEvent ? 'comments' : 'source');
  }

  return (
    <div className="workspace-area" style={workspaceStyle}>
      <main className="workspace-main">
        <header className="workspace-patient-header">
          <div className="patient-identity">
            <div>
              <p className="eyebrow">Patient record</p>
              <h1>{patient.name}</h1>
              <span>{patient.patient_id}{latestEvent ? ` · Latest event ${formatDate(latestEvent.started_at)}` : ''}</span>
            </div>
          </div>
          <div className="patient-primary-actions">
            {identity.role === 'staff' && <div className="workspace-role-chip"><strong>Clinical support</strong><span>Staff Notes · Tasks · collaboration</span></div>}
            {identity.role === 'clinician' && <button
              className="primary-button"
              onClick={() => onNavigate({ kind: 'patient', patientId, mode: 'new' })}
            >
              Record consultation
            </button>}
          </div>
        </header>

        {route.mode !== 'new' && (
          <nav className="workspace-tabs" aria-label="Patient workspace views">
            {(['glance', 'timeline'] as PatientTab[]).map((tab) => (
              <button
                key={tab}
                className={route.mode === tab ? 'active' : ''}
                aria-selected={route.mode === tab}
                onClick={() => openTab(tab)}
              >
                {patientTabLabel(tab)}
              </button>
            ))}
            {route.mode === 'event' && <button className="active" aria-selected="true">Event Detail</button>}
            {(['notes', 'tasks'] as PatientTab[]).map((tab) => (
              <button key={tab} className={route.mode === tab ? 'active' : ''} aria-selected={route.mode === tab} onClick={() => openTab(tab)}>{patientTabLabel(tab)}</button>
            ))}
          </nav>
        )}

        {completion && route.mode === 'event' && (
          <div className={`completion-banner ${completion.degraded ? 'fallback' : 'success'}`}>
            <strong>{completion.degraded ? 'Completed with deterministic fallback' : 'Doctor Consult completed'}</strong>
            <span>Raw transcript saved · AI summary saved · {completion.highlight_ids.length} exact-source highlight{completion.highlight_ids.length === 1 ? '' : 's'}</span>
            {completion.fallback_reason && <small>Fallback reason: {completion.fallback_reason}</small>}
          </div>
        )}

        {route.mode === 'glance' && (
          <GlancePanel key={`glance:${refreshKey}`} patientId={patientId} onViewSource={handleViewSource} onOpenTasks={handleOpenTask} reviewRole={identity.role ?? undefined} />
        )}
        {route.mode === 'timeline' && <ClinicalTimeline events={events} onOpenEvent={openEvent} />}
        {route.mode === 'notes' && (
          <ClinicalNotesView
            events={events}
            refreshKey={refreshKey}
            onOpenArtifact={(event, artifactId) => openEvent(event, artifactId)}
            onOpenEvent={(event) => openEvent(event)}
          />
        )}
        {route.mode === 'tasks' && (
          <ClinicalTasksView
            patientId={patientId}
            events={events}
            identity={identity}
            refreshKey={refreshKey}
            focusTaskId={taskFocusId}
            onFocusHandled={() => setTaskFocusId(null)}
            onChanged={changed}
            onOpenEvent={openEvent}
          />
        )}
        {route.mode === 'new' && identity.role === 'clinician' && (
          <NewDoctorConsult
            patient={patient}
            onCancel={() => openTab('timeline')}
            onCompleted={completed}
          />
        )}
        {route.mode === 'new' && identity.role !== 'clinician' && (
          <div className="empty-state"><h3>Clinician access required</h3><p>Staff share the clinic shell and Care Tasks workflow, but cannot start a Doctor Consult.</p><button onClick={() => openTab('tasks')}>Open Care Tasks</button></div>
        )}
        {route.mode === 'event' && selectedEvent && (
          <ClinicalEventDetail
            key={selectedEvent.event_id}
            event={selectedEvent}
            initialArtifactId={initialArtifactId}
            refreshKey={eventRefreshKey}
            onBack={() => openTab('timeline')}
            onChanged={changed}
            onContextState={updateContextState}
            role={identity.role ?? ''}
          />
        )}
        {route.mode === 'event' && !selectedEvent && (
          <div className="empty-state"><h3>Event not found</h3><p>It may no longer be available in this patient record.</p><button onClick={() => openTab('timeline')}>Back to Timeline</button></div>
        )}
      </main>

      <PanelResizer label="Resize clinical context" value={contextWidth} min={280} max={520} direction={-1} onChange={onContextWidthChange} />
      <aside className="context-panel" aria-label="Clinical context">
        <div className="context-panel-head context-rail-head">
          <div>
            <p className="eyebrow">{contextTab === 'copilot' ? 'Evidence-bound assistant' : 'Review context'}</p>
            <h2>{contextTab === 'copilot' ? 'Clinical Copilot' : selectedArtifact ? artifactLabel(selectedArtifact) : 'Patient context'}</h2>
            <span className="context-patient-scope">{patient.name} only</span>
          </div>
        </div>
        {identity.role === 'clinician' && (
          <nav className="context-mode-tabs" aria-label="Clinical side panel modes">
            <button className={!contextMode ? 'active' : ''} onClick={() => setContextTab('copilot')}>Copilot</button>
            <button className={contextMode ? 'active' : ''} onClick={openContextMode}>Context</button>
          </nav>
        )}
        {contextMode && (
          <nav className="context-tabs" aria-label="Context tools">
            <button className={contextTab === 'source' ? 'active' : ''} onClick={() => setContextTab('source')}>Source</button>
            {selectedEvent && <button className={contextTab === 'comments' ? 'active' : ''} onClick={() => setContextTab('comments')}>Comments</button>}
            {selectedEvent && <button className={contextTab === 'history' ? 'active' : ''} onClick={() => setContextTab('history')}>History</button>}
          </nav>
        )}
        <div className="context-scroll">
          {contextTab === 'copilot' && identity.role === 'clinician' && (
            <CopilotPanel patientId={patientId} roleKey={`${identity.user_id}:${identity.role}`} onOpenEvidence={handleOpenCopilotEvidence} onConfirmed={changed} />
          )}
          {contextTab === 'source' && provenance && (
            <ProvenancePanel
              provenance={provenance}
              onClose={() => { setProvenance(null); setContextTab(selectedEvent ? 'comments' : identity.role === 'clinician' ? 'copilot' : 'source'); }}
              onFocusEvent={(eventId) => onNavigate({ kind: 'patient', patientId, mode: 'event', eventId })}
            />
          )}
          {contextTab === 'source' && copilotEvidence && (
            <div className="copilot-source-card">
              <p className="eyebrow">Verified Copilot evidence</p>
              <h3>{copilotEvidence.artifact_type.replace(/_/g, ' ')}</h3>
              <p>{copilotEvidence.event_type.replace(/_/g, ' ')} · Event {new Date(copilotEvidence.event_time).toLocaleString()}</p>
              <p>Recorded {new Date(copilotEvidence.record_time).toLocaleString()}</p>
              <small>{copilotEvidence.author_role} · exact {copilotEvidence.span.kind} span</small>
              <blockquote>{copilotEvidence.quote}</blockquote>
              {copilotEvidence.review_required && <div className="verification-callout">Review flag on this source.</div>}
            </div>
          )}
          {contextTab === 'source' && !provenance && !copilotEvidence && <ContextEmpty role={identity.role ?? undefined} />}
          {contextTab === 'comments' && selectedEvent && (
            <CommentThread key={`${selectedEvent.event_id}:${eventRefreshKey}`} eventId={selectedEvent.event_id} artifacts={eventContext.artifacts} canWrite onChanged={changed} />
          )}
          {contextTab === 'history' && selectedEvent && (
            <>
              {hasVersions && selectedArtifact && <RevisionPanel key={`${selectedArtifact.artifact_id}:${selectedArtifact.version}`} artifact={selectedArtifact} onReverted={changed} canRevert={selectedArtifact.artifact_type === `${identity.role}_note`} defaultOpen />}
              <AuditList key={`${selectedEvent.event_id}:${eventRefreshKey}`} eventId={selectedEvent.event_id} defaultOpen />
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

export default function ClinicianWorkspacePage({ roleKey, onLogout }: { roleKey: string; onLogout?: () => void }) {
  const [identity, setIdentity] = useState<CurrentIdentity | null>(null);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [route, setRoute] = useState<ClinicalRoute>(() => parseRoute());
  const [error, setError] = useState<string | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(216);
  const [contextWidth, setContextWidth] = useState(320);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    Promise.all([
      api.getCurrentIdentity(controller.signal),
      api.getClinicPatients(controller.signal),
    ])
      .then(([nextIdentity, nextPatients]) => {
        if (!active) return;
        setIdentity(nextIdentity);
        setPatients(nextPatients);
        setError(null);
        const current = parseRoute();
        if (current.kind === 'patient' && !nextPatients.some((patient) => patient.patient_id === current.patientId)) {
          window.history.replaceState({}, '', '/clinical');
          setRoute({ kind: 'dashboard' });
        }
      })
      .catch((loadError: any) => {
        if (active && loadError?.name !== 'AbortError') setError(String(loadError.message ?? loadError));
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [roleKey]);

  useEffect(() => {
    const onPopState = () => setRoute(parseRoute());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  function navigate(next: ClinicalRoute) {
    window.history.pushState({}, '', routePath(next));
    setRoute(next);
  }

  if (error) return <div className="shell-load-error">Unable to load clinician workspace: {error}</div>;
  if (!identity) return <div className="shell-loading">Loading clinician workspace…</div>;

  const selectedPatientId = route.kind === 'patient' ? route.patientId : null;
  const shellStyle = { '--sidebar-width': `${sidebarWidth}px` } as CSSProperties;
  const workspaceStyle = { '--context-width': `${contextWidth}px` } as CSSProperties;
  return (
    <div className="clinician-shell" style={shellStyle}>
      <ClinicianSidebar
        identity={identity}
        patients={patients}
        selectedPatientId={selectedPatientId}
        onDashboard={() => navigate({ kind: 'dashboard' })}
        onSelectPatient={(patientId) => navigate({ kind: 'patient', patientId, mode: 'glance' })}
        onLogout={onLogout}
      />
      <PanelResizer label="Resize patient navigation" value={sidebarWidth} min={196} max={310} direction={1} onChange={setSidebarWidth} />
      {route.kind === 'dashboard' ? (
        <div className="workspace-area dashboard-area" style={workspaceStyle}>
          <main className="workspace-main clinic-dashboard">
            <p className="eyebrow">{identity.clinic_name}</p>
            <h1>Clinic dashboard</h1>
            <p className="dashboard-lead">Choose an authorized clinic patient to open their longitudinal record.</p>
            <div className="dashboard-patient-grid">
              {patients.map((patient) => (
                <button key={patient.patient_id} onClick={() => navigate({ kind: 'patient', patientId: patient.patient_id, mode: 'glance' })}>
                  <span className="patient-list-avatar">{patient.name.slice(0, 1)}</span>
                  <span><strong>{patient.name}</strong><small>{patient.patient_id}</small></span>
                  <span aria-hidden="true">→</span>
                </button>
              ))}
            </div>
          </main>
          <PanelResizer label="Resize clinical context" value={contextWidth} min={280} max={520} direction={-1} onChange={setContextWidth} />
          <aside className="context-panel"><ContextEmpty role={identity.role ?? undefined} /></aside>
        </div>
      ) : (
        <PatientWorkspace
          key={`${roleKey}:${route.patientId}`}
          patientId={route.patientId}
          route={route}
          onNavigate={navigate}
          identity={identity}
          contextWidth={contextWidth}
          onContextWidthChange={setContextWidth}
        />
      )}
    </div>
  );
}
