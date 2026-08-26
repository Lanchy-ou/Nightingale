import { useEffect, useRef, useState } from 'react';
import { api, getCurrentRole } from '../api';
import type { Artifact, Event } from '../types';
import ArtifactContent from './ArtifactContent';
import ArtifactEdit from './ArtifactEdit';
import AuditList from './AuditList';
import CommentThread from './CommentThread';
import NoteComposer from './NoteComposer';
import RevisionPanel from './RevisionPanel';

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

const EDITABLE = new Set(['staff_note', 'clinician_note']);

export default function EventCard({
  event,
  focusEventId,
}: {
  event: Event;
  focusEventId: string | null;
}) {
  const role = getCurrentRole();
  const [open, setOpen] = useState(false);
  const [artifacts, setArtifacts] = useState<Artifact[] | null>(null);
  const [loading, setLoading] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const isFocused = focusEventId === event.event_id;

  async function load() {
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
  const isNonPatient = role !== 'patient';
  const canWriteNote = role === 'staff' || role === 'clinician';
  const noteType = role === 'staff' ? 'staff_note' : 'clinician_note';

  function ownsNote(a: Artifact): boolean {
    return (
      (role === 'staff' && a.artifact_type === 'staff_note') ||
      (role === 'clinician' && a.artifact_type === 'clinician_note')
    );
  }

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
            const editable = EDITABLE.has(a.artifact_type);
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
                {editable && ownsNote(a) && (
                  <div className="artifact-actions">
                    <ArtifactEdit artifact={a} onSaved={load} />
                    <RevisionPanel artifact={a} onReverted={load} />
                  </div>
                )}
                {editable && !ownsNote(a) && role === 'admin' && (
                  <div className="artifact-actions">
                    <RevisionPanel artifact={a} onReverted={load} canRevert={false} />
                  </div>
                )}
              </div>
            );
          })}
          {canWriteNote && (
            <NoteComposer eventId={event.event_id} artifactType={noteType} onSaved={load} />
          )}
          {isNonPatient && (
            <>
              <CommentThread eventId={event.event_id} canWrite={canWriteNote} />
              <AuditList eventId={event.event_id} />
            </>
          )}
        </div>
      )}
    </div>
  );
}
