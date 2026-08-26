import { useState } from 'react';
import { api, getCurrentRole } from '../api';

export default function IngestPanel({
  patientId,
  onIngested,
}: {
  patientId: string;
  onIngested: () => void;
}) {
  const role = getCurrentRole();
  const [text, setText] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (role === 'admin') return null; // admin is read-only

  async function submit() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      if (role === 'patient') {
        const r = await api.createSession(
          patientId,
          `sess-${Date.now()}`,
          'patient_followup',
          new Date().toISOString(),
          { messages: [{ id: 'm1', speaker: 'patient', text }] },
        );
        setResult(`Session ingested · degraded=${r.degraded}`);
      } else {
        const eventId = role === 'staff' ? 'evt_nurse_0821' : 'evt_doc_0821';
        const r = await api.ingestSource(eventId, `k-${Date.now()}`, {
          segments: [{ index: 1, speaker: role === 'staff' ? 'nurse' : 'doctor', text }],
        });
        setResult(`Summary generated · method=${r.generation_method} · degraded=${r.degraded}`);
      }
      setText('');
      onIngested();
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ingest-panel">
      <h4>Ingest {role === 'patient' ? 'follow-up' : 'transcript'} (demo)</h4>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste source text…"
        rows={3}
      />
      <div className="inline-actions">
        <button onClick={submit} disabled={busy || !text.trim()}>
          Generate AI summary
        </button>
        {result && <span className="muted">{result}</span>}
        {error && <span className="error-inline">{error}</span>}
      </div>
    </div>
  );
}
