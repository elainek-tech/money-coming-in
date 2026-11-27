"""Check the real model against the fictional sample messages (needs GEMINI_API_KEY).

Run this once before you present, and again if you change the prompt, schema or model.
It prints what the model extracted and whether the gate agrees with what the talk says should happen.
"""

import sys

from app.demo_data import CONVERSATION, SINGLE_MESSAGES
from app.extract import ExtractionError, GeminiExtractor
from app.gate import passes_gate

# What the talk expects for each single message: does it pass the gate?
EXPECTED_SINGLES = [True, False, False, True, False, False]


def show(label: str, e) -> None:
    budget = f"{e.budget_currency or ''} {e.budget_amount:,.0f}".strip() if e.budget_amount is not None else "none"
    print(f"  {label:<10} intent={e.intent:<8} urgency={e.urgency_score} budget={budget:<12} "
          f"decider={e.decision_maker:<7} conf={e.confidence:.2f} qualified={passes_gate(e)}")
    print(f"             {e.summary}")


def main() -> int:
    extractor = GeminiExtractor()
    print(f"Model: {extractor.model}\n\nSingle messages")
    mismatches = 0
    for index, (text, expected) in enumerate(zip(SINGLE_MESSAGES, EXPECTED_SINGLES), start=1):
        try:
            e = extractor.extract([{"text": text}])
        except ExtractionError as error:
            print(f"  #{index} FAILED: {error}")
            mismatches += 1
            continue
        show(f"#{index}", e)
        if passes_gate(e) != expected:
            print(f"             ^ the talk expects qualified={expected}")
            mismatches += 1

    print("\nConversation (the lead should qualify only on message 3)")
    history: list[dict] = []
    for step, text in enumerate(CONVERSATION, start=1):
        history.append({"text": text})
        e = extractor.extract(history)
        show(f"step {step}", e)
        if passes_gate(e) != (step == 3):
            print(f"             ^ the talk expects qualified={step == 3}")
            mismatches += 1

    print(f"\n{'All as expected.' if not mismatches else f'{mismatches} difference(s): tune the prompt or the gate.'}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
