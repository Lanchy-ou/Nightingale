"""Result lifecycle and durable in-app delivery. Clinical text stays in Artifacts."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class TestOrder(Base):
    __tablename__ = "test_orders"
    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.clinic_id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.event_id"))
    result_event_id: Mapped[str | None] = mapped_column(ForeignKey("events.event_id"))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("care_workflows.workflow_id"), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(String(4000))
    expected_at: Mapped[datetime] = mapped_column(DateTime)
    coordinator_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    legacy_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.task_id"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    current_report_id: Mapped[str | None] = mapped_column(String(64))
    current_review_id: Mapped[str | None] = mapped_column(String(64))
    cancelled_reason: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class TestReport(Base):
    __tablename__ = "test_reports"
    __table_args__ = (UniqueConstraint("order_id", "version"),)
    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("test_orders.order_id"), index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.artifact_id"))
    version: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    issued_at: Mapped[datetime] = mapped_column(DateTime)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    withdrawn_reason: Mapped[str | None] = mapped_column(String(2000))


class TestReview(Base):
    __tablename__ = "test_reviews"
    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("test_reports.report_id"), index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.artifact_id"))
    outcome: Mapped[str] = mapped_column(String(32))
    follow_up_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.task_id"))
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class TestCommunication(Base):
    __tablename__ = "test_communications"
    communication_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("test_orders.order_id"), index=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("test_reviews.review_id"))
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.artifact_id"))
    publication_id: Mapped[str | None] = mapped_column(ForeignKey("patient_instruction_publications.publication_id"))
    method: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(32))
    performed_by: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    performed_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class ResultOperation(Base):
    __tablename__ = "result_operations"
    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)


class NotificationSettings(Base):
    __tablename__ = "notification_settings"
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.clinic_id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Singapore")
    review_hours: Mapped[int] = mapped_column(Integer, default=24)
    communication_hours: Mapped[int] = mapped_column(Integer, default=24)
    verification_hours: Mapped[int] = mapped_column(Integer, default=24)
    escalation_hours: Mapped[int] = mapped_column(Integer, default=24)
    last_sweep_at: Mapped[datetime | None] = mapped_column(DateTime)


class NotificationJob(Base):
    __tablename__ = "notification_jobs"
    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.clinic_id"), index=True)
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    target_version: Mapped[str] = mapped_column(String(128))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    stage: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("target_type", "target_id", "target_version", "recipient_id", "stage"),)


class InboxNotification(Base):
    __tablename__ = "inbox_notifications"
    notification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("notification_jobs.job_id"), unique=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
