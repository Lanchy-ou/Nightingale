"""Idempotent additive migration; never resets existing records."""
from .result_models import (TestOrder, TestReport, TestReview, TestCommunication,
                            ResultOperation, NotificationSettings, NotificationJob, InboxNotification)


def migrate_results(engine):
    for model in (TestOrder, TestReport, TestReview, TestCommunication, ResultOperation,
                  NotificationSettings, NotificationJob, InboxNotification):
        model.__table__.create(engine, checkfirst=True)
    from sqlalchemy import inspect
    if "legacy_task_id" not in {column["name"] for column in inspect(engine).get_columns("test_orders")}:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE test_orders ADD COLUMN legacy_task_id VARCHAR(64) REFERENCES tasks(task_id)")
    # Ownership-only defense in depth, matching existing SQLite/SQLCipher storage.
    checks = {
        "test_orders": "EXISTS (SELECT 1 FROM patients p JOIN events e ON e.patient_id=p.patient_id JOIN care_workflows w ON w.workflow_id=NEW.workflow_id WHERE p.patient_id=NEW.patient_id AND p.clinic_id=NEW.clinic_id AND e.event_id=NEW.event_id AND e.clinic_id=NEW.clinic_id AND w.clinic_id=NEW.clinic_id AND w.patient_id=NEW.patient_id)",
        "test_reports": "EXISTS (SELECT 1 FROM test_orders o JOIN artifacts a ON a.event_id=o.result_event_id WHERE o.order_id=NEW.order_id AND a.artifact_id=NEW.artifact_id)",
        "test_reviews": "EXISTS (SELECT 1 FROM test_reports r JOIN test_orders o ON o.order_id=r.order_id JOIN artifacts a ON a.event_id=o.result_event_id JOIN users u ON u.clinic_id=o.clinic_id WHERE r.report_id=NEW.report_id AND a.artifact_id=NEW.artifact_id AND u.user_id=NEW.clinician_id)",
        "test_communications": "EXISTS (SELECT 1 FROM test_reviews v JOIN test_reports r ON r.report_id=v.report_id JOIN test_orders o ON o.order_id=r.order_id JOIN artifacts a ON a.event_id=o.result_event_id WHERE v.review_id=NEW.review_id AND o.order_id=NEW.order_id AND a.artifact_id=NEW.artifact_id)",
        "notification_jobs": "EXISTS (SELECT 1 FROM users u WHERE u.user_id=NEW.recipient_id AND u.clinic_id=NEW.clinic_id)",
        "inbox_notifications": "EXISTS (SELECT 1 FROM notification_jobs j WHERE j.job_id=NEW.job_id AND j.recipient_id=NEW.owner_id)",
    }
    with engine.begin() as connection:
        for table, condition in checks.items():
            for operation in ("INSERT", "UPDATE"):
                connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS scope_{table}_{operation.lower()} BEFORE {operation} ON {table} WHEN NOT ({condition}) BEGIN SELECT RAISE(ABORT, 'result ownership mismatch'); END")
