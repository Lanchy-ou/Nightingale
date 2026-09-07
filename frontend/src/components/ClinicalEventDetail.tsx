import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import { artifactBadge, artifactLabel, eventLabel, formatDateTime } from '../clinical';
import type { Artifact, AuditLog, Comment, Event } from '../types';
import ArtifactContent from './ArtifactContent';
import ArtifactEdit from './ArtifactEdit';
import NoteComposer from './NoteComposer';
import PatientInstructionComposer from './PatientInstructionComposer';
import { TaskCreateForm } from './ClinicalTasksView';
import InstructionPublicationControl from './InstructionPublicationControl';

export interface EventContextState {
  artifacts: Artifact[];
  selectedArtifact: Artifact | null;
}

type LifecycleItem = {
  key: string;
  at: string;
  kind: 'event' | 'artifact' | 'comment' | 'audit';
  title: string;
  detail: string;
  artifact?: Artifact;
};

function systemAuthority(artifact: Artifact): string {
  const method = artifact.degraded ? 'Safe fallback' : artifact.generation_method === 'deepseek' ? 'DeepSeek AI' : 'Local deterministic';
  return `${method} · system-generated · not a clinician assessment`;
}

const AUDIT_LABELS: Record<string, string> = {
  conflict: 'Edit conflict recorded',
  edit_note: 'Note updated',
  highlight_status: 'Priority status changed',
  resolve: 'Comment resolved',
  revert: 'Earlier version restored',
  task_create: 'Task created',
  task_transition: 'Task status changed',
  unresolve: 'Comment reopened',
};

