import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import type { CopilotCategory, CopilotDraft, CopilotEvidence, CopilotResponse } from '../types';

type DraftType = CopilotDraft['artifact_type'];

const QUICK: { category: CopilotCategory; label: string }[] = [
  { category: 'what_changed', label: 'What changed?' },
  { category: 'what_matters_now', label: 'What matters now?' },
  { category: 'find_evidence', label: 'Find evidence' },
  { category: 'draft_action', label: 'Draft action' },
];

function draftLabel(type: DraftType): string {
  if (type === 'task') return 'Care Task';
  return type === 'patient_instruction' ? 'Patient instruction' : 'Clinician note';
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
  const [draftType, setDraftType] = useState<DraftType>('clinician_note');
  const [draftContent, setDraftContent] = useState<Record<string, string>>({});
  const [response, setResponse] = useState<CopilotResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const evidence = useMemo(() => new Map(response?.evidence.map((item) => [item.evidence_id, item]) ?? []), [response]);

  useEffect(() => {
    // Hard patient/role/session boundary. The parent is also keyed so logout
    // unmounts this component before another identity can render it.
    setCategory('what_changed');
    setQuestion('');
    setDraftType('clinician_note');
    setDraftContent({});
    setResponse(null);
    setBusy(false);
    setConfirming(false);
    setError(null);
  }, [patientId, roleKey]);

  function chooseQuick(next: CopilotCategory) {
    setCategory(next);
    setResponse(null);
    setDraftContent({});
    setError(null);
    if (next !== 'draft_action') void ask(next);
  }

  async function ask(next = category) {
    setCategory(next);
    setBusy(true);
    setError(null);
    setResponse(null);
    setDraftContent({});
    try {
      const result = await api.queryCopilot(
        patientId,
        next,
        question.trim(),
        next === 'draft_action' ? draftType : undefined,
      );
      setResponse(result);
      setDraftContent(result.draft?.content ?? {});
    } catch (requestError: any) {
      setError(String(requestError.message ?? requestError));
    } finally {
      setBusy(false);
    }
  }

  function editDraft(field: string, value: string) {
    setDraftContent((current) => ({ ...current, [field]: value }));
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
          title: draftContent.title ?? '',
          description: draftContent.description ?? '',
          assigned_role: 'clinician',
          assigned_user_id: null,
          patient_visible: false,
          due_at: null,
          source_artifact_id: source?.artifact_id ?? null,
          source_span: source?.span ?? null,
          confirmation_token: draft.confirmation_token,
        });
      } else {
        await api.createNote(
          draft.event_id,
          draft.artifact_type,
          draftContent,
          draft.confirmation_token,
        );
      }
      setResponse((current) => current ? { ...current, draft: null } : current);
      setDraftContent({});
      onConfirmed();
    } catch (confirmError: any) {
      setError(String(confirmError.message ?? confirmError));
    } finally {
      setConfirming(false);
    }
  }

  const patientInstructionEdited = response?.draft?.artifact_type !== 'patient_instruction'
    || (
      draftContent.instruction?.trim() !== response.draft.content.instruction?.trim()
      && !draftContent.instruction?.trim().toUpperCase().startsWith('EDIT REQUIRED')
    );
  const draftComplete = response?.draft?.artifact_type === 'task'
    ? Boolean(draftContent.title?.trim())
    : response?.draft?.artifact_type === 'patient_instruction'
      ? Boolean(draftContent.instruction?.trim()) && patientInstructionEdited
      : Boolean(draftContent.assessment?.trim() || draftContent.plan?.trim());

  return (
    <section className="copilot-panel" aria-labelledby="copilot-heading">
      <header><p className="eyebrow">Evidence-bound assistant</p><h2 id="copilot-heading">Copilot</h2><span>Clinical review only — never diagnoses or acts automatically.</span></header>
      <div className="copilot-quick-actions">
        {QUICK.map((item) => <button key={item.category} className={category === item.category ? 'active' : ''} disabled={busy} onClick={() => chooseQuick(item.category)}>{item.label}</button>)}
      </div>
      {category === 'draft_action' && <label className="copilot-question">Draft type — selected by clinician<select value={draftType} onChange={(event) => { setDraftType(event.target.value as DraftType); setResponse(null); setDraftContent({}); }}><option value="clinician_note">Clinician note</option><option value="task">Care Task</option><option value="patient_instruction">Patient instruction</option></select></label>}
      <label className="copilot-question">Refine this question (optional)<textarea value={question} maxLength={300} rows={2} onChange={(event) => setQuestion(event.target.value)} placeholder="Find a symptom, medication, task, or statement" /></label>
      <button className="primary-button copilot-ask" disabled={busy} onClick={() => ask()}>{busy ? 'Checking bounded evidence…' : category === 'draft_action' ? `Generate ${draftLabel(draftType)} preview` : 'Ask Copilot'}</button>
      {error && <div className="form-error">Copilot request failed: {error}</div>}
      {response && <div className="copilot-result" aria-live="polite">
        {response.status === 'unavailable' && <div className="copilot-unavailable">Unavailable — no clinical answer was generated.</div>}
        {response.claims.map((claim, index) => <article className={`copilot-claim ${claim.status}`} key={`${claim.status}:${index}`}><strong>{claim.status === 'supported' ? 'Source fact' : claim.status === 'inference' ? 'Comparison inference' : 'Unknown'}</strong><p>{claim.text}</p>{claim.evidence_ids.map((id) => <button key={id} className="link-btn" onClick={() => { const item = evidence.get(id); if (item) onOpenEvidence(item); }}>Open evidence {id}</button>)}</article>)}
        {response.evidence.length > 0 && <div className="copilot-evidence"><h3>Verified evidence</h3>{response.evidence.map((item) => <article key={item.evidence_id}><button className="link-btn" onClick={() => onOpenEvidence(item)}>{item.event_type.replace(/_/g, ' ')} · {item.artifact_type}</button><small>Event {new Date(item.event_time).toLocaleString()} · Recorded {new Date(item.record_time).toLocaleString()} · {item.author_role} · {item.span.kind}</small><blockquote>{item.quote}</blockquote>{item.review_required && <em>Review flag on this source.</em>}</article>)}</div>}
        {response.draft && <div className="copilot-draft"><h3>AI-generated editable preview</h3><p><strong>{draftLabel(response.draft.artifact_type)}</strong> · Server-selected Event {response.draft.event_id} · {response.draft.patient_visible ? 'patient visible if confirmed' : 'internal'}</p><DraftEditor type={response.draft.artifact_type} content={draftContent} onChange={editDraft} /><p className="muted">Nothing has been saved. The signed confirmation is actor/patient/Event/type/evidence-bound and expires shortly.</p>{response.draft.artifact_type === 'patient_instruction' && !patientInstructionEdited && <p className="verification-callout">Edit the patient-facing instruction before it can be confirmed.</p>}<button className="primary-button" disabled={confirming || !draftComplete} onClick={confirmDraft}>{confirming ? 'Confirming…' : 'Confirm and create'}</button></div>}
        <div className="copilot-limitations"><h3>Limits</h3>{response.limitations.map((item) => <p key={item}>{item}</p>)}</div>
      </div>}
    </section>
  );
}

function DraftEditor({ type, content, onChange }: { type: DraftType; content: Record<string, string>; onChange: (field: string, value: string) => void }) {
  if (type === 'task') return <div className="copilot-draft-fields"><label>Task title<input value={content.title ?? ''} onChange={(event) => onChange('title', event.target.value)} /></label><label>Description<textarea rows={3} value={content.description ?? ''} onChange={(event) => onChange('description', event.target.value)} /></label></div>;
  if (type === 'patient_instruction') return <div className="copilot-draft-fields"><label>Patient-facing instruction<textarea rows={4} value={content.instruction ?? ''} onChange={(event) => onChange('instruction', event.target.value)} /></label><label>Follow-up (optional)<textarea rows={2} value={content.follow_up ?? ''} onChange={(event) => onChange('follow_up', event.target.value)} /></label></div>;
  return <div className="copilot-draft-fields"><label>Assessment<textarea rows={4} value={content.assessment ?? ''} onChange={(event) => onChange('assessment', event.target.value)} /></label><label>Plan<textarea rows={3} value={content.plan ?? ''} onChange={(event) => onChange('plan', event.target.value)} /></label></div>;
}
