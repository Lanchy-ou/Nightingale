import { useEffect, useReducer, useRef, useState } from 'react';
import {
  initialVoiceCaptureState,
  releaseVoiceResources,
  voiceCaptureReducer,
} from '../voiceCaptureMachine.js';

export interface CapturedAudio {
  blob: Blob;
  mimeType: string;
  durationMs: number;
}

export interface VoiceCaptureTransport {
  uploadAudio(audio: CapturedAudio, signal: AbortSignal): Promise<void>;
  requestTranscription(signal: AbortSignal): Promise<void>;
}

interface VoiceCaptureProps {
  /** Changes on patient, role or session switch; it is a hard cleanup boundary. */
  boundaryKey: string;
  transport?: VoiceCaptureTransport;
  onNeedsReview?: () => void;
  onCancel?: () => void;
}

function preferredMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  return [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
  ].find((mimeType) => MediaRecorder.isTypeSupported(mimeType));
}

function errorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'NotAllowedError') {
    return 'Microphone permission was denied.';
  }
  if (error instanceof Error) return error.message;
  return 'Voice capture failed.';
}

export default function VoiceCapture({
  boundaryKey,
  transport,
  onNeedsReview,
  onCancel,
}: VoiceCaptureProps) {
  const [state, dispatch] = useReducer(voiceCaptureReducer, undefined, initialVoiceCaptureState);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [audio, setAudio] = useState<CapturedAudio | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const timerRef = useRef<number | null>(null);
  const generationRef = useRef(0);

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
    releaseAll();
    setElapsedMs(0);
    setAudio(null);
    setPreviewUrl(null);
    dispatch({ type: 'RESET' });
    return releaseAll;
    // The boundary value, not the individual props, defines sensitive state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundaryKey]);

  async function startRecording() {
    releaseAll();
    setAudio(null);
    setPreviewUrl(null);
    setElapsedMs(0);
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

      const mimeType = preferredMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      const startedAt = performance.now();
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
        const blob = new Blob(chunks, { type: recorder.mimeType || 'application/octet-stream' });
        if (blob.size === 0) {
          dispatch({ type: 'FAIL', error: 'The recording is empty.', retryStatus: 'ready' });
          return;
        }
        const durationMs = Math.max(0, Math.round(performance.now() - startedAt));
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;
        setPreviewUrl(url);
        setAudio({ blob, mimeType: blob.type, durationMs });
        dispatch({ type: 'STOP' });
      };
      recorder.start();
      dispatch({ type: 'START' });
      timerRef.current = window.setInterval(
        () => setElapsedMs(Math.max(0, Math.round(performance.now() - startedAt))),
        250,
      );
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
    if (!transport || !audio) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current;

    try {
      if (!skipUpload) {
        dispatch({ type: 'UPLOAD' });
        await transport.uploadAudio(audio, controller.signal);
        if (generation !== generationRef.current) return;
        dispatch({ type: 'UPLOAD_COMPLETE' });
      }
      await transport.requestTranscription(controller.signal);
      if (generation !== generationRef.current) return;
      dispatch({ type: 'TRANSCRIPT_READY' });
      onNeedsReview?.();
    } catch (error) {
      if (generation !== generationRef.current || controller.signal.aborted) return;
      const retryStatus = skipUpload ? 'transcribing' : 'preview';
      dispatch({ type: 'FAIL', error: errorMessage(error), retryStatus });
    }
  }

  function retry() {
    const retryStatus = state.retryStatus;
    dispatch({ type: 'RETRY' });
    void submitAudio(retryStatus === 'transcribing');
  }

  function cancel() {
    releaseAll();
    setElapsedMs(0);
    setAudio(null);
    setPreviewUrl(null);
    dispatch({ type: 'RESET' });
    onCancel?.();
  }

  const elapsedSeconds = Math.floor(elapsedMs / 1000);
  const canStart = ['idle', 'permission_denied', 'ready'].includes(state.status);

  return (
    <section aria-label="Voice capture" className="voice-capture">
      <div aria-live="polite">
        <strong>Recording status:</strong> {state.status.replace(/_/g, ' ')}
        {state.status === 'recording' && <span> · {elapsedSeconds}s</span>}
      </div>

      {state.error && <p role="alert">{state.error}</p>}
      {canStart && (
        <button type="button" onClick={() => void startRecording()}>
          Start recording
        </button>
      )}
      {state.status === 'permission_pending' && <p>Waiting for microphone permission…</p>}
      {state.status === 'recording' && (
        <button type="button" onClick={stopRecording}>Stop recording</button>
      )}
      {previewUrl && <audio controls src={previewUrl}>Audio preview is unavailable.</audio>}
      {state.status === 'preview' && transport && (
        <button type="button" onClick={() => void submitAudio(false)}>Upload for transcription</button>
      )}
      {state.status === 'preview' && !transport && (
        <p>Recording preview is ready. No ASR transport is connected.</p>
      )}
      {state.status === 'failed' && state.retryStatus && (
        <button type="button" onClick={retry}>Retry</button>
      )}
      {state.status === 'needs_review' && <p>Transcript review is required before confirmation.</p>}

      <button type="button" onClick={cancel}>Cancel capture</button>
    </section>
  );
}
