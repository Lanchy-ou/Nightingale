import { useEffect, useState } from 'react';
import { api, getCurrentRole } from '../api';
import type { Event, Patient, ProvenanceResult } from '../types';
import GlancePanel from '../components/GlancePanel';
import IngestPanel from '../components/IngestPanel';
import PatientHeader from '../components/PatientHeader';
import ProvenancePanel from '../components/ProvenancePanel';
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
  const [provenance, setProvenance] = useState<ProvenanceResult | null>(null);
  const [focusEventId, setFocusEventId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const role = getCurrentRole();

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
  }, [patientId, roleKey, refreshKey]);

  function handleViewSource(p: ProvenanceResult) {
    setProvenance(p);
    setFocusEventId(p.event.event_id);
  }

  function handleFocusEvent(eventId: string) {
    setFocusEventId(eventId);
  }

  function handleIngested() {
    setRefreshKey((k) => k + 1);
  }

  if (error) return <div className="error">Failed to load patient: {error}</div>;
  if (!patient) return <div className="muted">Loading…</div>;

  return (
    <div className="patient-page">
      <PatientHeader patient={patient} />
      {role !== 'patient' && (
        <GlancePanel key={`glance-${refreshKey}`} patientId={patientId} onViewSource={handleViewSource} />
      )}
      {provenance && (
        <ProvenancePanel
          provenance={provenance}
          onClose={() => setProvenance(null)}
          onFocusEvent={handleFocusEvent}
        />
      )}
      <IngestPanel patientId={patientId} onIngested={handleIngested} />
      {/* key=roleKey remounts the timeline on role switch so artifacts refetch
          under the new role (patient sees API-filtered content, not a UI hack). */}
      <Timeline key={roleKey} events={events} focusEventId={focusEventId} />
    </div>
  );
}
