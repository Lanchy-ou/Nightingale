import { useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api } from '../api';
import type {
  DoctorConsultResult,
  DoctorTranscriptSegment,
  Patient,
  TranscriptNormalizeResult,
  TranscriptPreviewSegment,
} from '../types';

const DEMO_TRANSCRIPT = `DOCTOR: How has your headache changed?
PATIENT: It is better, about 3 out of 10, but I still feel nauseous in the morning.
DOCTOR: Have you completed the blood test?
PATIENT: Not yet.
DOCTOR: Please continue propranolol 20 mg daily while we chase the result.`;

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

function newOperation() {
  return {
    consultId: newOperationId('consult'),
    ingestionKey: newOperationId('submission'),
  };
}

function reindex(segments: TranscriptPreviewSegment[]): TranscriptPreviewSegment[] {
  return segments.map((segment, index) => ({ ...segment, index }));
}

function issueLabel(issue: string): string {
  if (issue.startsWith('unknown_speaker_label:')) return `Unknown speaker label: ${issue.split(':').slice(1).join(':')}`;
  const labels: Record<string, string> = {
    continuation_line: 'Continuation line grouped with the previous speaker',
    unowned_continuation: 'Text appears before any supported speaker label',
    empty_segment_text: 'Segment text is empty',
    user_edited: 'Canonical text edited during review',
    user_split: 'Segment split during review',
    user_merged: 'Segments merged during review',
    unmapped_source_range: 'Source range is unmapped after this edit (no exact original range)',
  };
  return labels[issue] ?? issue;
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
  const operation = useRef(newOperation());
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const cursorByIndex = useRef<Record<number, number>>({});
  const [text, setText] = useState('');
  const [startedAt, setStartedAt] = useState(localDateTimeValue);
  const [stage, setStage] = useState<'paste' | 'review'>('paste');
  const [normalization, setNormalization] = useState<TranscriptNormalizeResult | null>(null);
  const [segments, setSegments] = useState<TranscriptPreviewSegment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'normalizing' | 'submitting' | null>(null);
  const [submissionAttempted, setSubmissionAttempted] = useState(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    // patientId is a security/state boundary: no draft, preview, operation ID,
    // or pending response may cross into another patient workspace.
    abortRef.current?.abort();
    operation.current = newOperation();
    setText('');
    setStartedAt(localDateTimeValue());
    setStage('paste');
    setNormalization(null);
    setSegments([]);
    setError(null);
    setBusy(null);
    setSubmissionAttempted(false);
    cursorByIndex.current = {};
  }, [patient.patient_id]);

  const draftDirty = text.trim().length > 0;
  const wordCount = useMemo(
    () => text.trim().split(/\s+/).filter(Boolean).length,
    [text],
  );
  const blockingIssues = useMemo(() => {
    const issues: string[] = [];
    if (normalization?.outcome === 'REJECT') {
      issues.push(normalization.normalize_reason ?? 'Transcript was rejected');
    }
    if (segments.length === 0) issues.push('At least one canonical segment is required');
    if (segments.length > 500) issues.push('Canonical segment limit exceeded');
    segments.forEach((segment, index) => {
      if (segment.speaker_candidate === null) issues.push(`Segment ${index}: choose doctor or patient`);
      if (!segment.text.trim()) issues.push(`Segment ${index}: text cannot be empty`);
      if (segment.text.length > 4000) issues.push(`Segment ${index}: text exceeds 4000 characters`);
    });
    return issues;
  }, [normalization, segments]);
  const canConfirm = stage === 'review'
    && normalization?.outcome !== 'REJECT'
    && blockingIssues.length === 0
    && Boolean(startedAt)
    && busy === null;

  function resetOperationAfterEdit() {
    if (submissionAttempted) {
      operation.current = newOperation();
      setSubmissionAttempted(false);
    }
    setError(null);
  }

  function changeRawText(value: string) {
    resetOperationAfterEdit();
    setText(value);
    setNormalization(null);
    setSegments([]);
    setStage('paste');
  }

  function cancel() {
    if (draftDirty && !window.confirm('Discard this unsaved transcript draft?')) return;
    onCancel();
  }

  async function normalize() {
    setBusy('normalizing');
    setError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await api.normalizeTranscript(text, controller.signal);
      if (!mountedRef.current) return;
      setNormalization(result);
      setSegments(reindex(result.segments));
      setStage('review');
    } catch (caught: any) {
      if (!mountedRef.current || caught?.name === 'AbortError') return;
      if (caught instanceof ApiError) {
        setError(caught.body?.error?.message ?? caught.message);
      } else {
        setError(String(caught.message ?? caught));
      }
    } finally {
      if (mountedRef.current) setBusy(null);
    }
  }

  function updateSegment(index: number, update: Partial<TranscriptPreviewSegment>) {
    resetOperationAfterEdit();
    setSegments((current) => reindex(current.map((segment) => {
      if (segment.index !== index) return segment;
      const textEdited = update.text !== undefined;
      return {
        ...segment,
        ...update,
        // An arbitrary text edit no longer maps 1:1 to the raw source range,
        // so the range is cleared rather than shown as a pseudo-precise span.
        ...(textEdited ? { source_start: null, source_end: null } : {}),
        issues: textEdited
          ? [...new Set([...segment.issues, 'user_edited', 'unmapped_source_range'])]
          : segment.issues,
      };
    })));
  }

  function splitSegment(index: number) {
    const segment = segments[index];
    if (!segment) return;
    const remembered = cursorByIndex.current[index] ?? 0;
    const newline = segment.text.indexOf('\n');
    const midpoint = Math.floor(segment.text.length / 2);
    const leftSpace = segment.text.lastIndexOf(' ', midpoint);
    const rightSpace = segment.text.indexOf(' ', midpoint);
    const wordBoundary = leftSpace > 0
      && (rightSpace < 0 || midpoint - leftSpace <= rightSpace - midpoint)
      ? leftSpace
      : rightSpace > 0
        ? rightSpace
        : midpoint;
    const cursor = remembered > 0 && remembered < segment.text.length
      ? remembered
      : newline > 0
        ? newline
        : wordBoundary;
    const before = segment.text.slice(0, cursor).trimEnd();
    const after = segment.text.slice(cursor).trimStart();
    if (!before || !after) {
      setError('A split must leave non-empty text on both sides.');
      return;
    }
    resetOperationAfterEdit();
    // Exact remap: `before` is a prefix of the segment text and `after` is its
    // suffix, so when the segment still carries an exact raw range we can map
    // both halves precisely. Otherwise both halves are marked unmapped.
    const mapped = segment.source_start !== null && segment.source_end !== null
      ? { start: segment.source_start, end: segment.source_end }
      : null;
    const beforeIssues = [...new Set([...segment.issues, 'user_split'])];
    const afterIssues = [...new Set([...segment.issues, 'user_split'])];
    setSegments((current) => reindex([
      ...current.slice(0, index),
      {
        ...segment,
        text: before,
        source_start: mapped ? mapped.start : null,
        source_end: mapped ? mapped.start + before.length : null,
        issues: mapped ? beforeIssues : [...new Set([...beforeIssues, 'unmapped_source_range'])],
      },
      {
        ...segment,
        text: after,
        source_start: mapped ? mapped.end - after.length : null,
        source_end: mapped ? mapped.end : null,
        issues: mapped ? afterIssues : [...new Set([...afterIssues, 'unmapped_source_range'])],
      },
      ...current.slice(index + 1),
    ]));
  }

  function mergeWithPrevious(index: number) {
    if (index <= 0) return;
    resetOperationAfterEdit();
    setSegments((current) => {
      const previous = current[index - 1];
      const selected = current[index];
      const merged: TranscriptPreviewSegment = {
        ...previous,
        text: `${previous.text}\n${selected.text}`,
        // A merge spans the interleaving label line, so no exact raw range can
        // be reconstructed; clear it instead of showing a pseudo-precise span.
        source_start: null,
        source_end: null,
        confidence_marker: 'inferred_boundary',
        issues: [...new Set([...previous.issues, ...selected.issues, 'user_merged', 'unmapped_source_range'])],
      };
      return reindex([
        ...current.slice(0, index - 1),
        merged,
        ...current.slice(index + 1),
      ]);
    });
  }

  async function submit() {
    if (!canConfirm) return;
    const canonical: DoctorTranscriptSegment[] = segments.map((segment, index) => ({
      index,
      speaker: segment.speaker_candidate as 'doctor' | 'patient',
      text: segment.text.trim(),
    }));
    setBusy('submitting');
    setSubmissionAttempted(true);
    setError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await api.createDoctorConsult(
        patient.patient_id,
        operation.current.consultId,
        operation.current.ingestionKey,
        startedAt.length === 16 ? `${startedAt}:00` : startedAt,
        null,
        canonical,
        controller.signal,
      );
      if (mountedRef.current) onCompleted(result);
    } catch (caught: any) {
      if (!mountedRef.current || caught?.name === 'AbortError') return;
      if (caught instanceof ApiError) {
        setError(
          caught.status >= 500
            ? 'Derived processing failed. The confirmed raw transcript may already be saved; retry without editing uses the same idempotency identity.'
            : caught.body?.error?.message ?? caught.message,
        );
      } else {
        setError(String(caught.message ?? caught));
      }
    } finally {
      if (mountedRef.current) setBusy(null);
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

      <ol className="consult-steps" aria-label="Consult import progress">
        <li className={stage === 'paste' ? 'active' : 'complete'}><span>1</span>Paste transcript</li>
        <li className={stage === 'review' ? 'active' : ''}><span>2</span>Review segments</li>
        <li><span>3</span>Confirm and process</li>
      </ol>

      {stage === 'paste' && (
        <div className="consult-form-card">
          <label>
            Consult started
            <input
              type="datetime-local"
              value={startedAt}
              onChange={(event) => setStartedAt(event.target.value)}
              disabled={busy !== null}
            />
          </label>
          <div className="format-help">
            <strong>Manual text only · no audio, ASR, OCR, or timestamp inference</strong>
            <span>Supported labels include DOCTOR/PATIENT, case variants, and Dr/Pt. Unknown speakers remain unresolved for review.</span>
          </div>
          <label>
            Raw transcript
            <textarea
              value={text}
              onChange={(event) => changeRawText(event.target.value)}
              rows={12}
              placeholder={'DOCTOR: How have your symptoms changed?\nPATIENT: The headache is better.'}
              disabled={busy !== null}
            />
          </label>
          <div className="consult-form-actions">
            <button className="secondary-button" onClick={() => changeRawText(DEMO_TRANSCRIPT)} disabled={busy !== null}>
              Use synthetic demo
            </button>
            <span className="muted">{wordCount} words · raw preview is not persisted</span>
            <button className="primary-button" onClick={normalize} disabled={busy !== null || !text.trim()}>
              {busy === 'normalizing' ? 'Normalizing…' : 'Review transcript'}
            </button>
          </div>
        </div>
      )}

      {stage === 'review' && normalization && (
        <>
          <div className={`normalization-banner ${normalization.outcome.toLowerCase()}`}>
            <strong>{normalization.outcome}</strong>
            <span>
              {normalization.outcome === 'ACCEPT' && 'Deterministic parsing succeeded. Review before confirming.'}
              {normalization.outcome === 'NEEDS_REVIEW' && 'Resolve every unknown speaker and empty segment before confirming.'}
              {normalization.outcome === 'REJECT' && `Cannot safely normalize: ${normalization.normalize_reason ?? 'unsupported input'}. Edit the raw transcript and try again.`}
            </span>
            <small>{normalization.raw_byte_length} UTF-8 bytes · {segments.length} preview segments</small>
          </div>

          <div className="transcript-review-grid">
            <div className="raw-transcript-panel">
              <div className="preview-head"><h3>Submitted raw text</h3><span>Not persisted</span></div>
              <pre>{text}</pre>
            </div>
            <div className="transcript-preview">
              <div className="preview-head"><h3>Canonical preview</h3><span>Continuous indexes regenerated</span></div>
              {segments.map((segment) => (
                <article className={`preview-segment ${segment.speaker_candidate ?? 'unknown'}`} key={segment.index}>
                  <span className="segment-index">{segment.index}</span>
                  <label>
                    Speaker
                    <select
                      value={segment.speaker_candidate ?? ''}
                      onChange={(event) => updateSegment(segment.index, {
                        speaker_candidate: event.target.value === ''
                          ? null
                          : event.target.value as 'doctor' | 'patient',
                      })}
                      disabled={busy !== null || normalization.outcome === 'REJECT'}
                    >
                      <option value="">Needs review</option>
                      <option value="doctor">Doctor</option>
                      <option value="patient">Patient</option>
                    </select>
                  </label>
                  <label className="segment-text-field">
                    Text
                    <textarea
                      value={segment.text}
                      rows={Math.max(2, segment.text.split('\n').length)}
                      onChange={(event) => updateSegment(segment.index, { text: event.target.value })}
                      onSelect={(event) => { cursorByIndex.current[segment.index] = event.currentTarget.selectionStart; }}
                      onClick={(event) => { cursorByIndex.current[segment.index] = event.currentTarget.selectionStart; }}
                      onKeyUp={(event) => { cursorByIndex.current[segment.index] = event.currentTarget.selectionStart; }}
                      disabled={busy !== null || normalization.outcome === 'REJECT'}
                    />
                  </label>
                  <div className="segment-meta">
                    <span>{segment.confidence_marker}</span>
                    {segment.source_start !== null && segment.source_end !== null
                      ? <span>original chars {segment.source_start}–{segment.source_end}</span>
                      : <span>source range unmapped (user-modified)</span>}
                  </div>
                  {segment.issues.length > 0 && (
                    <ul className="segment-issues">
                      {segment.issues.map((issue) => <li key={issue}>{issueLabel(issue)}</li>)}
                    </ul>
                  )}
                  {normalization.outcome !== 'REJECT' && (
                    <div className="segment-actions">
                      <button className="secondary-button" onClick={() => splitSegment(segment.index)} disabled={busy !== null}>Split at cursor / midpoint</button>
                      {segment.index > 0 && <button className="secondary-button" onClick={() => mergeWithPrevious(segment.index)} disabled={busy !== null}>Merge with previous</button>}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </div>

          {blockingIssues.length > 0 && (
            <div className="review-blockers" role="alert">
              <strong>Confirmation blocked</strong>
              <ul>{blockingIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
            </div>
          )}

          <div className="consult-submit-card">
            <div className={`processing-step ${busy === 'submitting' ? 'active' : ''}`}>
              <span>1</span><div><strong>Commit immutable canonical Transcript</strong><small>New Event and raw source commit before derived work</small></div>
            </div>
            <div className="processing-step">
              <span>2</span><div><strong>Generate independent AI artifacts</strong><small>Redaction → existing provider/fallback path → exact spans</small></div>
            </div>
            <button className="secondary-button" onClick={() => { setStage('paste'); setError(null); }} disabled={busy !== null}>
              Back to raw text
            </button>
            <button className="primary-button" onClick={submit} disabled={!canConfirm}>
              {busy === 'submitting' ? 'Saving raw source and processing…' : 'Confirm and create Doctor Consult'}
            </button>
          </div>
        </>
      )}

      {error && <div className="form-error" role="alert">{error}</div>}
    </section>
  );
}
