export interface Patient {
  patient_id: string;
  clinic_id: string;
  name: string;
  clinic_name: string | null;
}

export interface Event {
  event_id: string;
  patient_id: string;
  clinic_id: string;
  event_type: string;
  started_at: string;
  ended_at: string | null;
  created_at: string;
  artifact_count: number;
}

export interface Span {
  kind: string;
  index?: number;
}

export interface ProvenancePointer {
  event_id: string;
  artifact_id: string;
  span: Span;
}

export interface Artifact {
  artifact_id: string;
  event_id: string;
  artifact_type: string;
  author_role: string;
  author_id: string | null;
  content: Record<string, unknown>;
  created_at: string;
  version: number;
  provenance_pointer: ProvenancePointer | null;
}
