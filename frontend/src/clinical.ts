import type { Artifact, Event } from './types';

export const EVENT_LABELS: Record<string, string> = {
  patient_ai_preconsult: 'Patient AI Pre-consult',
  nurse_consult: 'Nurse Consult',
  doctor_consult: 'Doctor Consult',
  patient_followup: 'Patient Follow-up',
  clinician_review: 'Clinician Review',
  historical_review: 'Historical Review',
};

export const ARTIFACT_LABELS: Record<string, string> = {
  raw_conversation: 'Raw conversation',
  transcript: 'Transcript',
  clinician_note: 'Clinician assessment & plan',
  staff_note: 'Staff note',
  patient_instruction: 'Patient instruction',
  ai_doctor_consult_summary: 'AI doctor consult summary',
  ai_nurse_consult_summary: 'AI nurse consult summary',
  ai_patient_session_summary: 'AI patient session summary',
};

export function eventLabel(event: Event): string {
  return EVENT_LABELS[event.event_type] ?? event.event_type.replace(/_/g, ' ');
}

export function artifactLabel(artifact: Artifact): string {
  return ARTIFACT_LABELS[artifact.artifact_type] ?? artifact.artifact_type.replace(/_/g, ' ');
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function artifactBadge(type: string): { badge: string; cls: string } {
  if (type === 'transcript' || type === 'raw_conversation') return { badge: 'RAW', cls: 'raw' };
  if (type === 'clinician_note' || type === 'patient_instruction') return { badge: 'CLINICIAN', cls: 'clinician' };
  if (type === 'staff_note') return { badge: 'STAFF', cls: 'staff' };
  if (type.startsWith('ai_')) return { badge: 'AI', cls: 'ai' };
  return { badge: 'RECORD', cls: '' };
}
