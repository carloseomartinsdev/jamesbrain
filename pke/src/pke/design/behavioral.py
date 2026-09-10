"""Behavioral memory e hipóteses contextuais — experimental I11.2."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class ConceptMappingType(StrEnum):
    CANONICAL_ALIAS = "canonical_alias"
    TYPE_LEXEME = "type_lexeme"
    INSTANCE_MENTION = "instance_mention"
    ROLE_CUE = "role_cue"
    EVENT_CUE = "event_cue"
    CONTEXTUAL_CUE = "contextual_cue"


class BehavioralPattern(BaseModel):
    """Padrão observado — NÃO é fato."""

    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    conditions: dict[str, str] = Field(default_factory=dict)
    prediction: dict[str, str] = Field(default_factory=dict)
    support: int = 0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    exceptions: list[str] = Field(default_factory=list)
    evidence_summary: str = ""


class ContextualHypothesis(BaseModel):
    """Hipótese contextual — não promovida a fato sem confirmação."""

    model_config = ConfigDict(extra="forbid")

    about_dimension: str
    candidate_value: str
    candidate_concept_key: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    basis: str = "behavioral_pattern"
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    pattern_id: str | None = None


class InformationValueProfile(BaseModel):
    """Perfil de valor informacional por dimensão — sem scoring produtivo."""

    model_config = ConfigDict(extra="forbid")

    dimension: str
    required_for_validity: str = "low"
    information_value: str = "medium"
    future_utility: str = "medium"
    query_utility: str = "medium"
    uncertainty_reduction: str = "medium"
    user_relevance: str = "medium"
    interaction_cost: str = "medium"

    def clarification_priority_label(self) -> str:
        if self.future_utility in {"very_high", "high"} and self.interaction_cost != "high":
            return "high"
        if self.required_for_validity == "high":
            return "blocking"
        return "low"


class ClarificationPolicy(BaseModel):
    """Política conceitual — uma pergunta prioritária por interação."""

    model_config = ConfigDict(extra="forbid")

    max_questions_per_turn: int = 1
    block_on_useful_missing: bool = False
    prefer_high_future_utility: bool = True
    avoid_low_value_interrogation: bool = True
    confirm_behavioral_hypothesis: bool = True

    def select_dimension(self, profiles: list[InformationValueProfile]) -> str | None:
        non_blocking = [p for p in profiles if p.required_for_validity != "high"]
        if not non_blocking:
            return None
        ranked = sorted(
            non_blocking,
            key=lambda p: (
                p.future_utility == "very_high",
                p.query_utility == "high",
                p.uncertainty_reduction == "high",
            ),
            reverse=True,
        )
        best = ranked[0]
        if best.clarification_priority_label() == "low":
            return None
        return best.dimension
