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
  generation_method?: string | null;
  degraded?: boolean;
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
  score_rule_version: string;
  score_factors: Record<string, any>;
  status: string;
  status_history: { from: string; to: string; at: string }[];
  created_at: string;
  updated_at: string;
  entity_type: string | null;
  entity_key: string | null;
  assertion_value: string | null;
  conflict_with_artifact_id: string | null;
  review_status: string | null;
  task_context: {
    task_kind: string;
    workflow_id: string | null;
    assigned_role: string;
    status: string;
    attention_class: string;
    verification_outcome: string;
    verification_overdue?: boolean;
    due_at: string | null;
    escalate_at: string | null;
    escalated_at: string | null;
    creation_method: string;
  } | null;
  glance_explanation: Record<string, any> | null;
  ranking_rule_version: string | null;
}

export interface CoverageDecision {
  decision_id: string;
  highlight_id: string;
  text: string;
  entity_type: string | null;
  task_id: string | null;
  eligible: boolean;
  exclusion_reason: string | null;
  priority_band: number;
  base_score: number;
  shadow_adjustment: number;
  shadow_score: number;
  base_rank: number | null;
  shadow_rank: number | null;
  surfaced_base: boolean;
  surfaced_shadow: boolean;
  source_binding_status: string;
  factor_snapshot: Record<string, any>;
}

export interface CoverageReview {
  run_id: string;
  patient_id: string;
  viewer_role: 'staff' | 'clinician';
  serving_mode: 'base_only';
  shadow_policy: string;
  shadow_only: true;
  evaluated_at: string;
  base_top_five: CoverageDecision[];
  eligible_unsurfaced: CoverageDecision[];
  excluded: CoverageDecision[];
}

export interface LearningSignal {
  signal_id: string;
  decision_id: string;
  clinic_id: string;
  actor_id: string;
  actor_role: string;
  signal_type: 'explicit_demotion' | 'quality_issue' | 'outcome_label';
  reason_code: string;
  feedback_key: string;
  signal_value: number;
  eligible_for_shadow: boolean;
  ineligibility_reason: string | null;
  independence_key: string;
  policy_version: string;
  supersedes_signal_id: string | null;
  created_at: string;
}

export interface LearningEvaluation {
  evaluation_id: string;
  clinic_id: string;
  policy_version: string;
  run_ids: string[];
  metrics: Record<string, any>;
  created_by: string;
  created_at: string;
}

