import type {
  Artifact,
  AdminAccessAudit,
  AdminUser,
  AdminSystemSettings,
  ArtifactVersion,
  AuditLog,
  Comment,
  CurrentIdentity,
  DiffResult,
  DoctorConsultResult,
  DoctorTranscriptSegment,
  NurseConsultResult,
  NurseTranscriptSegment,
  Event,
  Highlight,
  InviteCreated,
  InviteInfo,
  InvitePreview,
  Patient,
  ClinicalTask,
  CopilotCategory,
  CopilotResponse,
  PatientTask,
  PatientCheckInIntent,
  PatientCheckInList,
  PatientCheckInSession,
  PatientView,
  ProvenanceResult,
  RegisterResult,
  Span,
  TaskProvenance,
  TranscriptNormalizeResult,
  VoiceCapabilities,
  VoiceCaptureMode,
  VoiceCaptureRecord,
  VoiceModelStatus,
  VoiceReviewedSegment,
} from './types';

// ---------------------------------------------------------------------------
// Identity mode (D1).
//
// Product mode (default): identity comes from the server-side HttpOnly session
// cookie. No client-side identity headers are sent; role is NEVER read from
// localStorage or any client state.
//
// Development/demo mode: only when VITE_DEMO_AUTH=true does the legacy
// X-User-Id / X-Role header simulation apply (the backend additionally
// requires NANTINGALE_DEMO_AUTH=true server-side, so both flags must match).
// The demo toolbar in App.tsx is gated by the same flag.
// ---------------------------------------------------------------------------
export const DEMO_AUTH = import.meta.env.VITE_DEMO_AUTH === 'true';

export const ROLE_USERS = [
  { role: 'clinician', userId: 'usr_clinician_01', label: 'Clinician' },
  { role: 'staff', userId: 'usr_staff_01', label: 'Staff' },
  { role: 'patient', userId: 'usr_patient_01', label: 'Patient' },
  { role: 'admin', userId: 'usr_admin_01', label: 'Admin' },
];

export const MENTIONABLE = [
  { user_id: 'usr_staff_01', label: 'Bob Lee (staff)' },
  { user_id: 'usr_clinician_01', label: 'Dr. Carol Wong (clinician)' },
];

let current = { userId: ROLE_USERS[0].userId, role: ROLE_USERS[0].role };

// Product-mode role source: the server session identity (set by App at boot
// and login). Never trusted for authorization — the backend re-resolves the
// DB user on every request.
let sessionIdentity: CurrentIdentity | null = null;

export function setSessionIdentity(identity: CurrentIdentity | null) {
  sessionIdentity = identity;
}

export function setRole(userId: string, role: string) {
  current = { userId, role };
}

export function getCurrentRole(): string {
  if (DEMO_AUTH) return current.role;
  return sessionIdentity?.role ?? '';
}

// 401 handling: product mode clears client-sensitive state and returns to
// Login. Auth endpoints (login/register/preview) opt out because they already
// surface their own errors to the form.
type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler;
}

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, message: string, body: any) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function headers(): Record<string, string> {
  if (!DEMO_AUTH) return {};
  return { 'X-User-Id': current.userId, 'X-Role': current.role };
}

interface RequestOptions {
  skipUnauthorized?: boolean;
}

async function request<T>(path: string, init?: RequestInit, options: RequestOptions = {}): Promise<T> {
  const res = await fetch(path, { credentials: 'include', ...init });
  if (res.status === 401 && !DEMO_AUTH && !options.skipUnauthorized) {
    unauthorizedHandler?.();
  }
  if (!res.ok) {
    let body: any = null;
    try {
      body = await res.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, res.statusText, body);
  }
  return res.json() as Promise<T>;
}

function get<T>(path: string, signal?: AbortSignal, options?: RequestOptions): Promise<T> {
  return request<T>(path, { headers: headers(), signal }, options);
}

function post<T>(path: string, body: unknown, signal?: AbortSignal, options?: RequestOptions): Promise<T> {
  return request<T>(
    path,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers() },
      body: JSON.stringify(body),
      signal,
    },
    options,
  );
}

function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify(body),
  });
}

function del<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify(body),
  });
}

function putAudio<T>(
  path: string,
  audio: Blob,
  expectedRevision: number,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
    headers: {
      'Content-Type': audio.type.split(';', 1)[0] || 'application/octet-stream',
      'X-Expected-Revision': String(expectedRevision),
      'Idempotency-Key': idempotencyKey,
      ...headers(),
    },
    body: audio,
    signal,
  });
}

