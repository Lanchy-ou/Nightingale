import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Event, Patient } from '../types';
import GlancePlaceholder from '../components/GlancePlaceholder';
import PatientHeader from '../components/PatientHeader';
import Timeline from '../components/Timeline';

export default function PatientPage({
  patientId,
  roleKey,
}: {
  patientId: string;
  roleKey: string;
}) {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [p, evs] = await Promise.all([
          api.getPatient(patientId),
          api.getEvents(patientId),
        ]);
        if (!cancelled) {
          setPatient(p);
          setEvents(evs);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [patientId, roleKey]);

  if (error) return <div className="error">Failed to load patient: {error}</div>;
  if (!patient) return <div className="muted">Loading…</div>;

  return (
    <div className="patient-page">
      <PatientHeader patient={patient} />
      <GlancePlaceholder />
      <Timeline events={events} />
    </div>
  );
}
