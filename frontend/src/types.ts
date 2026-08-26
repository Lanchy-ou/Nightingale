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
  index?: number | string;
  offset?: [number, number];
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
  content: Record<string, any>;
  created_at: string;
  version: number;
  provenance_pointer: ProvenancePointer | null;
}

export interface FeatureFlags {
  recency: boolean;
  explicit_risk: boolean;
  unresolved_task: boolean;
  clinician_confirmed: boolean;
  symptom_change: boolean;
  repeated_mentions: boolean;
}

export interface Highlight {
  highlight_id: string;
  patient_id: string;
  event_id: string;
  artifact_id: string;
  source_artifact_id: string;
  source_span: Span;
  text: string;
  risk_reason: string;
  feature_flags: FeatureFlags;
  importance_score: number;
  status: string;
  status_history: { from: string; to: string; at: string }[];
  created_at: string;
  updated_at: string;
  entity_type: string | null;
  entity_key: string | null;
  assertion_value: string | null;
  conflict_with_artifact_id: string | null;
  review_status: string | null;
}

export interface ProvenanceResult {
  highlight_id: string;
  event: {
    event_id: string;
    event_type: string;
    started_at: string;
    ended_at: string | null;
  };
  summary_artifact: Artifact | null;
  source_artifact: Artifact;
  span: Span;
  quote: string | null;
  conflict_artifact: Artifact | null;
}

export interface Comment {
  comment_id: string;
  anchor_type: string;
  anchor_id: string;
  parent_comment_id: string | null;
  author_id: string;
  author_role: string;
  body: string;
  mentions: string[];
  resolved: boolean;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface ArtifactVersion {
  version_id: string;
  artifact_id: string;
  version: number;
  content: Record<string, any>;
  actor_id: string;
  actor_role: string;
  created_at: string;
}

export interface AuditLog {
  audit_id: string;
  actor_id: string;
  actor_role: string;
  action: string;
  target_type: string;
  target_id: string;
  from_version: number | null;
  to_version: number | null;
  clinic_id: string;
  patient_id: string;
  event_id: string | null;
  created_at: string;
}

export interface DiffResult {
  artifact_id: string;
  since_version: number;
  to_version: number;
  diff: string;
}

// --- Patient View (M6) ---
export interface PatientViewSummary {
  source_artifact_id: string;
  event_id: string;
  event_time: string;
  instruction: string;
  follow_up: string | null;
}

export interface PatientViewInstruction {
  artifact_id: string;
  event_id: string;
  event_time: string;
  instruction: string;
  follow_up: string | null;
}

export interface PatientViewUpcoming {
  source_artifact_id: string;
  event_id: string;
  event_time: string;
  kind: 'follow_up';
  text: string;
}

export interface PatientViewSession {
  event_id: string;
  event_type: string;
  started_at: string;
  ended_at: string | null;
}

export interface PatientView {
  patient_id: string;
  display_name: string;
  current_summary: PatientViewSummary | null;
  instructions: PatientViewInstruction[];
  upcoming: PatientViewUpcoming[];
  sessions: PatientViewSession[];
}
