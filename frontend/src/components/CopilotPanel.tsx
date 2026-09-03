import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '../api';
import type { CopilotCategory, CopilotEvidence, CopilotResponse } from '../types';

type ReadCategory = Exclude<CopilotCategory, 'draft_action'>;
type CopilotRequest = {
  category: ReadCategory;
  question: string;
};

function inferCategory(question: string): ReadCategory {
  const normalized = question.toLowerCase();
  if (/\b(source|evidence|where|from|support|provenance)\b/.test(normalized) || /(来源|证据|出处|哪里)/.test(normalized)) return 'find_evidence';
  if (/\b(matter|priority|priorities|important|attention|now|today)\b/.test(normalized) || /(重点|重要|优先|现在|目前)/.test(normalized)) return 'what_matters_now';
  return 'what_changed';
}

export default function CopilotPanel({
  patientId,
  roleKey,
  onOpenEvidence,
}: {
  patientId: string;
  roleKey: string;
  onOpenEvidence: (evidence: CopilotEvidence) => void;
  onConfirmed: () => void;
}) {
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState<CopilotResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<CopilotRequest | null>(null);
  const requestInFlight = useRef(false);
  const evidence = useMemo(() => new Map(response?.evidence.map((item) => [item.evidence_id, item]) ?? []), [response]);

  useEffect(() => {
    // Hard patient/role/session boundary. The parent is also keyed so logout
    // unmounts this component before another identity can render it.
    setQuestion('');
    setResponse(null);
    setBusy(false);
    setError(null);
    setLastRequest(null);
    requestInFlight.current = false;
  }, [patientId, roleKey]);

  async function runRequest(request: CopilotRequest) {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setLastRequest(request);
    setBusy(true);
    setError(null);
    setResponse(null);
    try {
      const result = await api.queryCopilot(patientId, request.category, request.question);
      setResponse(result);
      setQuestion('');
    } catch (requestError: any) {
      setError(String(requestError.message ?? requestError));
    } finally {
      requestInFlight.current = false;
      setBusy(false);
    }
  }

  function sendQuestion() {
    const focusedQuestion = question.trim();
    if (!focusedQuestion || busy) return;
    void runRequest({ category: inferCategory(focusedQuestion), question: focusedQuestion });
  }

  function handleQuestionKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    sendQuestion();
  }

  return (
    <section className="copilot-panel copilot-chat" aria-label="Copilot">
      <div className="copilot-conversation" aria-live="polite">
        {!response && !busy && !error && !lastRequest && (
          <div className="copilot-welcome"><h3>Ask about this patient record</h3><p>Ask what changed, what matters now, or where a statement came from.</p></div>
        )}
        {lastRequest && <div className="copilot-user-message"><span>You</span><p>{lastRequest.question}</p></div>}
        {busy && <div className="copilot-thinking">Checking the patient record…</div>}
        {error && <div className="copilot-error-state"><div className="form-error">Copilot request failed: {error}</div><button className="secondary-button" disabled={busy || !lastRequest} onClick={() => lastRequest && void runRequest(lastRequest)}>Retry</button></div>}
        {response && <div className="copilot-result">
          <div className="copilot-answer-head"><div><p className="eyebrow">Read-only answer</p><h3>Answer</h3></div><span>{response.claims.length} source-linked item{response.claims.length === 1 ? '' : 's'}</span></div>
          {response.status === 'unavailable' && <div className="copilot-unavailable">No supported answer could be generated from the available record.</div>}
          {response.claims.map((claim, index) => (
            <article className={`copilot-claim ${claim.status}`} key={`${claim.status}:${index}`}>
              <strong>{claim.status === 'supported' ? 'From the record' : claim.status === 'inference' ? 'Comparison requiring review' : 'Not established'}</strong>
              <p>{claim.text}</p>
              {claim.evidence_ids.map((id) => {
                const item = evidence.get(id);
                return item ? <button key={id} className="link-btn" onClick={() => onOpenEvidence(item)}>View source</button> : null;
              })}
            </article>
          ))}
          {response.evidence.length > 0 && <details className="copilot-evidence"><summary>Sources used ({response.evidence.length})</summary>{response.evidence.map((item) => <article key={item.evidence_id}><button className="link-btn" onClick={() => onOpenEvidence(item)}>Open exact source</button><small>{item.event_type.replace(/_/g, ' ')} · {item.artifact_type.replace(/_/g, ' ')} · {item.author_role}</small><blockquote>{item.quote}</blockquote></article>)}</details>}
          <details className="copilot-limitations"><summary>What this answer cannot do</summary>{response.limitations.map((item) => <p key={item}>{item}</p>)}</details>
        </div>}
      </div>
      <div className="copilot-composer">
        <div className="copilot-record-boundary">Copilot only reads the record. Use Notes, Tasks, or Comments to record clinical work.</div>
        <div className="copilot-input-shell">
          <label className="sr-only" htmlFor="copilot-question">Ask Copilot about this patient record</label>
          <textarea id="copilot-question" value={question} maxLength={300} rows={2} disabled={busy} onChange={(event) => setQuestion(event.target.value)} onKeyDown={handleQuestionKeyDown} placeholder="Ask a question about this patient record…" />
          <div className="copilot-input-toolbar"><span>Enter to send · Shift+Enter for a new line</span><button className="copilot-send" type="button" aria-label="Send Copilot request" disabled={busy || !question.trim()} onClick={sendQuestion}><span aria-hidden="true">↑</span></button></div>
        </div>
      </div>
    </section>
  );
}
