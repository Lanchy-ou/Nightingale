export type VoiceCaptureStatus =
  | 'idle'
  | 'permission_pending'
  | 'permission_denied'
  | 'ready'
  | 'recording'
  | 'preview'
  | 'uploading'
  | 'transcribing'
  | 'needs_review'
  | 'failed'
  | 'confirmed'
  | 'processed';

export interface VoiceCaptureState {
  status: VoiceCaptureStatus;
  error: string | null;
  retryStatus: VoiceCaptureStatus | null;
}

export type VoiceCaptureEvent =
  | { type: 'REQUEST_PERMISSION' }
  | { type: 'PERMISSION_GRANTED' }
  | { type: 'PERMISSION_DENIED'; error: string }
  | { type: 'START' }
  | { type: 'STOP' }
  | { type: 'UPLOAD' }
  | { type: 'UPLOAD_COMPLETE' }
  | { type: 'TRANSCRIPT_READY' }
  | { type: 'CONFIRM' }
  | { type: 'PROCESSED' }
  | { type: 'FAIL'; error: string; retryStatus: VoiceCaptureStatus | null }
  | { type: 'RETRY' }
  | { type: 'RESET' };

export interface VoiceResources {
  recorder: { state: string; stop(): void } | null;
  stream: { getTracks(): Array<{ stop(): void }> } | null;
  objectUrl: string | null;
  abortController: { abort(): void } | null;
}

export const VOICE_CAPTURE_STATUSES: readonly VoiceCaptureStatus[];
export function initialVoiceCaptureState(): VoiceCaptureState;
export function voiceCaptureReducer(
  state: VoiceCaptureState,
  event: VoiceCaptureEvent,
): VoiceCaptureState;
export function releaseVoiceResources(
  resources: VoiceResources,
  revokeObjectURL?: (url: string) => void,
): void;
