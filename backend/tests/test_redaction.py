"""M4: recursive PHI redaction + placeholder restore + raw-span roundtrip."""
from __future__ import annotations

from app.highlights import extract_text, locate_span
from app.redaction import (
    redact_content,
    restore_placeholders,
    unresolved_placeholders,
)


def test_names_ic_phone_redacted():
    content = {
        "messages": [
            {
                "id": "msg_1",
                "speaker": "patient",
                "text": "My name is Alice Tan, IC 880523-01-1234, phone 012-3456789.",
            }
        ]
    }
    res = redact_content(content, ["Alice Tan", "Dr. Carol Wong"])
    txt = res.redacted.content["messages"][0]["text"]
    assert "Alice Tan" not in txt
    assert "880523-01-1234" not in txt
    assert "012-3456789" not in txt
    assert "[NAME_1]" in txt and "[ID_1]" in txt and "[PHONE_1]" in txt
    assert res.redacted.redaction_counts["name"] >= 1
    assert res.redacted.redaction_counts["id"] >= 1
    assert res.redacted.redaction_counts["phone"] >= 1


def test_structure_and_role_speaker_preserved():
    content = {"segments": [{"index": 1, "speaker": "nurse", "text": "BP 158/96 for Alice Tan"}]}
    res = redact_content(content, ["Alice Tan"])
    seg = res.redacted.content["segments"][0]
    assert seg["index"] == 1
    assert seg["speaker"] == "nurse"  # role label is preserved
    assert "Alice Tan" not in seg["text"]


def test_no_raw_phi_in_redacted_content():
    import json

    content = {"messages": [{"id": "m1", "speaker": "patient", "text": "Call 012-3456789, IC 880523-01-1234."}]}
    res = redact_content(content, ["Alice Tan"])
    blob = json.dumps(res.redacted.content)
    assert "012-3456789" not in blob
    assert "880523-01-1234" not in blob


def test_restore_and_anchor_roundtrip():
    raw = {"messages": [{"id": "m1", "speaker": "patient", "text": "Alice Tan's headache is worse."}]}
    res = redact_content(raw, ["Alice Tan"])
    red_text = res.redacted.content["messages"][0]["text"]
    assert "[NAME_1]" in red_text

    restored = restore_placeholders(red_text, res.placeholder_mapping)
    assert restored == "Alice Tan's headache is worse."

    span = locate_span(raw, restored)
    assert span is not None
    assert extract_text(raw, span) == restored


def test_unresolved_placeholder_detected():
    mapping = {"[NAME_1]": "Alice Tan"}
    assert unresolved_placeholders("I saw [NAME_1] and [NAME_99]", mapping) == ["[NAME_99]"]
    assert unresolved_placeholders("I saw [NAME_1]", mapping) == []


def test_ic_phone_no_double_replacement():
    content = {"text": "IC 880523-01-1234 and phone 012-3456789."}
    res = redact_content(content, [])
    txt = res.redacted.content["text"]
    assert txt.count("[ID_") == 1
    assert txt.count("[PHONE_") == 1
    assert "[ID_1]" in txt and "[PHONE_1]" in txt
