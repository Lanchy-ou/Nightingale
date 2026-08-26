import { useEffect, useState } from 'react';
import { MENTIONABLE, api } from '../api';
import type { Artifact, Comment } from '../types';

export default function CommentThread({
  eventId,
  artifacts,
  canWrite,
  onChanged,
}: {
  eventId: string;
  artifacts: Artifact[];
  canWrite: boolean;
  onChanged?: () => void;
}) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [body, setBody] = useState('');
  const [mentions, setMentions] = useState<string[]>([]);
  const [anchorKey, setAnchorKey] = useState(`event:${eventId}`);
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
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
      const [selectedType, ...idParts] = anchorKey.split(':');
      await api.createComment({
        anchor_type: replyTo?.anchor_type ?? selectedType,
        anchor_id: replyTo?.anchor_id ?? idParts.join(':'),
        parent_comment_id: replyTo?.comment_id ?? null,
        body,
        mentions,
      });
      setBody('');
      setMentions([]);
      setReplyTo(null);
      await load();
      onChanged?.();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  async function toggleResolved(c: Comment) {
    try {
      if (c.resolved) await api.unresolveComment(c.comment_id);
      else await api.resolveComment(c.comment_id);
      await load();
      onChanged?.();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  function mention(u: { user_id: string; label: string }) {
    setBody((b) => b + '@' + u.label + ' ');
    if (!mentions.includes(u.user_id)) setMentions((m) => [...m, u.user_id]);
    setShowMentions(false);
  }

  const commentIds = new Set(comments.map((c) => c.comment_id));
  const roots = comments.filter(
    (c) => c.parent_comment_id === null || !commentIds.has(c.parent_comment_id),
  );

  function anchorLabel(c: Comment): string {
    if (c.anchor_type === 'event') return 'Event';
    const artifact = artifacts.find((a) => a.artifact_id === c.anchor_id);
    return artifact ? artifact.artifact_type.replace(/_/g, ' ') : 'Artifact';
  }

  function renderComment(c: Comment, depth = 0) {
    const replies = comments.filter((candidate) => candidate.parent_comment_id === c.comment_id);
    return (
      <div key={c.comment_id} style={{ marginLeft: `${Math.min(depth, 3) * 20}px` }}>
        <div className={`comment ${c.resolved ? 'resolved' : ''}`}>
          <div className="comment-meta">
            {c.author_role} · {anchorLabel(c)} · {new Date(c.created_at).toLocaleString()}
            {c.resolved && <span className="resolved-tag">resolved</span>}
          </div>
          <div className="comment-body">{c.body}</div>
          {canWrite && (
            <div className="inline-actions">
              <button className="link-btn" onClick={() => setReplyTo(c)}>
                Reply
              </button>
              <button className="link-btn" onClick={() => toggleResolved(c)}>
                {c.resolved ? 'Unresolve' : 'Resolve'}
              </button>
            </div>
          )}
        </div>
        {replies.map((reply) => renderComment(reply, depth + 1))}
      </div>
    );
  }

  return (
    <div className="comment-thread">
      <h4>Comments</h4>
      {error && <div className="error-inline">{error}</div>}
      {comments.length === 0 && <div className="muted">No comments yet.</div>}
      {roots.map((c) => renderComment(c))}
      {canWrite && (
        <div className="comment-composer">
          {replyTo ? (
            <div className="comment-meta">
              Replying to {replyTo.author_role} on {anchorLabel(replyTo)}
              <button className="link-btn" onClick={() => setReplyTo(null)}>
                Cancel reply
              </button>
            </div>
          ) : (
            <label>
              Attach to{' '}
              <select value={anchorKey} onChange={(e) => setAnchorKey(e.target.value)}>
                <option value={`event:${eventId}`}>Event</option>
                {artifacts.map((artifact) => (
                  <option
                    key={artifact.artifact_id}
                    value={`artifact:${artifact.artifact_id}`}
                  >
                    {artifact.artifact_type.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
            </label>
          )}
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
