import { useState } from 'react';
import { api } from '../api';

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

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.createNote(eventId, artifactType, { body: text });
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
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`Add ${artifactType.replace('_', ' ')}…`}
        rows={3}
      />
      <div className="inline-actions">
        <button onClick={save} disabled={busy || !text.trim()}>
          Save note
        </button>
        {error && <span className="error-inline">{error}</span>}
      </div>
    </div>
  );
}
