"""M4: extraction schema + normalization fail-closed behavior."""
from __future__ import annotations

from app.extraction import (
    Candidate,
    normalize_entity_key,
    normalize_token,
    validate_candidate,
)


def test_normalize_token_and_entity_key():
    assert normalize_token("  Blood Pressure!  ") == "blood pressure"
    assert normalize_entity_key("risk", "Blood Pressure!") == "risk:blood pressure"


def test_validate_drops_empty_text():
    c = Candidate(text="", quote="q", risk_reason="r", entity_type="risk")
    assert validate_candidate(c) is None


def test_validate_drops_empty_quote_and_reason():
    assert validate_candidate(Candidate(text="t", quote="", risk_reason="r", entity_type="risk")) is None
    assert validate_candidate(Candidate(text="t", quote="q", risk_reason="", entity_type="risk")) is None


def test_validate_recomputes_entity_key():
    c = Candidate(text="Elevated BP", quote="q", risk_reason="r", entity_type="risk", entity_key="attacker:key")
    out = validate_candidate(c)
    assert out is not None
    assert out.entity_key == "risk:elevated bp"


def test_invalid_entity_type_rejected_by_schema():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Candidate(text="t", quote="q", risk_reason="r", entity_type="bogus")
