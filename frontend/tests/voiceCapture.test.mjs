// E4 browser capture state and cleanup checks. Plain ESM for Node 18+.
import assert from 'node:assert/strict';
import {
  initialVoiceCaptureState,
  releaseVoiceResources,
  voiceCaptureReducer,
} from '../src/voiceCaptureMachine.js';

let state = initialVoiceCaptureState();
for (const event of [
  { type: 'REQUEST_PERMISSION' },
  { type: 'PERMISSION_GRANTED' },
  { type: 'START' },
  { type: 'STOP' },
  { type: 'UPLOAD' },
  { type: 'UPLOAD_COMPLETE' },
  { type: 'TRANSCRIPT_READY' },
  { type: 'CONFIRM' },
  { type: 'PROCESSED' },
]) {
  state = voiceCaptureReducer(state, event);
}
assert.equal(state.status, 'processed');

const denied = voiceCaptureReducer(
  voiceCaptureReducer(initialVoiceCaptureState(), { type: 'REQUEST_PERMISSION' }),
  { type: 'PERMISSION_DENIED', error: 'Microphone denied' },
);
assert.deepEqual(denied, {
  status: 'permission_denied',
  error: 'Microphone denied',
  retryStatus: null,
});

const recorderSetupFailure = voiceCaptureReducer(
  { status: 'ready', error: null, retryStatus: null },
  { type: 'FAIL', error: 'Recorder unavailable', retryStatus: 'ready' },
);
assert.equal(recorderSetupFailure.status, 'failed');
assert.equal(voiceCaptureReducer(recorderSetupFailure, { type: 'RETRY' }).status, 'ready');

let upload = voiceCaptureReducer(
  { status: 'preview', error: null, retryStatus: null },
  { type: 'UPLOAD' },
);
upload = voiceCaptureReducer(upload, {
  type: 'FAIL',
  error: 'Upload failed',
  retryStatus: 'preview',
});
assert.equal(upload.status, 'failed');
assert.equal(voiceCaptureReducer(upload, { type: 'RETRY' }).status, 'preview');

assert.throws(
  () => voiceCaptureReducer(initialVoiceCaptureState(), { type: 'CONFIRM' }),
  /invalid voice capture transition/,
);

let recorderStops = 0;
let trackStops = 0;
let aborts = 0;
const revoked = [];
const resources = {
  recorder: { state: 'recording', stop: () => { recorderStops += 1; } },
  stream: { getTracks: () => [{ stop: () => { trackStops += 1; } }] },
  objectUrl: 'blob:voice-demo',
  abortController: { abort: () => { aborts += 1; } },
};

releaseVoiceResources(resources, (url) => revoked.push(url));
assert.equal(recorderStops, 1, 'active recorder stopped');
assert.equal(trackStops, 1, 'microphone track stopped');
assert.equal(aborts, 1, 'pending request aborted');
assert.deepEqual(revoked, ['blob:voice-demo'], 'preview URL revoked');

console.log('voice capture checks passed');
