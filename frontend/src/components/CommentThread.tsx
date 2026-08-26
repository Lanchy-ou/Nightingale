import { useEffect, useState } from 'react';
import { MENTIONABLE, api } from '../api';
import type { Comment } from '../types';

export default function CommentThread({
  eventId,
  canWrite,
}: {
  eventId: string;
  canWrite: boolean;
}) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [body, setBody] = useState('');
  const [mentions, setMentions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showMentions, setShowMentions] = useState(false);

  async function load() {
    try {
      setComments(await api.getComments(eventId));
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  useEffect(() => {
    load();
  }, [eventId]);

  async function postComment() {
    try {
      await api.createComment({ anchor_type: 'event', anchor_id: eventId, body, mentions });
      setBody('');
      setMentions([]);
      await load();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  async function toggleResolved(c: Comment) {
    try {
      if (c.resolved) await api.unresolveComment(c.comment_id);
      else await api.resolveComment(c.comment_id);
      await load();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  function mention(u: { user_id: string; label: string }) {
    setBody((b) => b + '@' + u.label + ' ');
    if (!mentions.includes(u.user_id)) setMentions((m) => [...m, u.user_id]);
    setShowMentions(false);
  }

  return (
    <div className="comment-thread">
      <h4>Comments</h4>
      {error && <div className="error-inline">{error}</div>}
      {comments.length === 0 && <div className="muted">No comments yet.</div>}
      {comments.map((c) => (
        <div key={c.comment_id} className={`comment ${c.resolved ? 'resolved' : ''}`}>
          <div className="comment-meta">
            {c.author_role} · {new Date(c.created_at).toLocaleString()}
            {c.resolved && <span className="resolved-tag">resolved</span>}
          </div>
          <div className="comment-body">{c.body}</div>
          {canWrite && (
            <button className="link-btn" onClick={() => toggleResolved(c)}>
              {c.resolved ? 'Unresolve' : 'Resolve'}
            </button>
          )}
        </div>
      ))}
      {canWrite && (
        <div className="comment-composer">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Add comment… use @ to mention"
            rows={2}
          />
          <div className="inline-actions">
            <button className="link-btn" onClick={() => setShowMentions((s) => !s)}>
              @ mention
            </button>
            <button onClick={postComment} disabled={!body.trim()}>
              Post
            </button>
          </div>
          {showMentions && (
            <div className="mention-list">
              {MENTIONABLE.map((u) => (
                <button key={u.user_id} onClick={() => mention(u)}>
                  {u.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
