export type PatientCheckInUiStatus =
  | 'loading' | 'ready' | 'saving' | 'ai_working' | 'awaiting_confirmation'
  | 'submitting' | 'submitted' | 'safety_escalated' | 'failed';

export interface PatientCheckInUiState {
  status: PatientCheckInUiStatus;
  error: string | null;
  retryMessageId: string | null;
}

export function initialPatientCheckInState(): PatientCheckInUiState;
export function patientCheckInReducer(state: PatientCheckInUiState, event: Record<string, any>): PatientCheckInUiState;
export function releasePatientCheckInRequest(controller: AbortController | null): void;
