import { useEffect, useRef } from 'react';
import { artifactLabel, formatDate, formatDateTime } from '../clinical';
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
  onFocusEvent,
}: {
  provenance: ProvenanceResult;
  onClose: () => void;
  onFocusEvent: (eventId: string) => void;
}) {
  const markRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // Scroll the exact quoted sentence into view.
    markRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [provenance]);

  const { event, summary_artifact, source_artifact, span, quote, conflict_artifact } = provenance;

  return (
    <div className="provenance-panel">
      <div className="provenance-head">
        <div>
          <p className="eyebrow">{quote ? 'Exact supporting span' : 'Provenance check'}</p>
          <h3>{TYPE_LABELS[event.event_type] ?? event.event_type}</h3>
        </div>
        <button onClick={onClose} aria-label="Close source viewer">✕</button>
      </div>
      {quote && <blockquote className="source-quote-preview">“{quote}”</blockquote>}
      <p className="provenance-compact-meta">{formatDate(event.started_at)} · {artifactLabel(source_artifact)} · {source_artifact.author_role} · exact {span.kind} span</p>
      {quote ? (
        <details className="provenance-details" open><summary>Event → Artifact → exact Span</summary><ol className="chain">
          <li><span className="chain-type">Event</span><span>{TYPE_LABELS[event.event_type] ?? event.event_type}<small>{formatDate(event.started_at)}</small></span></li>
          {summary_artifact && <li><span className="chain-type">Artifact</span><span>{artifactLabel(summary_artifact)}<small>AI · system-generated</small></span></li>}
          <li><span className="chain-type">Source Artifact</span><span>{artifactLabel(source_artifact)}<small>{source_artifact.author_role} · created {formatDateTime(source_artifact.created_at)}</small></span></li>
          <li><span className="chain-type">Exact Span</span><span>{span.kind.replace(/_/g, ' ')}<small>Highlighted verbatim in the source below</small></span></li>
        </ol><div className="source-box"><ArtifactContent artifact={source_artifact} span={span} markRef={markRef} /></div></details>
      ) : (
        <div className="form-error">The provenance span could not be resolved; no source text is being claimed.</div>
      )}
      {conflict_artifact && (
        <div className="conflict-box">
          <span className="needs-review-tag">Needs review</span>
          <span>conflicts with clinician-authored note</span>
          <button
            className="link-btn"
            onClick={() => onFocusEvent(conflict_artifact.event_id)}
          >
            Jump to clinician note
          </button>
        </div>
      )}
    </div>
  );
}
