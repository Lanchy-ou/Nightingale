import assert from 'node:assert/strict';
import {
  initialPatientCheckInState,
  patientCheckInReducer,
  releasePatientCheckInRequest,
} from '../src/patientCheckInMachine.js';

let state = initialPatientCheckInState();
state = patientCheckInReducer(state, { type: 'READY' });
state = patientCheckInReducer(state, { type: 'SAVE', messageId: 'patient-message-stable-001' });
assert.equal(state.status, 'saving');
assert.equal(state.retryMessageId, 'patient-message-stable-001');
state = patientCheckInReducer(state, { type: 'SAVED', messageId: state.retryMessageId });
assert.equal(state.status, 'ai_working');
state = patientCheckInReducer(state, { type: 'FAIL', error: 'network lost' });
assert.equal(state.retryMessageId, 'patient-message-stable-001', 'retry preserves message id');

state = patientCheckInReducer(state, { type: 'AWAIT_CONFIRMATION' });
assert.equal(state.status, 'awaiting_confirmation');
state = patientCheckInReducer(state, { type: 'SUBMIT' });
state = patientCheckInReducer(state, { type: 'SUBMITTED' });
assert.equal(state.status, 'submitted');

state = patientCheckInReducer(state, { type: 'SAFETY' });
assert.equal(state.status, 'safety_escalated');

let aborts = 0;
releasePatientCheckInRequest({ abort: () => { aborts += 1; } });
assert.equal(aborts, 1, 'patient/role/session boundary aborts pending request');
assert.throws(
  () => patientCheckInReducer(state, { type: 'UNBOUNDED_CHAT' }),
  /unknown Patient Check-in event/,
);

console.log('patient Check-in state checks passed');
