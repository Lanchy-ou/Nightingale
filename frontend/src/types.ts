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
  encounter_id: string | null;
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
  artifact_id: string | null;
  source_artifact_id: string | null;
  source_span: Span | null;
  task_id: string | null;
  text: string;
  risk_reason: string;
  feature_flags: FeatureFlags;
  base_importance_score: number;
  adaptive_adjustment: number;
  decay_adjustment: number;
  importance_score: number;
  learning_metadata: {
    feedback_key?: string;
    review_count?: number;
    positive_count?: number;
    negative_count?: number;
    raw_adjustment?: number;
    cap_min?: number;
    cap_max?: number;
    reason?: string;
    protection_applied?: boolean;
  };
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
  details: Record<string, string> | null;
  created_at: string;
}

export interface DiffResult {
  artifact_id: string;
  since_version: number;
  to_version: number;
  diff: string;
}

// --- C1 Clinician consult handoff ---
export interface CurrentIdentity {
  user_id: string | null;
  role: string | null;
  clinic_id: string | null;
  patient_id: string | null;
  display_name: string | null;
  professional_title: string | null;
  clinic_name: string | null;
  authenticated: boolean;
}

export interface DoctorTranscriptSegment {
  index: number;
  speaker: 'doctor' | 'patient';
  text: string;
}

export interface NurseTranscriptSegment {
  index: number;
  speaker: 'nurse' | 'patient';
  text: string;
}

export type TranscriptNormalizeOutcome = 'ACCEPT' | 'NEEDS_REVIEW' | 'REJECT';

export interface TranscriptPreviewSegment {
  index: number;
  speaker_candidate: 'doctor' | 'nurse' | 'patient' | null;
  text: string;
  // Nullable: after a user edit/split/merge that cannot be mapped back to the
  // raw text exactly, the source range is cleared (never a pseudo-precise span).
  source_start: number | null;
  source_end: number | null;
  confidence_marker: 'exact_label' | 'mapped_label' | 'inferred_boundary' | 'unknown';
  issues: string[];
}

export interface TranscriptNormalizeResult {
  outcome: TranscriptNormalizeOutcome;
  normalize_reason: string | null;
  raw_byte_length: number;
  segments: TranscriptPreviewSegment[];
  issues: string[];
}

export interface DoctorConsultResult {
  event: Event;
  encounter_id: string;
  source_artifact_id: string;
  ai_summary_artifact_id: string;
  highlight_ids: string[];
  generation_method: string;
  degraded: boolean;
  fallback_reason: string | null;
  idempotent_replay: boolean;
}

export type NurseConsultResult = DoctorConsultResult;

// --- E1 Admin oversight ---------------------------------------------------
export interface AdminUser {
  user_id: string;
  display_name: string;
  email: string | null;
  role: 'patient' | 'staff' | 'clinician' | 'admin';
  professional_title: string | null;
  patient_id: string | null;
  account_status: 'active' | 'disabled';
  disabled_at: string | null;
  active_session_count: number;
  last_seen_at: string | null;
}

export interface AdminAccessAudit {
  audit_id: string;
  actor_id: string | null;
  actor_role: string | null;
  action: string;
  target_type: string;
  target_id: string;
  details: Record<string, string> | null;
  created_at: string;
}

// --- D1 Identity, Invite, Login and Session ---
export interface InviteInfo {
  invite_id: string;
  email: string;
  role: string;
  patient_id: string | null;
  created_by: string;
  created_at: string;
  expires_at: string;
  used_at: string | null;
  status: 'pending' | 'used' | 'expired';
}

export interface InviteCreated {
  invite_id: string;
  email: string;
  role: string;
  patient_id: string | null;
  expires_at: string;
  invite_link: string;
}

export interface InvitePreview {
  status: 'valid' | 'used' | 'expired';
  email_masked: string;
  role: string;
  clinic_name: string;
  patient_name: string | null;
  expires_at: string;
}

export interface RegisterResult {
  user_id: string;
  email: string;
  role: string;
  clinic_id: string;
}

// --- D2 Care Tasks + Patient Experience ---
export interface PatientViewInstruction {
  artifact_id: string;
  event_id: string;
  event_time: string;
  instruction: string;
  follow_up: string | null;
}

export interface PatientViewSession {
  event_id: string;
  event_type: string;
  started_at: string;
  ended_at: string | null;
}

export type TaskStatus = 'open' | 'in_progress' | 'reported_done' | 'completed' | 'cancelled';

export interface PatientTask {
  task_id: string;
  title: string;
  status: TaskStatus;
  due_at: string | null;
  updated_at: string;
  reported_done_at: string | null;
  completed_at: string | null;
  patient_visible: boolean;
}

export interface ClinicalTask extends PatientTask {
  patient_id: string;
  clinic_id: string;
  event_id: string;
  source_artifact_id: string | null;
  source_span: Span | null;
  description: string;
  assigned_role: 'patient' | 'staff' | 'clinician';
  assigned_user_id: string | null;
  created_by: string;
  created_at: string;
  completed_by: string | null;
  cancelled_by: string | null;
  cancelled_at: string | null;
}

export interface TaskProvenance {
  task_id: string;
  event: {
    event_id: string;
    event_type: string;
    started_at: string;
    ended_at: string | null;
  };
  source_artifact: Artifact | null;
  span: Span | null;
  quote: string | null;
}

// --- D4 Evidence-Bound Clinician Copilot ---------------------------------
export type CopilotCategory = 'what_changed' | 'what_matters_now' | 'find_evidence' | 'draft_action';

export interface CopilotEvidence {
  evidence_id: string;
  event_id: string;
  event_type: string;
  event_time: string;
  record_time: string;
  artifact_id: string;
  artifact_type: string;
  author_role: string;
  span: Span;
  quote: string;
  review_required: boolean;
}

export interface CopilotClaim {
  text: string;
  status: 'supported' | 'inference' | 'unknown';
  evidence_ids: string[];
}

export interface CopilotDraft {
  artifact_type: 'clinician_note' | 'patient_instruction' | 'task';
  event_id: string;
  evidence_ids: string[];
  content: Record<string, string>;
  patient_visible: boolean;
  ai_generated: true;
  requires_clinician_confirmation: true;
  confirmation_token: string;
}

export interface CopilotResponse {
  category: CopilotCategory;
  status: 'ok' | 'unavailable';
  claims: CopilotClaim[];
  evidence: CopilotEvidence[];
  limitations: string[];
  draft: CopilotDraft | null;
}

export interface PatientView {
  patient_id: string;
  display_name: string;
  today: {
    instruction: PatientViewInstruction | null;
    tasks: PatientTask[];
    next_follow_up: string | null;
  };
  care_plan: {
    open: PatientTask[];
    in_progress: PatientTask[];
    reported_done: PatientTask[];
    completed: PatientTask[];
  };
  check_in: { sessions: PatientViewSession[] };
  visit_summaries: { summaries: PatientViewInstruction[] };
}
