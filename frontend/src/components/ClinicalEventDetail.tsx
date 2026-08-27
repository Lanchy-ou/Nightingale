import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { artifactBadge, artifactLabel, eventLabel, formatDateTime } from '../clinical';
import type { Artifact, AuditLog, Comment, Event } from '../types';
import ArtifactContent from './ArtifactContent';
import ArtifactEdit from './ArtifactEdit';
import NoteComposer from './NoteComposer';
import { TaskCreateForm } from './ClinicalTasksView';

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

export default function ClinicalEventDetail({
  event,
  initialArtifactId,
  refreshKey,
  onBack,
  onChanged,
  onContextState,
  role,
}: {
  event: Event;
  initialArtifactId: string | null;
  refreshKey: number;
  onBack: () => void;
  onChanged: () => void;
  onContextState: (state: EventContextState) => void;
  role: string;
}) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [audit, setAudit] = useState<AuditLog[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialArtifactId);
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
  useEffect(() => {
    onContextState({ artifacts, selectedArtifact });
  }, [artifacts, selectedArtifact, onContextState]);

  const lifecycle = useMemo<LifecycleItem[]>(() => {
    const rows: LifecycleItem[] = [{
      key: `event:${event.event_id}`,
      at: event.started_at,
      kind: 'event',
      title: 'Consult started',
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
      if (['source_ingest', 'ai_generate', 'ai_fallback', 'doctor_consult_create', 'comment', 'create_note'].includes(log.action)) continue;
      rows.push({
        key: `audit:${log.audit_id}`,
        at: log.created_at,
        kind: 'audit',
        title: log.action.replace(/_/g, ' '),
        detail: `${log.actor_role}${log.to_version ? ` · v${log.to_version}` : ''}`,
      });
    }
    return rows.sort((a, b) => a.at.localeCompare(b.at) || a.key.localeCompare(b.key));
  }, [event, artifacts, comments, audit]);

  return (
    <section className="clinical-view event-detail" aria-labelledby="event-detail-heading">
      <button className="back-button" onClick={onBack}>← Back to Timeline</button>
      <div className="event-detail-title">
        <div>
          <p className="eyebrow">{event.encounter_id ? 'Clinic Visit event' : 'Clinical event'}</p>
          <h2 id="event-detail-heading">{eventLabel(event)}</h2>
          <p className="view-subtitle">Occurred {formatDateTime(event.started_at)}</p>
        </div>
        <span className="record-count">{artifacts.length} artifacts</span>
      </div>

      {loading && <div className="loading-card">Loading Event lifecycle…</div>}
      {error && <div className="form-error">Could not load Event Detail: {error}</div>}

      {!loading && !error && (
        <div className="event-detail-columns">
          <div className="lifecycle-panel">
            <h3>Event lifecycle</h3>
            <p className="panel-help">Clinical time starts the Event; record activity stays inside it.</p>
            <div className="lifecycle-list">
              {lifecycle.map((item) => (
                <button
                  key={item.key}
                  className={`${item.kind} ${item.artifact?.artifact_id === selectedId ? 'active' : ''}`}
                  onClick={() => item.artifact && setSelectedId(item.artifact.artifact_id)}
                  disabled={!item.artifact}
                >
                  <span className="lifecycle-dot" aria-hidden="true" />
                  <span>
                    <small>{formatDateTime(item.at)}</small>
                    <strong>{item.title}</strong>
                    <em>{item.detail}</em>
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="artifact-reader">
            {selectedArtifact ? (
              <>
                <header className="artifact-reader-head">
                  <div>
                    <span className={`badge ${artifactBadge(selectedArtifact.artifact_type).cls}`}>
                      {artifactBadge(selectedArtifact.artifact_type).badge}
                    </span>
                    <h3>{artifactLabel(selectedArtifact)}</h3>
                  </div>
                  <div className="artifact-authority">
                    {selectedArtifact.author_role === 'system' ? 'System-generated · not a clinician assessment' : `${selectedArtifact.author_role}-authored`}
                  </div>
                </header>
                <div className="reader-scroll">
                  <ArtifactContent artifact={selectedArtifact} />
                </div>
                {selectedArtifact.artifact_type === `${role}_note` && (
                  <div className="reader-actions">
                    <ArtifactEdit artifact={selectedArtifact} onSaved={onChanged} />
                    <span className="muted">Version {selectedArtifact.version}</span>
                  </div>
                )}
                {selectedArtifact.artifact_type === 'transcript' && (
                  <p className="immutable-note">Immutable raw source · corrections belong in Comments or a Clinician Note.</p>
                )}
              </>
            ) : (
              <div className="empty-state"><h3>No artifacts</h3><p>Add a clinician note or ingest a source for this Event.</p></div>
            )}
            <div className="event-note-composer">
              <h3>{role === 'clinician' ? 'Formal assessment / plan' : 'Staff supplement'}</h3>
              <p className="panel-help">Creates a separate role-owned note; it never overwrites AI or raw source.</p>
              <NoteComposer eventId={event.event_id} artifactType={role === 'clinician' ? 'clinician_note' : 'staff_note'} onSaved={onChanged} />
            </div>
            <div className="event-task-composer">
              <h3>Create care Task</h3>
              <p className="panel-help">Uses this Event and, when resolvable, the selected Artifact's exact first source span.</p>
              <TaskCreateForm event={event} sourceArtifact={selectedArtifact} onCreated={onChanged} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
