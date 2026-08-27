export const VOICE_CAPTURE_STATUSES = Object.freeze([
  'idle',
  'permission_pending',
  'permission_denied',
  'ready',
  'recording',
  'preview',
  'uploading',
  'transcribing',
  'needs_review',
  'failed',
  'confirmed',
  'processed',
]);

export function initialVoiceCaptureState() {
  return { status: 'idle', error: null, retryStatus: null };
}

const transitions = {
  REQUEST_PERMISSION: new Map([
    ['idle', 'permission_pending'],
    ['permission_denied', 'permission_pending'],
    ['ready', 'permission_pending'],
  ]),
  PERMISSION_GRANTED: new Map([['permission_pending', 'ready']]),
  PERMISSION_DENIED: new Map([['permission_pending', 'permission_denied']]),
  START: new Map([['ready', 'recording']]),
  STOP: new Map([['recording', 'preview']]),
  UPLOAD: new Map([['preview', 'uploading']]),
  UPLOAD_COMPLETE: new Map([['uploading', 'transcribing']]),
  TRANSCRIPT_READY: new Map([['transcribing', 'needs_review']]),
  CONFIRM: new Map([['needs_review', 'confirmed']]),
  PROCESSED: new Map([['confirmed', 'processed']]),
};

export function voiceCaptureReducer(state, event) {
  if (event.type === 'RESET') return initialVoiceCaptureState();

  if (event.type === 'FAIL') {
    if (!['permission_pending', 'ready', 'recording', 'uploading', 'transcribing'].includes(state.status)) {
      throw new Error(`invalid voice capture transition: ${state.status} -> failed`);
    }
    return {
      status: 'failed',
      error: event.error || 'Voice capture failed',
      retryStatus: event.retryStatus ?? null,
    };
  }

  if (event.type === 'RETRY') {
    if (state.status !== 'failed' || state.retryStatus === null) {
      throw new Error(`invalid voice capture transition: ${state.status} -> retry`);
    }
    return { status: state.retryStatus, error: null, retryStatus: null };
  }

  const transition = transitions[event.type];
  const target = transition?.get(state.status);
  if (!target) {
    throw new Error(`invalid voice capture transition: ${state.status} -> ${event.type}`);
  }
  return {
    status: target,
    error: event.error ?? null,
    retryStatus: null,
  };
}

export function releaseVoiceResources(resources, revokeObjectURL = URL.revokeObjectURL) {
  const { recorder, stream, objectUrl, abortController } = resources;
  if (recorder && recorder.state !== 'inactive') recorder.stop();
  if (stream) {
    for (const track of stream.getTracks()) track.stop();
  }
  if (objectUrl) revokeObjectURL(objectUrl);
  if (abortController) abortController.abort();
}
