import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.events import LogPublisher
from app.extract import ExtractionError
from app.schema import Extraction
from app.store import MemoryStore


def make_extraction(**overrides) -> Extraction:
    base = dict(
        intent="enquire",
        budget_amount=None,
        budget_currency=None,
        decision_maker="unknown",
        urgency_score=2,
        objection=None,
        summary="A customer enquiry.",
        evidence=[],
        confidence=0.9,
    )
    base.update(overrides)
    return Extraction(**base)


class ScriptedExtractor:
    """Stands in for Gemini. Looks at the whole transcript, like the real model would."""

    def __init__(self):
        self.calls = 0
        self.fail = False

    def extract(self, messages):
        self.calls += 1
        if self.fail:
            raise ExtractionError("scripted failure")
        text = " ".join(m["text"] for m in messages).lower()
        if "rm45k" in text:
            return make_extraction(intent="buy", budget_amount=45000, budget_currency="MYR",
                                   decision_maker="yes", urgency_score=4, objection=None)
        if "rm60k" in text:
            return make_extraction(intent="buy", budget_amount=60000, budget_currency="MYR",
                                   decision_maker="yes", urgency_score=4)
        if "january" in text:
            return make_extraction(urgency_score=4)
        if "won a free cruise" in text:
            return make_extraction(intent="spam", urgency_score=1)
        return make_extraction()


@pytest.fixture
def extractor():
    return ScriptedExtractor()


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def publisher():
    return LogPublisher()
