import { useState } from 'react';
import { ApiError, api } from '../api';
import type { Artifact } from '../types';

export default function ArtifactEdit({
  artifact,
  onSaved,
}: {
  artifact: Artifact;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(JSON.stringify(artifact.content, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    let content: any;
    try {
      content = JSON.parse(text);
    } catch {
      setError('Invalid JSON');
      setBusy(false);
      return;
    }
    try {
      await api.editArtifact(artifact.artifact_id, content, artifact.version);
      setOpen(false);
      onSaved();
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 409) {
        setError(`他人已修改（当前 v${e.body?.error?.current_version}），刷新后重试`);
        onSaved(); // refresh to pick up the latest version
      } else {
        setError(String(e.message ?? e));
      }
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="link-btn" onClick={() => setOpen(true)}>
        Edit
      </button>
    );
  }
  return (
    <div className="editor">
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} />
      <div className="inline-actions">
        <button onClick={save} disabled={busy}>
          Save (v{artifact.version} → v{artifact.version + 1})
        </button>
        <button className="link-btn" onClick={() => setOpen(false)}>
          Cancel
        </button>
        {error && <span className="error-inline">{error}</span>}
      </div>
    </div>
  );
}
