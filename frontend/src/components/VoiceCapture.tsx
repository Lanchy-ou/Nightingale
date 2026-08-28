import { useEffect, useReducer, useRef, useState } from 'react';
import { api } from '../api';
import type {
  VoiceCapabilities,
  VoiceCaptureMode,
  VoiceCaptureRecord,
  VoiceReviewedSegment,
} from '../types';
import {
  initialVoiceCaptureState,
  releaseVoiceResources,
  voiceCaptureReducer,
} from '../voiceCaptureMachine.js';

interface ReviewDraft extends VoiceReviewedSegment {
  resolvedIssues: string[];
}

interface VoiceCaptureProps {
  boundaryKey: string;
  patientId: string;
  captureMode: VoiceCaptureMode;
  encounterId?: string | null;
  patientEventType?: 'patient_ai_preconsult' | 'patient_followup';
  onProcessed: (capture: VoiceCaptureRecord) => void;
}

function operationKey(prefix: string): string {
  const id = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${id}`.slice(0, 64);
}

function preferredMimeType(capabilities: VoiceCapabilities): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  const browserChoices = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg',
  ];
  return browserChoices.find((candidate) => {
    const base = candidate.split(';', 1)[0];
    return capabilities.accepted_mime_types.includes(base)
      && MediaRecorder.isTypeSupported(candidate);
  });
}

function errorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'NotAllowedError') {
    return 'Microphone permission was denied.';
  }
  if (error instanceof Error) return error.message;
  return 'Voice capture failed.';
}

function speakerOptions(mode: VoiceCaptureMode): string[] {
  if (mode === 'doctor_consult') return ['doctor', 'patient'];
  if (mode === 'nurse_consult') return ['nurse', 'patient'];
  // Local ASR never observes an AI/system voice, so Patient Check-in cannot
  // invent one during review.
  return ['patient'];
}

function formatRange(segment: VoiceReviewedSegment): string {
  if (segment.source_start_ms === null || segment.source_end_ms === null) return 'Time unavailable';
  return `${(segment.source_start_ms / 1000).toFixed(1)}–${(segment.source_end_ms / 1000).toFixed(1)}s`;
}

export default function VoiceCapture({
  boundaryKey,
  patientId,
  captureMode,
  encounterId = null,
  patientEventType,
  onProcessed,
}: VoiceCaptureProps) {
  const [state, dispatch] = useReducer(voiceCaptureReducer, undefined, initialVoiceCaptureState);
  const [capabilities, setCapabilities] = useState<VoiceCapabilities | null>(null);
  const [capabilitiesError, setCapabilitiesError] = useState(false);
  const [consent, setConsent] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [audio, setAudio] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [capture, setCapture] = useState<VoiceCaptureRecord | null>(null);
  const [drafts, setDrafts] = useState<ReviewDraft[]>([]);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const timerRef = useRef<number | null>(null);
  const generationRef = useRef(0);
  const keysRef = useRef({ create: '', upload: '', transcribe: '', confirm: '' });
  const startedAtRef = useRef<string>('');
  const endedAtRef = useRef<string | null>(null);

  function stopTimer() {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
  }

  function releaseAll() {
    generationRef.current += 1;
    stopTimer();
    if (recorderRef.current) recorderRef.current.onstop = null;
    releaseVoiceResources({
      recorder: recorderRef.current,
      stream: streamRef.current,
      objectUrl: objectUrlRef.current,
      abortController: abortRef.current,
    });
    recorderRef.current = null;
    streamRef.current = null;
    objectUrlRef.current = null;
    abortRef.current = null;
  }

  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => api.getVoiceCapabilities(controller.signal)
      .then((next) => { setCapabilities(next); setCapabilitiesError(false); })
      .catch((error: any) => {
        if (error?.name !== 'AbortError') setCapabilitiesError(true);
      });
    void refresh();
    const poll = window.setInterval(() => void refresh(), 10_000);
    return () => { window.clearInterval(poll); controller.abort(); };
  }, [boundaryKey]);

  useEffect(() => {
    if (!capabilities || (
      capabilities.enabled
      && capabilities.asr_ready
      && capabilities.allowed_modes.includes(captureMode)
    )) return;
    releaseAll();
    setConsent(false);
    setAudio(null);
    setPreviewUrl(null);
    setCapture(null);
    setDrafts([]);
    dispatch({ type: 'RESET' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capabilities?.enabled, capabilities?.asr_ready, capabilities?.allowed_modes.join(','), captureMode]);

  useEffect(() => {
    releaseAll();
    setConsent(false);
    setElapsedMs(0);
    setAudio(null);
    setPreviewUrl(null);
    setCapture(null);
    setDrafts([]);
    setReviewError(null);
    dispatch({ type: 'RESET' });
    return releaseAll;
    // boundaryKey contains patient, role and session identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundaryKey, patientId, captureMode]);

  if (capabilities && !capabilities.eligible_modes.includes(captureMode)) {
    return null;
  }
  if (!capabilities || !capabilities.enabled || !capabilities.asr_ready) {
    const reason = capabilitiesError
      ? 'Voice status is unavailable.'
      : capabilities?.disabled_reason === 'model_not_ready'
        ? 'The local speech model is not installed. Ask an Admin to prepare it.'
        : capabilities
          ? 'Voice Capture is disabled by Admin.'
          : 'Checking Voice Capture status…';
    return (
      <section aria-label="Voice capture" className="voice-capture voice-capture-product voice-capture-unavailable">
        <div className="voice-capture-heading"><div><p className="eyebrow">Local voice adapter</p><h2>Record and review</h2></div><span>Unavailable</span></div>
        <p>{reason}</p>
      </section>
    );
  }
  if (!capabilities.allowed_modes.includes(captureMode)) return null;
  const activeCapabilities = capabilities;

  async function startRecording() {
    if (!consent) return;
    releaseAll();
    setAudio(null);
    setPreviewUrl(null);
    setCapture(null);
    setDrafts([]);
    setReviewError(null);
    setElapsedMs(0);
    keysRef.current = {
      create: operationKey('capture'),
      upload: operationKey('upload'),
      transcribe: operationKey('transcribe'),
      confirm: operationKey('confirm'),
    };
    dispatch({ type: 'REQUEST_PERMISSION' });
    const generation = generationRef.current;

    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
        throw new Error('Audio recording is not supported in this browser.');
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (generation !== generationRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      dispatch({ type: 'PERMISSION_GRANTED' });

      const mimeType = preferredMimeType(activeCapabilities);
      if (!mimeType) throw new Error('This browser cannot produce an accepted audio format.');
      const recorder = new MediaRecorder(stream, { mimeType });
      const chunks: BlobPart[] = [];
      const started = performance.now();
      startedAtRef.current = new Date().toISOString();
      endedAtRef.current = null;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      recorder.onstop = () => {
        if (generation !== generationRef.current) return;
        stopTimer();
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        endedAtRef.current = new Date().toISOString();
        const blob = new Blob(chunks, { type: recorder.mimeType });
        if (blob.size === 0) {
          dispatch({ type: 'FAIL', error: 'The recording is empty.', retryStatus: 'ready' });
          return;
        }
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;
        setPreviewUrl(url);
        setAudio(blob);
        setElapsedMs(Math.max(0, Math.round(performance.now() - started)));
        dispatch({ type: 'STOP' });
      };
      recorder.start();
      dispatch({ type: 'START' });
      timerRef.current = window.setInterval(() => {
        const next = Math.max(0, Math.round(performance.now() - started));
        setElapsedMs(next);
        if (next >= activeCapabilities.max_duration_ms && recorder.state === 'recording') recorder.stop();
      }, 250);
    } catch (error) {
      if (generation !== generationRef.current) return;
      stopTimer();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      recorderRef.current = null;
      const message = errorMessage(error);
      if (error instanceof DOMException && error.name === 'NotAllowedError') {
        dispatch({ type: 'PERMISSION_DENIED', error: message });
      } else {
        dispatch({ type: 'FAIL', error: message, retryStatus: 'ready' });
      }
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
  }

  async function submitAudio(skipUpload = false) {
    if (!audio) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current;
    let transcriptionAttempted = skipUpload;
    try {
      let current = capture;
      if (!skipUpload) {
        dispatch({ type: 'UPLOAD' });
        current = await api.createVoiceCapture({
          idempotency_key: keysRef.current.create,
          patient_id: patientId,
          capture_mode: captureMode,
          ...(patientEventType ? { patient_event_type: patientEventType } : {}),
          started_at: startedAtRef.current,
          ended_at: endedAtRef.current,
          ...(encounterId ? { encounter_id: encounterId } : {}),
        }, controller.signal);
        current = await api.uploadVoiceAudio(
          current.capture_id,
          audio,
          current.revision,
          keysRef.current.upload,
          controller.signal,
        );
        if (generation !== generationRef.current) return;
        setCapture(current);
        dispatch({ type: 'UPLOAD_COMPLETE' });
      }
      if (!current) throw new Error('The voice capture is not ready to transcribe.');
      if (skipUpload) keysRef.current.transcribe = operationKey('transcribe');
      transcriptionAttempted = true;
      current = await api.transcribeVoiceCapture(
        current.capture_id,
        current.revision,
        keysRef.current.transcribe,
        controller.signal,
      );
      if (generation !== generationRef.current) return;
      setCapture(current);
      if (current.status !== 'needs_review' || !current.reviewed_segments) {
        throw new Error(`Transcription failed: ${current.failure_reason ?? 'ASR unavailable'}`);
      }
      setDrafts(current.reviewed_segments.map((segment) => ({
        ...segment,
        resolvedIssues: [],
      })));
      dispatch({ type: 'TRANSCRIPT_READY' });
    } catch (error) {
      if (generation !== generationRef.current || controller.signal.aborted) return;
      const retryStatus = transcriptionAttempted ? 'transcribing' : 'preview';
      dispatch({ type: 'FAIL', error: errorMessage(error), retryStatus });
    }
  }

  function retry() {
    const retryStatus = state.retryStatus;
    dispatch({ type: 'RETRY' });
    void submitAudio(retryStatus === 'transcribing');
  }

  function updateDraft(index: number, update: Partial<ReviewDraft>) {
    setDrafts((current) => current.map((draft, draftIndex) => (
      draftIndex === index ? { ...draft, ...update } : draft
    )));
  }

  function splitDraft(index: number) {
    setDrafts((current) => {
      const target = current[index];
      const midpoint = Math.floor(target.text.length / 2);
      const splitAt = target.text.indexOf(' ', midpoint);
      if (splitAt <= 0 || splitAt >= target.text.length - 1) return current;
      const parts = [target.text.slice(0, splitAt).trim(), target.text.slice(splitAt + 1).trim()];
      const replacements = parts.map((text) => ({ ...target, text, audio_range_exact: false }));
      return [...current.slice(0, index), ...replacements, ...current.slice(index + 1)]
        .map((draft, nextIndex) => ({ ...draft, index: nextIndex }));
    });
  }

  function mergeWithNext(index: number) {
    setDrafts((current) => {
      if (index >= current.length - 1) return current;
      const left = current[index];
      const right = current[index + 1];
      const resolvedIssues = left.resolvedIssues.filter((issue) => right.resolvedIssues.includes(issue));
      const merged: ReviewDraft = {
        ...left,
        source_machine_segment_ids: [...new Set([
          ...left.source_machine_segment_ids,
          ...right.source_machine_segment_ids,
        ])],
        speaker: left.speaker === right.speaker ? left.speaker : null,
        text: `${left.text} ${right.text}`.trim(),
        source_start_ms: null,
        source_end_ms: null,
        confidence: null,
        issues: [...new Set([...left.issues, ...right.issues])],
        resolvedIssues,
        audio_range_exact: false,
      };
      return [...current.slice(0, index), merged, ...current.slice(index + 2)]
        .map((draft, nextIndex) => ({ ...draft, index: nextIndex }));
    });
  }

  async function confirmAndProcess() {
    if (!capture) return;
    setReviewBusy(true);
    setReviewError(null);
    try {
      const reviewed = await api.reviewVoiceSegments(
        capture.capture_id,
        capture.revision,
        drafts.map((draft) => ({
          source_machine_segment_ids: draft.source_machine_segment_ids,
          speaker: draft.speaker,
          text: draft.text,
          resolved_issues: draft.resolvedIssues,
          speaker_source_verified: false,
        })),
      );
      setCapture(reviewed);
      const processed = await api.confirmVoiceCapture(
        reviewed.capture_id,
        reviewed.revision,
        keysRef.current.confirm,
      );
      setCapture(processed);
      dispatch({ type: 'CONFIRM' });
      dispatch({ type: 'PROCESSED' });
      onProcessed(processed);
    } catch (error) {
      setReviewError(errorMessage(error));
    } finally {
      setReviewBusy(false);
    }
  }

  function cancel() {
    releaseAll();
    setConsent(false);
    setElapsedMs(0);
    setAudio(null);
    setPreviewUrl(null);
    setCapture(null);
    setDrafts([]);
    setReviewError(null);
    dispatch({ type: 'RESET' });
  }

  const elapsedSeconds = Math.floor(elapsedMs / 1000);
  const canStart = ['idle', 'permission_denied', 'ready'].includes(state.status);

  return (
    <section aria-label="Voice capture" className="voice-capture voice-capture-product">
      <div className="voice-capture-heading">
        <div><p className="eyebrow">Local voice adapter</p><h2>Record and review</h2></div>
        <span>Base multilingual · local CPU</span>
      </div>
      <p>For this synthetic Demo only. Audio stays in the encrypted Nightingale database and is not sent to the Summary model.</p>
      <label className="voice-consent">
        <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} disabled={state.status === 'recording'} />
        Everyone present has agreed to this synthetic recording.
      </label>
      <div aria-live="polite"><strong>Status:</strong> {state.status.replace(/_/g, ' ')}{state.status === 'recording' && <span> · {elapsedSeconds}s</span>}</div>
      {state.error && <p role="alert" className="form-error">{state.error}</p>}
      <div className="voice-actions">
        {canStart && <button type="button" disabled={!consent} onClick={() => void startRecording()}>Start recording</button>}
        {state.status === 'permission_pending' && <span>Waiting for microphone permission…</span>}
        {state.status === 'recording' && <button type="button" onClick={stopRecording}>Stop recording</button>}
        {state.status === 'preview' && <button type="button" onClick={() => void submitAudio(false)}>Upload and transcribe locally</button>}
        {state.status === 'failed' && state.retryStatus && <button type="button" onClick={retry}>Retry</button>}
        <button type="button" className="secondary-button" onClick={cancel}>Cancel</button>
      </div>
      {previewUrl && <audio controls src={previewUrl}>Audio preview is unavailable.</audio>}

      {state.status === 'needs_review' && (
        <div className="voice-review">
          <header><h3>Review every segment</h3><p>Local ASR does not guess speakers. Assign a permitted speaker and explicitly resolve each issue before confirmation.</p></header>
          {capture?.machine_transcript && <small>{capture.machine_transcript.provider} · {capture.machine_transcript.language ?? 'language unavailable'} · confidence is shown only when observed</small>}
          {drafts.map((draft, index) => (
            <article className="voice-segment" key={`${draft.source_machine_segment_ids.join(':')}:${index}`}>
              <div className="voice-segment-meta"><strong>Segment {index + 1}</strong><span>{formatRange(draft)}</span><span>{draft.confidence === null ? 'Confidence unavailable' : `Confidence ${Math.round(draft.confidence * 100)}%`}</span></div>
              <label>Speaker<select value={draft.speaker ?? ''} onChange={(event) => updateDraft(index, { speaker: event.target.value || null })}><option value="">Select speaker</option>{speakerOptions(captureMode).map((speaker) => <option key={speaker} value={speaker}>{speaker}</option>)}</select></label>
              <label>Transcript<textarea rows={3} value={draft.text} onChange={(event) => updateDraft(index, { text: event.target.value })} /></label>
              {draft.issues.length > 0 && <fieldset><legend>Observed issues</legend>{draft.issues.map((issue) => <label key={issue}><input type="checkbox" checked={draft.resolvedIssues.includes(issue)} onChange={(event) => updateDraft(index, { resolvedIssues: event.target.checked ? [...draft.resolvedIssues, issue] : draft.resolvedIssues.filter((item) => item !== issue) })} />Reviewed and resolved: {issue.replace(/_/g, ' ')}</label>)}</fieldset>}
              <div className="voice-segment-actions"><button type="button" onClick={() => splitDraft(index)}>Split</button>{index < drafts.length - 1 && <button type="button" onClick={() => mergeWithNext(index)}>Merge with next</button>}</div>
            </article>
          ))}
          {reviewError && <p className="form-error" role="alert">Review failed: {reviewError}</p>}
          <button type="button" className="primary-button" disabled={reviewBusy || drafts.length === 0} onClick={() => void confirmAndProcess()}>{reviewBusy ? 'Confirming…' : 'Confirm transcript and process'}</button>
        </div>
      )}
    </section>
  );
}
