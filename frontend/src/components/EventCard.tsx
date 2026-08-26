import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { Artifact, Event } from '../types';
import ArtifactContent from './ArtifactContent';

const TYPE_LABELS: Record<string, string> = {
  patient_ai_preconsult: 'Patient AI Pre-consult',
  nurse_consult: 'Nurse Consult',
  doctor_consult: 'Doctor Consult',
  patient_followup: 'Patient Follow-up',
  clinician_review: 'Clinician Review',
  historical_review: 'Historical Review',
};

const ARTIFACT_STYLE: Record<string, { badge: string; cls: string }> = {
  raw_conversation: { badge: 'RAW', cls: 'raw' },
  transcript: { badge: 'RAW', cls: 'raw' },
  clinician_note: { badge: 'CLINICIAN', cls: 'clinician' },
  staff_note: { badge: 'STAFF', cls: 'staff' },
  patient_instruction: { badge: 'CLINICIAN', cls: 'clinician' },
  ai_doctor_consult_summary: { badge: 'AI', cls: 'ai' },
  ai_nurse_consult_summary: { badge: 'AI', cls: 'ai' },
  ai_patient_session_summary: { badge: 'AI', cls: 'ai' },
};

export default function EventCard({
  event,
  focusEventId,
}: {
  event: Event;
  focusEventId: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [artifacts, setArtifacts] = useState<Artifact[] | null>(null);
  const [loading, setLoading] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const isFocused = focusEventId === event.event_id;

  async function load() {
    if (artifacts !== null) return;
    setLoading(true);
    try {
      setArtifacts(await api.getArtifacts(event.event_id));
    } finally {
      setLoading(false);
    }
  }

  async function toggle() {
    if (!open) await load();
    setOpen((o) => !o);
  }

  useEffect(() => {
    if (isFocused) {
      setOpen(true);
      load();
      cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [isFocused]);

  const label = TYPE_LABELS[event.event_type] ?? event.event_type;

  return (
    <div className="event-card" ref={cardRef}>
      <button type="button" className="event-row" onClick={toggle}>
        <span className="event-date">{new Date(event.started_at).toLocaleDateString()}</span>
        <span className="event-type">{label}</span>
        <span className="event-count">{event.artifact_count} artifacts</span>
        <span className="chevron">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="artifact-list">
          {loading && <div className="muted">Loading…</div>}
          {artifacts?.map((a) => {
            const style = ARTIFACT_STYLE[a.artifact_type] ?? { badge: a.artifact_type, cls: '' };
            return (
              <div className="artifact" key={a.artifact_id}>
                <div className="artifact-head">
                  <span className={`badge ${style.cls}`}>{style.badge}</span>
                  <span className="artifact-type">{a.artifact_type}</span>
                  {a.author_role === 'system' && <span className="system-tag">System-generated</span>}
                  {a.provenance_pointer && (
                    <span className="provenance-tag" title={JSON.stringify(a.provenance_pointer)}>
                      ⟵ source
                    </span>
                  )}
                </div>
                <ArtifactContent artifact={a} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
