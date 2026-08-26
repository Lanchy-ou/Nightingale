import type {
  Artifact,
  ArtifactVersion,
  AuditLog,
  Comment,
  DiffResult,
  Event,
  Highlight,
  Patient,
  PatientView,
  ProvenanceResult,
} from './types';

// Demo-only role switcher mapping. NOT a security boundary — the backend
// resolves identity from X-User-Id against the DB and enforces RBAC server-side.
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

export function setRole(userId: string, role: string) {
  current = { userId, role };
}

export function getCurrentRole(): string {
  return current.role;
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
  return { 'X-User-Id': current.userId, 'X-Role': current.role };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
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

function get<T>(path: string): Promise<T> {
  return request<T>(path, { headers: headers() });
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify(body),
  });
}

function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify(body),
  });
}

export const api = {
  getPatient: (id: string) => get<Patient>(`/api/patients/${id}`),
  getPatientView: (id: string) => get<PatientView>(`/api/patients/${id}/patient-view`),
  getEvents: (id: string) => get<Event[]>(`/api/patients/${id}/events`),
  getArtifacts: (eventId: string) => get<Artifact[]>(`/api/events/${eventId}/artifacts`),
  getGlance: (patientId: string) => get<{ highlights: Highlight[] }>(`/api/patients/${patientId}/glance`),
  getProvenance: (highlightId: string) => get<ProvenanceResult>(`/api/highlights/${highlightId}/provenance`),
  setStatus: (highlightId: string, status: string) =>
    post<Highlight>(`/api/highlights/${highlightId}/status`, { status }),

  createNote: (eventId: string, artifactType: string, content: Record<string, any>) =>
    post<Artifact>(`/api/events/${eventId}/notes`, { artifact_type: artifactType, content }),
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
  getComments: (eventId: string) => get<Comment[]>(`/api/events/${eventId}/comments`),
  getAudit: (eventId: string) => get<AuditLog[]>(`/api/events/${eventId}/audit`),

  ingestSource: (eventId: string, ingestionKey: string, content: Record<string, any>) =>
    post<any>(`/api/events/${eventId}/sources`, {
      ingestion_key: ingestionKey,
      artifact_type: 'transcript',
      content,
    }),
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
};
