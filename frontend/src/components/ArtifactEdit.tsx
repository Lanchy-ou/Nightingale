import { useEffect, useState } from 'react';
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
  const [fields, setFields] = useState<Record<string, string>>(() => Object.fromEntries(
    Object.entries(artifact.content).filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
  ));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setOpen(false);
    setFields(Object.fromEntries(
      Object.entries(artifact.content).filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
    ));
    setError(null);
  }, [artifact.artifact_id, artifact.version]);

  function fieldLabel(key: string): string {
    return key.replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase());
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.editArtifact(artifact.artifact_id, { ...artifact.content, ...fields }, artifact.version);
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
      <div className="structured-note-editor">
        {Object.entries(fields).map(([key, value]) => (
          <label key={key}>{fieldLabel(key)}<textarea value={value} onChange={(event) => setFields((current) => ({ ...current, [key]: event.target.value }))} rows={key === 'assessment' ? 4 : 3} /></label>
        ))}
      </div>
      <div className="inline-actions">
        <button className="primary-button" onClick={save} disabled={busy || Object.keys(fields).length === 0}>
          {busy ? 'Saving…' : 'Save new version'}
        </button>
        <button className="secondary-button" onClick={() => setOpen(false)}>
          Cancel
        </button>
        <span className="editor-version">v{artifact.version} → v{artifact.version + 1}</span>
        {error && <span className="error-inline">{error}</span>}
      </div>
    </div>
  );
}
