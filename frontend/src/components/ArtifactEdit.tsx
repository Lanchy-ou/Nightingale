import { useEffect, useRef, useState } from 'react';
import { ApiError, api } from '../api';
import { useNoteDraft } from '../useNoteDraft';
import type { Artifact } from '../types';

function editableFields(artifact: Artifact): Record<string, string> {
  return Object.fromEntries(
    Object.entries(artifact.content).filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
  );
}

export default function ArtifactEdit({
  artifact,
  onSaved,
}: {
  artifact: Artifact;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [fields, setFields] = useState(() => editableFields(artifact));
  const [draftBase, setDraftBase] = useState(artifact);
  const [conflict, setConflict] = useState(false);
  const [latest, setLatest] = useState<Artifact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const privateDraft = useNoteDraft(artifact.event_id, artifact.artifact_id, fields, draftBase.version, open, (draft) => {
    setFields(draft.fields!);
    setDraftBase({ ...artifact, version: draft.base_version, content: draft.base_content });
    setConflict(draft.base_version !== artifact.version);
    setLatest(draft.base_version !== artifact.version ? artifact : null);
  });
  const mounted = useRef(true);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; request.current?.abort(); };
  }, []);

  useEffect(() => {
    if (open && artifact.version !== draftBase.version) {
      setConflict(true);
      setLatest(artifact);
      return;
    }
    setDraftBase(artifact);
    setFields(editableFields(artifact));
    setConflict(false);
    setLatest(null);
    setError(null);
  }, [artifact.artifact_id, artifact.version]);

  function fieldLabel(key: string): string {
    return key.replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase());
  }

  async function loadLatest() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    try {
      const artifacts = await api.getArtifacts(artifact.event_id, controller.signal);
      if (!mounted.current || controller.signal.aborted) return;
      const current = artifacts.find((item) => item.artifact_id === artifact.artifact_id);
      if (!current) throw new Error('This note is no longer available. Your draft is still shown below.');
      setLatest(current);
      setError(null);
    } catch (e: any) {
      if (mounted.current && e?.name !== 'AbortError') setError(String(e.message ?? e));
    } finally {
      if (mounted.current && !controller.signal.aborted) setBusy(false);
    }
  }

  function reviewLatest() {
    if (!latest) return;
    const merged = editableFields(latest);
    for (const [key, value] of Object.entries(fields)) {
      if (value !== draftBase.content[key]) merged[key] = value;
    }
    setFields(merged);
    setDraftBase(latest);
    setLatest(null);
    setConflict(false);
    setError(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.editArtifact(artifact.artifact_id, { ...draftBase.content, ...fields }, draftBase.version);
      if (!mounted.current) return;
      await privateDraft.clearAfterPublish();
      if (!mounted.current) return;
      setOpen(false);
      onSaved();
    } catch (e: any) {
      if (!mounted.current) return;
      if (e instanceof ApiError && e.status === 409) {
        setConflict(true);
        setLatest(null);
        // Keep this editor mounted: a parent refresh used to discard the draft.
        await loadLatest();
      } else {
        setError(String(e.message ?? e));
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="link-btn" onClick={() => {
        setFields(editableFields(artifact)); setDraftBase(artifact);
        setConflict(false); setLatest(null); setError(null); setOpen(true);
      }}>
        Edit
      </button>
    );
  }
  return (
    <div className="editor">
      <p className="private-draft-status" role="status">{privateDraft.message}</p>
      {privateDraft.error && <p className="form-error" role="alert">{privateDraft.error}</p>}
      {conflict && <section className="note-edit-conflict" aria-label="Note edit conflict">
        <p role="alert">This note changed elsewhere. Your unsaved draft is preserved below. Compare it with the latest saved version before retrying.</p>
        {latest ? <>
          <h4>Latest saved version · v{latest.version}</h4>
          <dl>{Object.entries(editableFields(latest)).map(([key, value]) => <div key={key}><dt>{fieldLabel(key)}</dt><dd>{value}</dd></div>)}</dl>
          <p>Your edited fields will stay in the draft. Unchanged fields will use the latest saved content.</p>
          <button className="secondary-button" disabled={busy} onClick={reviewLatest}>I reviewed v{latest.version} — enable retry</button>
        </> : <button className="secondary-button" disabled={busy} onClick={() => void loadLatest()}>{busy ? 'Loading latest version…' : 'Reload latest version'}</button>}
      </section>}
      <div className="structured-note-editor">
        {Object.entries(fields).map(([key, value]) => (
          <label key={key}>{fieldLabel(key)}<textarea value={value} disabled={busy || privateDraft.pending || !privateDraft.ready} onChange={(event) => setFields((current) => ({ ...current, [key]: event.target.value }))} rows={key === 'assessment' ? 4 : 3} /></label>
        ))}
      </div>
      <div className="inline-actions">
        <button className="primary-button" onClick={save} disabled={busy || privateDraft.pending || !privateDraft.ready || conflict || Object.keys(fields).length === 0}>
          {busy ? 'Saving…' : 'Save new version'}
        </button>
        <button className="secondary-button" onClick={privateDraft.savePrivate} disabled={busy || privateDraft.pending || !privateDraft.ready}>{privateDraft.pending ? 'Saving draft…' : 'Save private draft'}</button>
        {privateDraft.hasSaved && <button className="secondary-button" disabled={busy || privateDraft.pending} onClick={async () => {
          if (await privateDraft.discardPrivate(editableFields(artifact), artifact.version)) {
            setFields(editableFields(artifact)); setDraftBase(artifact); setConflict(false); setLatest(null);
          }
        }}>Discard private draft</button>}
        <button className="secondary-button" data-leave-editor disabled={busy || privateDraft.pending} onClick={() => {
          setOpen(false);
          if (conflict || draftBase.version !== artifact.version) onSaved();
        }}>
          Cancel
        </button>
        <span className="editor-version">v{draftBase.version} → v{draftBase.version + 1}</span>
        {error && <span className="error-inline">{error}</span>}
      </div>
    </div>
  );
}
