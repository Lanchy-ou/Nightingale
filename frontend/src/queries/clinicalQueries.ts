import { useQuery } from '@tanstack/react-query';
import { api } from '../api';

export const clinicalQueryKeys = {
  patientDetails: (scopeKey: string, patientId: string) =>
    ['clinical', scopeKey, 'patient', patientId] as const,
  patientTimeline: (scopeKey: string, patientId: string) =>
    ['clinical', scopeKey, 'patient', patientId, 'events'] as const,
};

export function usePatientDetails(patientId: string, scopeKey: string) {
  return useQuery({
    queryKey: clinicalQueryKeys.patientDetails(scopeKey, patientId),
    queryFn: ({ signal }) => api.getPatient(patientId, signal),
    enabled: Boolean(patientId && scopeKey),
  });
}

export function usePatientTimeline(patientId: string, scopeKey: string) {
  return useQuery({
    queryKey: clinicalQueryKeys.patientTimeline(scopeKey, patientId),
    queryFn: ({ signal }) => api.getEvents(patientId, signal),
    enabled: Boolean(patientId && scopeKey),
  });
}
