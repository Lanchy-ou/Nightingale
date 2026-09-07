import { useState } from 'react';
import { api } from '../api';
import { useNoteDraft } from '../useNoteDraft';

export default function NoteComposer({
  eventId,
  artifactType,
  onSaved,
}: {
  eventId: string;
  artifactType: string;
  onSaved: () => void;
}) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const privateDraft = useNoteDraft(eventId, 'new', { body: text }, 0, true, (draft) => setText(draft.fields?.body ?? ''));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.createNote(eventId, artifactType, { body: text });
      await privateDraft.clearAfterPublish();
      setText('');
      onSaved();
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="note-composer">
      <p className="private-draft-status" role="status">{privateDraft.message}</p>
      {privateDraft.error && <p className="form-error" role="alert">{privateDraft.error}</p>}
      <textarea
        disabled={busy || privateDraft.pending || !privateDraft.ready}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`Add ${artifactType.replace('_', ' ')}…`}
        rows={3}
      />
      <div className="inline-actions">
        <button className="primary-button" onClick={save} disabled={busy || privateDraft.pending || !privateDraft.ready || !text.trim()}>
          Save note
        </button>
        <button className="secondary-button" disabled={busy || privateDraft.pending || !privateDraft.ready} onClick={privateDraft.savePrivate}>{privateDraft.pending ? 'Saving draft…' : 'Save private draft'}</button>
        {privateDraft.hasSaved && <button className="secondary-button" disabled={busy || privateDraft.pending} onClick={async () => {
          if (await privateDraft.discardPrivate({ body: '' }, 0)) setText('');
        }}>Discard private draft</button>}
        {error && <span className="error-inline">{error}</span>}
      </div>
    </div>
  );
}
