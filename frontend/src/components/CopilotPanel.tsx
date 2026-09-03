import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '../api';
import type { CopilotCategory, CopilotDraft, CopilotEvidence, CopilotResponse } from '../types';

type DraftType = CopilotDraft['artifact_type'];
type CopilotRequest = {
  category: CopilotCategory;
  draftType?: DraftType;
  question: string;
  label: string;
};

const QUERY_CHIPS: { category: Exclude<CopilotCategory, 'draft_action'>; label: string }[] = [
  { category: 'what_changed', label: 'What changed?' },
  { category: 'what_matters_now', label: 'What matters now?' },
  { category: 'find_evidence', label: 'Find evidence' },
];

const DRAFT_CHIPS: { draftType: DraftType; label: string }[] = [
  { draftType: 'clinician_note', label: 'Draft clinician note' },
  { draftType: 'task', label: 'Draft care task' },
  { draftType: 'patient_instruction', label: 'Draft patient instruction' },
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
  const [errorKind, setErrorKind] = useState<'request' | 'confirmation' | null>(null);
  const [lastRequest, setLastRequest] = useState<CopilotRequest | null>(null);
  const requestInFlight = useRef(false);
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
    setErrorKind(null);
    setLastRequest(null);
    requestInFlight.current = false;
  }, [patientId, roleKey]);

  async function runRequest(request: CopilotRequest) {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setCategory(request.category);
    if (request.draftType) setDraftType(request.draftType);
    setLastRequest(request);
    setBusy(true);
    setError(null);
    setErrorKind(null);
    setResponse(null);
    setDraftContent({});
    try {
      const result = await api.queryCopilot(
        patientId,
        request.category,
        request.question,
        request.category === 'draft_action' ? request.draftType : undefined,
      );
      setResponse(result);
      setDraftContent(result.draft?.content ?? {});
      setQuestion('');
    } catch (requestError: any) {
      setError(String(requestError.message ?? requestError));
      setErrorKind('request');
    } finally {
      requestInFlight.current = false;
      setBusy(false);
    }
  }

  function sendChip(next: CopilotCategory, label: string, nextDraftType?: DraftType) {
    const guidance = question.trim();
    void runRequest({
      category: next,
      draftType: nextDraftType,
      question: guidance,
      label: guidance ? `${label}: ${guidance}` : label,
    });
  }

  function sendFocusedQuestion() {
    const focusedQuestion = question.trim();
    if (!focusedQuestion || busy) return;
    void runRequest({
      category,
      draftType: category === 'draft_action' ? draftType : undefined,
      question: focusedQuestion,
      label: focusedQuestion,
    });
  }

  function handleQuestionKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    sendFocusedQuestion();
  }

  function editDraft(field: string, value: string) {
    setDraftContent((current) => ({ ...current, [field]: value }));
  }

  async function confirmDraft() {
    const draft = response?.draft;
    if (!draft) return;
    setConfirming(true);
    setError(null);
    setErrorKind(null);
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
      setErrorKind('confirmation');
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
    <section className="copilot-panel" aria-label="Copilot">
      <div className="copilot-authority-strip"><strong>Evidence-bound Copilot</strong><span>Claims stay separated as source facts, inferences or unknowns. Nothing is saved without explicit confirmation.</span></div>
      <div className="copilot-conversation" aria-live="polite">
        {!response && !busy && !error && !lastRequest && <div className="copilot-welcome"><p className="eyebrow">Current review</p><h3>Ask about this patient record</h3><p>Answers separate source facts, comparison inferences and unknowns. Open any citation to inspect its exact source span.</p></div>}
        {lastRequest && <div className="copilot-user-message"><span>You</span><p>{lastRequest.label}</p></div>}
        {busy && <div className="copilot-thinking">Checking evidence...</div>}
        {error && <div className="copilot-error-state"><div className="form-error">{errorKind === 'confirmation' ? 'Confirmation failed' : 'Copilot request failed'}: {error}</div>{errorKind === 'request' && <button className="secondary-button" disabled={busy || !lastRequest} onClick={() => lastRequest && void runRequest(lastRequest)}>Retry</button>}</div>}
        {response && <div className="copilot-result">
          <div className="copilot-answer-head"><div><p className="eyebrow">{response.degraded ? 'Copilot · unavailable' : response.generation_method === 'deepseek' ? 'DeepSeek AI · current review' : 'Local deterministic · current review'}</p><h3>Evidence-bound answer</h3></div><span>{response.claims.length} claim{response.claims.length === 1 ? '' : 's'}</span></div>
          {response.status === 'unavailable' && <div className="copilot-unavailable">Unavailable — no clinical answer was generated.</div>}
          {response.claims.map((claim, index) => <article className={`copilot-claim ${claim.status}`} key={`${claim.status}:${index}`}><strong>{claim.status === 'supported' ? 'Source fact' : claim.status === 'inference' ? 'Comparison inference' : 'Unknown'}</strong><p>{claim.text}</p>{claim.evidence_ids.map((id) => <button key={id} className="link-btn" onClick={() => { const item = evidence.get(id); if (item) onOpenEvidence(item); }}>Open source {id}</button>)}</article>)}
          {response.draft && <div className="copilot-draft"><h3>AI-generated editable preview</h3><p><strong>{draftLabel(response.draft.artifact_type)}</strong> · Server-selected Event {response.draft.event_id} · {response.draft.artifact_type === 'patient_instruction' ? 'saved as a clinic draft; publish separately' : 'internal'}</p><DraftEditor type={response.draft.artifact_type} content={draftContent} onChange={editDraft} /><p className="muted">Nothing has been saved. The signed confirmation is actor/patient/Event/type/evidence-bound and expires shortly.</p>{response.draft.artifact_type === 'patient_instruction' && !patientInstructionEdited && <p className="verification-callout">Edit the patient-facing instruction before it can be confirmed.</p>}<button className="primary-button" disabled={confirming || !draftComplete} onClick={confirmDraft}>{confirming ? 'Confirming…' : response.draft.artifact_type === 'patient_instruction' ? 'Confirm and create draft' : 'Confirm and create'}</button></div>}
          {response.evidence.length > 0 && <details className="copilot-evidence"><summary>{response.evidence.length} verified source{response.evidence.length === 1 ? '' : 's'}</summary>{response.evidence.map((item) => <article key={item.evidence_id}><button className="link-btn" onClick={() => onOpenEvidence(item)}>{item.event_type.replace(/_/g, ' ')} · {item.artifact_type}</button><small>Event {new Date(item.event_time).toLocaleString()} · Recorded {new Date(item.record_time).toLocaleString()} · {item.author_role} · {item.span.kind}</small><blockquote>{item.quote}</blockquote>{item.review_required && <em>Review flag on this source.</em>}</article>)}</details>}
          <details className="copilot-limitations"><summary>Limits</summary>{response.limitations.map((item) => <p key={item}>{item}</p>)}</details>
        </div>}
      </div>
      <div className="copilot-composer">
        <div className="copilot-composer-head">
          <strong>Ask Copilot</strong>
          <span>{category === 'draft_action' ? `${draftLabel(draftType)} preview · confirmation required` : 'Evidence-bound question'}</span>
        </div>
        <div className="copilot-chip-group">
          <span>Suggested questions</span>
          <div className="copilot-quick-actions" aria-label="Suggested Copilot questions">
            {QUERY_CHIPS.map((item) => {
              const checking = busy && lastRequest?.category === item.category;
              return <button key={item.category} className={category === item.category ? 'active' : ''} disabled={busy} onClick={() => sendChip(item.category, item.label)}>{checking ? 'Checking evidence...' : item.label}</button>;
            })}
          </div>
        </div>
        <div className="copilot-chip-group">
          <span>Draft previews</span>
          <div className="copilot-quick-actions draft-actions" aria-label="Draft preview actions">
            {DRAFT_CHIPS.map((item) => {
              const checking = busy && lastRequest?.category === 'draft_action' && lastRequest.draftType === item.draftType;
              return <button key={item.draftType} className={category === 'draft_action' && draftType === item.draftType ? 'active' : ''} disabled={busy} onClick={() => sendChip('draft_action', item.label, item.draftType)}>{checking ? 'Checking evidence...' : item.label}</button>;
            })}
          </div>
        </div>
        <div className="copilot-input-shell">
          <label className="sr-only" htmlFor="copilot-focused-question">Focused Copilot question</label>
          <textarea
            id="copilot-focused-question"
            value={question}
            maxLength={300}
            rows={1}
            disabled={busy}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleQuestionKeyDown}
            placeholder={category === 'draft_action' ? `Add guidance for the ${draftLabel(draftType).toLowerCase()} preview` : "Ask about this patient's record"}
          />
          <div className="copilot-input-toolbar">
            <span>Enter to send · Shift+Enter for a new line</span>
            <button className="copilot-send" type="button" aria-label="Send Copilot request" disabled={busy || !question.trim()} onClick={sendFocusedQuestion}><span aria-hidden="true">↑</span></button>
          </div>
        </div>
      </div>
    </section>
  );
}

function DraftEditor({ type, content, onChange }: { type: DraftType; content: Record<string, string>; onChange: (field: string, value: string) => void }) {
  if (type === 'task') return <div className="copilot-draft-fields"><label>Task title<input value={content.title ?? ''} onChange={(event) => onChange('title', event.target.value)} /></label><label>Description<textarea rows={3} value={content.description ?? ''} onChange={(event) => onChange('description', event.target.value)} /></label></div>;
  if (type === 'patient_instruction') return <div className="copilot-draft-fields"><label>Patient-facing instruction<textarea rows={4} value={content.instruction ?? ''} onChange={(event) => onChange('instruction', event.target.value)} /></label><label>Follow-up (optional)<textarea rows={2} value={content.follow_up ?? ''} onChange={(event) => onChange('follow_up', event.target.value)} /></label></div>;
  return <div className="copilot-draft-fields"><label>Assessment<textarea rows={4} value={content.assessment ?? ''} onChange={(event) => onChange('assessment', event.target.value)} /></label><label>Plan<textarea rows={3} value={content.plan ?? ''} onChange={(event) => onChange('plan', event.target.value)} /></label></div>;
}
