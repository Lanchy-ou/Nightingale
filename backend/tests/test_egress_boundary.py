import pytest
from app.redaction import redact_content, restore_placeholders


def test_extended_redaction_roundtrip():
    text = "我叫张三，邮箱 jane@example.test，住址：12 Sample Road。"
    result = redact_content({"text": text}, [])
    safe = result.redacted.content["text"]
    assert "张三" not in safe and "jane@example.test" not in safe and "12 Sample Road" not in safe
    assert restore_placeholders(safe, result.placeholder_mapping) == text


def test_provider_payload_minimizes_and_restores_ids():
    from app.egress import call_provider
    from app.redaction import RedactedContent
    from app.schemas import CheckInTurnResult
    class Client:
        def checkin_turn(self, payload, count):
            assert set(payload.content) == {"messages"}
            message = payload.content["messages"][0]
            assert "patient_id" not in message
            assert message["id"] != "private-message-id"
            return CheckInTurnResult(acknowledgement="Recorded", next_question=None,
                question_type=None, conversation_action="await_confirmation",
                referenced_patient_message_ids=[message["id"]])
    result = call_provider(Client(), "checkin_turn", RedactedContent({
        "patient_id": "private-patient", "audit": "internal",
        "messages": [{"id": "private-message-id", "speaker": "patient", "text": "Headache",
                      "patient_id": "private-patient"}]}, {}), 0)
    assert result.referenced_patient_message_ids == ["private-message-id"]


def test_egress_guard_rejects_supported_sensitive_pattern():
    from app.egress import call_provider, EgressRejected
    from app.redaction import RedactedContent
    class Client:
        def summarize(self, *args):
            pytest.fail("provider must not be invoked")
    with pytest.raises(EgressRejected):
        call_provider(Client(), "summarize", RedactedContent({"text": "jane@example.test"}, {}), "doctor")


@pytest.mark.parametrize('method,content', [
    ('summarize', {'segments': [{'index': 0, 'text': {'patient_id': 'private'}}]}),
    ('copilot', {'evidence': [{'quote': {'internal': 'private'}}]}),
    ('checkin_turn', {'messages': [{'text': {'internal': 'private'}}]}),
    ('checkin_summary', {'messages': [{'text': {'internal': 'private'}}]}),
])
def test_all_flows_reject_nested_payload_bypass(method, content):
    from app.egress import prepare, EgressRejected
    from app.redaction import RedactedContent
    with pytest.raises(EgressRejected):
        prepare(RedactedContent(content, {}), method)
