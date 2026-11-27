"""The extraction schema: the contract between the model and the rest of the pipeline.

Keep it FLAT (no nested models). Flat schemas avoid $ref/$defs, which not every
structured-output implementation handles, and they are easier to read on a slide.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Extraction(BaseModel):
    intent: Literal["buy", "enquire", "support", "spam", "other"] = Field(
        description="What the sender wants. 'support' is an existing customer with a problem."
    )
    budget_amount: Optional[float] = Field(
        default=None,
        description="Budget as a number, only if the customer stated one. null if not stated. Never guess.",
    )
    budget_currency: Optional[str] = Field(
        default=None,
        description="Currency code or symbol for the stated budget (for example MYR for RM). null if no budget.",
    )
    decision_maker: Literal["yes", "no", "unknown"] = Field(
        description="Can the sender decide? 'no' if gathering quotes for someone else. 'unknown' if unclear."
    )
    urgency_score: int = Field(
        ge=1,
        le=5,
        description="1 no timeline, 2 vague or someday, 3 within a few months, 4 a stated date or within weeks, 5 wants contact now.",
    )
    objection: Optional[str] = Field(
        default=None,
        description="Why they hesitated, in a few words (for example 'budget too low'). null if none.",
    )
    summary: str = Field(description="One sentence in English a salesperson can read before replying.")
    evidence: list[str] = Field(
        max_length=3,
        description="Up to 3 short quotes copied from the conversation that justify the scores.",
    )
    confidence: float = Field(ge=0, le=1, description="How sure you are, from 0 to 1.")

    @property
    def budget_stated(self) -> bool:
        return self.budget_amount is not None


def to_gemini_schema(model: type[BaseModel] = Extraction) -> dict[str, Any]:
    """Pydantic JSON schema, with Optional fields rewritten as type arrays.

    Pydantic writes Optional[float] as anyOf [number, null]. Structured-output docs
    describe nullable fields as {"type": ["number", "null"]}, so we write that form.
    """
    schema = model.model_json_schema()

    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            any_of = node.get("anyOf")
            if isinstance(any_of, list) and len(any_of) == 2:
                kinds = [item for item in any_of if item.get("type") != "null"]
                if len(kinds) == 1 and len(any_of) - len(kinds) == 1 and "type" in kinds[0]:
                    merged = {k: v for k, v in node.items() if k != "anyOf"}
                    merged.update({k: v for k, v in kinds[0].items() if k != "type"})
                    merged["type"] = [kinds[0]["type"], "null"]
                    return fix(merged)
            return {key: fix(value) for key, value in node.items()}
        if isinstance(node, list):
            return [fix(item) for item in node]
        return node

    return fix(schema)


def to_ai_studio_schema(model: type[BaseModel] = Extraction) -> dict[str, Any]:
    """The same schema in the subset the AI Studio schema editor accepts.

    The editor rejects "title" and "default", and wants {"type": "number", "nullable": true}
    instead of type arrays. The API call keeps using to_gemini_schema().
    """

    def convert(node: Any) -> Any:
        if isinstance(node, dict):
            out = {k: convert(v) for k, v in node.items() if k not in ("title", "default")}
            kind = out.get("type")
            if isinstance(kind, list) and "null" in kind:
                rest = [k for k in kind if k != "null"]
                out["type"] = rest[0] if len(rest) == 1 else rest
                out["nullable"] = True
            return out
        if isinstance(node, list):
            return [convert(item) for item in node]
        return node

    return convert(to_gemini_schema(model))
