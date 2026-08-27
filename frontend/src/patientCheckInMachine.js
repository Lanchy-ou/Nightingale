export function initialPatientCheckInState() {
  return { status: 'loading', error: null, retryMessageId: null };
}

export function patientCheckInReducer(state, event) {
  switch (event.type) {
    case 'LOAD': return { status: 'loading', error: null, retryMessageId: null };
    case 'READY': return { status: 'ready', error: null, retryMessageId: null };
    case 'SAVE': return { status: 'saving', error: null, retryMessageId: event.messageId };
    case 'SAVED': return { status: 'ai_working', error: null, retryMessageId: event.messageId };
    case 'AWAIT_CONFIRMATION': return { status: 'awaiting_confirmation', error: null, retryMessageId: null };
    case 'SUBMIT': return { status: 'submitting', error: null, retryMessageId: null };
    case 'SUBMITTED': return { status: 'submitted', error: null, retryMessageId: null };
    case 'SAFETY': return { status: 'safety_escalated', error: null, retryMessageId: null };
    case 'FAIL': return { status: 'failed', error: event.error, retryMessageId: event.messageId ?? state.retryMessageId };
    case 'RESET': return initialPatientCheckInState();
    default: throw new Error(`unknown Patient Check-in event: ${event.type}`);
  }
}

export function releasePatientCheckInRequest(controller) {
  controller?.abort?.();
}
