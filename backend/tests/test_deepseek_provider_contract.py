"""DeepSeek request/response boundary: requirements + text in, final content out."""

from __future__ import annotations

import json

from app.llm_client import DeepSeekAdapter
from app.redaction import RedactedContent


def test_request_keeps_thinking_but_sends_no_generated_token_limit():
    adapter = DeepSeekAdapter(api_key="synthetic-key")
    payload = adapter._request_payload(
        system="Return the required JSON shape.",
        messages=[{"role": "user", "content": "De-identified text."}],
        json_output=True,
    )

    assert payload == {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "Return the required JSON shape."},
            {"role": "user", "content": "De-identified text."},
        ],
        "thinking": {"type": "enabled"},
        "response_format": {"type": "json_object"},
    }
    assert "max_tokens" not in payload
    assert "max_output_tokens" not in payload


def test_summarize_ignores_reasoning_and_parses_only_final_content(monkeypatch):
    adapter = DeepSeekAdapter(api_key="synthetic-key")
    final = {
        "summary": "Headache improved; nausea persists.",
        "chief_complaint": "Headache",
        "candidates": [],
    }

    def completed_response(**kwargs):
        assert kwargs["json_output"] is True
        return {
            "choices": [
                {
                    "message": {
                        "reasoning_content": "This is not the final answer.",
                        "content": json.dumps(final),
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

    monkeypatch.setattr(adapter, "_run_chat_create", completed_response)
    result = adapter.summarize(
        RedactedContent(
            content={
                "segments": [
                    {
                        "index": 0,
                        "speaker": "patient",
                        "text": "Sakit kepala is better, but nausea masih ada.",
                    }
                ]
            },
            redaction_counts={},
        ),
        "ai_doctor_consult_summary",
    )

    assert result.summary == final["summary"]
    assert result.chief_complaint == final["chief_complaint"]
