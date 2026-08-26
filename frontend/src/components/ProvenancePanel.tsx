import { useEffect, useRef } from 'react';
import type { ProvenanceResult } from '../types';
import ArtifactContent from './ArtifactContent';

const TYPE_LABELS: Record<string, string> = {
  patient_ai_preconsult: 'Patient AI Pre-consult',
  nurse_consult: 'Nurse Consult',
  doctor_consult: 'Doctor Consult',
  patient_followup: 'Patient Follow-up',
  clinician_review: 'Clinician Review',
  historical_review: 'Historical Review',
};

export default function ProvenancePanel({
  provenance,
  onClose,
}: {
  provenance: ProvenanceResult;
  onClose: () => void;
}) {
  const markRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // Scroll the exact quoted sentence into view.
    markRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [provenance]);

  const { event, summary_artifact, source_artifact, span, quote } = provenance;

  return (
    <div className="provenance-panel">
      <div className="provenance-head">
        <h3>Source · “{quote ?? 'unresolved'}”</h3>
        <button onClick={onClose}>✕</button>
      </div>
      <ol className="chain">
        <li>
          <span className="chain-type">Event</span>
          {TYPE_LABELS[event.event_type] ?? event.event_type} · {new Date(event.started_at).toLocaleDateString()}
        </li>
        {summary_artifact && (
          <li>
            <span className="chain-type">AI Summary</span>
            {summary_artifact.artifact_type} <span className="system-tag">System-generated</span>
          </li>
        )}
        <li>
          <span className="chain-type">Source</span>
          {source_artifact.artifact_type} · {source_artifact.author_role}
        </li>
      </ol>
      <div className="source-box">
        <ArtifactContent artifact={source_artifact} span={span} markRef={markRef} />
      </div>
    </div>
  );
}
