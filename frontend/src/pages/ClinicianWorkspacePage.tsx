import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { artifactLabel, formatDate } from '../clinical';
import { clinicalQueryKeys, usePatientDetails, usePatientTimeline } from '../queries/clinicalQueries';
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
import CoverageReview from '../components/CoverageReview';
import GlancePanel from '../components/GlancePanel';
import NewDoctorConsult from '../components/NewDoctorConsult';
import VoiceCapture from '../components/VoiceCapture';
import ProvenancePanel from '../components/ProvenancePanel';
import RevisionPanel from '../components/RevisionPanel';

type PatientTab = 'glance' | 'coverage' | 'timeline' | 'notes' | 'tasks';
type ClinicalRoute =
  | { kind: 'dashboard' }
  | { kind: 'patient'; patientId: string; mode: PatientTab | 'new' | 'event'; eventId?: string };

const SIDEBAR_COLLAPSED_KEY = 'nightingale:clinical-sidebar-collapsed';

function initialSidebarCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
  } catch {
    return false;
  }
}

function parseRoute(): ClinicalRoute {
  const parts = window.location.pathname.split('/').filter(Boolean);
  if (parts[0] !== 'clinical' || parts[1] !== 'patients' || !parts[2]) return { kind: 'dashboard' };
  const patientId = parts[2];
  if (parts[3] === 'consults' && parts[4] === 'new') return { kind: 'patient', patientId, mode: 'new' };
  if (parts[3] === 'events' && parts[4]) return { kind: 'patient', patientId, mode: 'event', eventId: parts[4] };
  if (['glance', 'coverage', 'timeline', 'notes', 'tasks'].includes(parts[3])) {
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
  if (tab === 'glance') return 'Glance';
  if (tab === 'coverage') return 'Coverage';
  return tab[0].toUpperCase() + tab.slice(1);
}

function ContextEmpty({ role }: { role?: string }) {
  const staff = role === 'staff';
  return (
    <div className="context-empty">
      <div className="context-empty-icon" aria-hidden="true">↗</div>
      <p className="eyebrow">{staff ? 'Clinical support context' : 'Review context'}</p>
      <h3>{staff ? 'Open an Event or source' : 'Select supporting detail'}</h3>
      <p>{staff ? 'Review evidence, add Staff Notes, coordinate Tasks, and collaborate without changing clinician-authored assessment.' : 'Open a Glance source or Event artifact without losing your place in the patient record.'}</p>
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
  const queryClient = useQueryClient();
  const queryScope = `${identity.clinic_id}:${identity.user_id}:${identity.role}`;
  const patientQuery = usePatientDetails(patientId, queryScope);
  const timelineQuery = usePatientTimeline(patientId, queryScope);
  const patient = patientQuery.data ?? null;
  const events = timelineQuery.data ?? [];
  const loading = patientQuery.isLoading || timelineQuery.isLoading;
  const isError = patientQuery.isError || timelineQuery.isError;
  const queryError = patientQuery.error ?? timelineQuery.error;
  const serverStateRevision = timelineQuery.dataUpdatedAt;
  const [eventRefreshKey, setEventRefreshKey] = useState(0);
  const [provenance, setProvenance] = useState<ProvenanceResult | null>(null);
  const [copilotEvidence, setCopilotEvidence] = useState<CopilotEvidence | null>(null);
  const [contextTab, setContextTab] = useState<'copilot' | 'source' | 'comments' | 'history'>(identity.role === 'clinician' ? 'copilot' : 'source');
  const [eventContext, setEventContext] = useState<EventContextState>({ artifacts: [], selectedArtifact: null });
  const [initialArtifactId, setInitialArtifactId] = useState<string | null>(null);
  const [completion, setCompletion] = useState<DoctorConsultResult | null>(null);
  const [contextDrawerOpen, setContextDrawerOpen] = useState(false);
  // Glance "Open Task" target: lands on the SPECIFIC task in the Tasks view.
  const [taskFocusId, setTaskFocusId] = useState<string | null>(null);

  useEffect(() => {
    // patientId is a remount boundary, and route transitions clear context that
    // does not belong to the newly opened mode.
    if (route.mode !== 'event') setEventContext({ artifacts: [], selectedArtifact: null });
    if (route.mode === 'glance' || route.mode === 'coverage' || route.mode === 'timeline' || route.mode === 'notes' || route.mode === 'tasks' || route.mode === 'new') {
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
    setContextDrawerOpen(false);
    setContextTab(identity.role === 'clinician' ? 'copilot' : 'source');
  }, [patientId, identity.role, identity.user_id]);

  const selectedEvent = useMemo(
    () => events.find((event) => event.event_id === route.eventId) ?? null,
    [events, route.eventId],
  );
  const latestEvent = events.length ? [...events].sort((a, b) => b.started_at.localeCompare(a.started_at))[0] : null;
  const encounterOptions = useMemo(() => {
    const grouped = new Map<string, Event[]>();
    events.forEach((event) => {
      if (!event.encounter_id) return;
      grouped.set(event.encounter_id, [...(grouped.get(event.encounter_id) ?? []), event]);
    });
    return [...grouped.entries()]
      .sort(([, left], [, right]) => right[0].started_at.localeCompare(left[0].started_at))
      .map(([encounterId, groupedEvents]) => ({
        encounterId,
        label: `Clinic Visit · ${formatDate(groupedEvents[0].started_at)} · ${groupedEvents.map((event) => event.event_type.replace(/_/g, ' ')).join(' + ')}`,
      }));
  }, [events]);

  const updateContextState = useCallback((state: EventContextState) => {
    setEventContext(state);
  }, []);

  function openTab(tab: PatientTab) {
    setCompletion(null);
    setProvenance(null);
    setCopilotEvidence(null);
    setContextTab(identity.role === 'clinician' ? 'copilot' : 'source');
    setContextDrawerOpen(false);
    onNavigate({ kind: 'patient', patientId, mode: tab });
  }

  function openEvent(event: Event, artifactId: string | null = null) {
    setInitialArtifactId(artifactId);
    setContextTab('comments');
    setContextDrawerOpen(false);
    onNavigate({ kind: 'patient', patientId, mode: 'event', eventId: event.event_id });
  }

  function handleOpenTask(taskId: string) {
    setTaskFocusId(taskId);
    setProvenance(null);
    setCopilotEvidence(null);
    setContextTab(identity.role === 'clinician' ? 'copilot' : 'source');
    setContextDrawerOpen(false);
    onNavigate({ kind: 'patient', patientId, mode: 'tasks' });
  }

  function handleViewSource(next: ProvenanceResult) {
    setProvenance(next);
    setCopilotEvidence(null);
    setContextTab('source');
    setContextDrawerOpen(true);
  }

  function handleOpenCopilotEvidence(next: CopilotEvidence) {
    setCopilotEvidence(next);
    setProvenance(null);
    setInitialArtifactId(next.artifact_id);
    setContextTab('source');
    setContextDrawerOpen(true);
    onNavigate({ kind: 'patient', patientId, mode: 'event', eventId: next.event_id });
  }

  function handleOpenComments() {
    setProvenance(null);
    setCopilotEvidence(null);
    setContextTab('comments');
    setContextDrawerOpen(true);
  }

  function changed() {
    setEventRefreshKey((value) => value + 1);
    void timelineQuery.refetch();
  }

  function completed(result: DoctorConsultResult) {
    setCompletion(result);
    setInitialArtifactId(result.ai_summary_artifact_id);
    queryClient.setQueryData<Event[]>(
      clinicalQueryKeys.patientTimeline(queryScope, patientId),
      (current = []) => [...current.filter((event) => event.event_id !== result.event.event_id), result.event]
        .sort((a, b) => a.started_at.localeCompare(b.started_at)),
    );
    setContextTab('comments');
    setContextDrawerOpen(false);
    onNavigate({ kind: 'patient', patientId, mode: 'event', eventId: result.event.event_id });
  }

  async function voiceCompleted(capture: import('../types').VoiceCaptureRecord) {
    if (!capture.event_id) return;
    setCompletion(null);
    await timelineQuery.refetch();
    setContextTab('comments');
    setContextDrawerOpen(false);
    onNavigate({ kind: 'patient', patientId, mode: 'event', eventId: capture.event_id });
  }

  const workspaceStyle = { '--context-width': `${contextWidth}px` } as CSSProperties;

  if (loading) {
    return <div className="workspace-area" style={workspaceStyle}><main className="workspace-main"><div className="loading-card">Loading clinical workspace…</div></main><PanelResizer label="Resize clinical context" value={contextWidth} min={280} max={520} direction={-1} onChange={onContextWidthChange} /><aside className="context-panel"><ContextEmpty role={identity.role ?? undefined} /></aside></div>;
  }
  if (isError || !patient) {
    const message = queryError instanceof Error ? queryError.message : String(queryError ?? 'Patient not found');
    return <div className="workspace-area" style={workspaceStyle}><main className="workspace-main"><div className="form-error">Failed to load patient workspace: {message}</div></main><PanelResizer label="Resize clinical context" value={contextWidth} min={280} max={520} direction={-1} onChange={onContextWidthChange} /><aside className="context-panel"><ContextEmpty role={identity.role ?? undefined} /></aside></div>;
  }

  const selectedArtifact = eventContext.selectedArtifact;
  const hasVersions = selectedArtifact && ['clinician_note', 'staff_note'].includes(selectedArtifact.artifact_type);
  let contextHeading = selectedArtifact ? artifactLabel(selectedArtifact) : 'Review context';
  if (contextTab === 'copilot') contextHeading = 'Clinical Copilot';
  if (contextTab === 'comments' && !selectedArtifact) contextHeading = 'Event discussion';
  if (contextTab === 'history') contextHeading = 'Review history';

  function openContextRail() {
    if (provenance || copilotEvidence) setContextTab('source');
    else setContextTab(selectedEvent ? 'comments' : 'source');
    setContextDrawerOpen(true);
  }

  return (
    <div className={`workspace-area ${contextDrawerOpen ? 'context-drawer-open' : ''}`} style={workspaceStyle}>
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
            <button
              className="secondary-button context-rail-toggle"
              aria-expanded={contextDrawerOpen}
              aria-controls="clinical-context-rail"
              onClick={openContextRail}
            >
              Context
            </button>
            {identity.role === 'staff' && <div className="workspace-role-chip"><strong>Nurse workspace</strong><span>Staff Notes · Tasks · collaboration</span></div>}
            {identity.role === 'clinician' && <button
              className="primary-button"
              onClick={() => onNavigate({ kind: 'patient', patientId, mode: 'new' })}
            >
              Record doctor consultation
            </button>}
            {identity.role === 'staff' && <button
              className="primary-button"
              onClick={() => onNavigate({ kind: 'patient', patientId, mode: 'new' })}
            >
              Record nurse consultation
            </button>}
          </div>
        </header>

        {route.mode !== 'new' && (
          <nav className={`workspace-tabs ${route.mode === 'event' ? 'with-event-detail' : ''}`} aria-label="Patient workspace views">
            {(['glance', 'coverage', 'timeline'] as PatientTab[]).map((tab) => (
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
            <strong>{completion.degraded ? 'Completed with deterministic fallback' : `${completion.event.event_type === 'nurse_consult' ? 'Nurse' : 'Doctor'} Consult completed`}</strong>
            <span>Raw transcript saved · AI summary saved · {completion.highlight_ids.length} exact-source highlight{completion.highlight_ids.length === 1 ? '' : 's'}</span>
            {completion.fallback_reason && <small>Fallback reason: {completion.fallback_reason}</small>}
          </div>
        )}

        {route.mode === 'glance' && (
          <GlancePanel key={`glance:${serverStateRevision}`} patientId={patientId} onViewSource={handleViewSource} onOpenTasks={handleOpenTask} reviewRole={identity.role ?? undefined} />
        )}
        {route.mode === 'coverage' && (
          <CoverageReview patientId={patientId} identity={identity} onViewSource={handleViewSource} />
        )}
        {route.mode === 'timeline' && <ClinicalTimeline events={events} onOpenEvent={openEvent} />}
        {route.mode === 'notes' && (
          <ClinicalNotesView
            events={events}
            refreshKey={serverStateRevision}
            onOpenArtifact={(event, artifactId) => openEvent(event, artifactId)}
            onOpenEvent={(event) => openEvent(event)}
          />
        )}
        {route.mode === 'tasks' && (
          <ClinicalTasksView
            patientId={patientId}
            events={events}
            identity={identity}
            refreshKey={serverStateRevision}
            focusTaskId={taskFocusId}
            onFocusHandled={() => setTaskFocusId(null)}
            onChanged={changed}
            onOpenEvent={openEvent}
            onViewSource={handleViewSource}
          />
        )}
        {route.mode === 'new' && (identity.role === 'clinician' || identity.role === 'staff') && (
          <div className="consult-input-stack">
            <VoiceCapture
              boundaryKey={`${identity.user_id}:${identity.role}:${patientId}:voice`}
              patientId={patientId}
              captureMode={identity.role === 'clinician' ? 'doctor_consult' : 'nurse_consult'}
              onProcessed={(capture) => { void voiceCompleted(capture); }}
            />
            <div className="consult-input-divider"><span>or use a reviewed text transcript</span></div>
            {identity.role === 'staff' ? (
              <NewDoctorConsult
                patient={patient}
                consultKind="nurse"
                encounterOptions={encounterOptions}
                onCancel={() => openTab('timeline')}
                onCompleted={completed}
              />
            ) : (
              <NewDoctorConsult
                patient={patient}
                onCancel={() => openTab('timeline')}
                onCompleted={completed}
              />
            )}
          </div>
        )}
        {route.mode === 'event' && selectedEvent && (
          <ClinicalEventDetail
            key={selectedEvent.event_id}
            event={selectedEvent}
            initialArtifactId={initialArtifactId}
            refreshKey={eventRefreshKey}
            onBack={() => openTab('timeline')}
            onChanged={changed}
            onOpenComments={handleOpenComments}
            onContextState={updateContextState}
            role={identity.role ?? ''}
          />
        )}
        {route.mode === 'event' && !selectedEvent && (
          <div className="empty-state"><h3>Event not found</h3><p>It may no longer be available in this patient record.</p><button onClick={() => openTab('timeline')}>Back to Timeline</button></div>
        )}
      </main>

      <button className="context-drawer-backdrop" aria-label="Close clinical context" onClick={() => setContextDrawerOpen(false)} />
      <PanelResizer label="Resize clinical context" value={contextWidth} min={280} max={520} direction={-1} onChange={onContextWidthChange} />
      <aside id="clinical-context-rail" className="context-panel" aria-label="Clinical context">
        <div className="context-panel-head context-rail-head">
          <div>
            <h2>{contextHeading}</h2>
            <p className="context-panel-meta">
              <span>{contextTab === 'copilot' ? 'Evidence-bound assistant' : 'Review context'}</span>
              <span aria-hidden="true">·</span>
              <span>{patient.name}</span>
            </p>
          </div>
          <button className="context-rail-close" aria-label="Close clinical context" onClick={() => setContextDrawerOpen(false)}>✕</button>
        </div>
        <nav className="context-tabs context-tabs-unified" aria-label="Clinical context views">
          {identity.role === 'clinician' && <button className={contextTab === 'copilot' ? 'active' : ''} onClick={() => setContextTab('copilot')}>Copilot</button>}
          <button className={contextTab === 'source' ? 'active' : ''} onClick={() => setContextTab('source')}>Source</button>
          {selectedEvent && <button className={contextTab === 'comments' ? 'active' : ''} onClick={() => setContextTab('comments')}>Comments</button>}
          {selectedEvent && <button className={contextTab === 'history' ? 'active' : ''} onClick={() => setContextTab('history')}>History</button>}
        </nav>
        <div className={`context-scroll ${contextTab === 'comments' ? 'comments-layout' : ''}`}>
          {contextTab === 'copilot' && identity.role === 'clinician' && (
            <CopilotPanel patientId={patientId} roleKey={`${identity.user_id}:${identity.role}`} onOpenEvidence={handleOpenCopilotEvidence} onConfirmed={changed} />
          )}
          {contextTab === 'source' && provenance && (
            <ProvenancePanel
              provenance={provenance}
              onClose={() => { setProvenance(null); setContextDrawerOpen(false); setContextTab(selectedEvent ? 'comments' : identity.role === 'clinician' ? 'copilot' : 'source'); }}
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
            <CommentThread key={`${selectedEvent.event_id}:${eventRefreshKey}`} eventId={selectedEvent.event_id} artifacts={eventContext.artifacts} canWrite onChanged={changed} variant="context" />
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(initialSidebarCollapsed);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [contextWidth, setContextWidth] = useState(380);
  const mobileSidebarTriggerRef = useRef<HTMLButtonElement>(null);

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

  useEffect(() => {
    if (!mobileSidebarOpen) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setMobileSidebarOpen(false);
      mobileSidebarTriggerRef.current?.focus();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [mobileSidebarOpen]);

  function navigate(next: ClinicalRoute) {
    window.history.pushState({}, '', routePath(next));
    setRoute(next);
    setMobileSidebarOpen(false);
  }

  function toggleSidebarCollapsed() {
    setSidebarCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      } catch {
        // The navigation still works when browser storage is unavailable.
      }
      return next;
    });
  }

  function closeMobileSidebar() {
    setMobileSidebarOpen(false);
    mobileSidebarTriggerRef.current?.focus();
  }

  if (error) return <div className="shell-load-error">Unable to load clinical workspace: {error}</div>;
  if (!identity) return <div className="shell-loading">Loading clinical workspace…</div>;

  const selectedPatientId = route.kind === 'patient' ? route.patientId : null;
  const shellStyle = { '--sidebar-width': sidebarCollapsed ? '64px' : '232px' } as CSSProperties;
  const workspaceStyle = { '--context-width': `${contextWidth}px` } as CSSProperties;
  return (
    <div className={`clinician-shell role-${identity.role}${sidebarCollapsed ? ' sidebar-collapsed' : ''}`} style={shellStyle}>
      <button
        ref={mobileSidebarTriggerRef}
        className="mobile-sidebar-trigger"
        type="button"
        aria-controls="clinical-patient-navigation"
        aria-expanded={mobileSidebarOpen}
        aria-label="Open patient navigation"
        onClick={() => setMobileSidebarOpen(true)}
      >
        <span aria-hidden="true">☰</span>
      </button>
      <button
        className={`mobile-sidebar-backdrop${mobileSidebarOpen ? ' is-visible' : ''}`}
        type="button"
        aria-label="Close patient navigation"
        tabIndex={mobileSidebarOpen ? 0 : -1}
        onClick={closeMobileSidebar}
      />
      <ClinicianSidebar
        identity={identity}
        patients={patients}
        selectedPatientId={selectedPatientId}
        collapsed={sidebarCollapsed}
        mobileOpen={mobileSidebarOpen}
        onToggleCollapsed={toggleSidebarCollapsed}
        onCloseMobile={closeMobileSidebar}
        onDashboard={() => navigate({ kind: 'dashboard' })}
        onSelectPatient={(patientId) => navigate({ kind: 'patient', patientId, mode: 'glance' })}
        onLogout={onLogout}
      />
      {route.kind === 'dashboard' ? (
        <div className="workspace-area dashboard-area dashboard-context-collapsed" style={workspaceStyle}>
          <main className="workspace-main clinic-dashboard">
            <div className="dashboard-content">
              <div className="dashboard-heading-row">
                <div><p className="eyebrow">{identity.clinic_name}</p><h1>{identity.role === 'staff' ? 'Nurse workspace' : 'Clinic dashboard'}</h1><p className="dashboard-lead">{identity.role === 'staff' ? 'Select an authorized patient to review evidence, coordinate care, and record Nurse Consults.' : 'Select an authorized patient to continue their longitudinal care record.'}</p></div>
                <span className="dashboard-role-label">{identity.professional_title ?? identity.role}</span>
              </div>
              <div className="dashboard-scope-note"><strong>Clinic-scoped access</strong><span>{patients.length} authorized patient{patients.length === 1 ? '' : 's'} · enforced by the server</span></div>
              <section className="dashboard-patient-directory" aria-labelledby="authorized-patients-heading">
                <div className="dashboard-directory-heading">
                  <div><p className="eyebrow">Patient directory</p><h2 id="authorized-patients-heading">Authorized patients</h2></div>
                  <span>Open a record to begin</span>
                </div>
                {patients.length === 0 ? (
                  <div className="empty-state"><h3>No authorized patients</h3><p>This account does not currently have access to a patient record.</p></div>
                ) : (
                  <div className="dashboard-patient-grid">
                    {patients.map((patient) => (
                      <button key={patient.patient_id} onClick={() => navigate({ kind: 'patient', patientId: patient.patient_id, mode: 'glance' })}>
                        <span className="patient-list-avatar">{patient.name.slice(0, 1)}</span>
                        <span><strong>{patient.name}</strong><small>{patient.patient_id} · Clinic patient</small></span>
                        <span className="dashboard-open-record">Open record <i aria-hidden="true">→</i></span>
                      </button>
                    ))}
                  </div>
                )}
              </section>
            </div>
          </main>
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
