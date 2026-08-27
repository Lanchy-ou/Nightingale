import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { artifactLabel, formatDate } from '../clinical';
import type {
  Artifact,
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

function patientInitials(name: string): string {
  return name.split(/\s+/).map((word) => word[0]).join('').slice(0, 2).toUpperCase();
}

function ContextEmpty() {
  return (
    <div className="context-empty">
      <div className="context-empty-icon" aria-hidden="true">↗</div>
      <p className="eyebrow">Review context</p>
      <h3>Select supporting detail</h3>
      <p>Open a Glance source or Event artifact without losing your place in the patient record.</p>
      <div className="context-capabilities" aria-label="Available context tools">
        <span>Sources</span><span>Comments</span><span>Versions</span><span>Audit</span>
      </div>
    </div>
  );
}

function PatientWorkspace({
  patientId,
  route,
  onNavigate,
  identity,
}: {
  patientId: string;
  route: Extract<ClinicalRoute, { kind: 'patient' }>;
  onNavigate: (route: ClinicalRoute) => void;
  identity: CurrentIdentity;
}) {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [eventRefreshKey, setEventRefreshKey] = useState(0);
  const [provenance, setProvenance] = useState<ProvenanceResult | null>(null);
  const [contextTab, setContextTab] = useState<'source' | 'comments' | 'versions' | 'audit'>('comments');
  const [eventContext, setEventContext] = useState<EventContextState>({ artifacts: [], selectedArtifact: null });
  const [initialArtifactId, setInitialArtifactId] = useState<string | null>(null);
  const [completion, setCompletion] = useState<DoctorConsultResult | null>(null);

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
    onNavigate({ kind: 'patient', patientId, mode: tab });
  }

  function openEvent(event: Event, artifactId: string | null = null) {
    setInitialArtifactId(artifactId);
    setContextTab('comments');
    onNavigate({ kind: 'patient', patientId, mode: 'event', eventId: event.event_id });
  }

  function handleViewSource(next: ProvenanceResult) {
    setProvenance(next);
    setContextTab('source');
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

  if (loading) {
    return <div className="workspace-area"><main className="workspace-main"><div className="loading-card">Loading clinical workspace…</div></main><aside className="context-panel"><ContextEmpty /></aside></div>;
  }
  if (error || !patient) {
    return <div className="workspace-area"><main className="workspace-main"><div className="form-error">Failed to load patient workspace: {error}</div></main><aside className="context-panel"><ContextEmpty /></aside></div>;
  }

  const selectedArtifact = eventContext.selectedArtifact;
  const hasVersions = selectedArtifact && ['clinician_note', 'staff_note'].includes(selectedArtifact.artifact_type);

  return (
    <div className="workspace-area">
      <main className="workspace-main">
        <header className="workspace-patient-header">
          <div className="patient-identity">
            <div className="avatar">{patientInitials(patient.name)}</div>
            <div>
              <p className="eyebrow">Patient longitudinal record</p>
              <h1>{patient.name}</h1>
              <span>{patient.patient_id} · {patient.clinic_name}</span>
              {latestEvent && <span className="patient-latest-event">Latest event {formatDate(latestEvent.started_at)}</span>}
            </div>
          </div>
          <div className="patient-primary-actions">
            <button
              className="secondary-button"
              onClick={() => latestEvent && openEvent(latestEvent)}
              disabled={!latestEvent}
            >
              Add note
            </button>
            {identity.role === 'clinician' && <button
              className="primary-button"
              onClick={() => onNavigate({ kind: 'patient', patientId, mode: 'new' })}
            >
              + New Consult
            </button>}
          </div>
        </header>

        {route.mode !== 'new' && route.mode !== 'event' && (
          <nav className="workspace-tabs" aria-label="Patient workspace views">
            {(['glance', 'timeline', 'notes', 'tasks'] as PatientTab[]).map((tab) => (
              <button
                key={tab}
                className={route.mode === tab ? 'active' : ''}
                aria-selected={route.mode === tab}
                onClick={() => openTab(tab)}
              >
                {tab[0].toUpperCase() + tab.slice(1)}
              </button>
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
          <GlancePanel key={`glance:${refreshKey}`} patientId={patientId} onViewSource={handleViewSource} onOpenTasks={() => openTab('tasks')} />
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

      <aside className="context-panel" aria-label="Clinical context">
        {route.mode === 'event' && selectedEvent ? (
          <>
            <div className="context-panel-head">
              <div><p className="eyebrow">Event context</p><h2>{selectedArtifact ? artifactLabel(selectedArtifact) : 'Collaboration'}</h2></div>
            </div>
            <nav className="context-tabs" aria-label="Event context tools">
              {provenance && <button className={contextTab === 'source' ? 'active' : ''} onClick={() => setContextTab('source')}>Source</button>}
              <button className={contextTab === 'comments' ? 'active' : ''} onClick={() => setContextTab('comments')}>Comments</button>
              {hasVersions && <button className={contextTab === 'versions' ? 'active' : ''} onClick={() => setContextTab('versions')}>Versions</button>}
              <button className={contextTab === 'audit' ? 'active' : ''} onClick={() => setContextTab('audit')}>Audit</button>
            </nav>
            <div className="context-scroll">
              {contextTab === 'source' && provenance && (
                <ProvenancePanel
                  provenance={provenance}
                  onClose={() => { setProvenance(null); setContextTab('comments'); }}
                  onFocusEvent={(eventId) => onNavigate({ kind: 'patient', patientId, mode: 'event', eventId })}
                />
              )}
              {contextTab === 'comments' && (
                <CommentThread
                  key={`${selectedEvent.event_id}:${eventRefreshKey}`}
                  eventId={selectedEvent.event_id}
                  artifacts={eventContext.artifacts}
                  canWrite
                  onChanged={changed}
                />
              )}
              {contextTab === 'versions' && hasVersions && selectedArtifact && (
                <RevisionPanel
                  key={`${selectedArtifact.artifact_id}:${selectedArtifact.version}`}
                  artifact={selectedArtifact}
                  onReverted={changed}
                  canRevert={selectedArtifact.artifact_type === `${identity.role}_note`}
                  defaultOpen
                />
              )}
              {contextTab === 'audit' && (
                <AuditList key={`${selectedEvent.event_id}:${eventRefreshKey}`} eventId={selectedEvent.event_id} defaultOpen />
              )}
            </div>
          </>
        ) : provenance ? (
          <div className="context-scroll standalone-source">
            <ProvenancePanel
              provenance={provenance}
              onClose={() => setProvenance(null)}
              onFocusEvent={(eventId) => onNavigate({ kind: 'patient', patientId, mode: 'event', eventId })}
            />
          </div>
        ) : (
          <ContextEmpty />
        )}
      </aside>
    </div>
  );
}

export default function ClinicianWorkspacePage({ roleKey, onLogout }: { roleKey: string; onLogout?: () => void }) {
  const [identity, setIdentity] = useState<CurrentIdentity | null>(null);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [route, setRoute] = useState<ClinicalRoute>(() => parseRoute());
  const [error, setError] = useState<string | null>(null);

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
  return (
    <div className="clinician-shell">
      <ClinicianSidebar
        identity={identity}
        patients={patients}
        selectedPatientId={selectedPatientId}
        onDashboard={() => navigate({ kind: 'dashboard' })}
        onSelectPatient={(patientId) => navigate({ kind: 'patient', patientId, mode: 'glance' })}
        onLogout={onLogout}
      />
      {route.kind === 'dashboard' ? (
        <div className="workspace-area dashboard-area">
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
          <aside className="context-panel"><ContextEmpty /></aside>
        </div>
      ) : (
        <PatientWorkspace
          key={`${roleKey}:${route.patientId}`}
          patientId={route.patientId}
          route={route}
          onNavigate={navigate}
          identity={identity}
        />
      )}
    </div>
  );
}
