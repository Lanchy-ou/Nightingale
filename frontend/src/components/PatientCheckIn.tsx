import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { api } from '../api';
import {
  initialPatientCheckInState,
  patientCheckInReducer,
  releasePatientCheckInRequest,
} from '../patientCheckInMachine.js';
import type {
  PatientCheckInIntent,
  PatientCheckInList,
  PatientCheckInSession,
} from '../types';
import VoiceCapture from './VoiceCapture';

type PendingMessage = { id: string; intent: PatientCheckInIntent; text: string };

function newId(prefix: string): string {
  const value = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${value}`;
}

function shortDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

function stateEvent(session: PatientCheckInSession) {
  if (session.status === 'safety_escalated') return { type: 'SAFETY' };
  if (session.status === 'awaiting_confirmation') return { type: 'AWAIT_CONFIRMATION' };
  if (session.status === 'submitted') return { type: 'SUBMITTED' };
  return { type: 'READY' };
}

export default function PatientCheckIn({
  patientId,
  roleKey,
  displayName,
  onBack,
}: {
  patientId: string;
  roleKey: string;
  displayName: string;
  onBack: () => void;
}) {
  const [machine, dispatch] = useReducer(patientCheckInReducer, undefined, initialPatientCheckInState);
  const [listing, setListing] = useState<PatientCheckInList>({ active_session_id: null, sessions: [] });
  const [current, setCurrent] = useState<PatientCheckInSession | null>(null);
  const [draft, setDraft] = useState('');
  const [intent, setIntent] = useState<PatientCheckInIntent>('answer');
  const [pending, setPending] = useState<PendingMessage | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const boundaryGenerationRef = useRef(0);
  const actionInFlightRef = useRef(false);

  function requestIsCurrent(controller: AbortController, generation: number): boolean {
    return boundaryGenerationRef.current === generation
      && requestRef.current === controller
      && !controller.signal.aborted;
  }

  const updateSession = useCallback((session: PatientCheckInSession) => {
    setCurrent(session);
    setListing((previous) => {
      const sessions = [session, ...previous.sessions.filter((item) => item.session_id !== session.session_id)]
        .sort((a, b) => b.started_at.localeCompare(a.started_at));
      return {
        active_session_id: ['active', 'awaiting_confirmation'].includes(session.status)
          ? session.session_id
          : previous.active_session_id === session.session_id ? null : previous.active_session_id,
        sessions,
      };
    });
    dispatch(stateEvent(session));
  }, []);

  const load = useCallback(async (controller: AbortController, generation: number) => {
    dispatch({ type: 'LOAD' });
    try {
      const next = await api.listPatientCheckIns(patientId, controller.signal);
      if (boundaryGenerationRef.current !== generation || requestRef.current !== controller) return;
      setListing(next);
      const active = next.sessions.find((session) => session.session_id === next.active_session_id) ?? null;
      setCurrent(active);
      dispatch(active ? stateEvent(active) : { type: 'READY' });
    } catch (error: any) {
      if (error?.name !== 'AbortError') {
        dispatch({ type: 'FAIL', error: String(error?.message ?? error) });
      }
    }
  }, [patientId]);

  useEffect(() => {
    // patient/role/auth-session identity is a hard boundary: abort requests and
    // remove every unsubmitted draft, pending id, AI response and selected history.
    releasePatientCheckInRequest(requestRef.current);
    const generation = boundaryGenerationRef.current + 1;
    boundaryGenerationRef.current = generation;
    actionInFlightRef.current = false;
    const controller = new AbortController();
    requestRef.current = controller;
    setDraft('');
    setIntent('answer');
    setPending(null);
    setCurrent(null);
    setListing({ active_session_id: null, sessions: [] });
    void load(controller, generation);
    return () => {
      boundaryGenerationRef.current += 1;
      actionInFlightRef.current = false;
      releasePatientCheckInRequest(controller);
      if (requestRef.current === controller) requestRef.current = null;
      setDraft('');
      setPending(null);
      setCurrent(null);
    };
  }, [patientId, roleKey, load]);

  async function start() {
    if (actionInFlightRef.current) return;
    actionInFlightRef.current = true;
    const generation = boundaryGenerationRef.current;
    releasePatientCheckInRequest(requestRef.current);
    const controller = new AbortController();
    requestRef.current = controller;
    dispatch({ type: 'LOAD' });
    try {
      const session = await api.startPatientCheckIn(patientId, newId('checkin'), controller.signal);
      if (requestIsCurrent(controller, generation)) updateSession(session);
    } catch (error: any) {
      if (error?.name !== 'AbortError' && requestIsCurrent(controller, generation)) {
        dispatch({ type: 'FAIL', error: String(error?.message ?? error) });
      }
    } finally {
      if (boundaryGenerationRef.current === generation) actionInFlightRef.current = false;
    }
  }

  async function transmit(message: PendingMessage) {
    if (!current || actionInFlightRef.current) return;
    actionInFlightRef.current = true;
    const generation = boundaryGenerationRef.current;
    releasePatientCheckInRequest(requestRef.current);
    const controller = new AbortController();
    requestRef.current = controller;
    let rawSaved = false;
    dispatch({ type: 'SAVE', messageId: message.id });
    try {
      const saved = await api.savePatientCheckInMessage(
        current.session_id, message.id, message.intent, message.text, controller.signal,
      );
      if (!requestIsCurrent(controller, generation)) return;
      rawSaved = true;
      setCurrent(saved);
      setDraft('');
      dispatch({ type: 'SAVED', messageId: message.id });
      const processed = await api.processPatientCheckInMessage(
        current.session_id, message.id, controller.signal,
      );
      if (!requestIsCurrent(controller, generation)) return;
      setPending(null);
      setIntent('answer');
      updateSession(processed);
    } catch (error: any) {
      if (error?.name === 'AbortError') return;
      if (!requestIsCurrent(controller, generation)) return;
      setPending(message);
      dispatch({
        type: 'FAIL',
        messageId: message.id,
        error: rawSaved
          ? 'Your words are safely saved, but Nightingale AI could not prepare the next question.'
          : 'We could not confirm that your words were saved. Retry will use the same message id.',
      });
    } finally {
      if (boundaryGenerationRef.current === generation) actionInFlightRef.current = false;
    }
  }

  function send(messageIntent: PatientCheckInIntent = intent) {
    if (!current || current.status !== 'active') return;
    const text = draft.trim();
    if (!text && !['skip', 'no_more'].includes(messageIntent)) return;
    const message = pending ?? { id: newId('patient-message'), intent: messageIntent, text };
    setPending(message);
    void transmit(message);
  }

  async function stateAction(action: 'finish' | 'resume' | 'abandon' | 'submit') {
    if (!current || actionInFlightRef.current) return;
    actionInFlightRef.current = true;
    const generation = boundaryGenerationRef.current;
    releasePatientCheckInRequest(requestRef.current);
    const controller = new AbortController();
    requestRef.current = controller;
    if (action === 'submit') dispatch({ type: 'SUBMIT' });
    try {
      let next: PatientCheckInSession;
      if (action === 'finish') next = await api.finishPatientCheckIn(current.session_id, current.status, controller.signal);
      else if (action === 'resume') next = await api.resumePatientCheckIn(current.session_id, current.status, controller.signal);
      else if (action === 'abandon') next = await api.abandonPatientCheckIn(current.session_id, current.status, controller.signal);
      else next = await api.submitPatientCheckIn(current.session_id, current.status, controller.signal);
      if (!requestIsCurrent(controller, generation)) return;
      setDraft('');
      setPending(null);
      if (action === 'abandon') {
        setListing((previous) => ({
          active_session_id: null,
          sessions: previous.sessions.filter((session) => session.session_id !== next.session_id),
        }));
        setCurrent(null);
        dispatch({ type: 'READY' });
      } else {
        updateSession(next);
      }
    } catch (error: any) {
      if (error?.name !== 'AbortError' && requestIsCurrent(controller, generation)) {
        dispatch({ type: 'FAIL', error: String(error?.message ?? error) });
      }
    } finally {
      if (boundaryGenerationRef.current === generation) actionInFlightRef.current = false;
    }
  }

  const historical = listing.sessions.filter((session) => !['active', 'awaiting_confirmation'].includes(session.status));

  return (
    <section className="patient-checkin-layout patient-checkin-multiturn">
      <aside className="patient-checkin-history">
        <button className="patient-back-home" onClick={onBack}>← Back to Today</button>
        <h2>Check-in</h2>
        <p>For non-emergency pre-visit or recovery updates. It cannot diagnose, prescribe, change a dose, or replace urgent care.</p>
        <h3>Previous Check-ins</h3>
        {historical.length === 0 ? <span className="patient-empty-compact">No previous Check-ins</span> : historical.map((session) => (
          <button
            className={`patient-session-row patient-session-button ${current?.session_id === session.session_id ? 'active' : ''}`}
            key={session.session_id}
            onClick={() => { setCurrent(session); dispatch(stateEvent(session)); }}
          >
            <strong>{shortDate(session.started_at)}</strong>
            <span>{session.status === 'safety_escalated' ? 'Safety guidance shown' : 'Submitted Check-in'}</span>
          </button>
        ))}
      </aside>

      <div className="patient-checkin-main">
        <header>
          <span className="patient-online-dot" aria-hidden="true" />
          <div><strong>Nightingale Check-in</strong><small>Bounded, non-emergency information collection</small></div>
        </header>

        <div className="patient-checkin-boundary" role="note">
          <strong>Before you begin</strong>
          <span>This is only for non-emergency pre-visit or recovery updates. It cannot diagnose, recommend medicine, adjust a dose, or replace emergency services.</span>
        </div>

        {machine.status === 'loading' && <div className="loading-card">Restoring your Check-in…</div>}

        {!current && machine.status !== 'loading' && (
          <div className="patient-checkin-start">
            <h2>Hi {displayName}. Share an update in your own words</h2>
            <p>Nightingale AI will ask one question at a time. You can correct, skip, add something new, or stop at any time.</p>
            <button onClick={start}>Start a Check-in</button>
          </div>
        )}

        {current && (
          <>
            {current.safety_escalated && (
              <div className="patient-checkin-safety" role="alert">
                <strong>Get urgent help now</strong>
                <p>{current.safety_message}</p>
              </div>
            )}

            <div className="patient-checkin-conversation" aria-live="polite">
              {current.messages.map((message) => (
                <div
                  className={`patient-checkin-bubble ${message.role === 'patient' ? 'patient' : 'ai'}`}
                  key={message.message_id}
                >
                  <small>{message.role === 'patient' ? 'Patient' : 'Nightingale AI'}</small>
                  <p>{message.text}</p>
                  {message.role === 'ai' && message.degraded && <em>Prepared with the safe fallback</em>}
                </div>
              ))}
              {machine.status === 'saving' && <div className="patient-checkin-progress">Saving your original words safely…</div>}
              {machine.status === 'ai_working' && <div className="patient-checkin-progress">Your words are saved. Nightingale AI is preparing one next question…</div>}
            </div>

            {current.status === 'active' && !['saving', 'ai_working'].includes(machine.status) && (
              <div className="patient-checkin-composer patient-checkin-composer-multiturn">
                <div className="patient-checkin-intents" aria-label="How this message should be handled">
                  {([
                    ['answer', 'Answer'], ['supplement', 'Add something'], ['correction', 'Correct something'],
                  ] as const).map(([value, label]) => (
                    <button key={value} className={intent === value ? 'active' : ''} onClick={() => { setIntent(value); setPending(null); }}>{label}</button>
                  ))}
                </div>
                <textarea
                  value={draft}
                  onChange={(event) => { setDraft(event.target.value); setPending(null); }}
                  placeholder={intent === 'correction' ? 'Tell us what should be corrected…' : 'Reply freely in your own words…'}
                  rows={4}
                />
                <div className="patient-checkin-composer-actions">
                  <button className="link-btn" onClick={() => send('skip')}>Skip this question</button>
                  <button className="link-btn" onClick={() => send('no_more')}>I have nothing else to add</button>
                  <button className="link-btn" onClick={() => void stateAction('finish')}>Finish now</button>
                  <button className="patient-checkin-send" onClick={() => send()} disabled={!draft.trim()}>Send</button>
                </div>
                <button className="patient-checkin-abandon" onClick={() => void stateAction('abandon')}>Abandon this Check-in</button>
              </div>
            )}

            {machine.status === 'failed' && (
              <div className="patient-checkin-failure" role="alert">
                <strong>Check-in paused</strong><p>{machine.error}</p>
                {pending && <button onClick={() => void transmit(pending)}>Retry the same saved message</button>}
              </div>
            )}

            {current.status === 'awaiting_confirmation' && (
              <div className="patient-checkin-confirmation">
                <p className="eyebrow">Before submitting</p>
                <h2>What you just told us</h2>
                <ul>{current.preview_summary.map((text, index) => <li key={`${index}:${text}`}>{text}</li>)}</ul>
                <details><summary>View my original messages</summary>
                  {current.messages.filter((message) => message.role === 'patient').map((message) => <p key={message.message_id}>{message.text}</p>)}
                </details>
                <p>This recap comes from your saved messages. You cannot edit it directly; go back to add or correct your words.</p>
                <div><button className="secondary-button" onClick={() => void stateAction('resume')}>Go back to add or correct</button><button onClick={() => void stateAction('submit')} disabled={current.preview_summary.length === 0}>Confirm and submit</button></div>
              </div>
            )}

            {current.status === 'submitted' && (
              <div className="patient-checkin-submitted">
                <strong>Check-in submitted</strong>
                <p>Your saved words are now available to your care team for review. This did not change your care plan or complete a Task.</p>
                <button onClick={() => { setCurrent(null); dispatch({ type: 'READY' }); }}>Back to Check-in home</button>
              </div>
            )}

            {current.status === 'active' && (
              <VoiceCapture
                boundaryKey={`${roleKey}:${patientId}:voice-checkin`}
                patientId={patientId}
                captureMode="patient_session"
                patientEventType="patient_followup"
                onProcessed={() => {
                  releasePatientCheckInRequest(requestRef.current);
                  const controller = new AbortController();
                  requestRef.current = controller;
                  void load(controller, boundaryGenerationRef.current);
                }}
              />
            )}
          </>
        )}
      </div>
    </section>
  );
}
