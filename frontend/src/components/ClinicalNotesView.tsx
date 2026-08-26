import { useEffect, useState } from 'react';
import { api } from '../api';
import { artifactLabel, eventLabel, formatDateTime } from '../clinical';
import type { Artifact, Comment, Event } from '../types';

type NoteItem = { event: Event; artifact: Artifact };
type CommentItem = { event: Event; comment: Comment };

function excerpt(content: Record<string, any>): string {
  const strings = Object.values(content).filter((value): value is string => typeof value === 'string');
  return strings.join(' · ').slice(0, 220) || 'Structured note';
}

export default function ClinicalNotesView({
  events,
  refreshKey,
  onOpenArtifact,
  onOpenEvent,
}: {
  events: Event[];
  refreshKey: number;
  onOpenArtifact: (event: Event, artifactId: string) => void;
  onOpenEvent: (event: Event) => void;
}) {
  const [notes, setNotes] = useState<NoteItem[]>([]);
  const [comments, setComments] = useState<CommentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const [artifactLists, commentLists] = await Promise.all([
          Promise.all(events.map((event) => api.getArtifacts(event.event_id, controller.signal))),
          Promise.all(events.map((event) => api.getComments(event.event_id, controller.signal))),
        ]);
        if (!active) return;
        const nextNotes = events.flatMap((event, index) =>
          artifactLists[index]
            .filter((artifact) => ['clinician_note', 'staff_note'].includes(artifact.artifact_type))
            .map((artifact) => ({ event, artifact })),
        );
        const nextComments = events.flatMap((event, index) =>
          commentLists[index].map((comment) => ({ event, comment })),
        );
        nextNotes.sort((a, b) => b.artifact.created_at.localeCompare(a.artifact.created_at));
        nextComments.sort((a, b) => b.comment.created_at.localeCompare(a.comment.created_at));
        setNotes(nextNotes);
        setComments(nextComments);
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
  }, [events, refreshKey]);

  return (
    <section className="clinical-view" aria-labelledby="notes-heading">
      <div className="view-title-row">
        <div>
          <p className="eyebrow">Canonical items remain on their Events</p>
          <h2 id="notes-heading">Notes</h2>
        </div>
      </div>
      {loading && <div className="loading-card">Loading patient notes and discussions…</div>}
      {error && <div className="form-error">Could not load Notes: {error}</div>}
      {!loading && !error && notes.length === 0 && comments.length === 0 && (
        <div className="empty-state"><h3>No notes or discussions</h3><p>Add a clinician note from an Event Detail.</p></div>
      )}

      {notes.length > 0 && (
        <div className="notes-section">
          <h3>Clinical notes</h3>
          <div className="notes-grid">
            {notes.map(({ event, artifact }) => (
              <button
                className="note-projection-card"
                key={artifact.artifact_id}
                onClick={() => onOpenArtifact(event, artifact.artifact_id)}
              >
                <span className={`badge ${artifact.artifact_type === 'staff_note' ? 'staff' : 'clinician'}`}>
                  {artifact.artifact_type === 'staff_note' ? 'STAFF' : 'CLINICIAN'}
                </span>
                <strong>{artifactLabel(artifact)}</strong>
                <p>{excerpt(artifact.content)}</p>
                <small>{eventLabel(event)} · {formatDateTime(artifact.created_at)} · v{artifact.version}</small>
              </button>
            ))}
          </div>
        </div>
      )}

      {comments.length > 0 && (
        <div className="notes-section">
          <h3>Collaboration discussions</h3>
          <div className="discussion-list">
            {comments.map(({ event, comment }) => (
              <button key={comment.comment_id} onClick={() => onOpenEvent(event)}>
                <span className={comment.resolved ? 'resolved-tag' : 'open-tag'}>
                  {comment.resolved ? 'Resolved' : 'Open'}
                </span>
                <span><strong>{comment.author_role}</strong> · {comment.body}</span>
                <small>{eventLabel(event)} · {formatDateTime(comment.created_at)}</small>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
