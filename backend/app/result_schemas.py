from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Operation(StrictBody):
    idempotency_key: str = Field(min_length=1, max_length=100)


class OrderCreate(Operation):
    title: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=4000)
    expected_at: datetime
    coordinator_id: str | None = None
    reviewer_id: str | None = None
    legacy_task_id: str | None = None


class OrderMutation(Operation):
    expected_revision: int = Field(ge=1)


class OrderUpdate(OrderMutation):
    expected_at: datetime | None = None
    coordinator_id: str | None = None
    reviewer_id: str | None = None
    cancel_reason: str | None = Field(default=None, min_length=1, max_length=2000)


class ReportUpload(OrderMutation):
    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["application/pdf"]
    file_base64: str = Field(max_length=13981016)
    issued_at: datetime
    external_source: str = Field(min_length=1, max_length=255)


class WithdrawReport(OrderMutation):
    reason: str = Field(min_length=1, max_length=2000)


class ReviewCreate(OrderMutation):
    conclusion: str = Field(min_length=1, max_length=8000)
    outcome: Literal["no_action", "monitor", "action_required"]
    follow_up_title: str | None = Field(default=None, min_length=1, max_length=255)
    follow_up_owner_id: str | None = None
    follow_up_due_at: datetime | None = None


class CommunicationCreate(OrderMutation):
    review_id: str
    method: Literal["portal", "phone", "in_person"]
    outcome: Literal["delivered", "not_reached", "message_left", "unconfirmed"]
    performed_at: datetime
    publication_id: str | None = None


class ReminderSettingsUpdate(StrictBody):
    expected_revision: int = Field(ge=0)
    timezone: str = "Asia/Singapore"
    review_hours: int = Field(default=24, ge=1, le=720)
    communication_hours: int = Field(default=24, ge=1, le=720)
    verification_hours: int = Field(default=24, ge=1, le=720)
    escalation_hours: int = Field(default=24, ge=1, le=720)