export default function ClinicalEventDetail({
  event,
  initialArtifactId,
  refreshKey,
  onBack,
  backLabel = 'Timeline',
  onChanged,
  onOpenComments,
  onContextState,
  role,
}: {
  event: Event;
  initialArtifactId: string | null;
  refreshKey: number;
  onBack: () => void;
  backLabel?: string;
  onChanged: () => void;
  onOpenComments: () => void;
  onContextState: (state: EventContextState) => void;
  role: string;
}) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [audit, setAudit] = useState<AuditLog[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialArtifactId);
  const [composerMode, setComposerMode] = useState<'note' | 'task' | 'instruction' | null>(null);
  const composerRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (composerMode) composerRef.current?.scrollIntoView({ block: 'nearest' });
  }, [composerMode]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const [nextArtifacts, nextComments, nextAudit] = await Promise.all([
          api.getArtifacts(event.event_id, controller.signal),
          api.getComments(event.event_id, controller.signal),
          api.getAudit(event.event_id, controller.signal),
        ]);
        if (!active) return;
        setArtifacts(nextArtifacts);
        setComments(nextComments);
        setAudit(nextAudit);
        setSelectedId((current) => {
          if (current && nextArtifacts.some((artifact) => artifact.artifact_id === current)) return current;
          if (initialArtifactId && nextArtifacts.some((artifact) => artifact.artifact_id === initialArtifactId)) {
            return initialArtifactId;
          }
          return nextArtifacts.find((artifact) => artifact.artifact_type.startsWith('ai_'))?.artifact_id
            ?? nextArtifacts[0]?.artifact_id
            ?? null;
        });
        setError(null);
      } catch (loadError: any) {
        if (active && loadError?.name !== 'AbortError') setError(String(loadError.message ?? loadError));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [event.event_id, initialArtifactId, refreshKey]);

  const selectedArtifact = artifacts.find((artifact) => artifact.artifact_id === selectedId) ?? null;
  const selectedBadge = selectedArtifact ? artifactBadge(selectedArtifact.artifact_type) : null;
  useEffect(() => {
    onContextState({ artifacts, selectedArtifact });
  }, [artifacts, selectedArtifact, onContextState]);

  const lifecycle = useMemo<LifecycleItem[]>(() => {
    const rows: LifecycleItem[] = [{
      key: `event:${event.event_id}`,
      at: event.started_at,
      kind: 'event',
      title: 'Event started',
      detail: eventLabel(event),
    }];
    for (const artifact of artifacts) {
      rows.push({
        key: `artifact:${artifact.artifact_id}`,
        at: artifact.created_at,
        kind: 'artifact',
        title: artifactLabel(artifact),
        detail: `${artifact.author_role}${artifact.author_role === 'system' ? ' · system-generated' : ''}`,
        artifact,
      });
    }
    for (const comment of comments) {
      rows.push({
        key: `comment:${comment.comment_id}`,
        at: comment.created_at,
        kind: 'comment',
        title: comment.parent_comment_id ? 'Comment replied' : 'Comment added',
        detail: `${comment.author_role} · ${comment.resolved ? 'resolved' : 'open'}`,
      });
    }
    for (const log of audit) {
      // Artifact and Comment rows already represent their creation once; keep
      // later collaboration/revision actions without duplicating creation.
      if (['source_ingest', 'ai_generate', 'ai_fallback', 'doctor_consult_create', 'nurse_consult_create', 'comment', 'create_note'].includes(log.action)) continue;
      rows.push({
        key: `audit:${log.audit_id}`,
        at: log.created_at,
        kind: 'audit',
        title: AUDIT_LABELS[log.action] ?? log.action.replace(/_/g, ' '),
        detail: `${log.actor_role}${log.to_version ? ` · v${log.to_version}` : ''}`,
      });
    }
    return rows.sort((a, b) => a.at.localeCompare(b.at) || a.key.localeCompare(b.key));
  }, [event, artifacts, comments, audit]);

  return (
    <section className="clinical-view event-detail" aria-labelledby="event-detail-heading">
      <button data-leave-editor className="back-button" onClick={onBack}>← Back to {backLabel}</button>
      <div className="event-detail-title">
        <div>
          <p className="eyebrow">{event.encounter_id ? 'Clinic Visit event' : 'Clinical event'}</p>
          <h2 id="event-detail-heading">{eventLabel(event)}</h2>
          <p className="view-subtitle">Occurred {formatDateTime(event.started_at)}</p>
        </div>
        <div className="event-detail-actions">
          <button className="secondary-button" onClick={onOpenComments}>Comments</button>
          <button className="primary-button" data-leave-editor onClick={() => setComposerMode((current) => current === 'note' ? null : 'note')}>{role === 'clinician' ? 'Add clinician note' : 'Add staff note'}</button>
          <button className="secondary-button" data-leave-editor onClick={() => setComposerMode((current) => current === 'task' ? null : 'task')}>Create task</button>
          {role === 'clinician' && <button className="secondary-button" data-leave-editor onClick={() => setComposerMode((current) => current === 'instruction' ? null : 'instruction')}>Add patient instruction</button>}
        </div>
      </div>

      <nav data-leave-editor className="event-document-tabs" aria-label="Event documents">
        {artifacts.map((artifact) => <button key={artifact.artifact_id} aria-pressed={artifact.artifact_id === selectedId} className={artifact.artifact_id === selectedId ? 'active' : ''} onClick={() => setSelectedId(artifact.artifact_id)}>
          <span className={`badge ${artifactBadge(artifact.artifact_type).cls}`}>{artifactBadge(artifact.artifact_type).badge}</span>{artifactLabel(artifact)}
        </button>)}
      </nav>

      {loading && <div className="loading-card">Loading event records…</div>}
      {error && <div className="form-error">Could not load Event Detail: {error}</div>}

      {(!loading || artifacts.length > 0) && !error && (
        <div className="event-detail-columns">

          <div className="event-reading-column">
            <div className={`artifact-reader ${selectedBadge ? `artifact-${selectedBadge.cls}` : ''}`}>
              {selectedArtifact ? (
                <>
                <header className="artifact-reader-head">
                  <div className="artifact-reader-title">
                    <span className={`badge ${selectedBadge!.cls}`}>
                      {selectedBadge!.badge}
                    </span>
                    <div>
                      <h3>{artifactLabel(selectedArtifact)}</h3>
                      <small>Recorded {formatDateTime(selectedArtifact.created_at)} · version {selectedArtifact.version}</small>
                    </div>
                  </div>
                  <div className="artifact-authority">
                    {selectedArtifact.artifact_type === 'external_test_report' ? 'External report · uploaded copy' : selectedArtifact.author_role === 'system' ? systemAuthority(selectedArtifact) : `${selectedArtifact.author_role}-authored`}
                  </div>
                </header>
                {role === 'clinician' && event.event_type === 'doctor_consult' && <a className="secondary-button" href={`/clinical/patients/${event.patient_id}/tests?event=${event.event_id}`}>Order examination</a>}
                <div className="reader-scroll" aria-label={`${artifactLabel(selectedArtifact)} content`}>
                  <ArtifactContent artifact={selectedArtifact} />
                </div>
                {selectedArtifact.artifact_type === 'patient_instruction' && (
                  <InstructionPublicationControl
                    artifact={selectedArtifact}
                    role={role}
                    onChanged={(nextArtifactId) => {
                      if (nextArtifactId) setSelectedId(nextArtifactId);
                      onChanged();
                    }}
                  />
                )}
                {selectedArtifact.artifact_type === `${role}_note` && (
                  <div className="reader-actions">
                    <ArtifactEdit key={selectedArtifact.artifact_id} artifact={selectedArtifact} onSaved={onChanged} />
                    <span className="muted">Version {selectedArtifact.version}</span>
                  </div>
                )}
                {['transcript', 'raw_conversation'].includes(selectedArtifact.artifact_type) && (
                  <p className="immutable-note">Immutable raw source · corrections belong in Comments or a {role === 'staff' ? 'Staff Note' : 'Clinician Note'}.</p>
                )}
                </>
              ) : (
                <div className="empty-state"><h3>No clinical material</h3><p>Add a role-owned note or ingest a source for this Event.</p></div>
              )}
            </div>
            {composerMode === 'note' && <section ref={composerRef} className="event-action-panel">
              <header><div><p className="eyebrow">New role-owned record</p><h3>{role === 'clinician' ? 'Clinician assessment / plan' : 'Staff supplement'}</h3></div><button className="link-btn" data-leave-editor onClick={() => setComposerMode(null)}>Close</button></header>
              <p className="panel-help">Creates a separate role-owned note; it never overwrites AI or raw source.</p>
              <NoteComposer eventId={event.event_id} artifactType={role === 'clinician' ? 'clinician_note' : 'staff_note'} onSaved={() => { onChanged(); setComposerMode(null); }} />
            </section>}
            {composerMode === 'task' && <section ref={composerRef} className="event-action-panel">
              <header><div><p className="eyebrow">New follow-up action</p><h3>Create care task</h3></div><button className="link-btn" data-leave-editor onClick={() => setComposerMode(null)}>Close</button></header>
              <p className="panel-help">The current Event is the origin. An exact quote is optional and must be explicitly confirmed.</p>
              <TaskCreateForm event={event} sourceArtifact={selectedArtifact} onCreated={() => { onChanged(); setComposerMode(null); }} />
            </section>}
            {composerMode === 'instruction' && <section ref={composerRef} className="event-action-panel">
              <header><div><p className="eyebrow">Patient communication</p><h3>Create patient instruction</h3></div><button className="link-btn" data-leave-editor onClick={() => setComposerMode(null)}>Close</button></header>
              <PatientInstructionComposer eventId={event.event_id} onSaved={(artifact) => { setSelectedId(artifact.artifact_id); onChanged(); setComposerMode(null); }} />
            </section>}
          </div>
          <details className="event-material-panel">
            <summary>Event activity · {lifecycle.length} records</summary>
            <p className="panel-help">Documents, comments and changes, ordered by when they were recorded.</p>
            <div className="lifecycle-list event-lifecycle-list">
              {lifecycle.map((item) => {
                const content = <>
                  <span className="lifecycle-dot" aria-hidden="true" />
                  <span>
                    <b className={`lifecycle-kind ${item.kind}`}>{item.kind === 'event' ? 'Event start' : item.kind}</b>
                    <small>{formatDateTime(item.at)}</small>
                    <strong>{item.title}</strong>
                    <em>{item.detail}</em>
                  </span>
                </>;
                return item.artifact ? (
                  <button data-leave-editor key={item.key} className={`lifecycle-item ${item.kind} ${item.artifact.artifact_id === selectedId ? 'active' : ''}`} onClick={() => setSelectedId(item.artifact!.artifact_id)} aria-pressed={item.artifact.artifact_id === selectedId}>{content}</button>
                ) : (
                  <div key={item.key} className={`lifecycle-item ${item.kind}`}>{content}</div>
                );
              })}
            </div>
          </details>
        </div>
      )}
    </section>
  );
}