export interface LearningStatus {
  serving_mode: 'base_only';
  shadow_only: true;
  active_policy: string;
  frozen: boolean;
  frozen_at: string | null;
  signal_cutoff_at: string | null;
  policies: { version_name: string; active: boolean; serving_mode: string; shadow_policy: string }[];
  latest_evaluation: LearningEvaluation | null;
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
  bound_source_version: number | null;
  current_source_version: number | null;
  source_changed: boolean;
  binding_status: string;
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

// --- E4 local voice adapter ----------------------------------------------
export type VoiceCaptureMode = 'doctor_consult' | 'nurse_consult' | 'patient_session';

export interface VoiceCapabilities {
  enabled: boolean;
  provider: string;
  asr_ready: boolean;
  allowed_modes: VoiceCaptureMode[];
  eligible_modes: VoiceCaptureMode[];
  disabled_reason: 'disabled_by_admin' | 'model_not_ready' | null;
  accepted_mime_types: string[];
  max_bytes: number;
  max_duration_ms: number;
}

export interface VoiceMachineSegment {
  machine_segment_id: string;
  source_start_ms: number | null;
  source_end_ms: number | null;
  speaker_candidate: string | null;
  text: string;
  confidence: number | null;
  issues: string[];
}

export interface VoiceReviewedSegment {
  index: number;
  source_machine_segment_ids: string[];
  speaker: string | null;
  text: string;
  source_start_ms: number | null;
  source_end_ms: number | null;
  confidence: number | null;
  issues: string[];
  audio_range_exact: boolean;
  speaker_source_verified: boolean;
}

export interface VoiceCaptureRecord {
  capture_id: string;
  patient_id: string;
  capture_mode: VoiceCaptureMode;
  event_type: string;
  encounter_id: string | null;
  status: string;
  revision: number;
  failure_reason: string | null;
  started_at: string;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
  audio: {
    mime_type: string;
    byte_length: number;
    sha256: string;
    duration_ms: number | null;
    sample_rate_hz: number | null;
    channels: number | null;
  } | null;
  machine_transcript: {
    provider: string;
    method: string;
    model: string | null;
    version: string | null;
    language: string | null;
    segments: VoiceMachineSegment[];
    degraded: boolean;
    failure_reason: string | null;
  } | null;
  reviewed_segments: VoiceReviewedSegment[] | null;
  event_id: string | null;
  processing: { method: string; degraded: boolean; fallback_reason: string | null } | null;
}

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

export interface AdminSystemSettings {
  scope: 'device';
  version: number;
  updated_at: string;
  ai: {
    mode: 'local' | 'deepseek';
    provider: 'local' | 'deepseek';
    key_configured: boolean;
    key_suffix: string | null;
    key_source: 'credential_manager' | 'environment' | null;
    verified_at: string | null;
    online_text_egress: boolean;
  };
  voice: {
    enabled: boolean;
    provider: string;
    model_status: 'missing' | 'downloading' | 'ready' | 'failed';
    model: string;
    revision: string;
    download_bytes_approx: number;
    storage_mode: 'sqlite' | 'sqlcipher';
    warning: string | null;
    error_code: string | null;
  };
}

export interface VoiceModelStatus {
  status: 'missing' | 'downloading' | 'ready' | 'failed';
  error_code: string | null;
  model: string;
  revision: string;
  download_bytes_approx: number;
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

export type PatientCheckInStatus =
  | 'active'
  | 'awaiting_confirmation'
  | 'submitted'
  | 'safety_escalated'
  | 'abandoned';

export type PatientCheckInIntent = 'answer' | 'supplement' | 'correction' | 'skip' | 'no_more';

export interface PatientCheckInMessage {
  message_id: string;
  sequence: number;
  role: 'patient' | 'ai';
  intent: string | null;
  text: string;
  question_type: string | null;
  conversation_action: string | null;
  referenced_patient_message_ids: string[];
  response_to_message_id: string | null;
  processing_status: string | null;
  generation_method: string | null;
  degraded: boolean;
  created_at: string;
}

export interface PatientCheckInSession {
  session_id: string;
  event_id: string;
  status: PatientCheckInStatus;
  clarification_count: number;
  max_clarification_questions: number;
  safety_escalated: boolean;
  safety_message: string | null;
  started_at: string;
  ended_at: string | null;
  submitted_at: string | null;
  messages: PatientCheckInMessage[];
  preview_summary: string[];
  formal_summary_created: boolean;
  resumed: boolean;
}

export interface PatientCheckInList {
  active_session_id: string | null;
  sessions: PatientCheckInSession[];
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
  task_kind: 'care_action' | 'patient_report_review' | 'clinician_priority_review';
  workflow_id: string | null;
  attention_class: 'routine' | 'priority_review';
  creation_method: 'human' | 'system_routed';
  verification_outcome: 'pending' | 'verified' | 'corrected' | 'unable_to_verify' | 'not_required';
  escalate_at: string | null;
  escalated_at: string | null;
  review_outcome: 'no_action' | 'monitor_or_record' | 'action_required' | null;
  time_sensitivity: 'routine' | 'time_sensitive' | null;
  follow_up_task_id: string | null;
  routing_metadata: Record<string, any>;
  source_artifact_version: number | null;
  source_quote_sha256: string | null;
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

export interface PatientReviewCandidate {
  review_item_id: string;
  highlight_id: string;
  text: string;
  entity_type: string | null;
  source_artifact_id: string | null;
  source_span: Span | null;
  review_status: string | null;
  review_outcome: 'pending' | 'verified' | 'corrected' | 'unable_to_verify';
  correction_artifact_id: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface PatientReviewContext {
  task: ClinicalTask;
  summary_artifact_id: string;
  generation_method: string | null;
  degraded: boolean;
  candidates: PatientReviewCandidate[];
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
  generation_method: string;
  degraded: boolean;
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