export const api = {
  // --- D1 auth ------------------------------------------------------------
  login: (email: string, password: string) =>
    post<CurrentIdentity>('/api/auth/login', { email, password }, undefined, { skipUnauthorized: true }),
  logout: () => post<{ status: string }>('/api/auth/logout', {}),
  getSession: (signal?: AbortSignal) =>
    get<CurrentIdentity>('/api/auth/session', signal, { skipUnauthorized: true }),
  getInvitePreview: (token: string) =>
    post<InvitePreview>('/api/auth/invites/preview', { token }, undefined, {
      skipUnauthorized: true,
    }),
  register: (payload: { token: string; password: string; name?: string }) =>
    post<RegisterResult>('/api/auth/register', payload, undefined, { skipUnauthorized: true }),
  createInvite: (payload: { email: string; role: string; patient_id?: string | null }) =>
    post<InviteCreated>('/api/auth/invites', payload),
  listInvites: (signal?: AbortSignal) => get<InviteInfo[]>('/api/auth/invites', signal),
  getAdminUsers: (signal?: AbortSignal) => get<AdminUser[]>('/api/admin/users', signal),
  updateAdminUserStatus: (
    userId: string,
    expectedStatus: 'active' | 'disabled',
    status: 'active' | 'disabled',
  ) => patch<AdminUser>(`/api/admin/users/${userId}/status`, {
    expected_status: expectedStatus,
    status,
  }),
  revokeAdminUserSessions: (userId: string, expectedActiveSessionCount: number) =>
    post<{ user_id: string; revoked_count: number }>(
      `/api/admin/users/${userId}/revoke-sessions`,
      { expected_active_session_count: expectedActiveSessionCount },
    ),
  getAdminAccessAudit: (signal?: AbortSignal) =>
    get<AdminAccessAudit[]>('/api/admin/access-audit', signal),
  getAdminSystemSettings: (signal?: AbortSignal) =>
    get<AdminSystemSettings>('/api/admin/system-settings', signal),
  updateAdminSystemSettings: (
    expectedVersion: number,
    updates: { ai_mode?: 'local' | 'deepseek'; voice_enabled?: boolean },
  ) => patch<AdminSystemSettings>('/api/admin/system-settings', {
    expected_version: expectedVersion,
    ...updates,
  }),
  storeDeepSeekKey: (expectedVersion: number, apiKey: string) =>
    post<AdminSystemSettings>('/api/admin/system-settings/deepseek-key', {
      expected_version: expectedVersion,
      api_key: apiKey,
    }),
  removeDeepSeekKey: (expectedVersion: number) =>
    del<AdminSystemSettings>('/api/admin/system-settings/deepseek-key', {
      expected_version: expectedVersion,
    }),
  prepareVoiceModel: () =>
    post<VoiceModelStatus>('/api/admin/system-settings/voice-model', {}),
  getVoiceModelStatus: (signal?: AbortSignal) =>
    get<VoiceModelStatus>('/api/admin/system-settings/voice-model/status', signal),

  getCurrentIdentity: (signal?: AbortSignal) => get<CurrentIdentity>(`/api/auth/session`, signal),
  getClinicPatients: (signal?: AbortSignal) => get<Patient[]>(`/api/patients`, signal),
  getPatient: (id: string, signal?: AbortSignal) => get<Patient>(`/api/patients/${id}`, signal),
  getPatientView: (id: string, signal?: AbortSignal) => get<PatientView>(`/api/patients/${id}/patient-view`, signal),
  listPatientCheckIns: (id: string, signal?: AbortSignal) =>
    get<PatientCheckInList>(`/api/patients/${id}/check-ins`, signal),
  getPatientCheckIn: (sessionId: string, signal?: AbortSignal) =>
    get<PatientCheckInSession>(`/api/check-ins/${sessionId}`, signal),
  startPatientCheckIn: (patientId: string, sessionId: string, signal?: AbortSignal) =>
    post<PatientCheckInSession>(`/api/patients/${patientId}/check-ins`, { session_id: sessionId }, signal),
  savePatientCheckInMessage: (
    sessionId: string,
    messageId: string,
    intent: PatientCheckInIntent,
    text: string,
    signal?: AbortSignal,
  ) => post<PatientCheckInSession>(`/api/check-ins/${sessionId}/messages/save`, {
    message_id: messageId,
    intent,
    text,
  }, signal),
  processPatientCheckInMessage: (sessionId: string, messageId: string, signal?: AbortSignal) =>
    post<PatientCheckInSession>(`/api/check-ins/${sessionId}/messages/${messageId}/process`, {}, signal),
  finishPatientCheckIn: (sessionId: string, expectedStatus: string, signal?: AbortSignal) =>
    post<PatientCheckInSession>(`/api/check-ins/${sessionId}/finish`, { expected_status: expectedStatus }, signal),
  resumePatientCheckIn: (sessionId: string, expectedStatus: string, signal?: AbortSignal) =>
    post<PatientCheckInSession>(`/api/check-ins/${sessionId}/resume`, { expected_status: expectedStatus }, signal),
  abandonPatientCheckIn: (sessionId: string, expectedStatus: string, signal?: AbortSignal) =>
    post<PatientCheckInSession>(`/api/check-ins/${sessionId}/abandon`, { expected_status: expectedStatus }, signal),
  submitPatientCheckIn: (sessionId: string, expectedStatus: string, signal?: AbortSignal) =>
    post<PatientCheckInSession>(`/api/check-ins/${sessionId}/submit`, { expected_status: expectedStatus }, signal),
  getTasks: (id: string, signal?: AbortSignal) => get<ClinicalTask[]>(`/api/patients/${id}/tasks`, signal),
  createTask: (
    eventId: string,
    payload: {
      title: string;
      description: string;
      assigned_role: 'patient' | 'staff' | 'clinician';
      assigned_user_id: string | null;
      patient_visible: boolean;
      due_at: string | null;
      source_artifact_id: string | null;
      source_span: Span | null;
      confirmation_token?: string;
    },
  ) => post<ClinicalTask>(`/api/events/${eventId}/tasks`, payload),
  transitionTask: (taskId: string, expectedStatus: string, status: string) =>
    post<ClinicalTask | PatientTask>(`/api/tasks/${taskId}/transition`, {
      expected_status: expectedStatus,
      status,
    }),
  getTaskProvenance: (taskId: string) => get<TaskProvenance>(`/api/tasks/${taskId}/provenance`),
  getEvents: (id: string, signal?: AbortSignal) => get<Event[]>(`/api/patients/${id}/events`, signal),
  getArtifacts: (eventId: string, signal?: AbortSignal) => get<Artifact[]>(`/api/events/${eventId}/artifacts`, signal),
  getGlance: (patientId: string, signal?: AbortSignal) => get<{ highlights: Highlight[] }>(`/api/patients/${patientId}/glance`, signal),
  getProvenance: (highlightId: string) => get<ProvenanceResult>(`/api/highlights/${highlightId}/provenance`),
  setStatus: (highlightId: string, status: string) =>
    post<Highlight>(`/api/highlights/${highlightId}/status`, { status }),

  createNote: (eventId: string, artifactType: string, content: Record<string, any>, confirmationToken?: string) =>
    post<Artifact>(`/api/events/${eventId}/notes`, { artifact_type: artifactType, content, ...(confirmationToken ? { confirmation_token: confirmationToken } : {}) }),
  queryCopilot: (
    patientId: string,
    category: CopilotCategory,
    question = '',
    draftType?: 'clinician_note' | 'patient_instruction' | 'task',
    signal?: AbortSignal,
  ) => post<CopilotResponse>(`/api/patients/${patientId}/copilot/query`, {
    category,
    question,
    ...(draftType ? { draft_type: draftType } : {}),
  }, signal),
  editArtifact: (artifactId: string, content: Record<string, any>, expectedVersion: number) =>
    patch<Artifact>(`/api/artifacts/${artifactId}`, { content, expected_version: expectedVersion }),
  revertArtifact: (artifactId: string, toVersion: number, expectedVersion: number) =>
    post<Artifact>(`/api/artifacts/${artifactId}/revert`, {
      to_version: toVersion,
      expected_version: expectedVersion,
    }),
  getVersions: (artifactId: string) => get<ArtifactVersion[]>(`/api/artifacts/${artifactId}/versions`),
  getDiff: (artifactId: string, since: number) =>
    get<DiffResult>(`/api/artifacts/${artifactId}/diff?since=${since}`),

  createComment: (body: Record<string, any>) => post<Comment>(`/api/comments`, body),
  resolveComment: (id: string) => post<Comment>(`/api/comments/${id}/resolve`, {}),
  unresolveComment: (id: string) => post<Comment>(`/api/comments/${id}/unresolve`, {}),
  getComments: (eventId: string, signal?: AbortSignal) => get<Comment[]>(`/api/events/${eventId}/comments`, signal),
  getAudit: (eventId: string, signal?: AbortSignal) => get<AuditLog[]>(`/api/events/${eventId}/audit`, signal),

  ingestSource: (eventId: string, ingestionKey: string, content: Record<string, any>) =>
    post<any>(`/api/events/${eventId}/sources`, {
      ingestion_key: ingestionKey,
      artifact_type: 'transcript',
      content,
    }),
  normalizeTranscript: (rawText: string, signal?: AbortSignal) =>
    post<TranscriptNormalizeResult>(`/api/transcripts/normalize`, { raw_text: rawText }, signal),
  normalizeNurseTranscript: (rawText: string, signal?: AbortSignal) =>
    post<TranscriptNormalizeResult>(`/api/transcripts/nurse-normalize`, { raw_text: rawText }, signal),
  createDoctorConsult: (
    patientId: string,
    consultId: string,
    ingestionKey: string,
    startedAt: string,
    endedAt: string | null,
    segments: DoctorTranscriptSegment[],
    signal?: AbortSignal,
  ) =>
    post<DoctorConsultResult>(`/api/patients/${patientId}/doctor-consults`, {
      consult_id: consultId,
      ingestion_key: ingestionKey,
      started_at: startedAt,
      ended_at: endedAt,
      content: { segments },
    }, signal),
  createNurseConsult: (
    patientId: string,
    consultId: string,
    ingestionKey: string,
    startedAt: string,
    endedAt: string | null,
    encounterId: string | null,
    segments: NurseTranscriptSegment[],
    signal?: AbortSignal,
  ) =>
    post<NurseConsultResult>(`/api/patients/${patientId}/nurse-consults`, {
      consult_id: consultId,
      ingestion_key: ingestionKey,
      started_at: startedAt,
      ended_at: endedAt,
      encounter_id: encounterId,
      content: { segments },
    }, signal),
  createSession: (
    patientId: string,
    sessionId: string,
    eventType: string,
    startedAt: string,
    content: Record<string, any>,
  ) =>
    post<any>(`/api/patients/${patientId}/sessions`, {
      session_id: sessionId,
      event_type: eventType,
      started_at: startedAt,
      content,
    }),
  getVoiceCapabilities: (signal?: AbortSignal) =>
    get<VoiceCapabilities>('/api/voice/capabilities', signal),
  createVoiceCapture: (payload: {
    idempotency_key: string;
    patient_id: string;
    capture_mode: VoiceCaptureMode;
    patient_event_type?: 'patient_ai_preconsult' | 'patient_followup';
    started_at: string;
    ended_at?: string | null;
    encounter_id?: string | null;
  }, signal?: AbortSignal) => post<VoiceCaptureRecord>('/api/voice/captures', payload, signal),
  uploadVoiceAudio: (
    captureId: string,
    audio: Blob,
    expectedRevision: number,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) => putAudio<VoiceCaptureRecord>(
    `/api/voice/captures/${captureId}/audio`,
    audio,
    expectedRevision,
    idempotencyKey,
    signal,
  ),
  transcribeVoiceCapture: (
    captureId: string,
    expectedRevision: number,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) => post<VoiceCaptureRecord>(`/api/voice/captures/${captureId}/transcribe`, {
    expected_revision: expectedRevision,
    idempotency_key: idempotencyKey,
  }, signal),
  reviewVoiceSegments: (
    captureId: string,
    expectedRevision: number,
    segments: Array<Pick<VoiceReviewedSegment,
      'source_machine_segment_ids' | 'speaker' | 'text' | 'speaker_source_verified'> & {
        resolved_issues: string[];
      }>,
  ) => patch<VoiceCaptureRecord>(`/api/voice/captures/${captureId}/segments`, {
    expected_revision: expectedRevision,
    segments,
  }),
  confirmVoiceCapture: (
    captureId: string,
    expectedRevision: number,
    idempotencyKey: string,
  ) => post<VoiceCaptureRecord>(`/api/voice/captures/${captureId}/confirm`, {
    expected_revision: expectedRevision,
    idempotency_key: idempotencyKey,
  }),
};
