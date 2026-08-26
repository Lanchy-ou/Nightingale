import type { Artifact, Event, Patient } from './types';

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

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    headers: {
      'X-User-Id': current.userId,
      'X-Role': current.role,
    },
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getPatient: (id: string) => get<Patient>(`/api/patients/${id}`),
  getEvents: (id: string) => get<Event[]>(`/api/patients/${id}/events`),
  getArtifacts: (eventId: string) => get<Artifact[]>(`/api/events/${eventId}/artifacts`),
};
