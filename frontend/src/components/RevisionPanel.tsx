import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Artifact, ArtifactVersion } from '../types';

export default function RevisionPanel({
  artifact,
  onReverted,
  canRevert = true,
  defaultOpen = false,
}: {
  artifact: Artifact;
  onReverted: () => void;
  canRevert?: boolean;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [since, setSince] = useState<number>(1);
  const [diff, setDiff] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setVersions(await api.getVersions(artifact.artifact_id));
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  useEffect(() => {
    if (open) load();
  }, [open, artifact.artifact_id]);

  async function showDiff() {
    try {
      setDiff((await api.getDiff(artifact.artifact_id, since)).diff);
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  async function revert(toVersion: number) {
    try {
      await api.revertArtifact(artifact.artifact_id, toVersion, artifact.version);
      setDiff(null);
      await load();
      onReverted();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  if (!open) {
    return (
      <button className="link-btn" onClick={() => setOpen(true)}>
        Versions
      </button>
    );
  }
  return (
    <div className="revision-panel">
      <header className="history-section-head"><div><p className="eyebrow">Authored record</p><h3>Version history</h3></div><button className="link-btn" onClick={() => setOpen(false)}>Collapse</button></header>
      {error && <div className="error-inline">{error}</div>}
      <ul className="version-list">
        {versions.map((v) => (
          <li key={v.version_id}>
            <span><strong>Version {v.version}</strong><small>{v.actor_role} · {new Date(v.created_at).toLocaleString()}</small></span>
            {v.version === artifact.version && <span className="current-version-tag">Current</span>}
            {canRevert && (
              <button onClick={() => revert(v.version)} disabled={v.version === artifact.version}>
                Restore
              </button>
            )}
          </li>
        ))}
      </ul>
      <div className="diff-controls">
        <label>Compare with</label>
        <select value={since} onChange={(e) => setSince(Number(e.target.value))}>
          {versions.map((v) => (
            <option key={v.version} value={v.version}>
              v{v.version}
            </option>
          ))}
        </select>
        <button onClick={showDiff}>View changes</button>
      </div>
      {diff !== null && <pre className="diff-view">{diff || '(no changes)'}</pre>}
    </div>
  );
}
