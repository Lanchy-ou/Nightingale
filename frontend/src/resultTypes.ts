export type ResultStage = 'waiting_report' | 'waiting_review' | 'waiting_communication' | 'completed' | 'cancelled';
export type TestOrder = {
  order_id: string; patient_id: string; event_id: string; result_event_id: string | null; title: string; reason: string;
  expected_at: string; coordinator_id: string; reviewer_id: string; revision: number; stage: ResultStage;
  legacy_task_id: string | null;
  current_report_id: string | null; current_review_id: string | null; cancelled_reason: string | null;
};
export type TestOrderDetail = TestOrder & {
  reports: { report_id: string; version: number; issued_at: string; created_at: string; uploaded_by: string; external_source: string; withdrawn_reason: string | null }[];
  reviews: { review_id: string; report_id: string; conclusion: string; outcome: string; clinician_id: string; follow_up_task_id: string | null }[];
  communications: { communication_id: string; method: string; outcome: string; review_id: string; performed_at: string; performed_by: string }[];
  publications: { publication_id: string; artifact_id: string; artifact_version: number }[];
};
export type NotificationList = { enabled: boolean; unread_count: number; items: {
  notification_id: string; title: string; stage: string; target: string | null; read_at: string | null; resolved: boolean;
}[] };
