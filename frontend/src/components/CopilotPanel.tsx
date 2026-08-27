import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import type { CopilotCategory, CopilotDraft, CopilotEvidence, CopilotResponse } from '../types';

const QUICK: { category: CopilotCategory; label: string }[] = [
  { category: 'what_changed', label: 'What changed?' },
  { category: 'what_matters_now', label: 'What matters now?' },
  { category: 'find_evidence', label: 'Find evidence' },
  { category: 'draft_action', label: 'Draft action' },
];

function draftLabel(draft: CopilotDraft): string {
  if (draft.artifact_type === 'task') return 'Care Task';
  return draft.artifact_type === 'patient_instruction' ? 'Patient instruction' : 'Clinician note';
}

export default function CopilotPanel({
  patientId,
  roleKey,
  onOpenEvidence,
  onConfirmed,
}: {
  patientId: string;
  roleKey: string;
  onOpenEvidence: (evidence: CopilotEvidence) => void;
  onConfirmed: () => void;
}) {
  const [category, setCategory] = useState<CopilotCategory>('what_changed');
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState<CopilotResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const evidence = useMemo(() => new Map(response?.evidence.map((item) => [item.evidence_id, item]) ?? []), [response]);

  useEffect(() => {
    // This is a hard patient/role/session boundary. The parent is additionally
    // keyed on session/patient, so unmount and this reset both prevent leaks.
    setCategory('what_changed');
    setQuestion('');
    setResponse(null);
    setBusy(false);
    setConfirming(false);
    setError(null);
  }, [patientId, roleKey]);

  async function ask(next = category) {
    setCategory(next);
    setBusy(true);
    setError(null);
    setResponse(null);
    try {
      setResponse(await api.queryCopilot(patientId, next, question.trim()));
    } catch (requestError: any) {
      setError(String(requestError.message ?? requestError));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDraft() {
    const draft = response?.draft;
    if (!draft) return;
    setConfirming(true);
    setError(null);
    try {
      if (draft.artifact_type === 'task') {
        const source = evidence.get(draft.evidence_ids[0]);
        await api.createTask(draft.event_id, {
          title: draft.content.title ?? 'Review draft task',
          description: draft.content.description ?? '',
          assigned_role: 'clinician',
          assigned_user_id: null,
          patient_visible: false,
          due_at: null,
          source_artifact_id: source?.artifact_id ?? null,
          source_span: source?.span ?? null,
          draft_origin: 'copilot',
        });
      } else {
        await api.createNote(draft.event_id, draft.artifact_type, draft.content, 'copilot');
      }
      setResponse((current) => current ? { ...current, draft: null } : current);
      onConfirmed();
    } catch (confirmError: any) {
      setError(String(confirmError.message ?? confirmError));
    } finally {
      setConfirming(false);
    }
  }

  return (
    <section className="copilot-panel" aria-labelledby="copilot-heading">
      <header><p className="eyebrow">Evidence-bound assistant</p><h2 id="copilot-heading">Copilot</h2><span>Clinical review only — never diagnoses or acts automatically.</span></header>
      <div className="copilot-quick-actions">
        {QUICK.map((item) => <button key={item.category} className={category === item.category ? 'active' : ''} disabled={busy} onClick={() => ask(item.category)}>{item.label}</button>)}
      </div>
      <label className="copilot-question">Refine this question (optional)<textarea value={question} maxLength={300} rows={2} onChange={(event) => setQuestion(event.target.value)} placeholder="Find a symptom, medication, task, or statement" /></label>
      <button className="primary-button copilot-ask" disabled={busy} onClick={() => ask()}>{busy ? 'Checking bounded evidence…' : 'Ask Copilot'}</button>
      {error && <div className="form-error">Copilot request failed: {error}</div>}
      {response && <div className="copilot-result" aria-live="polite">
        {response.status === 'unavailable' && <div className="copilot-unavailable">Unavailable — no clinical answer was generated.</div>}
        {response.claims.map((claim, index) => <article className={`copilot-claim ${claim.status}`} key={`${claim.status}:${index}`}><strong>{claim.status === 'supported' ? 'Source fact' : claim.status === 'inference' ? 'Inference' : 'Unknown'}</strong><p>{claim.text}</p>{claim.evidence_ids.map((id) => <button key={id} className="link-btn" onClick={() => { const item = evidence.get(id); if (item) onOpenEvidence(item); }}>Open evidence {id}</button>)}</article>)}
        {response.evidence.length > 0 && <div className="copilot-evidence"><h3>Verified evidence</h3>{response.evidence.map((item) => <article key={item.evidence_id}><button className="link-btn" onClick={() => onOpenEvidence(item)}>{item.event_type.replace(/_/g, ' ')} · {item.artifact_type}</button><small>{new Date(item.event_time).toLocaleString()} · {item.author_role} · {item.span.kind}</small><blockquote>{item.quote}</blockquote>{item.review_required && <em>Review flag on this source.</em>}</article>)}</div>}
        {response.draft && <div className="copilot-draft"><h3>AI-generated draft preview</h3><p><strong>{draftLabel(response.draft)}</strong> · Event {response.draft.event_id} · {response.draft.patient_visible ? 'patient visible if confirmed' : 'internal'}</p><pre>{JSON.stringify(response.draft.content, null, 2)}</pre><p className="muted">Nothing has been saved. Confirming uses the normal authorized write flow with you as the author.</p><button className="primary-button" disabled={confirming} onClick={confirmDraft}>{confirming ? 'Confirming…' : 'Confirm and create'}</button></div>}
        <div className="copilot-limitations"><h3>Limits</h3>{response.limitations.map((item) => <p key={item}>{item}</p>)}</div>
      </div>}
    </section>
  );
}
