import type { Artifact, Event, Highlight, Patient, ProvenanceResult } from './types';

// Demo-only role switcher mapping. NOT a security boundary — the backend
// parses these headers and will enforce RBAC server-side in Phase 3.
export const ROLE_USERS = [
  { role: 'clinician', userId: 'usr_clinician_01', label: 'Clinician' },
  { role: 'staff', userId: 'usr_staff_01', label: 'Staff' },
  { role: 'patient', userId: 'usr_patient_01', label: 'Patient' },
  { role: 'admin', userId: 'usr_admin_01', label: 'Admin' },
];

let current = { userId: '', role: '' };

export function setRole(userId: string, role: string) {
  current = { userId, role };
}

function headers(): Record<string, string> {
  return { 'X-User-Id': current.userId, 'X-Role': current.role };
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: headers() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  getPatient: (id: string) => get<Patient>(`/api/patients/${id}`),
  getEvents: (id: string) => get<Event[]>(`/api/patients/${id}/events`),
  getArtifacts: (eventId: string) => get<Artifact[]>(`/api/events/${eventId}/artifacts`),
  getGlance: (patientId: string) => get<{ highlights: Highlight[] }>(`/api/patients/${patientId}/glance`),
  getProvenance: (highlightId: string) => get<ProvenanceResult>(`/api/highlights/${highlightId}/provenance`),
  setStatus: (highlightId: string, status: string) =>
    post<Highlight>(`/api/highlights/${highlightId}/status`, { status }),
};
