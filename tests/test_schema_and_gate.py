import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.gate import (
    EVENT_QUALIFIED,
    EVENT_RECYCLED,
    diff_extractions,
    effective_status,
    next_status,
    passes_gate,
)
from app.models import utcnow
from app.schema import Extraction, to_gemini_schema
from tests.conftest import make_extraction


def test_schema_is_flat_and_nullable_fields_use_type_arrays():
    schema = to_gemini_schema()
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text and "anyOf" not in text
    assert schema["properties"]["budget_amount"]["type"] == ["number", "null"]
    assert schema["properties"]["objection"]["type"] == ["string", "null"]
    assert schema["properties"]["urgency_score"]["minimum"] == 1
    assert schema["properties"]["urgency_score"]["maximum"] == 5
    assert schema["properties"]["intent"]["enum"] == ["buy", "enquire", "support", "spam", "other"]
    assert "intent" in schema["required"] and "urgency_score" in schema["required"]


def test_extraction_rejects_out_of_range_and_unknown_values():
    good = make_extraction().model_dump_json()
    Extraction.model_validate_json(good)
    with pytest.raises(ValidationError):
        make_extraction(urgency_score=6)
    with pytest.raises(ValidationError):
        make_extraction(intent="maybe")
    with pytest.raises(ValidationError):
        make_extraction(confidence=1.5)


BUDGET = dict(budget_amount=1000, budget_currency="MYR")


@pytest.mark.parametrize(
    "overrides,expected",
    [
        (dict(intent="buy", urgency_score=3, confidence=0.6, **BUDGET), True),
        (dict(intent="enquire", urgency_score=5, decision_maker="yes", **BUDGET), True),
        (dict(intent="enquire", urgency_score=5, decision_maker="unknown", **BUDGET), True),
        (dict(intent="buy", urgency_score=2, **BUDGET), False),  # too slow
        (dict(intent="buy", urgency_score=4, confidence=0.59, **BUDGET), False),  # unsure
        (dict(intent="buy", urgency_score=5), False),  # no budget stated
        (dict(intent="buy", urgency_score=5, decision_maker="no", **BUDGET), False),  # gathering quotes
        (dict(intent="spam", urgency_score=5, **BUDGET), False),
        (dict(intent="support", urgency_score=5, **BUDGET), False),
    ],
)
def test_gate_boundaries(overrides, expected):
    assert passes_gate(make_extraction(**overrides)) is expected


HOT = dict(intent="buy", urgency_score=4, decision_maker="yes", **BUDGET)
COLD = dict(intent="enquire", urgency_score=2)


def test_status_transitions_publish_only_on_change():
    assert next_status(None, make_extraction(**COLD)) == ("active", None)
    assert next_status(None, make_extraction(**HOT)) == ("qualified", EVENT_QUALIFIED)
    assert next_status("active", make_extraction(**HOT)) == ("qualified", EVENT_QUALIFIED)
    assert next_status("qualified", make_extraction(**HOT)) == ("qualified", None)
    assert next_status("qualified", make_extraction(**COLD)) == ("qualified", None)  # no downgrade
    assert next_status("dormant", make_extraction(**HOT)) == ("recycled", EVENT_RECYCLED)
    assert next_status("dormant", make_extraction(**COLD)) == ("dormant", None)
    assert next_status("recycled", make_extraction(**HOT)) == ("recycled", None)


def test_long_silence_makes_an_active_lead_dormant():
    now = utcnow()
    lead = {"status": "active", "last_message_at": now - timedelta(days=31)}
    assert effective_status(lead, now, dormant_after_days=30) == "dormant"
    lead["last_message_at"] = now - timedelta(days=29)
    assert effective_status(lead, now, dormant_after_days=30) == "active"
    assert effective_status({"status": "qualified", "last_message_at": now - timedelta(days=400)}, now, 30) == "qualified"
    assert effective_status(None, now, 30) is None


def test_diff_lists_only_changed_tracked_fields():
    old = make_extraction(budget_amount=15000, budget_currency="MYR", objection="budget too low").model_dump()
    new = make_extraction(budget_amount=45000, budget_currency="MYR", objection=None, urgency_score=4)
    changes = diff_extractions(old, new)
    assert changes["budget_amount"] == {"from": 15000, "to": 45000}
    assert changes["objection"] == {"from": "budget too low", "to": None}
    assert "budget_currency" not in changes
    assert diff_extractions(None, new) == {}


def test_ai_studio_schema_file_matches_code():
    import json, pathlib
    from app.schema import to_ai_studio_schema
    path = pathlib.Path(__file__).parent.parent / "docs" / "ai-studio-schema.json"
    assert json.loads(path.read_text()) == to_ai_studio_schema()
