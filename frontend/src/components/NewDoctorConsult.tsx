import { useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api } from '../api';
import type { DoctorConsultResult, DoctorTranscriptSegment, Patient } from '../types';

const DEMO_TRANSCRIPT = `DOCTOR: How has your headache changed?
PATIENT: It is better, about 3 out of 10, but I still feel nauseous in the morning.
DOCTOR: Have you completed the blood test?
PATIENT: Not yet.
DOCTOR: Please continue propranolol 20 mg daily while we chase the result.`;

export function parseDoctorTranscript(input: string): DoctorTranscriptSegment[] {
  const lines = input.split(/\r?\n/);
  const segments: DoctorTranscriptSegment[] = [];
  for (let lineNumber = 0; lineNumber < lines.length; lineNumber += 1) {
    const line = lines[lineNumber].trim();
    if (!line) continue;
    const match = /^(DOCTOR|PATIENT)\s*:\s*(.*)$/i.exec(line);
    if (!match) {
      throw new Error(`Line ${lineNumber + 1}: expected DOCTOR: or PATIENT:.`);
    }
    const text = match[2].trim();
    if (!text) throw new Error(`Line ${lineNumber + 1}: speaker text cannot be empty.`);
    segments.push({
      index: segments.length,
      speaker: match[1].toLowerCase() as 'doctor' | 'patient',
      text,
    });
  }
  if (segments.length === 0) throw new Error('Add at least one labelled transcript line.');
  return segments;
}

function localDateTimeValue(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function newOperationId(prefix: string): string {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${random}`;
}

export default function NewDoctorConsult({
  patient,
  onCancel,
  onCompleted,
}: {
  patient: Patient;
  onCancel: () => void;
  onCompleted: (result: DoctorConsultResult) => void;
}) {
  const operation = useRef({
    consultId: newOperationId('consult'),
    ingestionKey: newOperationId('submission'),
  });
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const [text, setText] = useState('');
  const [startedAt, setStartedAt] = useState(localDateTimeValue);
  const [preview, setPreview] = useState<DoctorTranscriptSegment[] | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // React StrictMode runs a development setup/cleanup probe; reset the flag
    // on every real setup so a valid response is never mistaken for stale.
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const draftDirty = text.trim().length > 0;
  const wordCount = useMemo(
    () => text.trim().split(/\s+/).filter(Boolean).length,
    [text],
  );

  function validate() {
    try {
      const parsed = parseDoctorTranscript(text);
      setPreview(parsed);
      setValidationError(null);
    } catch (error: any) {
      setPreview(null);
      setValidationError(String(error.message ?? error));
    }
  }

  function cancel() {
    if (draftDirty && !window.confirm('Discard this unsaved transcript draft?')) return;
    onCancel();
  }

  async function submit() {
    let segments: DoctorTranscriptSegment[];
    try {
      segments = parseDoctorTranscript(text);
      setPreview(segments);
      setValidationError(null);
    } catch (error: any) {
      setValidationError(String(error.message ?? error));
      return;
    }

    setBusy(true);
    setSubmitError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await api.createDoctorConsult(
        patient.patient_id,
        operation.current.consultId,
        operation.current.ingestionKey,
        // Backend demo timestamps are stored as clinic-local naive datetimes;
        // preserve the clinician's datetime-local value instead of shifting it
        // through UTC and corrupting the real-world Event time axis.
        startedAt.length === 16 ? `${startedAt}:00` : startedAt,
        null,
        segments,
        controller.signal,
      );
      if (mountedRef.current) onCompleted(result);
    } catch (error: any) {
      if (!mountedRef.current || error?.name === 'AbortError') return;
      if (error instanceof ApiError) {
        setSubmitError(
          error.status >= 500
            ? 'Derived processing failed. The raw transcript may already be saved; retry uses the same idempotency identity.'
            : error.body?.error?.message ?? error.message,
        );
      } else {
        setSubmitError(String(error.message ?? error));
      }
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  }

  return (
    <section className="new-consult clinical-view" aria-labelledby="new-consult-title">
      <button className="back-button" onClick={cancel}>← Back to patient</button>
      <div className="view-title-row">
        <div>
          <p className="eyebrow">New real-world event</p>
          <h2 id="new-consult-title">New Doctor Consult</h2>
          <p className="view-subtitle">{patient.name} · {patient.clinic_name}</p>
        </div>
      </div>

      <div className="consult-form-card">
        <label>
          Consult started
          <input
            type="datetime-local"
            value={startedAt}
            onChange={(event) => setStartedAt(event.target.value)}
            disabled={busy}
          />
        </label>
        <div className="format-help">
          <strong>Manual speaker-labelled text only</strong>
          <span>Each non-empty line must begin with <code>DOCTOR:</code> or <code>PATIENT:</code>. No timestamps are inferred.</span>
        </div>
        <label>
          Transcript
          <textarea
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setPreview(null);
              setValidationError(null);
            }}
            rows={12}
            placeholder={'DOCTOR: How have your symptoms changed?\nPATIENT: The headache is better.'}
            disabled={busy}
          />
        </label>
        <div className="consult-form-actions">
          <button className="secondary-button" onClick={() => setText(DEMO_TRANSCRIPT)} disabled={busy}>
            Use synthetic demo
          </button>
          <span className="muted">{wordCount} words · draft is not stored locally</span>
          <button className="secondary-button" onClick={validate} disabled={busy || !text.trim()}>
            Validate & preview
          </button>
        </div>
        {validationError && <div className="form-error" role="alert">{validationError}</div>}
      </div>

      {preview && (
        <div className="transcript-preview" aria-live="polite">
          <div className="preview-head">
            <h3>Structured preview</h3>
            <span>{preview.length} continuous segments</span>
          </div>
          {preview.map((segment) => (
            <div className={`preview-segment ${segment.speaker}`} key={segment.index}>
              <span>{segment.index}</span>
              <strong>{segment.speaker}</strong>
              <p>{segment.text}</p>
            </div>
          ))}
        </div>
      )}

      <div className="consult-submit-card">
        <div className={`processing-step ${busy ? 'active' : ''}`}>
          <span>1</span><div><strong>Save immutable raw transcript</strong><small>Event and source commit before derived processing</small></div>
        </div>
        <div className="processing-step">
          <span>2</span><div><strong>Generate AI summary and highlights</strong><small>Redaction → existing LLM/fallback pipeline → exact spans</small></div>
        </div>
        <button className="primary-button" onClick={submit} disabled={busy || !preview || !startedAt}>
          {busy ? 'Saving source and processing…' : 'Create Doctor Consult'}
        </button>
        {submitError && <div className="form-error" role="alert">{submitError}</div>}
      </div>
    </section>
  );
}
